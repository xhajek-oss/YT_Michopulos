#!/usr/bin/env python3

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests


TIMEOUT = 20

OUT_DIR = Path("data/tv_probe")
OUT_DIR.mkdir(parents=True, exist_ok=True)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept": (
        "application/json, application/xml, text/xml, "
        "text/html;q=0.9, */*;q=0.8"
    ),
    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
}


TEST_URLS = {
    "sledovanitv_epg": [
        "https://sledovanitv.cz/epg",
        "https://api.sledovanitv.cz/epg",
    ],
    "ct_tv_program": [
        "https://www.ceskatelevize.cz/xml/tv-program/",
        "https://www.ceskatelevize.cz/tv-program/",
    ],
    "idnes_tv": [
        "https://tvprogram.idnes.cz/",
    ],
    "oneplay_tv": [
        "https://www.oneplay.cz/",
    ],
}


def save_text(name, text):
    path = OUT_DIR / f"{name}.txt"

    with path.open("w", encoding="utf-8") as f:
        f.write(text)

    return path


def save_meta(name, data):
    path = OUT_DIR / f"{name}.json"

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return path


def extract_interesting_urls(text, base_url):
    """
    Pokusí se z HTML najít URL adresy, které mohou vypadat jako:
    API / JSON / EPG / program endpoint.
    """

    patterns = [
        r'https?://[^"\']+',
        r'["\']([^"\']*(?:api|epg|program|schedule|json)[^"\']*)["\']',
    ]

    found = set()

    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.I):
            if isinstance(match, tuple):
                match = match[0]

            if not match:
                continue

            if match.startswith("http://") or match.startswith("https://"):
                found.add(match)
            elif match.startswith("/"):
                found.add(match)

    return sorted(found)[:200]


def test_url(source, url):
    print()
    print("=" * 80)
    print(f"ZDROJ: {source}")
    print(f"URL:   {url}")
    print("=" * 80)

    result = {
        "source": source,
        "url": url,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": False,
    }

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        content_type = response.headers.get("content-type", "")

        result.update(
            {
                "ok": response.ok,
                "status_code": response.status_code,
                "final_url": response.url,
                "content_type": content_type,
                "content_length": len(response.content),
                "headers": dict(response.headers),
            }
        )

        print(f"HTTP:        {response.status_code}")
        print(f"Final URL:   {response.url}")
        print(f"Content-Type:{content_type}")
        print(f"Velikost:    {len(response.content):,} B")

        filename = re.sub(r"[^a-zA-Z0-9_-]", "_", source)

        text = response.text

        text_path = save_text(filename, text)
        meta_path = save_meta(filename, result)

        print(f"RAW data:    {text_path}")
        print(f"Metadata:    {meta_path}")

        print()
        print("--- ZAČÁTEK ODPOVĚDI ---")
        print(text[:3000])
        print("--- KONEC UKÁZKY ---")

        interesting = extract_interesting_urls(text, response.url)

        if interesting:
            print()
            print("--- ZAJÍMAVÉ URL / API STOPY ---")

            for item in interesting:
                print(item)

        result["interesting_urls"] = interesting

    except requests.RequestException as exc:
        result["error"] = str(exc)

        print(f"CHYBA: {exc}")

    return result


def main():
    print("=" * 80)
    print("TV PROBE")
    print("=" * 80)
    print(f"Čas: {datetime.now().astimezone().isoformat()}")
    print()

    all_results = []

    for source, urls in TEST_URLS.items():
        for url in urls:
            result = test_url(source, url)
            all_results.append(result)

    summary_path = OUT_DIR / "summary.json"

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(
            all_results,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print("=" * 80)
    print("SHRNUTÍ")
    print("=" * 80)

    for result in all_results:
        print(
            f"{result['source']:20} "
            f"{result['status_code'] if 'status_code' in result else 'ERROR':>8} "
            f"{result.get('content_type', '')}"
        )

    print()
    print(f"Souhrn uložen: {summary_path}")


if __name__ == "__main__":
    main()
