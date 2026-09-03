import os
import sys
import json
import re
import html
import unicodedata
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


# ============================================================
# SPORT MONITOR
# ============================================================

TIMEZONE = ZoneInfo("Europe/Prague")

DYNAMO_URL = "https://www.hcdynamo.cz/matches/MUZ"
CHL_TV_URL = "https://www.chl.hockey/en/fans/chl-games-on-tv"
ONEPLAY_SPORT_URL = "https://www.oneplay.cz/sport"
HOKEJ_CZ_URL = "https://www.hokej.cz/klub/hc-dynamo-pardubice/12/zapasy"

STATE_FILE = "data/sport_state.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

REQUEST_TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
    )
}


# ============================================================
# KONFIGURACE
# ============================================================

CONFIG = {
    "dynamo_pardubice": True,
    "diamond_league": True,
    "biathlon": True,
    "world_hockey_championship": False,
}


# ============================================================
# HTTP
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


def get_url(url, params=None):
    try:
        response = session.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.text
    except Exception as exc:
        print(f"HTTP chyba: {url}")
        print(f"  {exc}")
        return None


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )

    value = value.lower()
    value = value.replace("–", "-")
    value = value.replace("—", "-")
    value = value.replace("−", "-")

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def compact_text(value):
    return re.sub(r"[^a-z0-9]+", "", normalize_text(value))


def contains_alias(text, aliases):
    normalized = normalize_text(text)

    for alias in aliases:
        alias_normalized = normalize_text(alias)

        if alias_normalized and alias_normalized in normalized:
            return True

    return False


def unique_list(items):
    result = []

    for item in items:
        if item and item not in result:
            result.append(item)

    return result


# ============================================================
# TEAM ALIASES
# ============================================================

TEAM_ALIASES = {
    "HC Dynamo Pardubice": [
        "HC Dynamo Pardubice",
        "Dynamo Pardubice",
        "Dynamo",
        "Pardubice",
    ],

    "GKS Tychy": [
        "GKS Tychy",
        "Tychy",
    ],

    "Rögle BK": [
        "Rögle BK",
        "Rogle BK",
        "Rögle",
        "Rogle",
    ],

    "Mountfield HK": [
        "Mountfield HK",
        "Mountfield",
        "Hradec Kralove",
        "Hradec Králové",
    ],

    "HC VERVA Litvínov": [
        "HC VERVA Litvínov",
        "Litvínov",
        "Verva Litvínov",
    ],

    "HC Energie Karlovy Vary": [
        "HC Energie Karlovy Vary",
        "Karlovy Vary",
    ],

    "Bílí Tygři Liberec": [
        "Bílí Tygři Liberec",
        "Bili Tygri Liberec",
        "Liberec",
    ],

    "HC Kometa Brno": [
        "HC Kometa Brno",
        "Kometa Brno",
        "Brno",
    ],

    "BK Mladá Boleslav": [
        "BK Mladá Boleslav",
        "Mladá Boleslav",
        "Mlada Boleslav",
    ],

    "Banes Motor České Budějovice": [
        "Banes Motor České Budějovice",
        "Motor České Budějovice",
        "České Budějovice",
        "Ceske Budejovice",
    ],

    "SaiPa Lappeenranta": [
        "SaiPa Lappeenranta",
        "SaiPa",
        "Lappeenranta",
    ],

    "KooKoo Kouvola": [
        "KooKoo Kouvola",
        "KooKoo",
        "Kouvola",
    ],

    "Växjö Lakers": [
        "Växjö Lakers",
        "Vaxjo Lakers",
        "Växjö",
        "Vaxjo",
    ],

    "Red Bull München": [
        "Red Bull München",
        "Red Bull Munchen",
        "Red Bull Munich",
        "Munich",
        "München",
    ],

    "Vlci Žilina": [
        "Vlci Žilina",
        "Vlci Zilina",
        "Žilina",
        "Zilina",
    ],
}


# ============================================================
# COMPETITION
# ============================================================

