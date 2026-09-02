import os
import sys
import json
import hashlib
import re
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
        "Chrome/128.0 Safari/537.36"
    )
}


GENERIC_TITLES = {
    "více informací",
    "koupit vstupenky",
    "vstupenky",
    "detail akce",
    "close",
    "galerie",
    "na mapě",
    "na mape",
    "top",
}


def load_json(path, default):
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Chyba při načítání JSON {path}: {e}")
        return default


def save_json(path, data):
    directory = os.path.dirname(path)

    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_text(text):
    if not text:
        return ""

    text = re.sub(r"\s+", " ", str(text))
    return text.strip()


def normalize_title_for_match(title):
    title = normalize_text(title).lower()

    title = title.replace("…", " ")
    title = title.replace("...", " ")

    title = re.sub(r"[^a-z0-9áčďéěíňóřšťúůýž ]", " ", title)
    title = re.sub(r"\s+", " ", title)

    return title.strip()


def make_id(title, event_date, event_time):
    raw = f"{title}|{event_date}|{event_time}".lower()

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:16]


def make_signature(event):
    relevant = {
        "title": event.get("title"),
        "date": event.get("date"),
        "time": event.get("time"),
        "price": event.get("price"),
        "availability": event.get("availability"),
        "sources": sorted(event.get("sources", [])),
        "urls": sorted(event.get("urls", [])),
    }

    raw = json.dumps(
        relevant,
        ensure_ascii=False,
        sort_keys=True,
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def parse_czech_date(text):
    if not text:
        return None

    text = normalize_text(text)

    patterns = [
        r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})",
        r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if not match:
            continue

        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))

        if year < 100:
            year += 2000

        try:
            return date(year, month, day)
        except ValueError:
            return None

    return None


def parse_time(text):
    if not text:
        return None

    match = re.search(
        r"\b([01]?\d|2[0-3]):([0-5]\d)\b",
        text,
    )

    if not match:
        return None

    return (
        f"{int(match.group(1)):02d}:"
        f"{match.group(2)}"
    )


def clean_title(title):
    if not title:
        return ""

    title = normalize_text(title)

    if title.lower() in GENERIC_TITLES:
        return ""

    return title


def title_from_sms_url(url):
    """
    Příklad:

    /vstupenky/67010-jiri-charvat-komik-ktery-neexistuje-kd-hronovicka-pardubice

    Výsledkem bude:

    JIRI CHARVAT KOMIK KTERY NEEXISTUJE
    """

    if not url:
        return ""

    match = re.search(
        r"/vstupenky/[^/]+-([^/?#]+)",
        url,
        flags=re.IGNORECASE,
    )

    if not match:
        return ""

    slug = match.group(1)

    slug = re.sub(
        r"-kd-hronovicka-pardubice$",
        "",
        slug,
        flags=re.IGNORECASE,
    )

    slug = slug.replace("-", " ")
    slug = normalize_text(slug)

    if not slug:
        return ""

    return slug.upper()


def extract_sms_title(link, block_text):
    """
    U SMS Ticketu je odkaz často pojmenovaný pouze
    „Více informací“.

    Proto:
    1. zkusíme text odkazu,
    2. atributy,
    3. název z URL,
    4. až nakonec okolní text.
    """

    candidates = []

    link_text = clean_title(
        link.get_text(" ", strip=True)
    )

    if link_text:
        candidates.append(link_text)

    for attr in [
        "title",
        "aria-label",
        "data-title",
    ]:
        value = clean_title(
            link.get(attr)
        )

        if value:
            candidates.append(value)

    url_title = title_from_sms_url(
        link.get("href", "")
    )

    if url_title:
        candidates.append(url_title)

    for candidate in candidates:
        if candidate.lower() not in GENERIC_TITLES:
            return candidate

    # Pokud nic jiného není, zkusíme z okolního
    # textu najít část před datem.
    if block_text:
        text = normalize_text(block_text)

        date_match = re.search(
            r"\d{1,2}\.\s*\d{1,2}\.\s*\d{4}",
            text,
        )

        if date_match:
            before_date = text[
                :date_match.start()
            ].strip()

            before_date = re.sub(
                r"^(více informací|koupit vstupenky)\s*",
                "",
                before_date,
                flags=re.IGNORECASE,
            )

            before_date = normalize_text(
                before_date
            )

            if (
                before_date
                and len(before_date) <= 120
                and before_date.lower()
                not in GENERIC_TITLES
            ):
                return before_date

    return ""


