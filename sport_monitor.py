import os
import json
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup


TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SPORT_CONFIG_FILE = "sport_config.json"
SPORT_STATE_FILE = "data/sport_state.json"

TIMEZONE = ZoneInfo("Europe/Prague")

DYNAMO_URL = "https://www.hcdynamo.cz/matches/MUZ"

CT_BIATHLON_URL = "https://www.ceskatelevize.cz/tv-program/Biatlon/"
CT_ATHLETICS_URL = "https://www.ceskatelevize.cz/tv-program/Atletika/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; YT-Michopulos-Sport-Monitor/1.0)"
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
        json.dump(data, f, ensure_ascii=False, indent=2)


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


def parse_dynamo_matches():
    html = get_page(DYNAMO_URL)

    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text(" ", strip=True)

    matches = []

    import re

    pattern = re.compile(
        r"(po|út|st|čt|pá|so|ne)\s+"
        r"(\d{1,2})\.\s+(\d{1,2})\.\s+(\d{4}),\s+"
        r"(\d{1,2}):(\d{2})"
    )

    date_matches = list(pattern.finditer(text))

    for index, match in enumerate(date_matches):
        day = int(match.group(2))
        month = int(match.group(3))
        year = int(match.group(4))
        hour = int(match.group(5))
        minute = int(match.group(6))

        start = match.end()

        if index + 1 < len(date_matches):
            end = date_matches[index + 1].start()
        else:
            end = min(start + 500, len(text))

        section = text[start:end]

        if "HC Dynamo Pardubice" not in section:
            continue

        section = section.replace(
            "HC Dynamo Pardubice",
            "",
        )

        section = section.replace(
            "VS",
            " vs ",
        )

        section = section.strip()

        if not section:
            continue

        event_time = datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=TIMEZONE,
        )

        matches.append(
            {
                "id": (
                    f"dynamo-"
                    f"{event_time.strftime('%Y%m%d-%H%M')}-"
                    f"{section[:80]}"
                ),
                "category": "hockey",
                "name": section[:150],
                "date": event_time.strftime("%Y-%m-%d"),
                "time": event_time.strftime("%H:%M"),
                "datetime": event_time.isoformat(),
                "tv_channel": None,
                "tv_confirmed": False,
                "source": DYNAMO_URL,
            }
        )

    return matches


def parse_ct_program(url, category, keywords):
    html = get_page(url)

    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n", strip=True)

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    events = []

    import re

    date_pattern = re.compile(
        r"^(Pondělí|Úterý|Středa|Čtvrtek|Pátek|Sobota|Neděle)"
        r"\s+(\d{1,2})\.\s+(\d{1,2})\.\s+(\d{4})$"
    )

    time_pattern = re.compile(
        r"^(\d{1,2}):(\d{2})$"
    )

    current_date = None

    for index, line in enumerate(lines):
        date_match = date_pattern.match(line)

        if date_match:
            day = int(date_match.group(2))
            month = int(date_match.group(3))
            year = int(date_match.group(4))

            current_date = datetime(
                year,
                month,
                day,
                tzinfo=TIMEZONE,
            )

            continue

        if current_date is None:
            continue

        time_match = time_pattern.match(line)

        if not time_match:
            continue

        hour = int(time_match.group(1))
        minute = int(time_match.group(2))

        title = ""

        for next_line in lines[index + 1:index + 6]:
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
                "date": event_time.strftime("%Y-%m-%d"),
                "time": event_time.strftime("%H:%M"),
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

    if config.get("dynamo_pardubice", True):
        try:
            dynamo_events = parse_dynamo_matches()
            events.extend(dynamo_events)

            print(
                f"Dynamo: nalezeno "
                f"{len(dynamo_events)} zápasů"
            )

        except Exception as e:
            print(f"Dynamo ERROR: {e}")

    if config.get("diamond_league", True):
        try:
            athletics_events = parse_ct_program(
                CT_ATHLETICS_URL,
                "athletics",
                [
                    "Diamantová liga",
                ],
            )

            events.extend(athletics_events)

            print(
                "Atletika: "
                f"nalezeno {len(athletics_events)} událostí"
            )

        except Exception as e:
            print(f"Atletika ERROR: {e}")

    if config.get("biathlon", True):
        try:
            biathlon_events = parse_ct_program(
                CT_BIATHLON_URL,
                "biathlon",
                [
                    "SP v biatlonu",
                    "Mistrovství světa",
                    "Biatlon",
                ],
            )

            events.extend(biathlon_events)

            print(
                "Biatlon: "
                f"nalezeno {len(biathlon_events)} událostí"
            )

        except Exception as e:
            print(f"Biatlon ERROR: {e}")

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

    if event.get("tv_confirmed") and event.get("tv_channel"):
        message += (
            f"\n📺 {event['tv_channel']}"
        )

    else:
        message += (
            "\n📺 TV kanál: "
            "nebyl jednoznačně potvrzen"
        )

    return message


def make_daily_message(events, today):
    today_events = []

    for event in events:
        if event["date"] == today.strftime("%Y-%m-%d"):
            today_events.append(event)

    today_events.sort(
        key=lambda event: event["datetime"]
    )

    if not today_events:
        return None

    message = "🔔 SPORT DNES\n\n"

    for index, event in enumerate(today_events):
        if index > 0:
            message += "\n\n"

        message += format_event(event)

    return message


def make_weekly_message(events, monday):
    sunday = monday + timedelta(days=6)

    week_events = []

    for event in events:
        event_date = datetime.fromisoformat(
            event["datetime"]
        ).date()

        if monday.date() <= event_date <= sunday.date():
            week_events.append(event)

    week_events.sort(
        key=lambda event: event["datetime"]
    )

    if not week_events:
        return None

    message = "📅 SPORT – PŘEHLED TÝDNE\n\n"

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
    now = datetime.now(TIMEZONE)

    print(
        "Sport monitor:"
        f" {now.isoformat()}"
    )

    events = get_sport_events()

    print(
        f"Celkem sportovních událostí: "
        f"{len(events)}"
    )

    state = load_json(
        SPORT_STATE_FILE,
        {
            "sent_daily": [],
            "sent_weekly": [],
        },
    )

    sent_daily = set(
        state.get("sent_daily", [])
    )

    sent_weekly = set(
        state.get("sent_weekly", [])
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
        today_key = now.strftime("%Y-%m-%d")

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

        sent_daily.add(today_key)

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

        sent_weekly.add(week_key)

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

    print("Sportovní stav uložen.")


if __name__ == "__main__":
    main()
