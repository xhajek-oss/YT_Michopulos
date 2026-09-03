import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urljoin, urlparse, parse_qs
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from models.sports_event import SportsEvent
from .base import BaseScraper


SOURCE_URL = "https://www.biathlonworld.com/calendar"
PRAGUE_TZ = ZoneInfo("Europe/Prague")

MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

# Handles both compact and line-separated text produced by the calendar.
COMPETITION_RE = re.compile(
    r"\b(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\s*(?P<day>\d{1,2})\s*(?P<year>\d{4})"
    r"\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?"
    r"\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})"
    r"\s*(?P<name>.+?)"
    r"\s*(?:Scheduled|Finished|Live)\b",
    re.IGNORECASE | re.DOTALL,
)


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _event_id_from_url(url: str) -> str | None:
    values = parse_qs(urlparse(url).query).get("EventId")
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _parse_competitions(
    text: str,
    location: str | None,
    country: str | None,
    source_url: str,
    competition: str = "International Biathlon Union",
) -> list[SportsEvent]:
    """
    Parse the rendered race list of one Biathlon World calendar event.

    The browser context is fixed to Europe/Prague, so any time rendered by
    the website is interpreted consistently in Prague time for later TV
    matching.
    """
    compact = _normalize_text(text)
    discovered_at = datetime.now(timezone.utc)
    events: list[SportsEvent] = []
    seen = set()

    for match in COMPETITION_RE.finditer(compact):
        name = _normalize_text(match.group("name"))

        # Prevent a greedy match from swallowing navigation/calendar labels.
        for marker in (
            "Upcoming competitions ",
            "Previous competitions ",
            "Competitions ",
        ):
            if marker in name:
                name = name.split(marker)[-1].strip()

        dt = datetime(
            int(match.group("year")),
            MONTHS[match.group("month").title()],
            int(match.group("day")),
            int(match.group("hour")),
            int(match.group("minute")),
            tzinfo=PRAGUE_TZ,
        )

        source_id = (
            f"{_event_id_from_url(source_url) or 'event'}-"
            f"{dt:%Y%m%d%H%M}-"
            f"{re.sub(r'[^A-Za-z0-9]+', '-', name).strip('-').lower()}"
        )

        key = (dt, name, source_url)
        if key in seen:
            continue
        seen.add(key)

        events.append(
            SportsEvent(
                source="biathlonworld",
                source_id=source_id,
                sport="biathlon",
                competition=competition,
                name=name,
                start_datetime=dt,
                end_datetime=None,
                location=location,
                country=country,
                source_url=source_url,
                discovered_at=discovered_at,
            )
        )

    return events


class BiathlonWorldScraper(BaseScraper):
    source = "biathlonworld"

    def scrape(self) -> Iterable[SportsEvent]:
        all_events: list[SportsEvent] = []
        seen_events = set()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                timezone_id="Europe/Prague",
                locale="en-US",
                user_agent=(
                    "Mozilla/5.0 (compatible; SportsEventsScraper/1.0; "
                    "+https://github.com/)"
                ),
            )
            page = context.new_page()

            try:
                page.goto(
                    SOURCE_URL,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                page.wait_for_timeout(2500)

                hrefs = page.locator('a[href*="EventId="]').evaluate_all(
                    "(els) => els.map(el => el.href)"
                )

                event_urls = []
                seen_urls = set()

                for href in hrefs:
                    event_id = _event_id_from_url(href)
                    if not event_id:
                        continue

                    absolute = urljoin(SOURCE_URL, href)
                    if absolute in seen_urls:
                        continue

                    seen_urls.add(absolute)
                    event_urls.append(absolute)

                if not event_urls:
                    # The selected/default event can still be parsed even if
                    # the navigation markup changes and no EventId links appear.
                    event_urls = [page.url]

                for event_url in event_urls:
                    page.goto(
                        event_url,
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                    page.wait_for_timeout(1000)

                    text = page.locator("body").inner_text()

                    h1 = page.locator("h1")
                    h2 = page.locator("h2")

                    location = (
                        _normalize_text(h1.first.inner_text())
                        if h1.count()
                        else None
                    )
                    country = (
                        _normalize_text(h2.first.inner_text())
                        if h2.count()
                        else None
                    )

                    events = _parse_competitions(
                        text=text,
                        location=location,
                        country=country,
                        source_url=page.url,
                    )

                    for event in events:
                        key = (
                            event.start_datetime,
                            event.name,
                            event.location,
                        )
                        if key in seen_events:
                            continue
                        seen_events.add(key)
                        all_events.append(event)

            finally:
                context.close()
                browser.close()

        if not all_events:
            raise RuntimeError(
                "Biathlon World scraper returned 0 events. "
                "The calendar structure may have changed."
            )

        all_events.sort(key=lambda event: event.start_datetime)
        return all_events
