import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from models.sports_event import SportsEvent
from .base import BaseScraper


SOURCE_URL = "https://www.diamondleague.com/calendar/"

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

# Venue timezone is deliberately explicit. If Diamond League adds a new
# venue, we prefer to skip it until its timezone is known rather than
# silently store a wrong time.
VENUES = {
    "shanghai/keqiao": ("CHN", "Asia/Shanghai"),
    "shanghai": ("CHN", "Asia/Shanghai"),
    "xiamen": ("CHN", "Asia/Shanghai"),
    "rabat": ("MAR", "Africa/Casablanca"),
    "rome": ("ITA", "Europe/Rome"),
    "stockholm": ("SWE", "Europe/Stockholm"),
    "oslo": ("NOR", "Europe/Oslo"),
    "doha": ("QAT", "Asia/Qatar"),
    "paris": ("FRA", "Europe/Paris"),
    "eugene": ("USA", "America/Los_Angeles"),
    "monaco": ("MON", "Europe/Monaco"),
    "london": ("GBR", "Europe/London"),
    "lausanne": ("SUI", "Europe/Zurich"),
    "silesia": ("POL", "Europe/Warsaw"),
    "zurich": ("SUI", "Europe/Zurich"),
    "brussels": ("BEL", "Europe/Brussels"),
}

CALENDAR_RE = re.compile(
    r"(?P<day>\d{1,2})(?:-\d{1,2})?\s+"
    r"(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+"
    r"(?P<city>Shanghai/Keqiao|Shanghai|Xiamen|Rabat|Rome|Stockholm|Oslo|"
    r"Doha|Paris|Eugene|Monaco|London|Lausanne|Silesia|Zurich|Brussels)"
    r"\s+\((?P<country>[A-Z]{3})\)",
    re.IGNORECASE,
)

# Common timetable forms from meeting pages / Swiss Timing:
#   18:42 Women's 100m
#   18.42 Women's 100m
#   18h42 Women's 100m
# We intentionally require minutes so text such as "17h: Doors open" is ignored.
TIME_RE = re.compile(
    r"(?<!\\d)(?P<hour>[01]?\\d|2[0-3])"
    r"(?:(?:[:.])(?P<minute_colon>[0-5]\\d)|h(?P<minute_h>[0-5]\\d)?)"
    r"(?!\\d)",
    re.IGNORECASE,
)

MAIN_PROGRAM_RE = re.compile(
    r"(?<!\\d)(?P<hour>[01]?\\d|2[0-3])"
    r"(?:(?:[:.])(?P<minute_colon>[0-5]\\d)|h(?P<minute_h>[0-5]\\d)?)"
    r"\\s*:?\\s*(?:Main program|Main programme|Hoofdprogramma)",
    re.IGNORECASE,
)

# Words that strongly suggest an actual athletics programme rather than
# generic website/navigation content.
ATHLETICS_MARKERS = (
    "100m", "200m", "400m", "800m", "1500m", "3000m", "5000m",
    "hurdles", "steeplechase", "pole vault", "high jump", "long jump",
    "triple jump", "shot put", "discus", "javelin", "relay",
)


def _norm(text: str) -> str:
    return " ".join(text.split())


def _meeting_key(city: str) -> str:
    return city.strip().lower()


def _extract_calendar(text: str, year: int) -> list[dict]:
    compact = _norm(text)
    result = []
    seen = set()

    for m in CALENDAR_RE.finditer(compact):
        city = m.group("city")
        key = _meeting_key(city)
        venue = VENUES.get(key)
        if not venue:
            continue

        country, tz_name = venue
        item = {
            "year": year,
            "month": MONTHS[m.group("month").title()],
            "day": int(m.group("day")),
            "city": city,
            "country": country,
            "timezone": tz_name,
        }
        dedupe = (item["year"], item["month"], item["day"], key)
        if dedupe not in seen:
            seen.add(dedupe)
            result.append(item)

    return result


def _match_time(match) -> tuple[int, int]:
    minute = match.groupdict().get("minute_colon") or match.groupdict().get("minute_h") or "00"
    return int(match.group("hour")), int(minute)


