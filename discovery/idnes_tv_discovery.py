import json
import re

from playwright.sync_api import sync_playwright


TARGETS = [
    ("HOME", "https://tvprogram.idnes.cz/"),
    ("ONEPLAY SPORT 1", "https://tvprogram.idnes.cz/oneplaysport-1"),
    ("SEARCH ATLETIKA", "https://tvprogram.idnes.cz/hledani?slovo=atletika"),
]

SPORT_CHANNEL_HINTS = (
    "sport",
    "eurosport",
    "oneplay",
    "premier",
    "nova-sport",
    "sport1",
    "sport2",
)


def short(value, limit=500):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value if len(value) <= limit else value[:limit] + "..."


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="cs-CZ",
            timezone_id="Europe/Prague",
        )

        for label, url in TARGETS:
            print(f"\n[IDNES] TARGET | {label} | {url}")
            page = context.new_page()
            seen_network = set()

            def on_response(response):
                request = response.request
                resource_type = request.resource_type
                headers = response.headers
                content_type = headers.get("content-type", "")
                response_url = response.url

                interesting = (
                    resource_type in {"xhr", "fetch"}
                    or "json" in content_type.lower()
                    or "api" in response_url.lower()
                    or "program" in response_url.lower()
                )
                if not interesting:
                    return

                key = (response.status, response_url)
                if key in seen_network:
                    return
                seen_network.add(key)

                print(
                    f"[IDNES-NET] {label} | {response.status} | "
                    f"{resource_type} | {content_type} | {response_url}"
                )

                if response.status >= 400:
                    return

                if "json" not in content_type.lower() and resource_type not in {"xhr", "fetch"}:
                    return

                try:
                    body = response.text()
                except Exception:
                    return

                body_strip = body.lstrip()
                if not (body_strip.startswith("{") or body_strip.startswith("[")):
                    print(f"[IDNES-NET-BODY] {label} | {short(body, 700)}")
                    return

                try:
                    payload = json.loads(body)
                except Exception:
                    return

                if isinstance(payload, dict):
                    info = f"dict keys={list(payload.keys())[:20]}"
                elif isinstance(payload, list):
                    info = f"list len={len(payload)}"
                else:
                    info = type(payload).__name__

                print(f"[IDNES-JSON] {label} | {response_url} | {info}")
                print(
                    f"[IDNES-JSON-SAMPLE] {label} | "
                    f"{short(json.dumps(payload, ensure_ascii=False), 900)}"
                )

            page.on("response", on_response)

            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            print(
                f"[IDNES] HTTP | {label} | "
                f"{response.status if response else 'none'}"
            )

            page.wait_for_timeout(4000)

            print(f"[IDNES] TITLE | {label} | {short(page.title(), 200)}")
            print(f"[IDNES] URL | {label} | {page.url}")

            body_text = page.locator("body").inner_text()
            print(
                f"[IDNES] BODY | {label} | len={len(body_text)} | "
                f"{short(body_text, 1600)}"
            )

            links = page.locator("a[href]")
            interesting_links = []
            for i in range(min(links.count(), 1000)):
                node = links.nth(i)
                try:
                    href = node.get_attribute("href") or ""
                    text = short(node.inner_text(), 140)
                except Exception:
                    continue

                low = (href + " " + text).lower()
                if (
                    any(hint in low for hint in SPORT_CHANNEL_HINTS)
                    or re.search(r"\.id\d+", href)
                    or "hledani" in href
                ):
                    interesting_links.append({"text": text, "href": href})

            print(
                f"[IDNES] LINKS | {label} | "
                f"{json.dumps(interesting_links[:80], ensure_ascii=False)}"
            )

            time_nodes = page.locator(
                "body *"
            ).filter(has_text=re.compile(r"^\s*\d{1,2}:\d{2}\s*$"))
            print(f"[IDNES-DOM] TIME_NODES | {label} | {time_nodes.count()}")

            for i in range(min(time_nodes.count(), 16)):
                node = time_nodes.nth(i)
                try:
                    info = node.evaluate(
                        """el => {
                            function item(node) {
                                if (!node) return null;
                                return {
                                    tag: node.tagName,
                                    cls: node.className || '',
                                    text: (node.innerText || '')
                                        .replace(/\\s+/g, ' ')
                                        .trim()
                                        .slice(0, 700),
                                    href: node.href || null
                                };
                            }
                            return {
                                self: item(el),
                                p1: item(el.parentElement),
                                p2: item(el.parentElement?.parentElement),
                                p3: item(el.parentElement?.parentElement?.parentElement),
                                p4: item(el.parentElement?.parentElement?.parentElement?.parentElement)
                            };
                        }"""
                    )
                except Exception as exc:
                    info = {"error": str(exc)}

                print(
                    f"[IDNES-DOM-TIME] {label} | {i} | "
                    f"{json.dumps(info, ensure_ascii=False)}"
                )

            range_nodes = page.locator(
                "body *"
            ).filter(
                has_text=re.compile(
                    r"^\s*\d{1,2}:\d{2}\s*(?:-|–|—)\s*\d{1,2}:\d{2}\s*$"
                )
            )
            print(f"[IDNES-DOM] RANGE_NODES | {label} | {range_nodes.count()}")

            for i in range(min(range_nodes.count(), 12)):
                node = range_nodes.nth(i)
                try:
                    info = node.evaluate(
                        """el => ({
                            self: {
                                tag: el.tagName,
                                cls: el.className || '',
                                text: (el.innerText || '').trim()
                            },
                            parent: {
                                tag: el.parentElement?.tagName || null,
                                cls: el.parentElement?.className || '',
                                text: (el.parentElement?.innerText || '')
                                    .replace(/\\s+/g, ' ')
                                    .trim()
                                    .slice(0, 900)
                            }
                        })"""
                    )
                    print(
                        f"[IDNES-DOM-RANGE] {label} | {i} | "
                        f"{json.dumps(info, ensure_ascii=False)}"
                    )
                except Exception as exc:
                    print(f"[IDNES-DOM-RANGE] {label} | {i} | ERROR {exc}")

            detail_links = page.locator('a[href*=".id"]')
            print(f"[IDNES-DOM] DETAIL_LINKS | {label} | {detail_links.count()}")

            for i in range(min(detail_links.count(), 8)):
                node = detail_links.nth(i)
                try:
                    snippet = node.evaluate(
                        """el => {
                            let n = el;
                            for (let i = 0; i < 3 && n?.parentElement; i++) {
                                n = n.parentElement;
                            }
                            return (n?.outerHTML || el.outerHTML || '')
                                .replace(/\\s+/g, ' ')
                                .slice(0, 1800);
                        }"""
                    )
                    print(f"[IDNES-HTML] {label} | {i} | {short(snippet, 1800)}")
                except Exception as exc:
                    print(f"[IDNES-HTML] {label} | {i} | ERROR {exc}")

            page.close()

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