def find_event_container(element, max_levels=8):
    """
    Najde nejmenší rodičovský element, který
    pravděpodobně obsahuje celý event.

    Nevyžadujeme současně datum + čas.
    Stačí, když obsahuje datum nebo čas.
    """

    current = element

    for _ in range(max_levels):
        if current.parent is None:
            break

        text = normalize_text(
            current.get_text(" ", strip=True)
        )

        has_date = bool(
            re.search(
                r"\d{1,2}\.\s*\d{1,2}\.\s*\d{4}",
                text,
            )
        )

        has_time = bool(
            re.search(
                r"\b([01]?\d|2[0-3]):[0-5]\d\b",
                text,
            )
        )

        if (
            len(text) >= 20
            and (has_date or has_time)
        ):
            return current

        current = current.parent

    return element.parent or element


def extract_event_block(element, max_chars=1000):
    container = find_event_container(
        element
    )

    text = normalize_text(
        container.get_text(
            " ",
            strip=True,
        )
    )

    if len(text) > max_chars:
        text = text[:max_chars]

    return text


def parse_sms_ticket(url):
    print(f"Načítám SMS Ticket: {url}")

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )

        response.raise_for_status()

    except Exception as e:
        print(
            f"SMS Ticket: chyba při načítání: {e}"
        )

        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    events = []
    seen_urls = set()

    links = soup.find_all(
        "a",
        href=lambda href: (
            href
            and "/vstupenky/" in href
        ),
    )

    for link in links:
        href = link.get("href")

        if not href:
            continue

        full_url = urljoin(
            "https://www.smsticket.cz",
            href,
        )

        if full_url in seen_urls:
            continue

        seen_urls.add(full_url)

        block_text = extract_event_block(
            link
        )

        event_date = parse_czech_date(
            block_text
        )

        event_time = parse_time(
            block_text
        )

        if not event_date or not event_time:
            continue

        title = extract_sms_title(
            link,
            block_text,
        )

        if not title:
            print(
                "SMS Ticket: "
                f"nepodařilo se určit název: "
                f"{full_url}"
            )

            continue

        price = None

        price_match = re.search(
            r"(\d[\d\s]*)\s*Kč",
            block_text,
            flags=re.IGNORECASE,
        )

        if price_match:
            price = (
                normalize_text(
                    price_match.group(1)
                )
                + " Kč"
            )

        availability = None

        lower_block = block_text.lower()

        if "vyprodáno" in lower_block:
            availability = "Vyprodáno"

        elif "v prodeji" in lower_block:
            availability = "V prodeji"

        elif "prodej zahájen" in lower_block:
            availability = "V prodeji"

        event = {
            "id": make_id(
                title,
                event_date.isoformat(),
                event_time,
            ),
            "title": title,
            "date": event_date.isoformat(),
            "time": event_time,
            "price": price,
            "availability": availability,
            "sources": [
                "SMS Ticket"
            ],
            "urls": [
                full_url
            ],
        }

        events.append(event)

    unique = {}

    for event in events:
        key = (
            normalize_title_for_match(
                event["title"]
            ),
            event["date"],
            event["time"],
        )

        unique[key] = event

    events = list(
        unique.values()
    )

    events.sort(
        key=lambda event: (
            event["date"],
            event["time"],
            event["title"].lower(),
        )
    )

    print(
        f"SMS Ticket: nalezeno "
        f"{len(events)} akcí"
    )

    return events


