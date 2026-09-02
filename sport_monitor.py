import os
import json
import re
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus
from bs4 import BeautifulSoup


TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SPORT_CONFIG_FILE = "sport_config.json"
SPORT_STATE_FILE = "data/sport_state.json"

TIMEZONE = ZoneInfo("Europe/Prague")

DYNAMO_URL = "https://www.hcdynamo.cz/matches/MUZ"

CT_BIATHLON_URL = "https://www.ceskatelevize.cz/tv-program/Biatlon/"
CT_ATHLETICS_URL = "https://www.ceskatelevize.cz/tv-program/Atletika/"

IDNES_SEARCH_URL = "https://tvprogram.idnes.cz/hledani?slovo="

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(compatible; YT-Michopulos-Sport-Monitor/1.0)"
    )
}


def load_json(filename, default):
    if not os.path.exists(filename):
        return default

    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename, data):
    directory = os.path.dirname(filename)

    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def send_telegram(message):
    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    response.raise_for_status()


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    return response.text


def normalize_text(text):
    text = text.lower()

    replacements = {
        "á": "a",
        "č": "c",
        "ď": "d",
        "é": "e",
        "ě": "e",
        "í": "i",
        "ň": "n",
        "ó": "o",
        "ř": "r",
        "š": "s",
        "ť": "t",
        "ú": "u",
        "ů": "u",
        "ý": "y",
        "ž": "z",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^a-z0-9]+", " ", text)

    return " ".join(text.split())


def extract_team_names_from_dynamo_section(section):
    section = section.replace(
        "HC Dynamo Pardubice",
        "",
    )

    section = section.replace(
        "VS",
        " ",
    )

    section = re.sub(
        r"\s+",
        " ",
        section,
    )

    return section.strip()


def parse_dynamo_matches():
    html = get_page(DYNAMO_URL)

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    matches = []

    text = soup.get_text(
        " ",
        strip=True,
    )

    pattern = re.compile(
        r"(po|út|st|čt|pá|so|ne)\s+"
        r"(\d{1,2})\.\s+"
        r"(\d{1,2})\.\s+"
        r"(\d{4}),\s+"
        r"(\d{1,2}):(\d{2})"
    )

    date_matches = list(
        pattern.finditer(text)
    )

    print(
        f"Dynamo: nalezeno "
        f"{len(date_matches)} datových bloků"
    )

    for index, match in enumerate(date_matches):
        day = int(match.group(2))
        month = int(match.group(3))
        year = int(match.group(4))
        hour = int(match.group(5))
        minute = int(match.group(6))

        start = match.end()

        if index + 1 < len(date_matches):
            end = date_matches[
                index + 1
            ].start()
        else:
            end = min(
                start + 500,
                len(text),
            )

        section = text[start:end]

        if "HC Dynamo Pardubice" not in section:
            continue

        opponent = extract_team_names_from_dynamo_section(
            section
        )

        if not opponent:
            continue

        event_time = datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=TIMEZONE,
        )

        event = {
            "id": (
                "dynamo-"
                f"{event_time.strftime('%Y%m%d-%H%M')}-"
                f"{normalize_text(opponent)[:80]}"
            ),
            "category": "hockey",
            "name": (
                f"Dynamo Pardubice vs {opponent}"
            ),
            "opponent": opponent,
            "date": event_time.strftime(
                "%Y-%m-%d"
            ),
            "time": event_time.strftime(
                "%H:%M"
            ),
            "datetime": event_time.isoformat(),
            "tv_channel": None,
            "tv_confirmed": False,
            "source": DYNAMO_URL,
        }

        matches.append(event)

        print(
            "Dynamo zápas:"
            f" {event['date']}"
            f" {event['time']}"
            f" - {event['name']}"
        )

    unique_matches = {}

    for event in matches:
        unique_matches[event["id"]] = event

    return list(
        unique_matches.values()
    )


def tv_title_matches_dynamo(
    title,
    opponent,
):
    title_normalized = normalize_text(
        title
    )

    opponent_normalized = normalize_text(
        opponent
    )

    if "dynamo pardubice" not in title_normalized:
        return False

    if opponent_normalized not in title_normalized:
        return False

    return True


