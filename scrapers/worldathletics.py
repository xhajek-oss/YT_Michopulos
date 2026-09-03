import re
from playwright.sync_api import sync_playwright
from .base import BaseScraper


class WorldAthleticsScraper(BaseScraper):
    source = "worldathletics"

    TARGETS = [
        ("Budapest 2026",
         "https://worldathletics.org/competitions/world-athletics-ultimate-championship/2026/schedule"),
        ("Copenhagen 2026",
         "https://worldathletics.org/competitions/world-athletics-road-running-championships/copenhagen26/timetable"),
    ]

    def scrape(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-GB")
            try:
                for label, url in self.TARGETS:
                    page = context.new_page()
                    print(f"[WA-DOM] TARGET | {label}")
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(5000)

                        # Find leaf-ish elements whose own text is exactly HH:MM.
                        time_nodes = page.locator(
                            "text=/^([01]?\\d|2[0-3]):[0-5]\\d$/"
                        )
                        count = min(time_nodes.count(), 12)
                        print(f"[WA-DOM] TIME_NODES | {label} | {time_nodes.count()}")

                        for i in range(count):
                            node = time_nodes.nth(i)
                            info = node.evaluate("""el => {
                                const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
                                const pack = x => x ? {
                                    tag: x.tagName,
                                    cls: x.className || '',
                                    text: clean(x.innerText).slice(0, 700)
                                } : null;
                                return {
                                    self: pack(el),
                                    p1: pack(el.parentElement),
                                    p2: pack(el.parentElement && el.parentElement.parentElement),
                                    p3: pack(el.parentElement && el.parentElement.parentElement &&
                                             el.parentElement.parentElement.parentElement)
                                };
                            }""")
                            print(f"[WA-DOM-TIME] {label} | {i} | {info}")

                        # Inspect likely day/tab controls and their accessibility role.
                        controls = page.locator("button, [role=tab], [role=button]")
                        useful = []
                        for i in range(min(controls.count(), 200)):
                            el = controls.nth(i)
                            txt = re.sub(r"\s+", " ", el.inner_text()).strip()
                            if re.search(
                                r"\b(FRIDAY|SATURDAY|SUNDAY|DAY\s*[12]|19\s+SEP|20\s+SEP)\b",
                                txt, re.I
                            ):
                                useful.append(el.evaluate("""el => ({
                                    tag: el.tagName,
                                    cls: el.className || '',
                                    role: el.getAttribute('role'),
                                    ariaSelected: el.getAttribute('aria-selected'),
                                    text: (el.innerText || '').replace(/\\s+/g,' ').trim()
                                })"""))
                        print(f"[WA-DOM] CONTROLS | {label} | {useful[:20]}")

                    except Exception as exc:
                        print(f"[WA-DOM] ERROR | {label} | {type(exc).__name__}: {exc}")
                    finally:
                        page.close()
            finally:
                context.close()
                browser.close()
        return []
