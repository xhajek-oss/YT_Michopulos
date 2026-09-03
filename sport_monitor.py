import os
import sys
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


# ============================================================
# KONFIGURACE
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DYNAMO_URL = "https://www.hcdynamo.cz/matches/MUZ"

CONFIG = {
    "dynamo_pardubice": True,
    "diamond_league": True,
    "biathlon": True,
    "world_hockey_championship": False,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
    )
}

TIMEZONE = ZoneInfo("Europe/Prague")
REQUEST_TIMEOUT = 20

STATE_FILE = "data/sport_state.json"


# ============================================================
# POMOCNÉ FUNKCE
# ============================================================

def get_now():
    return datetime.now(TIMEZONE)


def clean_text(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_html(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.text

    except requests.RequestException as exc:
        print(f"Chyba při načítání {url}: {exc}")
        return ""


def parse_czech_datetime(text):
    if not text:
        return None

    text = clean_text(text)

    pattern = re.compile(
        r"(?:po|út|ut|st|čt|ct|pá|pa|so|ne)?\s*"
        r"(\d{1,2})\.\s*"
        r"(\d{1,2})\.\s*"
        r"(\d{4})"
        r"(?:\s*,)?\s*"
        r"(\d{1,2}):(\d{2})",
        re.IGNORECASE,
    )

    match = pattern.search(text)

    if not match:
        return None

    day, month, year, hour, minute = map(
        int,
        match.groups(),
    )

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


def normalize_team_name(name):
    if not name:
        return ""

    name = clean_text(name)

    name = re.sub(
        r"^(?:Image:\s*)?Logo\s+",
        "",
        name,
        flags=re.IGNORECASE,
    )

    name = re.sub(
        r"^Image:\s*",
        "",
        name,
        flags=re.IGNORECASE,
    )

    return clean_text(name)


# ============================================================
# SOUTĚŽ
# ============================================================

def detect_competition(container):
    """
    Soutěž hledáme pouze v konkrétním zápasovém bloku.
    Pokud ji tam nenajdeme, vrátíme bezpečnou hodnotu.
    """

    if container is None:
        return "Hokej"

    text = clean_text(
        container.get_text(" ", strip=True)
    ).lower()

    # Pořadí je důležité.
    # Specifičtější soutěže mají přednost.
    competitions = [
        (
            "red bulls salute",
            "Red Bulls Salute",
        ),
        (
            "přípravná utkání dynama a",
            "Přípravné utkání",
        ),
        (
            "přípravná utkání dynama",
            "Přípravné utkání",
        ),
        (
            "liga mistrů",
            "Liga Mistrů",
        ),
        (
            "tipsport extraliga",
            "Tipsport extraliga",
        ),
    ]

    for search_text, result in competitions:
        if search_text in text:
            return result

    return "Hokej"


# ============================================================
# DYNAMO – TÝMY
# ============================================================

def extract_team_names(container):
    teams = []

    if container is None:
        return teams

    for img in container.find_all("img"):
        original_alt = clean_text(
            img.get("alt", "")
        )

        alt = normalize_team_name(
            original_alt
        )

        if not alt:
            continue

        # Ignorujeme obecné obrázky.
        ignored = {
            "online",
            "reportáž",
            "vs",
            "logo",
        }

        if alt.lower() in ignored:
            continue

        # Na stránce Dynama jsou týmová loga
        # označena "Logo ...".
        is_team_logo = (
            "logo" in original_alt.lower()
        )

        if is_team_logo or "dynamo" in alt.lower():
            if alt not in teams:
                teams.append(alt)

    return teams


# ============================================================
# DYNAMO – KONTEJNER ZÁPASU
# ============================================================

def find_match_container(date_node):
    """
    Od konkrétního data stoupáme DOM stromem.
    Vybereme nejmenší rodičovský blok, který obsahuje
    datum, VS, Dynamo a soupeře.
    """

    current = date_node

    for _ in range(12):
        if current is None:
            break

        if not hasattr(current, "find_all"):
            current = getattr(
                current,
                "parent",
                None,
            )
            continue

        text = clean_text(
            current.get_text(
                " ",
                strip=True,
            )
        )

        teams = extract_team_names(
            current
        )

        has_vs = bool(
            re.search(
                r"\bVS\b",
                text,
                flags=re.IGNORECASE,
            )
        )

        has_dynamo = any(
            "dynamo" in team.lower()
            for team in teams
        )

        if (
            has_vs
            and has_dynamo
            and len(teams) >= 2
        ):
            return current

        current = current.parent

    return None


# ============================================================
# DYNAMO – PARSER
# ============================================================

def parse_dynamo_matches():
    print("=== DYNAMO PARDUBICE ===")
    print(f"Zdroj: {DYNAMO_URL}")

    html = fetch_html(
        DYNAMO_URL
    )

    if not html:
        print(
            "Dynamo: stránku se nepodařilo načíst."
        )
        return []

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    date_pattern = re.compile(
        r"(?:po|út|ut|st|čt|ct|pá|pa|so|ne)?"
        r"\s*\d{1,2}\.\s*"
        r"\d{1,2}\.\s*"
        r"\d{4}"
        r"\s*,?\s*"
        r"\d{1,2}:\d{2}",
        re.IGNORECASE,
    )

    date_nodes = list(
        soup.find_all(
            string=date_pattern
        )
    )

    print(
        f"Nalezených datumových bloků: "
        f"{len(date_nodes)}"
    )

    matches = []

    for date_node in date_nodes:
        date_text = clean_text(
            str(date_node)
        )

        match_datetime = parse_czech_datetime(
            date_text
        )

        if match_datetime is None:
            continue

        container = find_match_container(
            date_node
        )

        if container is None:
            continue

        teams = extract_team_names(
            container
        )

        if len(teams) < 2:
            continue

        # Dynamo musí být jeden z týmů.
        dynamo_index = None

        for index, team in enumerate(teams):
            if "dynamo" in team.lower():
                dynamo_index = index
                break

        if dynamo_index is None:
            continue

        opponent = None

        for index, team in enumerate(teams):
            if index != dynamo_index:
                opponent = team
                break

        if not opponent:
            continue

        # Přesné pořadí týmů podle HTML.
        home_team = teams[0]
        away_team = teams[1]

        competition = detect_competition(
            container
        )

        event = {
            "sport": "hokej",
            "date": match_datetime,
            "home": home_team,
            "away": away_team,
            "competition": competition,
            "source": DYNAMO_URL,
            "tv_confirmed": False,
            "tv_sources": [],
        }

        matches.append(event)

    # --------------------------------------------------------
    # DEDUPLIKACE
    # --------------------------------------------------------

    unique = {}

    for event in matches:
        key = (
            event["date"].isoformat(),
            event["home"],
            event["away"],
        )

        unique[key] = event

    matches = list(
        unique.values()
    )

    matches.sort(
        key=lambda event: event["date"]
    )

    print(
        f"Výsledných zápasů Dynamo: "
        f"{len(matches)}"
    )

    for event in matches:
        print(
            f'{event["date"].strftime("%Y-%m-%d %H:%M")} '
            f'{event["home"]} vs {event["away"]} '
            f'| {event["competition"]}'
        )

    return matches


# ============================================================
# ATLETIKA
# ============================================================

def parse_athletics():
    print("=== ATLETIKA ===")
    print(
        "Kategorie: Diamond League, ME/MS, "
        "halové ME/MS, významné české mítinky"
    )

    events = []

    print(
        "ČT Atletika načtena jako záložní zdroj."
    )
    print(
        f"Vybraných atletických událostí: "
        f"{len(events)}"
    )

    return events


# ============================================================
# BIATLON
# ============================================================

def parse_biathlon():
    print("=== BIATLON ===")

    events = []

    print(
        f"Celkem událostí: {len(events)}"
    )

    return events


# ============================================================
# TV OVĚŘENÍ
# ============================================================

def verify_tv_broadcast(event):
    print(
        f'TV ověření: '
        f'{event["home"]} vs {event["away"]}'
    )

    # TV ověřování necháváme jako samostatnou funkci.
    # Zápas samotný není závislý na nalezení TV zdroje.

    event["tv_confirmed"] = False
    event["tv_sources"] = []

    return event


def should_check_tv(event, mode, now):
    event_date = event["date"].date()

    if mode == "daily":
        return event_date == now.date()

    monday = (
        now.date()
        - timedelta(days=now.weekday())
    )

    sunday = monday + timedelta(days=6)

    return monday <= event_date <= sunday


# ============================================================
# FILTRACE
# ============================================================

def filter_events_for_mode(
    events,
    mode,
    now,
):
    if mode == "daily":
        return [
            event
            for event in events
            if event["date"].date()
            == now.date()
        ]

    if mode == "weekly":
        monday = (
            now.date()
            - timedelta(days=now.weekday())
        )

        sunday = monday + timedelta(days=6)

        return [
            event
            for event in events
            if monday
            <= event["date"].date()
            <= sunday
        ]

    return events


# ============================================================
# SBĚR VŠECH SPORTŮ
# ============================================================

def get_sport_events(
    config,
    mode,
    now,
):
    events = []

    # Dynamo
    if config.get(
        "dynamo_pardubice"
    ):
        dynamo_events = (
            parse_dynamo_matches()
        )

        for event in dynamo_events:
            if should_check_tv(
                event,
                mode,
                now,
            ):
                verify_tv_broadcast(
                    event
                )

        events.extend(
            dynamo_events
        )

    # Atletika
    if config.get(
        "diamond_league"
    ):
        events.extend(
            parse_athletics()
        )

    # Biatlon
    if config.get(
        "biathlon"
    ):
        events.extend(
            parse_biathlon()
        )

    # MS v hokeji
    if config.get(
        "world_hockey_championship"
    ):
        pass

    return events


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN:
        print(
            "Telegram: chybí "
            "TELEGRAM_BOT_TOKEN."
        )
        return False

    if not TELEGRAM_CHAT_ID:
        print(
            "Telegram: chybí "
            "TELEGRAM_CHAT_ID."
        )
        return False

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}"
        "/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )

        if response.ok:
            print(
                "Telegram: zpráva odeslána."
            )
            return True

        print(
            "Telegram chyba:",
            response.status_code,
            response.text,
        )

    except requests.RequestException as exc:
        print(
            f"Telegram chyba připojení: "
            f"{exc}"
        )

    return False


# ============================================================
# TELEGRAM HTML
# ============================================================

def escape_telegram_html(text):
    """
    Telegram HTML dovoluje pouze určité tagy.
    Tato funkce escapuje pouze skutečný obsah,
    ne naše vlastní HTML tagy.
    """

    if text is None:
        return ""

    text = str(text)

    text = text.replace(
        "&",
        "&amp;",
    )
    text = text.replace(
        "<",
        "&lt;",
    )
    text = text.replace(
        ">",
        "&gt;",
    )

    return text


def format_event(event):
    date_text = event["date"].strftime(
        "%d.%m.%Y %H:%M"
    )

    home = escape_telegram_html(
        event["home"]
    )

    away = escape_telegram_html(
        event["away"]
    )

    competition = escape_telegram_html(
        event.get(
            "competition",
            "Sport",
        )
    )

    lines = [
        f"🏆 <b>{competition}</b>",
        f"🏒 <b>{home}</b> – <b>{away}</b>",
        f"🕐 {date_text}",
    ]

    if event.get(
        "tv_confirmed"
    ):
        sources = event.get(
            "tv_sources",
            [],
        )

        if sources:
            safe_sources = [
                escape_telegram_html(
                    source
                )
                for source in sources
            ]

            lines.append(
                "📺 TV: "
                + ", ".join(
                    safe_sources
                )
            )
        else:
            lines.append(
                "📺 TV: potvrzeno"
            )

    else:
        lines.append(
            "📺 TV: zatím nepotvrzeno"
        )

    return "\n".join(lines)


def make_message(
    events,
    mode,
):
    if not events:
        return None

    if mode == "daily":
        header = (
            "📅 <b>SPORT MONITOR – DNES</b>"
        )
    else:
        header = (
            "📅 <b>SPORT MONITOR – TENTO TÝDEN</b>"
        )

    parts = [
        header,
        "",
    ]

    for event in events:
        parts.append(
            format_event(event)
        )
        parts.append("")

    return "\n".join(
        parts
    ).strip()


# ============================================================
# STATE
# ============================================================

def load_state():
    try:
        if not os.path.exists(
            STATE_FILE
        ):
            return {}

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception as exc:
        print(
            f"State: nepodařilo se "
            f"načíst: {exc}"
        )
        return {}


def save_state(state):
    try:
        directory = os.path.dirname(
            STATE_FILE
        )

        if directory:
            os.makedirs(
                directory,
                exist_ok=True,
            )

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

    except Exception as exc:
        print(
            f"State: nepodařilo se "
            f"uložit: {exc}"
        )


# ============================================================
# MAIN
# ============================================================

def main():
    print(
        "======================================"
    )
    print(
        "SPORT MONITOR"
    )
    print(
        "======================================"
    )

    mode = "daily"

    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()

    if mode not in {
        "daily",
        "weekly",
    }:
        print(
            f"Neznámý režim: {mode}"
        )
        print(
            "Použij: daily nebo weekly"
        )
        sys.exit(1)

    now = get_now()

    print(
        f"Režim: {mode}"
    )

    print(
        f"Čas: {now.isoformat()}"
    )

    print(
        "Konfigurace:"
    )

    print(
        json.dumps(
            CONFIG,
            ensure_ascii=False,
            indent=2,
        )
    )

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    all_events = get_sport_events(
        CONFIG,
        mode,
        now,
    )

    # --------------------------------------------------------
    # RELEVANTNÍ UDÁLOSTI
    # --------------------------------------------------------

    relevant_events = (
        filter_events_for_mode(
            all_events,
            mode,
            now,
        )
    )

    relevant_events.sort(
        key=lambda event:
        event["date"]
    )

    print(
        f"Relevantních událostí: "
        f"{len(relevant_events)}"
    )

    for event in relevant_events:
        print(
            f'{event["date"].strftime("%Y-%m-%d %H:%M")} '
            f'{event["home"]} vs '
            f'{event["away"]}'
        )

    # --------------------------------------------------------
    # ZPRÁVA
    # --------------------------------------------------------

    message = make_message(
        relevant_events,
        mode,
    )

    if not message:
        print(
            "Žádné relevantní události."
        )
        print(
            "Telegram se neposílá."
        )

        save_state({
            "last_run": now.isoformat(),
            "mode": mode,
            "events": [],
        })

        return

    print(
        "======================================"
    )

    print(
        "GENEROVANÁ ZPRÁVA"
    )

    print(
        "======================================"
    )

    print(message)

    print(
        "======================================"
    )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    send_telegram(
        message
    )

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    state_events = []

    for event in relevant_events:
        state_events.append({
            "date": event[
                "date"
            ].isoformat(),

            "sport": event.get(
                "sport",
                "",
            ),

            "home": event[
                "home"
            ],

            "away": event[
                "away"
            ],

            "competition": event.get(
                "competition",
                "",
            ),

            "tv_confirmed": event.get(
                "tv_confirmed",
                False,
            ),
        })

    save_state({
        "last_run": now.isoformat(),
        "mode": mode,
        "events": state_events,
    })


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