COMPETITION_MAP = {
    "liga mistrů": "Liga mistrů",
    "liga mistru": "Liga mistrů",
    "champions hockey league": "Liga mistrů",
    "champions hockey": "Liga mistrů",
    "chl": "Liga mistrů",

    "tipsport extraliga": "Tipsport extraliga",
    "tipsport extraliga ledního hokeje": "Tipsport extraliga",
    "telh": "Tipsport extraliga",
    "extraliga": "Tipsport extraliga",

    "diamond league": "Diamond League",
    "diamantová liga": "Diamond League",
    "diamantova liga": "Diamond League",

    "biatlon": "Biatlon",
    "biathlon": "Biatlon",

    "mistrovství světa": "Mistrovství světa",
    "mistrovstvi sveta": "Mistrovství světa",

    "mistrovství evropy": "Mistrovství Evropy",
    "mistrovstvi evropy": "Mistrovství Evropy",
}


def normalize_competition(value):
    normalized = normalize_text(value)

    for key, result in COMPETITION_MAP.items():
        if key in normalized:
            return result

    return value.strip() if value else "Neznámá soutěž"


# ============================================================
# DATE PARSING
# ============================================================

CZECH_MONTHS = {
    "ledna": 1,
    "února": 2,
    "brezna": 3,
    "března": 3,
    "dubna": 4,
    "května": 5,
    "kvetna": 5,
    "června": 6,
    "cervna": 6,
    "července": 7,
    "cervence": 7,
    "srpna": 8,
    "září": 9,
    "rijna": 10,
    "října": 10,
    "listopadu": 11,
    "prosince": 12,
}


def parse_date_time(text, default_year=None):
    if not text:
        return None

    text = normalize_text(text)

    # 3. 9. 2026 18:00
    match = re.search(
        r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})"
        r"(?:[^\d]+(\d{1,2}):(\d{2}))?",
        text,
    )

    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))

        hour = int(match.group(4) or 0)
        minute = int(match.group(5) or 0)

        try:
            return datetime(
                year,
                month,
                day,
                hour,
                minute,
                tzinfo=TIMEZONE,
            )
        except ValueError:
            return None

    # 03.09.2026 18:00
    match = re.search(
        r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})"
        r"(?:[^\d]+(\d{1,2}):(\d{2}))?",
        text,
    )

    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))

        hour = int(match.group(4) or 0)
        minute = int(match.group(5) or 0)

        try:
            return datetime(
                year,
                month,
                day,
                hour,
                minute,
                tzinfo=TIMEZONE,
            )
        except ValueError:
            return None

    # 3. září 2026 18:00
    match = re.search(
        r"\b(\d{1,2})\.\s*"
        r"(ledna|února|brezna|března|dubna|května|kvetna|"
        r"června|cervna|července|cervence|srpna|září|rijna|října|"
        r"listopadu|prosince)"
        r"(?:\s+(\d{4}))?"
        r"(?:[^\d]+(\d{1,2}):(\d{2}))?",
        text,
    )

    if match:
        day = int(match.group(1))
        month_name = match.group(2)
        year = int(match.group(3) or default_year or datetime.now(TIMEZONE).year)

        month = CZECH_MONTHS.get(month_name)

        if month:
            hour = int(match.group(4) or 0)
            minute = int(match.group(5) or 0)

            try:
                return datetime(
                    year,
                    month,
                    day,
                    hour,
                    minute,
                    tzinfo=TIMEZONE,
                )
            except ValueError:
                return None

    return None


# ============================================================
# EVENT
# ============================================================

def make_event(
    event_date,
    home,
    away,
    competition,
    sport="hokej",
):
    competition = normalize_competition(competition)

    return {
        "date": event_date.isoformat(),
        "home": home.strip(),
        "away": away.strip(),
        "competition": competition,
        "sport": sport,

        "tv_confirmed": False,
        "tv_channels": [],
        "tv_sources": [],

        "tv_checked": False,
    }


def event_key(event):
    return (
        event.get("date", ""),
        normalize_text(event.get("home", "")),
        normalize_text(event.get("away", "")),
        normalize_text(event.get("competition", "")),
    )


# ============================================================
# DYNAMO – ROBUSTNÍ PARSOVÁNÍ
# ============================================================

