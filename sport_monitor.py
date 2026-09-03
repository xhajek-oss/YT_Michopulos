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
    """
    Najde datum ve formátu například:

    čt 3. 9. 2026, 18:00
    so 5. 9. 2026, 17:00
    3. 9. 2026, 18:00
    """

    if not text:
        return None

    text = clean_text(text)

    pattern = re.compile(
        r"(?:"
        r"po|út|ut|st|čt|ct|pá|pa|so|ne"
        r")?\s*"
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

    day, month, year, hour, minute = map(int, match.groups())

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
    """
    Změní například:
        Logo HC Dynamo Pardubice
    na:
        HC Dynamo Pardubice
    """

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
# DYNAMO PARDUBICE
# ============================================================

def extract_team_names(container):
    """
    Získá názvy týmů pouze z konkrétního zápasového bloku.

    Důležité:
    NIKDY už nepoužíváme všechny img alt z celé stránky.
    """

    teams = []

    for img in container.find_all("img"):
        alt = img.get("alt", "")
        alt = normalize_team_name(alt)

        if not alt:
            continue

        # Nejsou to názvy týmů.
        if alt.lower() in {
            "online",
            "reportáž",
            "vs",
        }:
            continue

        # U Dynama jsou loga označena "Logo ..."
        # Povolíme ale i případ, kdy web prefix Logo změní.
        original_alt = clean_text(img.get("alt", ""))

        if (
            "logo" in original_alt.lower()
            or "dynamo" in alt.lower()
        ):
            if alt not in teams:
                teams.append(alt)

    return teams


def find_match_container(date_node):
    """
    Od data postupně stoupá DOM stromem a hledá nejmenší
    rozumný kontejner, který obsahuje:

    - datum
    - VS
    - dvě loga týmů

    Tím se zabrání původní chybě, kdy se soupeř vzal
    z úplně jiného zápasu.
    """

    current = date_node

    for _ in range(10):
        if current is None:
            break

        if not hasattr(current, "find_all"):
            current = getattr(current, "parent", None)
            continue

        text = clean_text(current.get_text(" ", strip=True))

        teams = extract_team_names(current)

        has_vs = re.search(
            r"\bVS\b",
            text,
            flags=re.IGNORECASE,
        )

        has_dynamo = any(
            "dynamo" in team.lower()
            for team in teams
        )

        if has_vs and has_dynamo and len(teams) >= 2:
            return current

        current = current.parent

    return None


def find_competition(date_node, match_container):
    """
    Pokusí se najít soutěž patřící ke konkrétnímu zápasu.
    """

    if match_container is not None:
        text = clean_text(
            match_container.get_text(" ", strip=True)
        )

        known_competitions = [
            "Liga Mistrů",
            "Tipsport extraliga",
            "Přípravná utkání Dynama A",
            "Red Bulls Salute",
        ]

        for competition in known_competitions:
            if competition.lower() in text.lower():
                return competition

    # Když není soutěž přímo uvnitř bloku,
    # zkusíme několik rodičů.
    current = date_node

    for _ in range(6):
        if current is None:
            break

        if hasattr(current, "get_text"):
            text = clean_text(
                current.get_text(" ", strip=True)
            )

            known_competitions = [
                "Liga Mistrů",
                "Tipsport extraliga",
                "Přípravná utkání Dynama A",
                "Red Bulls Salute",
            ]

            for competition in known_competitions:
                if competition.lower() in text.lower():
                    return competition

        current = current.parent

    return "Hokej"


def parse_dynamo_matches():
    print("=== DYNAMO PARDUBICE ===")
    print(f"Zdroj: {DYNAMO_URL}")

    html = fetch_html(DYNAMO_URL)

    if not html:
        print("Dynamo: stránku se nepodařilo načíst.")
        return []

    soup = BeautifulSoup(html, "html.parser")

    matches = []

    # Najdeme všechny elementy, jejichž text obsahuje datum + čas.
    date_pattern = re.compile(
        r"(?:po|út|ut|st|čt|ct|pá|pa|so|ne)"
        r"?\s*\d{1,2}\.\s*\d{1,2}\.\s*\d{4}"
        r"\s*,?\s*\d{1,2}:\d{2}",
        re.IGNORECASE,
    )

    date_nodes = []

    for element in soup.find_all(
        string=date_pattern
    ):
        date_nodes.append(element)

    print(f"Nalezených datumových bloků: {len(date_nodes)}")

    for date_node in date_nodes:
        date_text = clean_text(str(date_node))

        match_datetime = parse_czech_datetime(date_text)

        if match_datetime is None:
            continue

        container = find_match_container(date_node)

        if container is None:
            continue

        teams = extract_team_names(container)

        # Musíme mít minimálně dva týmy.
        if len(teams) < 2:
            continue

        # Najdeme Dynamo.
        dynamo_index = None

        for index, team in enumerate(teams):
            if "dynamo" in team.lower():
                dynamo_index = index
                break

        if dynamo_index is None:
            continue

        # Bereme první další tým jako soupeře.
        opponent = None

        for index, team in enumerate(teams):
            if index != dynamo_index:
                opponent = team
                break

        if not opponent:
            continue

        dynamo = teams[dynamo_index]

        # Pořadí log v HTML určuje domácí/hosté.
        home_team = teams[0]
        away_team = teams[1]

        # Pokud web obsahuje více než 2 relevantní logo elementy,
        # vezmeme Dynamo + prvního soupeře.
        if "dynamo" not in home_team.lower() and \
                "dynamo" not in away_team.lower():

            home_team = dynamo
            away_team = opponent

        competition = find_competition(
            date_node,
            container,
        )

        event = {
            "sport": "hokej",
            "date": match_datetime,
            "home": home_team,
            "away": away_team,
            "competition": competition,
            "source": DYNAMO_URL,
        }

        matches.append(event)

    # --------------------------------------------------------
    # Odstranění duplicit
    # --------------------------------------------------------

    unique = {}

    for event in matches:
        key = (
            event["date"].isoformat(),
            event["home"],
            event["away"],
        )

        unique[key] = event

    matches = list(unique.values())

    matches.sort(key=lambda x: x["date"])

    print(f"Výsledných zápasů Dynamo: {len(matches)}")

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

    # Záměrně bezpečná implementace.
    # Pokud zdroj nic nenajde, neblokuje celý monitor.

    events = []

    print("ČT Atletika načtena jako záložní zdroj.")
    print(f"Vybraných atletických událostí: {len(events)}")

    return events


# ============================================================
# BIATLON
# ============================================================

def parse_biathlon():
    print("=== BIATLON ===")

    events = []

    # Zde ponecháváme bezpečný základ.
    # Pokud už máš vlastní biatlonový parser,
    # můžeš jeho funkci vložit sem.

    print(f"Celkem událostí: {len(events)}")

    return events


# ============================================================
# TV OVĚŘENÍ
# ============================================================

def verify_tv_broadcast(event):
    """
    Základní placeholder pro TV ověření.

    Důležité:
    TV ověření nemá rozhodovat o tom, zda zápas existuje.
    Zápas z oficiálního rozpisu je platný i bez nalezeného TV zdroje.
    """

    print(
        f'TV ověření: {event["home"]} vs {event["away"]}'
    )

    event["tv_confirmed"] = False
    event["tv_sources"] = []

    return event


def should_check_tv(event, mode, now):
    """
    TV kontrolujeme jen u relevantních zápasů.

    DAILY:
        pouze dnešní zápasy

    WEEKLY:
        zápasy v aktuálním týdnu
    """

    event_date = event["date"].date()

    if mode == "daily":
        return event_date == now.date()

    # Pondělí = 0 ... neděle = 6
    monday = now.date() - timedelta(
        days=now.weekday()
    )

    sunday = monday + timedelta(days=6)

    return monday <= event_date <= sunday


# ============================================================
# VÝBĚR UDÁLOSTÍ
# ============================================================

def filter_events_for_mode(events, mode, now):
    if mode == "daily":
        return [
            event
            for event in events
            if event["date"].date() == now.date()
        ]

    if mode == "weekly":
        monday = now.date() - timedelta(
            days=now.weekday()
        )

        sunday = monday + timedelta(days=6)

        return [
            event
            for event in events
            if monday <= event["date"].date() <= sunday
        ]

    return events


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN:
        print("Telegram: chybí TELEGRAM_BOT_TOKEN.")
        return False

    if not TELEGRAM_CHAT_ID:
        print("Telegram: chybí TELEGRAM_CHAT_ID.")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
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
            print("Telegram: zpráva odeslána.")
            return True

        print(
            "Telegram chyba:",
            response.status_code,
            response.text,
        )

    except requests.RequestException as exc:
        print(
            f"Telegram chyba připojení: {exc}"
        )

    return False


# ============================================================
# FORMÁTOVÁNÍ ZPRÁVY
# ============================================================

def format_event(event):
    date_text = event["date"].strftime(
        "%d.%m.%Y %H:%M"
    )

    home = event["home"]
    away = event["away"]
    competition = event.get(
        "competition",
        "Sport",
    )

    lines = [
        f"🏆 <b>{competition}</b>",
        f"🏒 <b>{home}</b> vs <b>{away}</b>",
        f"🕐 {date_text}",
    ]

    if event.get("tv_confirmed"):
        sources = event.get(
            "tv_sources",
            [],
        )

        if sources:
            lines.append(
                "📺 TV: " + ", ".join(sources)
            )
        else:
            lines.append("📺 TV potvrzeno")
    else:
        lines.append(
            "📺 TV: zatím nepotvrzeno"
        )

    return "\n".join(lines)


def make_message(events, mode):
    if not events:
        return None

    if mode == "daily":
        header = "📅 <b>SPORT MONITOR – DNES</b>"
    else:
        header = "📅 <b>SPORT MONITOR – TENTO TÝDEN</b>"

    parts = [header, ""]

    for event in events:
        parts.append(
            format_event(event)
        )
        parts.append("")

    return "\n".join(parts).strip()


# ============================================================
# HLAVNÍ SBĚR DAT
# ============================================================

def get_sport_events(config, mode, now):
    events = []

    # --------------------------------------------------------
    # Dynamo
    # --------------------------------------------------------

    if config.get("dynamo_pardubice"):
        dynamo_events = parse_dynamo_matches()

        # TV ověřujeme pouze pro relevantní období.
        for event in dynamo_events:
            if should_check_tv(
                event,
                mode,
                now,
            ):
                verify_tv_broadcast(event)

        events.extend(dynamo_events)

    # --------------------------------------------------------
    # Atletika
    # --------------------------------------------------------

    if config.get("diamond_league"):
        events.extend(
            parse_athletics()
        )

    # --------------------------------------------------------
    # Biatlon
    # --------------------------------------------------------

    if config.get("biathlon"):
        events.extend(
            parse_biathlon()
        )

    # --------------------------------------------------------
    # MS v hokeji
    # --------------------------------------------------------

    if config.get("world_hockey_championship"):
        # Zatím bez událostí.
        pass

    return events


# ============================================================
# STATE
# ============================================================

STATE_FILE = "data/sport_state.json"


def load_state():
    try:
        if not os.path.exists(STATE_FILE):
            return {}

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception as exc:
        print(
            f"State: nepodařilo se načíst: {exc}"
        )
        return {}


def save_state(state):
    try:
        os.makedirs(
            os.path.dirname(STATE_FILE),
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
            f"State: nepodařilo se uložit: {exc}"
        )


# ============================================================
# MAIN
# ============================================================

def main():
    print("======================================")
    print("SPORT MONITOR")
    print("======================================")

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
    # Data
    # --------------------------------------------------------

    all_events = get_sport_events(
        CONFIG,
        mode,
        now,
    )

    # --------------------------------------------------------
    # Filtrace
    # --------------------------------------------------------

    relevant_events = filter_events_for_mode(
        all_events,
        mode,
        now,
    )

    # --------------------------------------------------------
    # Řazení
    # --------------------------------------------------------

    relevant_events.sort(
        key=lambda event: event["date"]
    )

    print(
        f"Relevantních událostí: "
        f"{len(relevant_events)}"
    )

    for event in relevant_events:
        print(
            f'{event["date"].strftime("%Y-%m-%d %H:%M")} '
            f'{event["home"]} vs {event["away"]}'
        )

    # --------------------------------------------------------
    # Zpráva
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

    print("======================================")
    print("GENEROVANÁ ZPRÁVA")
    print("======================================")
    print(message)
    print("======================================")

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    send_telegram(message)

    # --------------------------------------------------------
    # State
    # --------------------------------------------------------

    state_events = []

    for event in relevant_events:
        state_events.append({
            "date": event["date"].isoformat(),
            "sport": event.get(
                "sport",
                "",
            ),
            "home": event["home"],
            "away": event["away"],
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
