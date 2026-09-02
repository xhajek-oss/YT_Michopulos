import json
import os
import re
import sys
import hashlib
from datetime import datetime, date, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


CONFIG_FILE = "culture_config.json"
STATE_FILE = "data/culture_state.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
}


CZECH_MONTHS = {
    "led": 1,
    "ún": 2,
    "bře": 3,
    "dub": 4,
    "kvě": 5,
    "čvn": 6,
    "čvc": 7,
    "srp": 8,
    "zář": 9,
    "říj": 10,
    "lis": 11,
    "pro": 12,
}


def load_json(path, default):
    if not os.path.exists(path):
        return default

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_text(value):
    if not value:
        return ""

    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_title(value):
    value = normalize_text(value)

    value = value.replace("…", "...")
    value = re.sub(r"\s+", " ", value)

    return value.lower()


def parse_czech_date(value):
    if not value:
        return None

    value = normalize_text(value)

    # 4. 10. 2026
    match = re.search(
        r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\b",
        value,
    )

    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))

        try:
            return date(year, month, day)
        except ValueError:
            return None

    # 4 Říj. 2026
    match = re.search(
        r"\b(\d{1,2})\s+"
        r"(Led\.|Ún\.|Bře\.|Dub\.|Kvě\.|Čvn\.|Čvc\.|Srp\.|"
        r"Zář\.|Říj\.|Lis\.|Pros\.)\s+"
        r"(\d{4})\b",
        value,
        re.IGNORECASE,
    )

    if match:
        day = int(match.group(1))
        month_text = match.group(2).lower().rstrip(".")
        year = int(match.group(3))

        month = CZECH_MONTHS.get(month_text)

        if month:
            try:
                return date(year, month, day)
            except ValueError:
                return None

    return None


def format_date(culture_date):
    return culture_date.strftime("%-d. %-m. %Y")


def format_short_date(culture_date):
    return culture_date.strftime("%-d. %-m.")


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    return response.text


def absolute_url(base_url, href):
    if not href:
        return None

    return urljoin(base_url, href)