def extract_ticketportal_title(link, container):
    """
    Ticketportal někdy obsahuje název přímo
    v odkazu, jindy v okolním elementu.

    Neakceptujeme obecné navigační názvy.
    """

    candidates = []

    link_text = clean_title(
        link.get_text(" ", strip=True)
    )

    if link_text:
        candidates.append(link_text)

    for attr in [
        "title",
        "aria-label",
        "data-title",
    ]:
        value = clean_title(
            link.get(attr)
        )

        if value:
            candidates.append(value)

    # Zkusíme heading uvnitř event bloku.
    for tag_name in [
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "strong",
    ]:
        for element in container.find_all(
            tag_name
        ):
            text = clean_title(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if text:
                candidates.append(text)

    # Vybereme první smysluplný kandidát.
    for candidate in candidates:
        candidate = normalize_text(
            candidate
        )

        if not candidate:
            continue

        if candidate.lower() in GENERIC_TITLES:
            continue

        if len(candidate) > 160:
            continue

        return candidate

    return ""


def parse_ticketportal_event_from_link(link):
    """
    Parsuje jednu Ticketportal event položku.

    Zkouší několik úrovní rodičovského HTML,
    protože struktura stránky se může měnit.
    """

    current = link

    for level in range(1, 11):
        if current is None:
            break

        text = normalize_text(
            current.get_text(
                " ",
                strip=True,
            )
        )

        event_date = parse_czech_date(
            text
        )

        event_time = parse_time(
            text
        )

        if (
            event_date
            and event_time
            and len(text) >= 20
        ):
            title = extract_ticketportal_title(
                link,
                current,
            )

            if title:
                return (
                    title,
                    event_date,
                    event_time,
                    text,
                )

        current = current.parent

    return (
        None,
        None,
        None,
        "",
    )


def parse_ticketportal(url):
    print(
        f"Načítám Ticketportal: {url}"
    )

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )

        response.raise_for_status()

    except Exception as e:
        print(
            f"Ticketportal: "
            f"chyba při načítání: {e}"
        )

        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    events = []
    seen_urls = set()

    links = soup.find_all(
        "a",
        href=lambda href: (
            href
            and "/Event/" in href
        ),
    )

    for link in links:
        href = link.get("href")

        if not href:
            continue

        full_url = urljoin(
            "https://www.ticketportal.cz",
            href,
        )

        if full_url in seen_urls:
            continue

        seen_urls.add(full_url)

        (
            title,
            event_date,
            event_time,
            block_text,
        ) = parse_ticketportal_event_from_link(
            link
        )

        if (
            not title
            or not event_date
            or not event_time
        ):
            continue

        lower_block = block_text.lower()

        if "vyprodáno" in lower_block:
            availability = "Vyprodáno"

        elif "v prodeji" in lower_block:
            availability = "V prodeji"

        else:
            availability = None

        event = {
            "id": make_id(
                title,
                event_date.isoformat(),
                event_time,
            ),
            "title": title,
            "date": event_date.isoformat(),
            "time": event_time,
            "price": None,
            "availability": availability,
            "sources": [
                "Ticketportal"
            ],
            "urls": [
                full_url
            ],
        }

        events.append(event)

    unique = {}

    for event in events:
        key = (
            normalize_title_for_match(
                event["title"]
            ),
            event["date"],
            event["time"],
        )

        unique[key] = event

    events = list(
        unique.values()
    )

    events.sort(
        key=lambda event: (
            event["date"],
            event["time"],
            event["title"].lower(),
        )
    )

    print(
        f"Ticketportal: nalezeno "
        f"{len(events)} akcí"
    )

    return events


def check_goout(url):
    print(
        "GoOut: JS-only stránka, "
        "akce zatím neparsujeme."
    )

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
        )

        if response.status_code != 200:
            print(
                f"GoOut: HTTP "
                f"{response.status_code}"
            )

    except Exception:
        pass


def titles_match(title_a, title_b):
    """
    Mírná normalizace názvů pro deduplikaci.

    Např.:
    CAVEMAN
    Caveman

    se považují za stejnou akci.

    Naopak různé názvy zůstávají oddělené.
    """

    a = normalize_title_for_match(
        title_a
    )

    b = normalize_title_for_match(
        title_b
    )

    if not a or not b:
        return False

    if a == b:
        return True

    # Malá tolerance pro názvy, kdy jeden zdroj
    # obsahuje pouze část názvu.
    if len(a) >= 8 and len(b) >= 8:
        if a in b or b in a:
            return True

    return False