def parse_idnes_tv_for_dynamo(event):
    query = (
        "Dynamo Pardubice "
        + event["opponent"]
    )

    url = (
        IDNES_SEARCH_URL
        + quote_plus(query)
    )

    print(
        "TV kontrola:"
        f" {query}"
    )

    try:
        html = get_page(url)
    except Exception as e:
        print(
            f"TV ERROR: {e}"
        )
        return None

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    target_date = datetime.fromisoformat(
        event["datetime"]
    ).date()

    candidates = []

    for link in soup.find_all(
        "a",
        href=True,
    ):
        href = link.get("href", "")

        title = link.get_text(
            " ",
            strip=True,
        )

        if not title:
            continue

        if not tv_title_matches_dynamo(
            title,
            event["opponent"],
        ):
            continue

        href_lower = href.lower()

        channel = None

        channel_patterns = {
            "/sport1/": "Sport1",
            "/sport2/": "Sport2",
            "/ct-sport/": "ČT sport",
            "/ctsport/": "ČT sport",
            "/oneplay-sport-1/": "Oneplay Sport 1",
            "/oneplay-sport-2/": "Oneplay Sport 2",
        }

        for pattern, channel_name in channel_patterns.items():
            if pattern in href_lower:
                channel = channel_name
                break

        if not channel:
            continue

        parent_text = ""

        parent = link.parent

        if parent:
            parent_text = parent.get_text(
                " ",
                strip=True,
            )

        container = link.find_parent(
            [
                "article",
                "li",
                "div",
            ]
        )

        if container:
            container_text = container.get_text(
                " ",
                strip=True,
            )

            if len(container_text) > len(parent_text):
                parent_text = container_text

        full_text = (
            title
            + " "
            + parent_text
        )

        normalized_full_text = normalize_text(
            full_text
        )

        if "primy prenos" not in normalized_full_text:
            print(
                f"TV kandidát ignorován "
                f"(není potvrzen přímý přenos): "
                f"{title} / {channel}"
            )
            continue

        if "zaznam" in normalized_full_text:
            print(
                f"TV kandidát ignorován "
                f"(záznam): "
                f"{title} / {channel}"
            )
            continue

        date_match = re.search(
            r"(\d{1,2})\.\s*"
            r"(\d{1,2})\.\s*"
            r"(\d{4})",
            full_text,
        )

        if not date_match:
            continue

        tv_day = int(
            date_match.group(1)
        )
        tv_month = int(
            date_match.group(2)
        )
        tv_year = int(
            date_match.group(3)
        )

        try:
            tv_date = datetime(
                tv_year,
                tv_month,
                tv_day,
            ).date()
        except ValueError:
            continue

        if tv_date != target_date:
            continue

        candidates.append(
            {
                "channel": channel,
                "title": title,
                "url": href,
            }
        )

    unique_channels = {}

    for candidate in candidates:
        unique_channels[
            candidate["channel"]
        ] = candidate

    if len(unique_channels) == 1:
        candidate = list(
            unique_channels.values()
        )[0]

        print(
            "TV potvrzen:"
            f" {candidate['channel']}"
        )

        return candidate

    if len(unique_channels) > 1:
        print(
            "TV není jednoznačné. "
            "Nalezené kanály:"
        )

        for channel in unique_channels:
            print(
                f"  - {channel}"
            )

        return None

    print(
        "TV kanál se nepodařilo "
        "jednoznačně potvrdit."
    )

    return None


def enrich_dynamo_tv(events):
    for event in events:
        try:
            tv = parse_idnes_tv_for_dynamo(
                event
            )

            if tv:
                event["tv_channel"] = (
                    tv["channel"]
                )

                event["tv_confirmed"] = True

        except Exception as e:
            print(
                "TV enrichment ERROR:"
                f" {e}"
            )

    return events


