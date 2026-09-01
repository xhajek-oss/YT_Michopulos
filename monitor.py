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


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "seen_video_ids": [],
            "last_checked_at": None
        }

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    os.makedirs("data", exist_ok=True)

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def search_youtube(keyword):
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

    with urllib.request.urlopen(url) as response:
        return json.load(response)


def send_telegram(keyword, title, published, video_url):
    message = (
        f"🎬 Nové YouTube video\n\n"
        f"🔎 Klíčové slovo: {keyword}\n"
        f"📺 {title}\n"
        f"📅 {published}\n\n"
        f"🔗 {video_url}"
    )

    telegram_url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    telegram_data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }).encode("utf-8")

    request = urllib.request.Request(
        telegram_url,
        data=telegram_data,
        method="POST",
    )

    with urllib.request.urlopen(request) as response:
        result = json.load(response)

    if not result.get("ok"):
        raise RuntimeError(f"Telegram chyba: {result}")


def main():
    config = load_config()
    keywords = config.get("keywords", [])

    if not keywords:
        print("V config.json nejsou žádná klíčová slova.")
        return

    state_exists = os.path.exists(STATE_FILE)
    state = load_state()

    seen_video_ids = set(state.get("seen_video_ids", []))

    now = datetime.now(timezone.utc)

    print(f"Kontrola: {now.isoformat()}")
    print(f"Klíčová slova: {keywords}")
    print()

    found_new = []

    for keyword in keywords:
        print(f"Hledám: {keyword}")

        data = search_youtube(keyword)
        items = data.get("items", [])

        print(f"  Výsledků: {len(items)}")

        for item in items:
            video_id = item["id"]["videoId"]
            snippet = item["snippet"]

            title = snippet["title"]
            published = snippet["publishedAt"]

            video_url = f"https://www.youtube.com/watch?v={video_id}"

            if video_id in seen_video_ids:
                continue

            found_new.append({
                "video_id": video_id,
                "keyword": keyword,
                "title": title,
                "published": published,
                "video_url": video_url,
            })

    print()

    # PRVNÍ SPUŠTĚNÍ
    # Existující výsledky pouze uložíme.
    # Telegram se neposílá.
    if not state_exists:
        print("První spuštění – vytvářím základní seznam videí.")

        for video in found_new:
            seen_video_ids.add(video["video_id"])

        state["seen_video_ids"] = list(seen_video_ids)[-500:]
        state["last_checked_at"] = now.isoformat()

        save_state(state)

        print(f"Zapamatováno videí: {len(found_new)}")
        print("Telegram zpráva nebyla odeslána.")

        return

    # DALŠÍ SPUŠTĚNÍ
    if not found_new:
        print("Žádná nová videa.")

    else:
        print(f"Nalezeno nových videí: {len(found_new)}")

        for video in found_new:

            print()
            print(f"NOVÉ: {video['title']}")
            print(video["video_url"])

            send_telegram(
                video["keyword"],
                video["title"],
                video["published"],
                video["video_url"],
            )

            seen_video_ids.add(video["video_id"])

    # Uložíme posledních 500 ID.
    state["seen_video_ids"] = list(seen_video_ids)[-500:]
    state["last_checked_at"] = now.isoformat()

    save_state(state)

    print()
    print("Stav monitoringu uložen.")


if __name__ == "__main__":
    main()