def detect_competition_from_container(container):
    """
    Soutěž hledáme co nejblíž konkrétnímu zápasu.

    Důležité:
    Nebereme celý <body> ani velkého rodiče, protože by se
    přípravný zápas mohl omylem označit jako CHL.
    """

    texts = []

    # Nejprve přímý text containeru
    own_text = container.get_text(" ", strip=True)

    if own_text:
        texts.append(own_text)

    # Potom pouze menší bezprostřední části
    for child in container.find_all(
        ["span", "div", "p", "a", "strong", "small"],
        limit=20,
    ):
        text = child.get_text(" ", strip=True)

        if text:
            texts.append(text)

    combined = " | ".join(texts)

    normalized = normalize_text(combined)

    # Priorita přesných soutěží
    if "liga mistr" in normalized:
        return "Liga mistrů"

    if "tipsport extraliga" in normalized:
        return "Tipsport extraliga"

    if "extraliga" in normalized:
        return "Tipsport extraliga"

    if "diamond league" in normalized:
        return "Diamond League"

    if "biatlon" in normalized or "biathlon" in normalized:
        return "Biatlon"

    # Příprava / turnaje
    if "pripr" in normalized or "přípr" in normalized:
        return "Příprava"

    if "red bulls salute" in normalized:
        return "Red Bull Salute"

    return "Neznámá soutěž"


def find_smallest_match_container(date_node):
    """
    Najde nejmenší DOM kontejner, který současně obsahuje:
    - datum
    - Dynamo
    - VS / soupeře

    Tím se zabrání párování týmů z jiného zápasu.
    """

    current = date_node

    for _ in range(8):
        if current is None:
            break

        text = current.get_text(" ", strip=True)
        normalized = normalize_text(text)

        has_dynamo = (
            "dynamo pardubice" in normalized
            or "dynamo" in normalized
        )

        has_vs = (
            " vs " in f" {normalized} "
            or "versus" in normalized
        )

        # Potřebujeme dostatečně malý kontejner
        if has_dynamo and has_vs:
            # Nechceme extrémně velké kontejnery
            if len(text) < 1500:
                return current

        current = current.parent

    return None


def extract_team_names(container):
    """
    Extrahuje týmy z obrázků/log alt textů a viditelného textu.
    """

    candidates = []

    # ALT texty log
    for img in container.find_all("img"):
        alt = img.get("alt", "").strip()

        if alt:
            candidates.append(alt)

    # Viditelné texty
    for node in container.find_all(
        ["span", "div", "a", "strong", "p"],
        limit=100,
    ):
        text = node.get_text(" ", strip=True)

        if 2 <= len(text) <= 100:
            candidates.append(text)

    # Zkusíme najít známé týmy
    found = []

    for canonical, aliases in TEAM_ALIASES.items():
        for candidate in candidates:
            if contains_alias(candidate, aliases):
                found.append(canonical)
                break

    found = unique_list(found)

    # Pokud máme přesně dva týmy, máme hotovo
    if len(found) >= 2:
        return found[:2]

    # Fallback – pokus o textovou formu:
    text = container.get_text(" ", strip=True)

    match = re.search(
        r"(.+?)\s+(?:VS|vs|versus)\s+(.+)",
        text,
        re.IGNORECASE,
    )

    if match:
        home = match.group(1).strip()
        away = match.group(2).strip()

        if home and away:
            return [home, away]

    return found


