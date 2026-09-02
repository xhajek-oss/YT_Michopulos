import os
import json
import requests
from datetime import datetime, timezone, timedelta

YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

CONFIG_FILE = "config.json"
STATE_FILE = "data/seen_videos.json"

MAX_AGE_DAYS = 1.5
MAX_RESULTS = 50

# Videa dlouhá 5 minut nebo méně budou vyřazena.
MIN_DURATION_SECONDS = 5 * 60

SEARCH_QUERIES = {
    "David Svoboda": [
        "David Svoboda Ukrajina",
        "David Svoboda ukrajinista",
        "David Svoboda historik",
    ]
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


def youtube_search(query):
    url = "https://www.googleapis.com/youtube/v3/search"

    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": MAX_RESULTS,
        "order": "date",
        "key": YOUTUBE_API_KEY,
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    return response.json().get("items", [])


def youtube_get_video_details(video_ids):
    """
    Načte délku videí přes YouTube videos.list API.

    Vrací slovník:
        {
            "video_id": {
                "duration_seconds": 123,
                "duration": "PT2M3S"
            }
        }
    """

    if not video_ids:
        return {}

    url = "https://www.googleapis.com/youtube/v3/videos"

    details = {}

    # YouTube API umožňuje maximálně 50 ID v jednom requestu.
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]

        params = {
            "part": "contentDetails",
            "id": ",".join(batch),
            "key": YOUTUBE_API_KEY,
        }

        response = requests.get(
            url,
            params=params,
            timeout=30,
        )
        response.raise_for_status()

        for item in response.json().get("items", []):
            video_id = item.get("id")
            duration = (
                item.get("contentDetails", {})
                .get("duration")
            )

            if not video_id or not duration:
                continue

            duration_seconds = parse_iso8601_duration(duration)

            details[video_id] = {
                "duration_seconds": duration_seconds,
                "duration": duration,
            }

    return details


def parse_iso8601_duration(duration):
    """
    Převod ISO 8601 délky YouTube videa na sekundy.

    Příklady:
        PT30S       = 30 sekund
        PT5M        = 300 sekund
        PT1H2M3S    = 3723 sekund
    """

    import re

    match = re.fullmatch(
        r"PT"
        r"(?:(\d+)H)?"
        r"(?:(\d+)M)?"
        r"(?:(\d+)S)?",
        duration,
    )

    if not match:
        return 0

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    return (
        hours * 3600
        + minutes * 60
        + seconds
    )


def format_duration(seconds):
    """
    Hezký zápis délky videa pro log.
    """

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60

    if hours:
        return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"

    return f"{minutes}:{remaining_seconds:02d}"


def send_telegram(message):
    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": False,
    }

    response = requests.post(
        url,
        data=data,
        timeout=30,
    )
    response.raise_for_status()


