import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "sites.yaml"
OUTPUT = ROOT / "discovery" / "output"


def discover_site(name: str, url: str):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    requests = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def on_request(request):
            if request.resource_type in {"xhr", "fetch"}:
                requests.append({
                    "method": request.method,
                    "url": request.url,
                    "resource_type": request.resource_type,
                    "post_data": request.post_data,
                })

        page.on("request", on_request)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        browser.close()

    payload = {
        "site": name,
        "url": url,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "requests": requests,
    }

    output_file = OUTPUT / f"{name}.json"
    output_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"{name}: {len(requests)} XHR/fetch requests -> {output_file}")


def main():
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

    for name, site in config["sites"].items():
        try:
            discover_site(name, site["url"])
        except Exception as exc:
            print(f"{name}: discovery failed: {exc}")


if __name__ == "__main__":
    main()