def parse_dynamo():
    print("=== DYNAMO PARDUBICE ===")
    print(f"Zdroj: {DYNAMO_URL}")

    html_text = get_url(DYNAMO_URL)

    if not html_text:
        print("Dynamo: nepodařilo se načíst stránku.")
        return []

    soup = BeautifulSoup(html_text, "html.parser")

    events = []

    # Hledáme všechny elementy obsahující datum
    date_nodes = []

    for node in soup.find_all(string=True):
        text = node.strip()

        if not text:
            continue

        if re.search(r"\b\d{1,2}\.\s*\d{1,2}\.\s*\d{4}", text):
            date_nodes.append(node)

    print(f"Datumových bloků: {len(date_nodes)}")

    for date_node in date_nodes:
        text = date_node.strip()

        event_date = parse_date_time(text)

        if not event_date:
            continue

        container = find_smallest_match_container(date_node.parent)

        if not container:
            continue

        teams = extract_team_names(container)

        if len(teams) < 2:
            continue

        # Musí jít skutečně o Dynamo
        if not any(
            contains_alias(team, TEAM_ALIASES["HC Dynamo Pardubice"])
            for team in teams
        ):
            continue

        # Určení domácí/hosté
        first = teams[0]
        second = teams[1]

        first_is_dynamo = contains_alias(
            first,
            TEAM_ALIASES["HC Dynamo Pardubice"],
        )

        second_is_dynamo = contains_alias(
            second,
            TEAM_ALIASES["HC Dynamo Pardubice"],
        )

        if first_is_dynamo:
            home = "HC Dynamo Pardubice"
            away = second

        elif second_is_dynamo:
            home = first
            away = "HC Dynamo Pardubice"

        else:
            continue

        competition = detect_competition_from_container(container)

        event = make_event(
            event_date=event_date,
            home=home,
            away=away,
            competition=competition,
            sport="hokej",
        )

        events.append(event)

    # --------------------------------------------------------
    # Deduplikace
    # --------------------------------------------------------

    unique_events = {}
    for event in events:
        unique_events[event_key(event)] = event

    events = list(unique_events.values())

    events.sort(key=lambda x: x["date"])

    print(f"Výsledných zápasů Dynamo: {len(events)}")

    for event in events:
        dt = datetime.fromisoformat(event["date"])

        print(
            f"{dt.strftime('%Y-%m-%d %H:%M')} "
            f"{event['home']} vs {event['away']} "
            f"| {event['competition']}"
        )

    return events


# ============================================================
# TV – KANÁLY
# ============================================================

TV_CHANNEL_PATTERNS = [
    r"\bSport\s*[1-4]\b",
    r"\bČT\s*sport\b",
    r"\bCT\s*sport\b",

    r"\bNova\s*Sport\s*[1-4]\b",

    r"\bOneplay\s*Sport\s*[1-4]\b",
    r"\bOneplay\s*Sport\b",

    r"\bO2\s*TV\s*Sport\b",

    r"\bPremier\s*Sport\s*[1-3]\b",

    r"\bEurosport\s*[1-2]\b",

    r"\bPolsat\s*Sport\s*[1-4]\b",

    r"\bESPN\b",

    r"\bDAZN\b",
]


def extract_tv_channels(text):
    channels = []

    for pattern in TV_CHANNEL_PATTERNS:
        for match in re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            channel = match.group(0).strip()

            if channel not in channels:
                channels.append(channel)

    return channels


# ============================================================
# TV – PÁROVÁNÍ UDÁLOSTI
# ============================================================

def event_matches_text(event, text):
    """
    Kritická funkce.

    Nestačí pouze datum.
    Nestačí pouze Dynamo.

    Musí být nalezen:
        1. domácí tým
        2. hostující tým
        3. datum

    Tím zabráníme přiřazení TV z jiného zápasu.
    """

    normalized = normalize_text(text)

    home_aliases = TEAM_ALIASES.get(
        event["home"],
        [event["home"]],
    )

    away_aliases = TEAM_ALIASES.get(
        event["away"],
        [event["away"]],
    )

    home_found = contains_alias(
        normalized,
        home_aliases,
    )

    away_found = contains_alias(
        normalized,
        away_aliases,
    )

    event_dt = datetime.fromisoformat(event["date"])

    date_patterns = [
        event_dt.strftime("%d.%m.%Y"),
        event_dt.strftime("%d. %m. %Y"),
        event_dt.strftime("%d/%m/%Y"),
        event_dt.strftime("%Y-%m-%d"),
        event_dt.strftime("%d.%m."),
        event_dt.strftime("%d. %m."),
    ]

    date_found = any(
        normalize_text(pattern) in normalized
        for pattern in date_patterns
    )

    return home_found and away_found and date_found


def add_tv_result(event, channels, source):
    if not channels:
        return False

    event["tv_confirmed"] = True
    event["tv_checked"] = True

    event["tv_channels"] = unique_list(
        event.get("tv_channels", []) + channels
    )

    event["tv_sources"] = unique_list(
        event.get("tv_sources", []) + [source]
    )

    return True


