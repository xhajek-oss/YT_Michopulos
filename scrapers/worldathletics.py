import json
import re

from playwright.sync_api import sync_playwright

from .base import BaseScraper


class WorldAthleticsScraper(BaseScraper):
    source = "worldathletics"

    # Discovery only. These are the two nearest official WA championship
    # timetable/schedule surfaces as of September 2026.
    TARGETS = [
        (
            "Budapest 2026",
            "https://worldathletics.org/competitions/"
            "world-athletics-ultimate-championship/2026/schedule",
        ),
        (
            "Copenhagen 2026",
            "https://worldathletics.org/competitions/"
            "world-athletics-road-running-championships/copenhagen26/timetable",
        ),
    ]

    @staticmethod
    def _compact(value, limit=3500):
        try:
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            text = str(value)
        return text[:limit]

    def scrape(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="en-GB",
                timezone_id="Europe/Prague",
            )

            try:
                for label, url in self.TARGETS:
                    print(f"[WA] TARGET | {label} | {url}")
                    page = context.new_page()
                    json_seen = set()

                    def on_response(response):
                        req = response.request
                        if req.resource_type not in {"fetch", "xhr"}:
                            return

                        ctype = (response.headers.get("content-type") or "").lower()
                        rurl = response.url

                        if "json" not in ctype:
                            print(
                                f"[WA-NET] {req.resource_type} | {response.status} | "
                                f"{ctype[:60]} | {rurl}"
                            )
                            return

                        if rurl in json_seen:
                            return
                        json_seen.add(rurl)

                        print(
                            f"[WA-JSON] {req.resource_type} | {response.status} | {rurl}"
                        )

                        try:
                            payload = response.json()
                        except Exception as exc:
                            print(f"[WA-JSON] parse failed | {exc}")
                            return

                        if isinstance(payload, dict):
                            print(
                                "[WA-JSON] top_keys="
                                + repr(list(payload.keys())[:40])
                            )
                        elif isinstance(payload, list):
                            print(f"[WA-JSON] list_length={len(payload)}")

                        compact = self._compact(payload)
                        lower = compact.lower()
                        if any(
                            key in lower
                            for key in (
                                "timetable",
                                "schedule",
                                "starttime",
                                "start time",
                                "discipline",
                                "eventname",
                                "competition",
                            )
                        ):
                            print(f"[WA-JSON] sample={compact}")

                    page.on("response", on_response)

                    try:
                        response = page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=60_000,
                        )
                        print(
                            f"[WA] STATUS | {label} | "
                            f"{response.status if response else 'no-response'}"
                        )

                        page.wait_for_timeout(7000)

                        body = page.locator("body").inner_text(timeout=15_000)
                        print(f"[WA] BODY_CHARS | {label} | {len(body)}")

                        # Show bounded snippets around likely timetable content.
                        normalized = re.sub(r"\s+", " ", body)
                        lower = normalized.lower()
                        for keyword in (
                            "timetable",
                            "local time",
                            "september 2026",
                            "100m",
                            "road mile",
                            "final",
                        ):
                            idx = lower.find(keyword)
                            if idx >= 0:
                                start = max(0, idx - 400)
                                end = min(len(normalized), idx + 1800)
                                print(
                                    f"[WA-TEXT] {label} | {keyword} | "
                                    f"{normalized[start:end]}"
                                )

                        # Links tell us whether WA exposes discipline/day timetable
                        # routes that can be parsed without reverse engineering.
                        links = page.locator("a").evaluate_all(
                            """els => els.map(a => ({
                                text: (a.innerText || '').trim(),
                                href: a.href || ''
                            }))"""
                        )
                        useful = []
                        for item in links:
                            href = item.get("href", "")
                            if any(
                                token in href.lower()
                                for token in (
                                    "/timetable",
                                    "/schedule",
                                    "/calendar-results",
                                )
                            ):
                                useful.append(item)

                        print(f"[WA-LINKS] {label} | count={len(useful)}")
                        for item in useful[:30]:
                            print(
                                f"[WA-LINK] {label} | "
                                f"{item.get('text', '')[:100]} | "
                                f"{item.get('href', '')}"
                            )

                    except Exception as exc:
                        print(f"[WA] ERROR | {label} | {type(exc).__name__}: {exc}")
                    finally:
                        page.close()
            finally:
                context.close()
                browser.close()

        # Discovery run intentionally writes no events.
        return []