def merge_events(events):
    """
    Sloučí stejnou akci z více zdrojů.

    Primární shoda:
        stejné datum + stejný čas + stejný název

    Sekundární shoda:
        stejné datum + stejný čas +
        velmi podobný název
    """

    merged = []

    for event in events:
        title = normalize_text(
            event.get("title", "")
        )

        event_date = event.get(
            "date"
        )

        event_time = event.get(
            "time"
        )

        if (
            not title
            or not event_date
            or not event_time
        ):
            continue

        found = None

        for existing in merged:
            if (
                existing.get("date")
                != event_date
            ):
                continue

            if (
                existing.get("time")
                != event_time
            ):
                continue

            if titles_match(
                existing.get("title", ""),
                title,
            ):
                found = existing
                break

        if found is None:
            merged.append(
                dict(event)
            )
            continue

        # Pokud má jeden zdroj hezčí/
        # smysluplnější název, ponecháme
        # delší název.
        existing_title = found.get(
            "title",
            "",
        )

        if len(title) > len(existing_title):
            found["title"] = title

        # Zdroje
        sources = set(
            found.get("sources", [])
        )

        sources.update(
            event.get("sources", [])
        )

        found["sources"] = sorted(
            sources
        )

        # URL
        urls = set(
            found.get("urls", [])
        )

        urls.update(
            event.get("urls", [])
        )

        found["urls"] = sorted(
            urls
        )

        # Cena
        if (
            not found.get("price")
            and event.get("price")
        ):
            found["price"] = event[
                "price"
            ]

        # Dostupnost
        if event.get("availability"):
            found["availability"] = event[
                "availability"
            ]

        # ID přepočítáme podle výsledného názvu.
        found["id"] = make_id(
            found["title"],
            found["date"],
            found["time"],
        )

    merged.sort(
        key=lambda event: (
            event["date"],
            event["time"],
            event["title"].lower(),
        )
    )

    return merged


def get_period(mode):
    today = date.today()

    if mode == "daily":
        return today, today

    if mode == "weekly":
        start = (
            today
            - timedelta(
                days=today.weekday()
            )
        )

        end = start + timedelta(
            days=6
        )

        return start, end

    raise ValueError(
        "Režim musí být daily nebo weekly."
    )


def filter_period(
    events,
    start_date,
    end_date,
):
    result = []

    for event in events:
        try:
            event_date = date.fromisoformat(
                event["date"]
            )

        except Exception:
            continue

        if (
            start_date
            <= event_date
            <= end_date
        ):
            result.append(event)

    result.sort(
        key=lambda event: (
            event["date"],
            event["time"],
            event["title"].lower(),
        )
    )

    return result


def format_date_cz(date_string):
    d = date.fromisoformat(
        date_string
    )

    return (
        f"{d.day}. "
        f"{d.month}. "
        f"{d.year}"
    )


def weekday_cz(d):
    names = [
        "pondělí",
        "úterý",
        "středa",
        "čtvrtek",
        "pátek",
        "sobota",
        "neděle",
    ]

    return names[d.weekday()]


def format_event(event):
    lines = []

    event_date = format_date_cz(
        event["date"]
    )

    lines.append(
        f"📅 {event_date} | "
        f"{event['time']}"
    )

    lines.append(
        event["title"]
    )

    if event.get("price"):
        lines.append(
            f"🎟️ {event['price']}"
        )

    if event.get("availability"):
        availability = event[
            "availability"
        ]

        if (
            availability.lower()
            == "v prodeji"
        ):
            lines.append(
                "🟢 V prodeji"
            )

        elif (
            availability.lower()
            == "vyprodáno"
        ):
            lines.append(
                "🔴 Vyprodáno"
            )

        else:
            lines.append(
                f"ℹ️ {availability}"
            )

    sources = event.get(
        "sources",
        [],
    )

    if sources:
        lines.append(
            "🌐 "
            + " + ".join(sources)
        )

    urls = event.get(
        "urls",
        [],
    )

    if urls:
        lines.append(
            urls[0]
        )

    return "\n".join(lines)


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN:
        print(
            "Telegram: chybí "
            "TELEGRAM_BOT_TOKEN"
        )

        return False

    if not TELEGRAM_CHAT_ID:
        print(
            "Telegram: chybí "
            "TELEGRAM_CHAT_ID"
        )

        return False

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": False,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=30,
        )

        response.raise_for_status()

        return True

    except Exception as e:
        print(
            "Telegram: chyba při "
            f"odesílání: {e}"
        )

        return False


def build_message(mode, events):
    if not events:
        return None

    if mode == "daily":
        today = date.today()

        heading = (
            "🎭 KULTURA – "
            f"{weekday_cz(today)} "
            f"{today.day}. "
            f"{today.month}. "
            f"{today.year}"
        )

    else:
        start_date, end_date = get_period(
            mode
        )

        heading = (
            "🎭 KULTURA – týden "
            f"{start_date.day}. "
            f"{start_date.month}. "
            "– "
            f"{end_date.day}. "
            f"{end_date.month}. "
            f"{end_date.year}"
        )

    blocks = []

    for event in events:
        blocks.append(
            format_event(event)
        )

    return (
        heading
        + "\n\n"
        + "\n\n".join(blocks)
    )