# ============================================================
# TV PROVIDER 1 – CHL
# ============================================================

def search_chl_tv(event):
    print("  TV zdroj: CHL")

    html_text = get_url(CHL_TV_URL)

    if not html_text:
        return False

    soup = BeautifulSoup(html_text, "html.parser")

    event_dt = datetime.fromisoformat(event["date"])

    target_date_strings = [
        event_dt.strftime("%d/%m/%Y"),
        event_dt.strftime("%d.%m.%Y"),
        event_dt.strftime("%d/%m/%y"),
    ]

    # --------------------------------------------------------
    # Nejprve hledáme jednotlivé řádky/tabulky.
    # --------------------------------------------------------

    containers = []

    containers.extend(soup.find_all("tr"))
    containers.extend(soup.find_all("article"))
    containers.extend(soup.find_all("li"))

    for container in containers:
        text = container.get_text(" ", strip=True)

        if not text:
            continue

        if not event_matches_text(event, text):
            continue

        # Pokud datum není v řádku přesně, zkusíme povolit
        # samotný rok + den/měsíc.
        normalized = normalize_text(text)

        date_ok = any(
            normalize_text(value) in normalized
            for value in target_date_strings
        )

        if not date_ok:
            continue

        channels = extract_tv_channels(text)

        if channels:
            print(f"  Nalezeno: {', '.join(channels)}")
            return add_tv_result(
                event,
                channels,
                "CHL Games on TV",
            )

    # --------------------------------------------------------
    # Fallback: textové bloky
    # --------------------------------------------------------

    full_text = soup.get_text("\n", strip=True)

    lines = [
        line.strip()
        for line in full_text.splitlines()
        if line.strip()
    ]

    for index, line in enumerate(lines):
        window = "\n".join(
            lines[max(0, index - 3): index + 5]
        )

        if event_matches_text(event, window):
            channels = extract_tv_channels(window)

            if channels:
                print(f"  Nalezeno: {', '.join(channels)}")

                return add_tv_result(
                    event,
                    channels,
                    "CHL Games on TV",
                )

    print("  Nenalezeno.")

    return False


# ============================================================
# TV PROVIDER 2 – ONEPLAY
# ============================================================

def search_oneplay_tv(event):
    print("  TV zdroj: Oneplay")

    html_text = get_url(ONEPLAY_SPORT_URL)

    if not html_text:
        return False

    soup = BeautifulSoup(html_text, "html.parser")

    # --------------------------------------------------------
    # Procházíme menší bloky, ne celou stránku.
    # --------------------------------------------------------

    containers = []

    containers.extend(soup.find_all("article"))
    containers.extend(soup.find_all("li"))
    containers.extend(soup.find_all("div"))

    checked = 0

    for container in containers:
        text = container.get_text(" ", strip=True)

        if len(text) > 1200:
            continue

        if not text:
            continue

        normalized = normalize_text(text)

        # Musí obsahovat alespoň Dynamo nebo soupeře
        if not (
            contains_alias(
                normalized,
                TEAM_ALIASES.get(
                    event["home"],
                    [event["home"]],
                ),
            )
            or
            contains_alias(
                normalized,
                TEAM_ALIASES.get(
                    event["away"],
                    [event["away"]],
                ),
            )
        ):
            continue

        checked += 1

        # Oneplay může používat jiné datumové formáty.
        if event_matches_text(event, text):
            channels = extract_tv_channels(text)

            if not channels:
                # Pokud se jedná o Oneplay sport stránku,
                # samotný název Oneplay Sport je relevantní.
                if "oneplay sport" in normalized:
                    channels = ["Oneplay Sport"]

            if channels:
                print(f"  Nalezeno: {', '.join(channels)}")

                return add_tv_result(
                    event,
                    channels,
                    "Oneplay Sport",
                )

    print(f"  Nenalezeno ({checked} kandidátních bloků).")

    return False


# ============================================================
# TV PROVIDER 3 – HOKEJ.CZ
# ============================================================