def make_event_id(title, event_date, event_time):
    raw = "|".join(
        [
            normalize_title(title),
            event_date.isoformat() if event_date else "",
            event_time or "",
        ]
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def extract_time(text):
    if not text:
        return None

    match = re.search(
        r"\b(\d{1,2}:\d{2})\b",
        text,
    )

    if not match:
        return None

    hour, minute = match.group(1).split(":")

    return f"{int(hour):02d}:{minute}"


def extract_price(text):
    if not text:
        return None

    match = re.search(
        r"(\d[\d\s]*)\s*Kč",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    number = re.sub(r"\s+", " ", match.group(1)).strip()

    return f"{number} Kč"


def parse_sms_ticket(html, source_url):
    soup = BeautifulSoup(html, "html.parser")

    events = []

    # SMS Ticket používá odkazy na /vstupenky/...
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        if "/vstupenky/" not in href:
            continue

        title = normalize_text(link.get_text(" ", strip=True))

        if not title:
            continue

        # Hledáme informační blok kolem konkrétní akce.
        current = link
        block_text = ""

        for _ in range(5):
            if current is None:
                break

            candidate = normalize_text(
                current.get_text(" ", strip=True)
            )

            if len(candidate) > len(block_text):
                block_text = candidate

            current = current.parent

        event_date = parse_czech_date(block_text)
        event_time = extract_time(block_text)
        price = extract_price(block_text)

        if not event_date:
            continue

        event_url = absolute_url(source_url, href)

        event_id = make_event_id(
            title,
            event_date,
            event_time,
        )

        events.append(
            {
                "id": event_id,
                "title": title,
                "date": event_date.isoformat(),
                "time": event_time,
                "price": price,
                "availability": "V prodeji",
                "source": "SMS Ticket",
                "url": event_url,
            }
        )

    return deduplicate_events(events)


def parse_ticketportal(html, source_url):
    soup = BeautifulSoup(html, "html.parser")

    events = []

    # Skutečné Ticketportal akce mají URL /Event/...
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        if not re.search(r"/Event/", href, re.IGNORECASE):
            continue

        title = normalize_text(link.get_text(" ", strip=True))

        if not title:
            continue

        # Hledáme nejbližší rozumný blok s údaji o akci.
        current = link
        block_text = ""

        for _ in range(6):
            if current is None:
                break

            candidate = normalize_text(
                current.get_text(" ", strip=True)
            )

            if len(candidate) > len(block_text):
                block_text = candidate

            current = current.parent

        event_date = parse_czech_date(block_text)
        event_time = extract_time(block_text)

        if not event_date:
            continue

        lower_block = block_text.lower()

        if "vyprodáno" in lower_block:
            availability = "Vyprodáno"
        elif "koupit" in lower_block:
            availability = "V prodeji"
        else:
            availability = "V prodeji"

        event_url = absolute_url(source_url, href)

        event_id = make_event_id(
            title,
            event_date,
            event_time,
        )

        events.append(
            {
                "id": event_id,
                "title": title,
                "date": event_date.isoformat(),
                "time": event_time,
                "price": None,
                "availability": availability,
                "source": "Ticketportal",
                "url": event_url,
            }
        )

    return deduplicate_events(events)


def deduplicate_events(events):
    unique = {}

    for event in events:
        key = (
            normalize_title(event["title"]),
            event["date"],
            event["time"],
        )

        # Pokud máme stejnou akci vícekrát,
        # ponecháme první záznam.
        if key not in unique:
            unique[key] = event
        else:
            existing = unique[key]

            # Pokud první záznam nemá cenu a druhý ji má,
            # doplníme cenu.
            if not existing.get("price") and event.get("price"):
                existing["price"] = event["price"]

    return list(unique.values())


def merge_sources(events):
    """
    Sloučí stejnou akci z více zdrojů.

    Klíč:
    název + datum + čas

    Výsledkem je jedna položka s více zdroji.
    """

    merged = {}

    for event in events:
        key = (
            normalize_title(event["title"]),
            event["date"],
            event["time"],
        )

        if key not in merged:
            merged[key] = {
                "id": event["id"],
                "title": event["title"],
                "date": event["date"],
                "time": event["time"],
                "price": event.get("price"),
                "availability": event.get("availability"),
                "sources": [],
                "urls": [],
            }

        item = merged[key]

        source = event.get("source")
        url = event.get("url")

        if source and source not in item["sources"]:
            item["sources"].append(source)

        if url and url not in item["urls"]:
            item["urls"].append(url)

        if not item.get("price") and event.get("price"):
            item["price"] = event["price"]

        # Pokud je některý zdroj vyprodán,
        # ale jiný stále prodává, necháme "V prodeji".
        if event.get("availability") == "V prodeji":
            item["availability"] = "V prodeji"

        elif (
            not item.get("availability")
            and event.get("availability")
        ):
            item["availability"] = event["availability"]

    return list(merged.values())


def fetch_all_events(config):
    all_events = []

    for venue in config.get("venues", []):
        sources = venue.get("sources", {})

        # SMS Ticket
        sms_url = sources.get("smsticket")

        if sms_url:
            try:
                print(f"Načítám SMS Ticket: {sms_url}")

                html = get_page(sms_url)

                events = parse_sms_ticket(
                    html,
                    sms_url,
                )

                print(
                    f"SMS Ticket: nalezeno {len(events)} akcí"
                )

                all_events.extend(events)

            except Exception as exc:
                print(
                    f"SMS Ticket CHYBA: {repr(exc)}"
                )

        # Ticketportal
        ticketportal_url = sources.get("ticketportal")

        if ticketportal_url:
            try:
                print(
                    f"Načítám Ticketportal: "
                    f"{ticketportal_url}"
                )

                html = get_page(ticketportal_url)

                events = parse_ticketportal(
                    html,
                    ticketportal_url,
                )

                print(
                    f"Ticketportal: nalezeno "
                    f"{len(events)} akcí"
                )

                all_events.extend(events)

            except Exception as exc:
                print(
                    f"Ticketportal CHYBA: {repr(exc)}"
                )

        # GoOut zatím pouze kontrolujeme.
        goout_url = sources.get("goout")

        if goout_url:
            try:
                html = get_page(goout_url)

                soup = BeautifulSoup(
                    html,
                    "html.parser",
                )

                text = soup.get_text(
                    " ",
                    strip=True,
                )

                if "Načítám" in text:
                    print(
                        "GoOut: JS-only stránka, "
                        "akce zatím neparsujeme."
                    )
                else:
                    print(
                        "GoOut: stránka obsahuje HTML data, "
                        "ale zatím ji nepoužíváme jako zdroj."
                    )

            except Exception as exc:
                print(
                    f"GoOut CHYBA: {repr(exc)}"
                )

    return merge_sources(all_events)


def event_datetime(event):
    event_date = date.fromisoformat(event["date"])

    if event.get("time"):
        hour, minute = event["time"].split(":")

        return datetime(
            event_date.year,
            event_date.month,
            event_date.day,
            int(hour),
            int(minute),
        )

    return datetime(
        event_date.year,
        event_date.month,
        event_date.day,
    )


def get_daily_range(today):
    return today, today


def get_weekly_range(today):
    monday = today - timedelta(
        days=today.weekday()
    )

    sunday = monday + timedelta(days=6)

    return monday, sunday


def filter_events_by_range(events, start_date, end_date):
    result = []

    for event in events:
        event_date = date.fromisoformat(
            event["date"]
        )

        if start_date <= event_date <= end_date:
            result.append(event)

    result.sort(
        key=lambda e: (
            e["date"],
            e.get("time") or "99:99",
            normalize_title(e["title"]),
        )
    )

    return result


def event_signature(event):
    """
    Signatura používaná pro historii.

    Změna dostupnosti nebo ceny může způsobit
    novou signaturu a tím upozornění.
    """

    raw = json.dumps(
        {
            "title": event["title"],
            "date": event["date"],
            "time": event["time"],
            "price": event["price"],
            "availability": event["availability"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def format_event(event):
    event_date = date.fromisoformat(
        event["date"]
    )

    lines = []

    if event.get("time"):
        lines.append(
            f"📅 {format_date(event_date)} | "
            f"{event['time']}"
        )
    else:
        lines.append(
            f"📅 {format_date(event_date)}"
        )

    lines.append(event["title"])

    if event.get("price"):
        lines.append(
            f"🎟️ {event['price']}"
        )

    if event.get("availability"):
        if event["availability"] == "V prodeji":
            lines.append("🟢 V prodeji")
        elif event["availability"] == "Vyprodáno":
            lines.append("🔴 Vyprodáno")
        else:
            lines.append(
                f"ℹ️ {event['availability']}"
            )

    if event.get("sources"):
        lines.append(
            "🌐 " + ", ".join(event["sources"])
        )

    if event.get("urls"):
        lines.append(event["urls"][0])

    return "\n".join(lines)


def build_message(events, mode, today):
    if mode == "daily":
        title = (
            f"🎭 KULTURA – "
            f"{today.strftime('%A')}"
        )

        # České názvy dnů.
        weekdays = {
            0: "pondělí",
            1: "úterý",
            2: "středa",
            3: "čtvrtek",
            4: "pátek",
            5: "sobota",
            6: "neděle",
        }

        title = (
            f"🎭 KULTURA – "
            f"{weekdays[today.weekday()]} "
            f"{format_date(today)}"
        )

    else:
        start_date, end_date = get_weekly_range(today)

        title = (
            f"🎭 KULTURA – "
            f"{format_date(start_date)}–"
            f"{format_date(end_date)}"
        )

    blocks = [title, ""]

    for event in events:
        blocks.append(format_event(event))
        blocks.append("")

    return "\n".join(blocks).strip()


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "Chybí TELEGRAM_BOT_TOKEN."
        )

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "Chybí TELEGRAM_CHAT_ID."
        )

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    response.raise_for_status()


def update_history(state, events):
    signatures = state.setdefault(
        "signatures",
        {},
    )

    for event in events:
        signatures[event["id"]] = {
            "signature": event_signature(event),
            "event": event,
            "updated_at": datetime.now().isoformat(),
        }

    # Historii necháme maximálně 1000 položek.
    if len(signatures) > 1000:
        items = sorted(
            signatures.items(),
            key=lambda x: x[1].get(
                "updated_at",
                "",
            ),
        )

        signatures = dict(
            items[-1000:]
        )

        state["signatures"] = signatures


def find_new_or_changed_events(state, events):
    result = []

    signatures = state.get(
        "signatures",
        {},
    )

    for event in events:
        old = signatures.get(event["id"])

        if not old:
            result.append(event)
            continue

        old_signature = old.get("signature")
        new_signature = event_signature(event)

        if old_signature != new_signature:
            result.append(event)

    return result


def main():
    mode = "daily"

    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()

    if mode not in ("daily", "weekly"):
        print(
            "Použití: python culture_monitor.py "
            "[daily|weekly]"
        )
        sys.exit(1)

    print("=" * 70)
    print("KULTURA MONITOR – KD HRONOVICKÁ")
    print("=" * 70)
    print(f"Režim: {mode}")
    print()

    config = load_json(
        CONFIG_FILE,
        {"venues": []},
    )

    state_exists = os.path.exists(
        STATE_FILE
    )

    state = load_json(
        STATE_FILE,
        {
            "initialized": False,
            "signatures": {},
        },
    )

    today = date.today()

    print(
        f"Dnes: {format_date(today)}"
    )

    events = fetch_all_events(config)

    print()
    print(
        f"Celkem po sloučení zdrojů: "
        f"{len(events)} akcí"
    )

    # Historii aktualizujeme ze všech nalezených akcí,
    # nejen z aktuálního dne/týdne.
    new_or_changed = find_new_or_changed_events(
        state,
        events,
    )

    if not state_exists or not state.get(
        "initialized",
        False,
    ):
        print()
        print(
            "PRVNÍ SPUŠTĚNÍ – ukládám aktuální stav."
        )

        update_history(
            state,
            events,
        )

        state["initialized"] = True
        state["last_run"] = datetime.now().isoformat()

        save_json(
            STATE_FILE,
            state,
        )

        print(
            "Telegram nebude odeslán."
        )

        return

    if mode == "daily":
        start_date, end_date = get_daily_range(
            today
        )
    else:
        start_date, end_date = get_weekly_range(
            today
        )

    period_events = filter_events_by_range(
        events,
        start_date,
        end_date,
    )

    changed_in_period = []

    changed_ids = {
        event["id"]
        for event in new_or_changed
    }

    for event in period_events:
        if event["id"] in changed_ids:
            changed_in_period.append(event)

    print()
    print(
        f"Akce v období: "
        f"{len(period_events)}"
    )

    print(
        f"Nové nebo změněné v období: "
        f"{len(changed_in_period)}"
    )

    # Aktualizujeme historii vždy.
    update_history(
        state,
        events,
    )

    state["last_run"] = datetime.now().isoformat()

    save_json(
        STATE_FILE,
        state,
    )

    # Telegram pouze pokud máme něco nového / změněného
    # v aktuálním období.
    if not changed_in_period:
        print()
        print(
            "Žádná nová ani změněná akce "
            "v aktuálním období."
        )
        print(
            "Telegram nebude odeslán."
        )

        return

    message = build_message(
        changed_in_period,
        mode,
        today,
    )

    print()
    print("=" * 70)
    print("TELEGRAM ZPRÁVA")
    print("=" * 70)
    print()
    print(message)

    send_telegram(message)

    print()
    print("Telegram odeslán.")


if __name__ == "__main__":
    main()