def parse_ct_program(
    url,
    category,
    keywords,
):
    html = get_page(url)

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = soup.get_text(
        "\n",
        strip=True,
    )

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    events = []

    date_pattern = re.compile(
        r"^(Pondělí|Úterý|Středa|Čtvrtek|Pátek|Sobota|Neděle)"
        r"\s+(\d{1,2})\.\s+"
        r"(\d{1,2})\.\s+"
        r"(\d{4})$"
    )

    time_pattern = re.compile(
        r"^(\d{1,2}):(\d{2})$"
    )

    current_date = None

    for index, line in enumerate(lines):
        date_match = date_pattern.match(
            line
        )

        if date_match:
            day = int(
                date_match.group(2)
            )
            month = int(
                date_match.group(3)
            )
            year = int(
                date_match.group(4)
            )

            current_date = datetime(
                year,
                month,
                day,
                tzinfo=TIMEZONE,
            )

            continue

        if current_date is None:
            continue

        time_match = time_pattern.match(
            line
        )

        if not time_match:
            continue

        hour = int(
            time_match.group(1)
        )
        minute = int(
            time_match.group(2)
        )

        title = ""

        for next_line in lines[
            index + 1:index + 6
        ]:
            if next_line == "Přehrát":
                continue

            if next_line == "ČT sport":
                continue

            if len(next_line) >= 5:
                title = next_line
                break

        if not title:
            continue

        title_lower = title.lower()

        if not any(
            keyword.lower() in title_lower
            for keyword in keywords
        ):
            continue

        event_time = current_date.replace(
            hour=hour,
            minute=minute,
        )

        events.append(
            {
                "id": (
                    f"{category}-"
                    f"{event_time.strftime('%Y%m%d-%H%M')}-"
                    f"{title[:80]}"
                ),
                "category": category,
                "name": title,
                "date": event_time.strftime(
                    "%Y-%m-%d"
                ),
                "time": event_time.strftime(
                    "%H:%M"
                ),
                "datetime": event_time.isoformat(),
                "tv_channel": "ČT sport",
                "tv_confirmed": True,
                "source": url,
            }
        )

    return events


def get_sport_events():
    config = load_json(
        SPORT_CONFIG_FILE,
        {
            "dynamo_pardubice": True,
            "diamond_league": True,
            "biathlon": True,
            "world_hockey_championship": False,
        },
    )

    events = []

    if config.get(
        "dynamo_pardubice",
        True,
    ):
        try:
            dynamo_events = (
                parse_dynamo_matches()
            )

            dynamo_events = enrich_dynamo_tv(
                dynamo_events
            )

            events.extend(
                dynamo_events
            )

            print(
                "Dynamo:"
                f" nalezeno "
                f"{len(dynamo_events)} zápasů"
            )

        except Exception as e:
            print(
                f"Dynamo ERROR: {e}"
            )

    if config.get(
        "diamond_league",
        True,
    ):
        try:
            athletics_events = (
                parse_ct_program(
                    CT_ATHLETICS_URL,
                    "athletics",
                    [
                        "Diamantová liga",
                    ],
                )
            )

            events.extend(
                athletics_events
            )

            print(
                "Atletika:"
                f" nalezeno "
                f"{len(athletics_events)} "
                f"událostí"
            )

        except Exception as e:
            print(
                f"Atletika ERROR: {e}"
            )

    if config.get(
        "biathlon",
        True,
    ):
        try:
            biathlon_events = (
                parse_ct_program(
                    CT_BIATHLON_URL,
                    "biathlon",
                    [
                        "SP v biatlonu",
                        "Mistrovství světa",
                        "Biatlon",
                    ],
                )
            )

            events.extend(
                biathlon_events
            )

            print(
                "Biatlon:"
                f" nalezeno "
                f"{len(biathlon_events)} "
                f"událostí"
            )

        except Exception as e:
            print(
                f"Biatlon ERROR: {e}"
            )

    return events


def format_event(event):
    category_icons = {
        "hockey": "🏒",
        "athletics": "🏃",
        "biathlon": "🎿",
    }

    icon = category_icons.get(
        event["category"],
        "🏆",
    )

    message = (
        f"{icon} {event['name']}\n"
        f"📅 {event['date']}\n"
        f"🕐 {event['time']}"
    )

    if (
        event.get("tv_confirmed")
        and event.get("tv_channel")
    ):
        message += (
            f"\n📺 {event['tv_channel']}"
        )

    return message