def search_hokej_cz_tv(event):
    print("  TV zdroj: Hokej.cz")

    html_text = get_url(HOKEJ_CZ_URL)

    if not html_text:
        return False

    soup = BeautifulSoup(html_text, "html.parser")

    containers = []

    containers.extend(soup.find_all("tr"))
    containers.extend(soup.find_all("article"))
    containers.extend(soup.find_all("li"))

    for container in containers:
        text = container.get_text(" ", strip=True)

        if not text:
            continue

        if event_matches_text(event, text):
            channels = extract_tv_channels(text)

            if channels:
                print(f"  Nalezeno: {', '.join(channels)}")

                return add_tv_result(
                    event,
                    channels,
                    "Hokej.cz",
                )

    print("  Nenalezeno.")

    return False


# ============================================================
# TV – GENERICKÉ WEBOVÉ HLEDÁNÍ
# ============================================================

def duckduckgo_search(query):
    url = "https://html.duckduckgo.com/html/"

    html_text = get_url(
        url,
        params={"q": query},
    )

    if not html_text:
        return []

    soup = BeautifulSoup(html_text, "html.parser")

    results = []

    for result in soup.select(".result"):
        title = result.select_one(".result__title")
        snippet = result.select_one(".result__snippet")

        title_text = (
            title.get_text(" ", strip=True)
            if title else ""
        )

        snippet_text = (
            snippet.get_text(" ", strip=True)
            if snippet else ""
        )

        text = f"{title_text} {snippet_text}".strip()

        if text:
            results.append(text)

    return results


def search_web_for_tv(event):
    print("  TV zdroj: obecné webové hledání")

    event_dt = datetime.fromisoformat(event["date"])

    date_cz = event_dt.strftime("%d.%m.%Y")
    date_iso = event_dt.strftime("%Y-%m-%d")

    home = event["home"]
    away = event["away"]

    queries = [
        f'"{home}" "{away}" "{date_cz}" TV',
        f'"{home}" "{away}" "{date_cz}" televize',
        f'"{home}" "{away}" "{date_iso}" TV',
        f'"{home}" "{away}" "{date_cz}" Sport 1 Sport 2',
        f'"{home}" "{away}" "{date_cz}" Oneplay',
    ]

    for query in queries:
        print(f"    Dotaz: {query}")

        results = duckduckgo_search(query)

        for result in results:
            # Zásadní: výsledek musí obsahovat oba týmy.
            if not event_matches_text(event, result):
                continue

            channels = extract_tv_channels(result)

            if channels:
                print(
                    f"    Nalezeno: {', '.join(channels)}"
                )

                return add_tv_result(
                    event,
                    channels,
                    "Web search",
                )

    print("  Nenalezeno.")

    return False


# ============================================================
# TV – SPECIALIZOVANÉ ZDROJE PODLE SOUTĚŽE
# ============================================================

TV_PROVIDERS = {
    "Liga mistrů": [
        search_chl_tv,
        search_oneplay_tv,
        search_web_for_tv,
    ],

    "Tipsport extraliga": [
        search_oneplay_tv,
        search_hokej_cz_tv,
        search_web_for_tv,
    ],

    "Diamond League": [
        search_oneplay_tv,
        search_web_for_tv,
    ],

    "Biatlon": [
        search_oneplay_tv,
        search_web_for_tv,
    ],

    "Mistrovství světa": [
        search_oneplay_tv,
        search_web_for_tv,
    ],

    "Mistrovství Evropy": [
        search_oneplay_tv,
        search_web_for_tv,
    ],

    # Pro přípravu zatím používáme obecné hledání.
    "Příprava": [
        search_oneplay_tv,
        search_web_for_tv,
    ],

    "Red Bull Salute": [
        search_oneplay_tv,
        search_web_for_tv,
    ],

    "Neznámá soutěž": [
        search_web_for_tv,
    ],
}


