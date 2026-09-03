from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import yaml
from bs4 import BeautifulSoup, Tag

from models.tv_program import TVProgram


BASE_URL = "https://tvprogram.idnes.cz/"
SEARCH_URL = BASE_URL + "hledani?slovo={query}"
DETAIL_ID_RE = re.compile(r"\.id(?P<id>\d+)(?:$|[?#])")
DETAIL_PATH_RE = re.compile(
    r"^/(?P<channel>[^/]+)/(?P<dow>po|ut|st|ct|pa|so|ne)-(?P<hour>\d{1,2})\.(?P<minute>\d{2})-",
    re.IGNORECASE,
)
TIME_RANGE_RE = re.compile(r"(?P<sh>\d{1,2}):(?P<sm>\d{2})\s*-\s*(?P<eh>\d{1,2}):(?P<em>\d{2})")
DATE_RE = re.compile(
    r"(?:Pondělí|Úterý|Středa|Čtvrtek|Pátek|Sobota|Neděle)\s+(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedSchedule:
    source_id: str
    channel_slug: str
    title: str
    description: Optional[str]
    start_local: datetime
    end_local: datetime
    source_url: str


class IdnesTVScraper:
    source = "idnes"

    def __init__(
        self,
        config_path: str = "config/tv_channels.yaml",
        now: Optional[datetime] = None,
        timeout: int = 30,
    ):
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))["idnes"]
        self.tz_name = config.get("timezone", "Europe/Prague")
        self.tz = ZoneInfo(self.tz_name)
        self.channels: dict[str, str] = config["channels"]
        self.search_queries: list[str] = config.get("search_queries", [])
        self.max_pages_per_query = int(config.get("max_pages_per_query", 5))
        self.timeout = timeout
        self.now = now.astimezone(self.tz) if now else datetime.now(self.tz)

    def _fetch_html(self, url: str) -> str:
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; SportsEventsScraper/1.0)",
                "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.7",
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "windows-1250"
        return raw.decode(charset, errors="replace")

    @staticmethod
    def _source_id(url: str) -> Optional[str]:
        match = DETAIL_ID_RE.search(url)
        return match.group("id") if match else None

    @staticmethod
    def _detail_parts(url: str) -> Optional[dict[str, str]]:
        return DETAIL_PATH_RE.match(urlparse(url).path).groupdict() if DETAIL_PATH_RE.match(urlparse(url).path) else None

    def _resolve_date(self, day: int, month: int) -> date:
        """Resolve iDNES day/month to the nearest plausible date in its ~14-day horizon."""
        candidates = []
        for year in (self.now.year - 1, self.now.year, self.now.year + 1):
            try:
                candidates.append(date(year, month, day))
            except ValueError:
                continue
        if not candidates:
            raise ValueError(f"Invalid iDNES date {day}.{month}.")

        today = self.now.date()
        # Search pages can briefly retain same-day/past entries; allow a small past window.
        plausible = [d for d in candidates if today - timedelta(days=2) <= d <= today + timedelta(days=31)]
        if plausible:
            return min(plausible, key=lambda d: abs((d - today).days))
        return min(candidates, key=lambda d: abs((d - today).days))

    @staticmethod
    def _smallest_schedule_container(anchor: Tag) -> Optional[Tag]:
        """Find the smallest ancestor that contains both a date and a start-end range."""
        node: Optional[Tag] = anchor
        for _ in range(8):
            if node is None:
                break
            text = " ".join(node.stripped_strings)
            if TIME_RANGE_RE.search(text) and DATE_RE.search(text):
                return node
            parent = node.parent
            node = parent if isinstance(parent, Tag) else None
        return None

    @staticmethod
    def _description(container: Tag, title: str) -> Optional[str]:
        parts = [s.strip() for s in container.stripped_strings if s.strip()]
        ignored = {title}
        kept = []
        for part in parts:
            if part in ignored or TIME_RANGE_RE.fullmatch(part) or DATE_RE.fullmatch(part):
                continue
            if DATE_RE.search(part) or TIME_RANGE_RE.search(part):
                # Usually a combined header; it is schedule metadata, not description.
                continue
            kept.append(part)
        if not kept:
            return None
        # Avoid huge text when an ancestor was broader than expected.
        description = " ".join(kept)
        return description[:1000] if description else None

    def parse_search_html(self, html: str, page_url: str = BASE_URL) -> list[ParsedSchedule]:
        soup = BeautifulSoup(html, "html.parser")
        parsed: list[ParsedSchedule] = []
        seen: set[tuple[str, datetime, str]] = set()

        for anchor in soup.find_all("a", href=True):
            href = urljoin(page_url, anchor["href"])
            source_id = self._source_id(href)
            parts = self._detail_parts(href)
            if not source_id or not parts:
                continue

            channel_slug = parts["channel"].lower()
            if channel_slug not in self.channels:
                continue

            title = " ".join(anchor.stripped_strings).strip()
            if not title:
                continue

            container = self._smallest_schedule_container(anchor)
            if container is None:
                continue
            text = " ".join(container.stripped_strings)
            time_match = TIME_RANGE_RE.search(text)
            date_match = DATE_RE.search(text)
            if not time_match or not date_match:
                continue

            local_date = self._resolve_date(int(date_match.group("day")), int(date_match.group("month")))
            start_t = time(int(time_match.group("sh")), int(time_match.group("sm")))
            end_t = time(int(time_match.group("eh")), int(time_match.group("em")))
            start_local = datetime.combine(local_date, start_t, self.tz)
            end_local = datetime.combine(local_date, end_t, self.tz)
            if end_local <= start_local:
                end_local += timedelta(days=1)

            # URL itself contains the advertised start time. A mismatch means we likely
            # climbed into a container belonging to a neighboring programme entry.
            url_start = (int(parts["hour"]), int(parts["minute"]))
            if (start_local.hour, start_local.minute) != url_start:
                continue

            key = (source_id, start_local, channel_slug)
            if key in seen:
                continue
            seen.add(key)
            parsed.append(
                ParsedSchedule(
                    source_id=source_id,
                    channel_slug=channel_slug,
                    title=title,
                    description=self._description(container, title),
                    start_local=start_local,
                    end_local=end_local,
                    source_url=href,
                )
            )
        return parsed

    @staticmethod
    def _next_page_url(html: str, current_url: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.find_all("a", href=True):
            label = " ".join(anchor.stripped_strings).strip().casefold()
            if label in {"další", "dalsi", "next"}:
                return urljoin(current_url, anchor["href"])
        return None

    def _scrape_query(self, query: str) -> Iterable[ParsedSchedule]:
        url: Optional[str] = SEARCH_URL.format(query=quote_plus(query))
        visited: set[str] = set()
        for _ in range(self.max_pages_per_query):
            if not url or url in visited:
                break
            visited.add(url)
            html = self._fetch_html(url)
            yield from self.parse_search_html(html, url)
            url = self._next_page_url(html, url)

    def scrape(self) -> list[TVProgram]:
        discovered_at = datetime.now(timezone.utc)
        programs: list[TVProgram] = []
        seen: set[tuple[str, datetime, str]] = set()

        for query in self.search_queries:
            for item in self._scrape_query(query):
                channel = self.channels[item.channel_slug]
                start_utc = item.start_local.astimezone(timezone.utc)
                end_utc = item.end_local.astimezone(timezone.utc)
                key = (item.source_id, start_utc, channel)
                if key in seen:
                    continue
                seen.add(key)
                programs.append(
                    TVProgram(
                        source=self.source,
                        source_id=item.source_id,
                        channel=channel,
                        title=item.title,
                        description=item.description,
                        start_datetime=start_utc,
                        end_datetime=end_utc,
                        source_url=item.source_url,
                        discovered_at=discovered_at,
                        timezone=self.tz_name,
                        distribution="tv",
                    )
                )

        programs.sort(key=lambda p: (p.start_datetime, p.channel, p.title))
        return programs