def make_daily_message(
    events,
    today,
):
    today_events = []

    for event in events:
        if event["date"] == today.strftime(
            "%Y-%m-%d"
        ):
            today_events.append(event)

    today_events.sort(
        key=lambda event: event["datetime"]
    )

    if not today_events:
        return None

    message = "🔔 SPORT DNES\n\n"

    for index, event in enumerate(
        today_events
    ):
        if index > 0:
            message += "\n\n"

        message += format_event(
            event
        )

    return message


def make_weekly_message(
    events,
    monday,
):
    sunday = monday + timedelta(
        days=6
    )

    week_events = []

    for event in events:
        event_date = datetime.fromisoformat(
            event["datetime"]
        ).date()

        if (
            monday.date()
            <= event_date
            <= sunday.date()
        ):
            week_events.append(event)

    week_events.sort(
        key=lambda event: event["datetime"]
    )

    if not week_events:
        return None

    message = (
        "📅 SPORT – PŘEHLED TÝDNE\n\n"
    )

    current_date = None

    for event in week_events:
        event_date = event["date"]

        if event_date != current_date:
            if current_date is not None:
                message += "\n"

            message += (
                f"📆 {event_date}\n"
            )

            current_date = event_date

        message += (
            "\n"
            + format_event(event)
            + "\n"
        )

    return message.strip()


def main():
    now = datetime.now(
        TIMEZONE
    )

    print(
        "Sport monitor:"
        f" {now.isoformat()}"
    )

    events = get_sport_events()

    print(
        "Celkem sportovních událostí:"
        f" {len(events)}"
    )

    state = load_json(
        SPORT_STATE_FILE,
        {
            "sent_daily": [],
            "sent_weekly": [],
        },
    )

    sent_daily = set(
        state.get(
            "sent_daily",
            [],
        )
    )

    sent_weekly = set(
        state.get(
            "sent_weekly",
            [],
        )
    )

    import sys

    if len(sys.argv) < 2:
        print(
            "Použití:"
            " python sport_monitor.py daily"
            " nebo"
            " python sport_monitor.py weekly"
        )
        return

    mode = sys.argv[1]

    if mode == "daily":
        today_key = now.strftime(
            "%Y-%m-%d"
        )

        if today_key in sent_daily:
            print(
                "Dnešní sportovní upozornění "
                "už bylo odesláno."
            )
            return

        message = make_daily_message(
            events,
            now,
        )

        if message is None:
            print(
                "Dnes není žádná sledovaná "
                "sportovní událost."
            )

            print(
                "Telegram se neposílá."
            )

            return

        send_telegram(message)

        print(
            "Denní sportovní upozornění "
            "odesláno."
        )

        sent_daily.add(
            today_key
        )

    elif mode == "weekly":
        monday = now - timedelta(
            days=now.weekday()
        )

        week_key = monday.strftime(
            "%Y-%m-%d"
        )

        if week_key in sent_weekly:
            print(
                "Týdenní přehled pro tento týden "
                "už byl odeslán."
            )
            return

        message = make_weekly_message(
            events,
            monday,
        )

        if message is None:
            print(
                "Tento týden není žádná "
                "sledovaná sportovní událost."
            )

            print(
                "Telegram se neposílá."
            )

            return

        send_telegram(message)

        print(
            "Týdenní sportovní přehled "
            "odeslán."
        )

        sent_weekly.add(
            week_key
        )

    else:
        print(
            "Neznámý režim. Použij:"
            " daily nebo weekly"
        )
        return

    state["sent_daily"] = list(
        sent_daily
    )[-90:]

    state["sent_weekly"] = list(
        sent_weekly
    )[-52:]

    save_json(
        SPORT_STATE_FILE,
        state,
    )

    print(
        "Sportovní stav uložen."
    )


if __name__ == "__main__":
    main()