def verify_tv_broadcast(event):
    print(
        f"=== TV OVĚŘENÍ ===\n"
        f"{event['home']} vs {event['away']}\n"
        f"Soutěž: {event['competition']}"
    )

    competition = event.get(
        "competition",
        "Neznámá soutěž",
    )

    providers = TV_PROVIDERS.get(
        competition,
        TV_PROVIDERS["Neznámá soutěž"],
    )

    event["tv_checked"] = True

    # --------------------------------------------------------
    # Postupně zkoušíme zdroje.
    # Jakmile najdeme potvrzení, můžeme skončit.
    # --------------------------------------------------------

    for provider in providers:
        try:
            found = provider(event)

            if found:
                print(
                    f"→ TV POTVRZENO: "
                    f"{', '.join(event['tv_channels'])}"
                )

                return event

        except Exception as exc:
            print(
                f"  Chyba TV providera "
                f"{provider.__name__}: {exc}"
            )

    event["tv_confirmed"] = False

    print(
        "→ TV NEPOTVRZENO: "
        "žádný zdroj nespároval přesnou událost."
    )

    return event


# ============================================================
# ATHLETICS
# ============================================================

def parse_athletics():
    print("=== ATLETIKA ===")
    print(
        "Kategorie: Diamond League, ME/MS, "
        "halové ME/MS, významné české mítinky"
    )

    # --------------------------------------------------------
    # Záměrně zde zatím negenerujeme falešné události.
    #
    # TV systém je připravený a pokud se později přidá zdroj
    # atletických událostí, každá událost projde stejnou funkcí
    # verify_tv_broadcast().
    # --------------------------------------------------------

    print("Vybraných atletických událostí: 0")

    return []


# ============================================================
# BIATLON
# ============================================================

def parse_biathlon():
    print("=== BIATLON ===")

    # Stejný princip jako u atletiky.
    # Události musí nejdříve přijít z datového zdroje.
    # TV se potom dohledává samostatně.

    print("Celkem událostí: 0")

    return []


# ============================================================
# WORLD HOCKEY CHAMPIONSHIP
# ============================================================

def parse_world_hockey():
    print("=== MS V HOKEJI ===")

    print(
        "World Hockey Championship je v konfiguraci vypnuté."
    )

    return []


# ============================================================
# FILTER
# ============================================================

def filter_events(events, mode):
    now = datetime.now(TIMEZONE)

    today = now.date()

    if mode == "daily":
        result = []

        for event in events:
            event_dt = datetime.fromisoformat(
                event["date"]
            )

            if event_dt.date() == today:
                result.append(event)

        return result

    if mode == "weekly":
        end_date = today + timedelta(days=7)

        result = []

        for event in events:
            event_dt = datetime.fromisoformat(
                event["date"]
            )

            if today <= event_dt.date() <= end_date:
                result.append(event)

        return result

    return events


# ============================================================
# TELEGRAM HTML
# ============================================================

def escape_telegram_html(text):
    if text is None:
        return ""

    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_event(event):
    event_dt = datetime.fromisoformat(
        event["date"]
    )

    date_text = event_dt.strftime(
        "%d.%m.%Y %H:%M"
    )

    competition = escape_telegram_html(
        event.get("competition", "")
    )

    home = escape_telegram_html(
        event.get("home", "")
    )

    away = escape_telegram_html(
        event.get("away", "")
    )

    message = (
        f"🏆 <b>{competition}</b>\n"
        f"📅 {date_text}\n"
        f"🏒 <b>{home}</b> vs <b>{away}</b>\n"
    )

    if event.get("tv_confirmed"):
        channels = ", ".join(
            event.get("tv_channels", [])
        )

        message += (
            f"📺 TV: <b>"
            f"{escape_telegram_html(channels)}"
            f"</b>\n"
        )

    else:
        message += "📺 TV: zatím nepotvrzeno\n"

    return message


def make_daily_message(events):
    if not events:
        return None

    lines = [
        "📅 <b>SPORT MONITOR – DNES</b>",
        "",
    ]

    for event in events:
        lines.append(
            format_event(event)
        )
        lines.append("")

    return "\n".join(lines).strip()


def make_weekly_message(events):
    if not events:
        return None

    lines = [
        "📅 <b>SPORT MONITOR – PŘÍŠTÍCH 7 DNÍ</b>",
        "",
    ]

    for event in events:
        lines.append(
            format_event(event)
        )
        lines.append("")

    return "\n".join(lines).strip()