def _extract_program_start(texts: list[str]) -> tuple[int, int] | None:
    """
    Prefer an explicitly published Main program time. If unavailable, use the
    earliest concrete athletics-event time from the rendered page/frame.
    """
    event_candidates = []

    for raw in texts:
        text = _norm(raw)
        lower = text.lower()

        main = MAIN_PROGRAM_RE.search(text)
        if main:
            return _match_time(main)

        for match in TIME_RE.finditer(text):
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 160)
            window = lower[start:end]

            if not any(marker in window for marker in ATHLETICS_MARKERS):
                continue

            hour, minute = _match_time(match)

            if hour < 9:
                continue

            event_candidates.append((hour, minute))

    return min(event_candidates) if event_candidates else None


def _make_event(meeting: dict, hour: int, minute: int, source_url: str) -> SportsEvent:
    tz_name = meeting["timezone"]
    local_dt = datetime(
        meeting["year"],
        meeting["month"],
        meeting["day"],
        hour,
        minute,
        tzinfo=ZoneInfo(tz_name),
    )
    utc_dt = local_dt.astimezone(timezone.utc)
    city = meeting["city"]

    return SportsEvent(
        source="diamondleague",
        source_id=f"{meeting['year']}-{meeting['month']:02d}{meeting['day']:02d}-{_meeting_key(city).replace('/', '-')}",
        sport="athletics",
        competition="Wanda Diamond League",
        name=f"Diamond League - {city}",
        start_datetime=utc_dt,
        end_datetime=None,
        location=city,
        country=meeting["country"],
        source_url=source_url,
        discovered_at=datetime.now(timezone.utc),
        timezone=tz_name,
    )


class DiamondLeagueScraper(BaseScraper):
    source = "diamondleague"

    def scrape(self) -> Iterable[SportsEvent]:
        events = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US")
            page = context.new_page()

            try:
                page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1500)

                body = page.locator("body").inner_text()

                year_match = re.search(r"Calendar\s+(20\d{2})", body, re.IGNORECASE)
                if not year_match:
                    return []

                year = int(year_match.group(1))
                meetings = _extract_calendar(body, year)

                # Map city -> official meeting subdomain discovered from calendar.
                links = page.locator("a").evaluate_all(
                    """els => els.map(a => ({
                        text: (a.innerText || '').trim(),
                        href: a.href
                    }))"""
                )

                city_urls = {}
                for item in links:
                    href = item.get("href") or ""
                    host = urlparse(href).netloc.lower()
                    text = (item.get("text") or "").lower()

                    if not host.endswith(".diamondleague.com"):
                        continue

                    for meeting in meetings:
                        city_key = _meeting_key(meeting["city"])
                        aliases = {
                            city_key,
                            city_key.split("/")[0],
                        }
                        if any(alias in text for alias in aliases if alias):
                            city_urls.setdefault(city_key, f"https://{host}/")

                for meeting in meetings:
                    key = _meeting_key(meeting["city"])
                    base = city_urls.get(key)
                    if not base:
                        # Most hosts follow city.diamondleague.com. Use only
                        # safe known slugs when calendar link extraction misses.
                        slug = key.split("/")[0].replace(" ", "")
                        base = f"https://{slug}.diamondleague.com/"

                    programme_url = base.rstrip("/") + "/en/programme-results/"

                    try:
                        page.goto(
                            programme_url,
                            wait_until="domcontentloaded",
                            timeout=45000,
                        )
                        page.wait_for_timeout(1200)
                    except Exception:
                        # One unavailable meeting must not stop the season.
                        continue

                    texts = []
                    try:
                        texts.append(page.locator("body").inner_text())
                    except Exception:
                        pass

                    # Swiss Timing is commonly embedded as a cross-origin frame.
                    for frame in page.frames:
                        if frame == page.main_frame:
                            continue
                        try:
                            texts.append(frame.locator("body").inner_text(timeout=5000))
                        except Exception:
                            continue

                    start = _extract_program_start(texts)
                    if start is None:
                        # No published concrete timetable: valid empty state
                        # for this meeting. Never invent a start time.
                        continue

                    event = _make_event(
                        meeting,
                        hour=start[0],
                        minute=start[1],
                        source_url=page.url,
                    )
                    events.append(event)

            finally:
                context.close()
                browser.close()

        events.sort(key=lambda event: event.start_datetime)
        return events