def main():
    config = load_json(
        CONFIG_FILE,
        {
            "keywords": [],
            "exclude_channels": {},
        },
    )

    state = load_json(
        STATE_FILE,
        {
            "seen_video_ids": [],
            "initialized_keywords": [],
            "last_checked_at": None,
        },
    )

    seen_video_ids = set(
        state.get("seen_video_ids", [])
    )

    initialized_keywords = set(
        state.get("initialized_keywords", [])
    )

    now = datetime.now(timezone.utc)
    max_age = timedelta(days=MAX_AGE_DAYS)

    all_new_videos = []

    print(f"Kontrola: {now.isoformat()}")
    print(
        f"Limit stáří videa: "
        f"{MAX_AGE_DAYS} dne"
    )
    print(
        f"Minimální délka videa: "
        f"{format_duration(MIN_DURATION_SECONDS)}"
    )

    for keyword in config.get("keywords", []):

        exclude_channels = set(
            config.get(
                "exclude_channels",
                {}
            ).get(keyword, [])
        )

        print()
        print(f"=== {keyword} ===")

        # -----------------------------------------
        # VYHLEDÁNÍ VIDEÍ
        # -----------------------------------------

        if keyword in SEARCH_QUERIES:

            queries = SEARCH_QUERIES[keyword]

            print("Hledám přes:")

            for query in queries:
                print(f"  - {query}")

            results_by_id = {}

            for query in queries:

                results = youtube_search(query)

                print(
                    f"Výsledků pro "
                    f"'{query}': {len(results)}"
                )

                for item in results:

                    video_id = (
                        item.get("id", {})
                        .get("videoId")
                    )

                    if video_id:
                        results_by_id[video_id] = item

            results = list(
                results_by_id.values()
            )

            print(
                f"Celkem unikátních výsledků: "
                f"{len(results)}"
            )

        else:

            results = youtube_search(keyword)

            print(
                f"Výsledků: {len(results)}"
            )

        # -----------------------------------------
        # NAČTENÍ DÉLEK VIDEÍ
        # -----------------------------------------

        video_ids = []

        for item in results:

            video_id = (
                item.get("id", {})
                .get("videoId")
            )

            if video_id:
                video_ids.append(video_id)

        video_details = youtube_get_video_details(
            video_ids
        )

        print(
            f"Načteno délek videí: "
            f"{len(video_details)}"
        )

        # -----------------------------------------
        # ZPRACOVÁNÍ
        # -----------------------------------------

        keyword_initialized = (
            keyword in initialized_keywords
        )

        for item in results:

            video_id = (
                item.get("id", {})
                .get("videoId")
            )

            snippet = item.get(
                "snippet",
                {}
            )

            if not video_id:
                continue

            title = snippet.get(
                "title",
                "Bez názvu"
            )

            channel_title = snippet.get(
                "channelTitle",
                "Neznámý kanál"
            )

            channel_id = snippet.get(
                "channelId"
            )

            published_at = snippet.get(
                "publishedAt"
            )

            if not published_at:
                continue

            published = datetime.fromisoformat(
                published_at.replace(
                    "Z",
                    "+00:00"
                )
            )

            age = now - published

            print()
            print(f"VIDEO: {title}")
            print(f"KANÁL: {channel_title}")
            print(f"DATUM: {published_at}")

            # -------------------------------------
            # VYLOUČENÝ KANÁL
            # -------------------------------------

            if channel_id in exclude_channels:

                print(
                    "→ VYŘAZENO: "
                    "vyloučený kanál"
                )

                continue

            # -------------------------------------
            # STÁŘÍ VIDEA
            # -------------------------------------

            if age > max_age:

                print(
                    "→ VYŘAZENO: "
                    "video je starší než limit"
                )

                continue

            # -------------------------------------
            # DÉLKA VIDEA
            # -------------------------------------

            details = video_details.get(
                video_id
            )

            if not details:

                print(
                    "→ VYŘAZENO: "
                    "nepodařilo se zjistit délku"
                )

                continue

            duration_seconds = details[
                "duration_seconds"
            ]

            duration_text = format_duration(
                duration_seconds
            )

            print(
                f"DÉLKA: {duration_text}"
            )

            if duration_seconds <= MIN_DURATION_SECONDS:

                print(
                    "→ VYŘAZENO: "
                    "video má 5 minut nebo méně"
                )

                # Krátké video zároveň uložíme
                # jako známé, aby se příště
                # znovu nezpracovávalo.
                seen_video_ids.add(video_id)

                continue

            # -------------------------------------
            # PRVNÍ KONTROLA
            # -------------------------------------

            if not keyword_initialized:

                print(
                    "→ PRVNÍ KONTROLA: "
                    "uloženo jako výchozí stav"
                )

                seen_video_ids.add(video_id)

                continue

            # -------------------------------------
            # DUPLICITA
            # -------------------------------------

            if video_id in seen_video_ids:

                print(
                    "→ VYŘAZENO: "
                    "video už bylo oznámeno"
                )

                continue

            # -------------------------------------
            # NOVÉ VIDEO
            # -------------------------------------

            video_url = (
                "https://www.youtube.com/watch?v="
                f"{video_id}"
            )

            all_new_videos.append(
                {
                    "keyword": keyword,
                    "title": title,
                    "channel_title": channel_title,
                    "published_at": published_at,
                    "duration_seconds": duration_seconds,
                    "duration": duration_text,
                    "url": video_url,
                    "video_id": video_id,
                }
            )

            seen_video_ids.add(video_id)

            print("→ NOVÉ VIDEO")

        initialized_keywords.add(keyword)

    # ---------------------------------------------
    # TELEGRAM
    # ---------------------------------------------

    print()
    print(
        f"Nových videí: "
        f"{len(all_new_videos)}"
    )

    for video in all_new_videos:

        message = (
            f"🎬 Nové video\n\n"
            f"{video['title']}\n\n"
            f"Kanál: "
            f"{video['channel_title']}\n"
            f"Délka: "
            f"{video['duration']}\n"
            f"Publikováno: "
            f"{video['published_at']}\n\n"
            f"{video['url']}"
        )

        try:

            send_telegram(message)

            print(
                f"Telegram OK: "
                f"{video['title']}"
            )

        except Exception as e:

            print(
                f"Telegram ERROR: {e}"
            )

    # ---------------------------------------------
    # ULOŽENÍ STAVU
    # ---------------------------------------------

    state["seen_video_ids"] = list(
        seen_video_ids
    )[-500:]

    state["initialized_keywords"] = list(
        initialized_keywords
    )

    state["last_checked_at"] = (
        now.isoformat()
    )

    save_json(
        STATE_FILE,
        state
    )

    print("Stav uložen.")


if __name__ == "__main__":
    main()
