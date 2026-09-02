```python
import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone


YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


CONFIG_FILE = "config.json"
STATE_FILE = "data/seen_videos.json"


def youtube_search(keyword):
    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "maxResults": 50,
        "order": "date",
        "key": YOUTUBE_API_KEY,
    }

    url = (
        "https://www.googleapis.com/youtube/v3/search?"
        + urllib.parse.urlencode(params)
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "YT-Michopulos-Monitor",
        },
    )

    with urllib.request.urlopen(request) as response:
        return json.load(response)


def send_telegram_message(text):
    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    data = urllib.parse.urlencode(
        {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
    )

    with urllib.request.urlopen(request) as response:
        return json.load(response)


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "seen_video_ids": [],
            "last_checked_at": None,
        }

    with open(STATE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_state(state):
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


def get_video_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


def main():
    print("YouTube Monitor - jednorázová kontrola.")

    config = load_config()
    state = load_state()

    keywords = config.get("keywords", [])
    exclude_channels = config.get(
        "exclude_channels",
        {},
    )

    seen_video_ids = state.get(
        "seen_video_ids",
        [],
    )

    first_run = len(seen_video_ids) == 0

    print(
        f"Sleduji {len(keywords)} klíčových slov."
    )

    if not keywords:
        print(
            "Není nastaveno žádné klíčové slovo."
        )

        state["last_checked_at"] = (
            datetime.now(timezone.utc).isoformat()
        )

        save_state(state)
        return

    all_seen_ids = set(seen_video_ids)

    new_videos = []

    for keyword in keywords:

        print(
            f"Kontroluji YouTube pro: {keyword}"
        )

        try:
            result = youtube_search(keyword)

        except Exception as error:
            print(
                f"Chyba při hledání '{keyword}': "
                f"{error}"
            )
            continue

        excluded_ids = set(
            exclude_channels.get(
                keyword,
                [],
            )
        )

        items = result.get(
            "items",
            [],
        )

        for item in items:

            video_id = item.get(
                "id",
                {},
            ).get(
                "videoId"
            )

            snippet = item.get(
                "snippet",
                {}
            )

            if not video_id:
                continue

            channel_id = snippet.get(
                "channelId",
                "",
            )

            channel_title = snippet.get(
                "channelTitle",
                "",
            )

            title = snippet.get(
                "title",
                "",
            )

            published_at = snippet.get(
                "publishedAt",
                "",
            )

            if channel_id in excluded_ids:
                print(
                    f"Ignoruji video z vyloučeného "
                    f"kanálu: {channel_title}"
                )
                continue

            if video_id in all_seen_ids:
                continue

            video = {
                "video_id": video_id,
                "keyword": keyword,
                "title": title,
                "channel_title": channel_title,
                "channel_id": channel_id,
                "published_at": published_at,
            }

            new_videos.append(video)
            all_seen_ids.add(video_id)

    # Při prvním spuštění pouze vytvoříme základ.
    # Nechceme uživatele zahlcovat starými videi.
    if first_run:

        print(
            f"První spuštění - ukládám "
            f"{len(all_seen_ids)} videí jako základ."
        )

    else:

        print(
            f"Nových videí: {len(new_videos)}"
        )

        for video in new_videos:

            message = (
                "🎬 Nové video na YouTube\n\n"
                f"🔎 Hledání: {video['keyword']}\n"
                f"📺 Kanál: {video['channel_title']}\n"
                f"📝 {video['title']}\n\n"
                f"{get_video_url(video['video_id'])}"
            )

            try:
                send_telegram_message(message)

                print(
                    f"Odesláno Telegramem: "
                    f"{video['title']}"
                )

            except Exception as error:
                print(
                    f"Chyba při odesílání Telegramu: "
                    f"{error}"
                )

    # Uchováme maximálně posledních 500 videí.
    updated_seen_ids = list(all_seen_ids)

    if len(updated_seen_ids) > 500:
        updated_seen_ids = updated_seen_ids[-500:]

    state = {
        "seen_video_ids": updated_seen_ids,
        "last_checked_at": (
            datetime.now(timezone.utc).isoformat()
        ),
    }

    save_state(state)

    print(
        "YouTube kontrola dokončena."
    )


if __name__ == "__main__":
    main()
```
