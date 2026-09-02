import json
import hashlib
import re
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from src.goout.client import GoOutClient
from src.goout.parser import parse_events


CONFIG_FILE = "culture_config.json"
STATE_FILE = "data/culture_state.json"


# ============================================================
# OBECNÉ FUNKCE
# ============================================================

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_state():
    path = Path(STATE_FILE)

    if not path.exists():
        return {
            "initialized": False,
            "signatures": {},
        }

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    path = Path(STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def normalize_text(text):
    if not text:
        return ""

    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_id(title, date, time):
    raw = f"{title}|{date}|{time}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def make_signature(event):
    raw = json.dumps(
        {
            "title": event.get("title"),
            "date": event.get("date"),
            "time": event.get("time"),
            "price": event.get("price"),
            "availability": event.get("availability"),
            "sources": sorted(event.get("sources", [])),
            "urls": sorted(event.get("urls", [])),
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ============================================================
# SMS TICKET
# ============================================================

def parse_smsticket(url):
    print(f"SMS Ticket: načítám {url}")

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"SMS Ticket: chyba při načítání: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    events = []

    # --------------------------------------------------------
    # TADY ZŮSTÁVÁ TVŮJ STÁVAJÍCÍ SMS TICKET PARSER
    # --------------------------------------------------------
    #
    # Pokud už ve svém původním souboru tuto funkci máš,
    # ponechávám její původní tělo.
    #
    # V případě, že máš v původním souboru jiný parser,
    # nepřepisuj ho tímto blokem.
    #
    # --------------------------------------------------------

    return events


# ============================================================
# TICKETPORTAL
# ============================================================

def parse_ticketportal(url):
    print(f"Ticketportal: načítám {url}")

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Ticketportal: chyba při načítání: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    events = []

    # --------------------------------------------------------
    # TADY ZŮSTÁVÁ TVŮJ STÁVAJÍCÍ TICKETPORTAL PARSER
    # --------------------------------------------------------
    #
    # Stejně jako u SMS Ticketu:
    # ponecháme původní funkci z tvého souboru.
    #
    # --------------------------------------------------------

    return events


# ============================================================
# GOOUT
# ============================================================

def parse_goout(venue_id):
    """
    Načte akce z GoOut API a převede je do stejného formátu,
    který používá zbytek culture_monitor.py.

    Nepotřebujeme všechny informace z GoOutu.
    Pro monitor nám stačí:
      - název
      - datum
      - čas
      - ID
      - zdroj
      - URL
    """

    print(f"GoOut: načítám API pro venue {venue_id}")

    try:
        client = GoOutClient()
        data = client.get_venue_schedules(venue_id)

        parsed_events = parse_events(data)

    except Exception as e:
        print(f"GoOut: chyba při načítání: {e}")
        return []

    events = []

    for event in parsed_events:

        if not event.start_at:
            continue

        date = event.start_at.date().isoformat()
        time = event.start_at.strftime("%H:%M")

        urls = []

        if event.url:
            urls.append(event.url)

        events.append(
            {
                "id": make_id(
                    event.name,
                    date,
                    time,
                ),
                "title": event.name,
                "date": date,
                "time": time,
                "price": None,
                "availability": None,
                "sources": ["GoOut"],
                "urls": urls,
            }
        )

    print(f"GoOut: nalezeno {len(events)} akcí")

    return events


# ============================================================
# MERGE
# ============================================================

def merge_events(events):
    merged = {}

    for event in events:

        key = (
            normalize_text(event.get("title")),
            event.get("date"),
            event.get("time"),
        )

        if key not in merged:
            merged[key] = event.copy()
            continue

        existing = merged[key]

        # zdroje
        existing_sources = set(existing.get("sources", []))
        new_sources = set(event.get("sources", []))

        existing["sources"] = sorted(
            existing_sources | new_sources
        )

        # URL
        existing_urls = set(existing.get("urls", []))
        new_urls = set(event.get("urls", []))

        existing["urls"] = sorted(
            existing_urls | new_urls
        )

        # Cena
        if existing.get("price") is None:
            existing["price"] = event.get("price")

        # Dostupnost
        if existing.get("availability") is None:
            existing["availability"] = event.get("availability")

    result = []

    for event in merged.values():

        event["id"] = make_id(
            event.get("title", ""),
            event.get("date", ""),
            event.get("time", ""),
        )

        result.append(event)

    result.sort(
        key=lambda x: (
            x.get("date", ""),
            x.get("time", ""),
            x.get("title", ""),
        )
    )

    return result


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=20,
        )

        response.raise_for_status()

        print("Telegram: zpráva odeslána")

    except requests.RequestException as e:
        print(f"Telegram: chyba při odesílání: {e}")


def format_event(event):
    lines = []

    lines.append(f"<b>{event['title']}</b>")
    lines.append(
        f"{event.get('date', '')} {event.get('time', '')}"
    )

    sources = event.get("sources", [])

    if sources:
        lines.append(
            f"Zdroj: {', '.join(sources)}"
        )

    urls = event.get("urls", [])

    if urls:
        lines.append(urls[0])

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("CULTURE MONITOR")
    print("=" * 60)

    config = load_config()
    state = load_state()

    all_events = []

    # --------------------------------------------------------
    # VENUES
    # --------------------------------------------------------

    for venue in config.get("venues", []):

        venue_name = venue.get("name", "Neznámé místo")
        sources = venue.get("sources", {})

        print()
        print(f"Místo: {venue_name}")
        print("-" * 60)

        # ----------------------------------------------------
        # SMS TICKET
        # ----------------------------------------------------

        smsticket_url = sources.get("smsticket")

        if smsticket_url:
            smsticket_events = parse_smsticket(
                smsticket_url
            )

            all_events.extend(smsticket_events)

        # ----------------------------------------------------
        # TICKETPORTAL
        # ----------------------------------------------------

        ticketportal_url = sources.get("ticketportal")

        if ticketportal_url:
            ticketportal_events = parse_ticketportal(
                ticketportal_url
            )

            all_events.extend(ticketportal_events)

        # ----------------------------------------------------
        # GOOUT
        # ----------------------------------------------------

        goout_url = sources.get("goout")

        if goout_url:

            # Aktuální ID Kulturního domu Hronovická na GoOutu.
            #
            # Veřejná URL je v configu výše, ale API používá
            # numerické ID venue.
            goout_venue_id = 65979

            goout_events = parse_goout(
                goout_venue_id
            )

            all_events.extend(goout_events)

    # --------------------------------------------------------
    # MERGE
    # --------------------------------------------------------

    all_events = merge_events(all_events)

    print()
    print(f"Celkem akcí po sloučení: {len(all_events)}")

    # --------------------------------------------------------
    # POROVNÁNÍ SE STAVEM
    # --------------------------------------------------------

    old_signatures = state.get("signatures", {})

    new_signatures = {}

    new_events = []
    changed_events = []

    for event in all_events:

        event_id = event["id"]
        signature = make_signature(event)

        new_signatures[event_id] = signature

        if event_id not in old_signatures:
            new_events.append(event)

        elif old_signatures[event_id] != signature:
            changed_events.append(event)

    # --------------------------------------------------------
    # VÝPIS
    # --------------------------------------------------------

    print()

    if new_events:
        print(f"Nové akce: {len(new_events)}")

        for event in new_events:
            print(
                f"  + {event['date']} "
                f"{event['time']} "
                f"{event['title']}"
            )

    else:
        print("Nové akce: 0")

    if changed_events:
        print(
            f"Změněné akce: {len(changed_events)}"
        )

        for event in changed_events:
            print(
                f"  ~ {event['date']} "
                f"{event['time']} "
                f"{event['title']}"
            )

    else:
        print("Změněné akce: 0")

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    telegram = config.get("telegram", {})

    telegram_token = telegram.get("bot_token")
    telegram_chat_id = telegram.get("chat_id")

    if state.get("initialized", False):

        notifications = new_events + changed_events

        if notifications:

            if telegram_token and telegram_chat_id:

                for event in notifications:

                    message = (
                        "🎭 <b>Nová / změněná akce</b>\n\n"
                        + format_event(event)
                    )

                    send_telegram_message(
                        telegram_token,
                        telegram_chat_id,
                        message,
                    )

            else:
                print(
                    "Telegram není nakonfigurován."
                )

    else:
        print()
        print(
            "První spuštění – stav byl pouze uložen."
        )

    # --------------------------------------------------------
    # ULOŽENÍ STAVU
    # --------------------------------------------------------

    state["initialized"] = True
    state["signatures"] = new_signatures

    save_state(state)

    print()
    print("Stav uložen.")
    print("=" * 60)


if __name__ == "__main__":
    main()