def main():
    mode = "daily"

    if len(sys.argv) > 1:
        mode = sys.argv[1]

    if mode not in [
        "daily",
        "weekly",
    ]:
        print(
            "Použití: "
            "python culture_monitor.py "
            "[daily|weekly]"
        )

        sys.exit(1)

    print("=" * 70)
    print(
        "KULTURA MONITOR – "
        "KD HRONOVICKÁ"
    )
    print("=" * 70)

    print(
        f"Režim: {mode}"
    )

    today = date.today()

    print(
        f"Dnes: {today.day}. "
        f"{today.month}. "
        f"{today.year}"
    )

    config = load_json(
        CONFIG_FILE,
        {"venues": []},
    )

    state = load_json(
        STATE_FILE,
        {
            "initialized": False,
            "signatures": {},
            "last_run": None,
        },
    )

    all_events = []

    for venue in config.get(
        "venues",
        [],
    ):
        sources = venue.get(
            "sources",
            {},
        )

        sms_url = sources.get(
            "smsticket"
        )

        if sms_url:
            all_events.extend(
                parse_sms_ticket(
                    sms_url
                )
            )

        ticketportal_url = sources.get(
            "ticketportal"
        )

        if ticketportal_url:
            all_events.extend(
                parse_ticketportal(
                    ticketportal_url
                )
            )

        goout_url = sources.get(
            "goout"
        )

        if goout_url:
            check_goout(
                goout_url
            )

    events = merge_events(
        all_events
    )

    print(
        "Celkem po sloučení zdrojů: "
        f"{len(events)} akcí"
    )

    now = datetime.now().isoformat()

    # -------------------------------------------------
    # PRVNÍ SPUŠTĚNÍ
    # -------------------------------------------------

    if not state.get(
        "initialized",
        False,
    ):
        signatures = {}

        for event in events:
            event_id = event["id"]

            signatures[event_id] = {
                "signature": make_signature(
                    event
                ),
                "event": event,
                "updated_at": now,
            }

        state = {
            "initialized": True,
            "signatures": signatures,
            "last_run": now,
        }

        save_json(
            STATE_FILE,
            state,
        )

        print(
            "PRVNÍ SPUŠTĚNÍ – "
            "ukládám aktuální stav."
        )

        print(
            "Telegram nebude odeslán."
        )

        return

    # -------------------------------------------------
    # POROVNÁNÍ SE STARÝM STAVEM
    # -------------------------------------------------

    old_signatures = state.get(
        "signatures",
        {},
    )

    new_signatures = {}
    changed_events = []

    for event in events:
        event_id = event["id"]

        signature = make_signature(
            event
        )

        new_signatures[event_id] = {
            "signature": signature,
            "event": event,
            "updated_at": now,
        }

        old = old_signatures.get(
            event_id
        )

        if old is None:
            changed_events.append(
                event
            )

        elif (
            old.get("signature")
            != signature
        ):
            changed_events.append(
                event
            )

    state["signatures"] = (
        new_signatures
    )

    state["last_run"] = now

    save_json(
        STATE_FILE,
        state,
    )

    # -------------------------------------------------
    # AKTUÁLNÍ OBDOBÍ
    # -------------------------------------------------

    start_date, end_date = get_period(
        mode
    )

    period_events = filter_period(
        changed_events,
        start_date,
        end_date,
    )

    print(
        "Nové/změněné akce: "
        f"{len(changed_events)}"
    )

    print(
        "Nové/změněné akce v období: "
        f"{len(period_events)}"
    )

    if not period_events:
        print(
            "Žádná nová nebo změněná "
            "akce v aktuálním období."
        )

        print(
            "Telegram nebude odeslán."
        )

        return

    message = build_message(
        mode,
        period_events,
    )

    if not message:
        print(
            "Není co odeslat."
        )

        return

    print()
    print(
        "Odesílám Telegram:"
    )
    print("-" * 70)
    print(message)
    print("-" * 70)

    if send_telegram(message):
        print(
            "Telegram: odesláno."
        )

    else:
        print(
            "Telegram: "
            "odeslání selhalo."
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