# ============================================================
# TELEGRAM SEND
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN:
        print("Telegram: chybí TELEGRAM_BOT_TOKEN.")
        return False

    if not TELEGRAM_CHAT_ID:
        print("Telegram: chybí TELEGRAM_CHAT_ID.")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = session.post(
            url,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        print("Telegram: zpráva odeslána.")

        return True

    except Exception as exc:
        print(f"Telegram chyba: {exc}")
        return False


# ============================================================
# STATE
# ============================================================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "events": {},
            "last_run": None,
        }

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception as exc:
        print(f"State: chyba načtení: {exc}")

        return {
            "events": {},
            "last_run": None,
        }


def save_state(state):
    os.makedirs(
        os.path.dirname(STATE_FILE),
        exist_ok=True,
    )

    try:
        with open(
            STATE_FILE,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                state,
                file,
                ensure_ascii=False,
                indent=2,
            )

        print(f"State uložen: {STATE_FILE}")

    except Exception as exc:
        print(f"State: chyba uložení: {exc}")


def update_state(state, events):
    for event in events:
        state["events"][event_key(event).__repr__()] = event

    state["last_run"] = datetime.now(
        TIMEZONE
    ).isoformat()

    return state


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 38)
    print("SPORT MONITOR")
    print("=" * 38)

    mode = "daily"

    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()

    if mode not in ("daily", "weekly"):
        print(
            f"Neznámý režim: {mode}"
        )
        print(
            "Použij: daily nebo weekly"
        )
        sys.exit(1)

    now = datetime.now(TIMEZONE)

    print(f"Režim: {mode}")
    print(
        f"Čas: {now.isoformat()}"
    )

    print("Konfigurace:")
    print(
        json.dumps(
            CONFIG,
            ensure_ascii=False,
            indent=2,
        )
    )

    # --------------------------------------------------------
    # SBĚR UDÁLOSTÍ
    # --------------------------------------------------------

    all_events = []

    if CONFIG["dynamo_pardubice"]:
        all_events.extend(
            parse_dynamo()
        )

    if CONFIG["diamond_league"]:
        all_events.extend(
            parse_athletics()
        )

    if CONFIG["biathlon"]:
        all_events.extend(
            parse_biathlon()
        )

    if CONFIG["world_hockey_championship"]:
        all_events.extend(
            parse_world_hockey()
        )

    # --------------------------------------------------------
    # DEDUPLIKACE
    # --------------------------------------------------------

    unique_events = {}

    for event in all_events:
        unique_events[event_key(event)] = event

    all_events = list(
        unique_events.values()
    )

    all_events.sort(
        key=lambda x: x["date"]
    )

    # --------------------------------------------------------
    # DAILY / WEEKLY FILTER
    # --------------------------------------------------------

    relevant_events = filter_events(
        all_events,
        mode,
    )

    print(
        f"Relevantních událostí: "
        f"{len(relevant_events)}"
    )

    if not relevant_events:
        print(
            "Žádné relevantní události."
        )
        print(
            "Telegram se neposílá."
        )

        # Přesto uložíme state
        state = load_state()
        state = update_state(
            state,
            all_events,
        )
        save_state(state)

        return

    # --------------------------------------------------------
    # TV VERIFIKACE
    # --------------------------------------------------------

    print()
    print(
        "======================================"
    )
    print(
        "TV VERIFIKACE RELEVANTNÍCH UDÁLOSTÍ"
    )
    print(
        "======================================"
    )

    verified_events = []

    for event in relevant_events:
        verified_event = verify_tv_broadcast(
            event
        )

        verified_events.append(
            verified_event
        )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    if mode == "weekly":
        message = make_weekly_message(
            verified_events
        )
    else:
        message = make_daily_message(
            verified_events
        )

    if message:
        print()
        print(
            "======================================"
        )
        print("TELEGRAM MESSAGE")
        print(
            "======================================"
        )
        print(message)
        print(
            "======================================"
        )

        send_telegram(message)

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    state = load_state()

    state = update_state(
        state,
        all_events,
    )

    # TV informace relevantních událostí
    for event in verified_events:
        key = event_key(event).__repr__()

        state["events"][key] = event

    save_state(state)

    print()
    print(
        "Sport Monitor dokončen."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
