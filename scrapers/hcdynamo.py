import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Iterable
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from models.sports_event import SportsEvent
from .base import BaseScraper


SOURCE_URL = "https://www.hcdynamo.cz/matches/MUZ"
PRAGUE_TZ = ZoneInfo("Europe/Prague")

DATE_RE = re.compile(
    r"(?:po|út|st|čt|pá|so|ne)\s+"
    r"(?P<day>\d{1,2})\.\s*"
    r"(?P<month>\d{1,2})\.\s*"
    r"(?P<year>\d{4}),\s*"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})",
    re.IGNORECASE,
)

ROUND_RE = re.compile(r"^(?:\d+\.\s*kolo|přát\.|Red Bulls Salute)\b", re.IGNORECASE)


class _ListItemParser(HTMLParser):
    """Collect text and image alt attributes for each <li> element."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.current = None
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            if self.depth == 0:
                self.current = {"text": [], "alts": []}
            self.depth += 1

        if self.depth and self.current is not None and tag == "img":
            attrs = dict(attrs)
            alt = (attrs.get("alt") or "").strip()
            if alt:
                self.current["alts"].append(alt)

    def handle_data(self, data):
        if self.depth and self.current is not None:
            text = " ".join(data.split())
            if text:
                self.current["text"].append(text)

    def handle_endtag(self, tag):
        if tag == "li" and self.depth:
            self.depth -= 1
            if self.depth == 0 and self.current is not None:
                self.items.append(self.current)
                self.current = None


def _clean_team_name(alt: str) -> str:
    alt = alt.strip()
    if alt.lower().startswith("logo "):
        return alt[5:].strip()
    return alt


def _competition_from_text(text: str) -> str:
    """
    HC Dynamo list items start with values such as:
    '1. kolo Liga Mistrů' or 'přát. Přípravná utkání Dynama A'.
    We remove the round marker and keep the competition name.
    """
    cleaned = " ".join(text.split())

    match = re.match(r"^\d+\.\s*kolo\s+(.+)$", cleaned, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    if cleaned.lower().startswith("přát. "):
        return cleaned[6:].strip()

    if cleaned.lower().startswith("red bulls salute "):
        return cleaned[len("Red Bulls Salute "):].strip()

    return cleaned or "HC Dynamo"


def _parse_event_item(item) -> SportsEvent | None:
    text = " ".join(item["text"])
    match = DATE_RE.search(text)
    if not match:
        return None

    teams = []
    for alt in item["alts"]:
        name = _clean_team_name(alt)
        if name and name not in teams:
            teams.append(name)

    # A match must contain exactly/at least two distinct team logos.
    if len(teams) < 2:
        return None

    home, away = teams[0], teams[1]

    # Competition text is the part before the date.
    prefix = text[:match.start()].strip(" -|")
    competition = _competition_from_text(prefix)

    dt = datetime(
        int(match.group("year")),
        int(match.group("month")),
        int(match.group("day")),
        int(match.group("hour")),
        int(match.group("minute")),
        tzinfo=PRAGUE_TZ,
    )

    source_id = f"{dt:%Y%m%d%H%M}-{home}-{away}"

    return SportsEvent(
        source="hcdynamo",
        source_id=source_id,
        sport="ice_hockey",
        competition=competition,
        name=f"{home} - {away}",
        start_datetime=dt,
        end_datetime=None,
        location=None,
        country="CZ",
        source_url=SOURCE_URL,
        discovered_at=datetime.now(timezone.utc),
    )


class HCDynamoScraper(BaseScraper):
    source = "hcdynamo"

    def scrape(self) -> Iterable[SportsEvent]:
        request = Request(
            SOURCE_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; SportsEventsScraper/1.0; "
                    "+https://github.com/)"
                )
            },
        )

        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8", errors="replace")

        parser = _ListItemParser()
        parser.feed(html)

        events = []
        seen = set()

        for item in parser.items:
            event = _parse_event_item(item)
            if event is None:
                continue

            key = (event.start_datetime, event.name)
            if key in seen:
                continue

            seen.add(key)
            events.append(event)

        if not events:
            raise RuntimeError(
                "HC Dynamo scraper returned 0 events. "
                "The page structure may have changed."
            )

        events.sort(key=lambda event: event.start_datetime)
        return events
