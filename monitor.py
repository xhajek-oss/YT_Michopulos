import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

print("================================")
print("YouTube Monitor")
print("================================")

YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

CONFIG_FILE = "config.json"
STATE_FILE = "data/seen_videos.json"

MAX_AGE_DAYS = 2


def load_json(filename, default):
    if not os.path.exists(filename):
        return default

    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename, data):
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def youtube_search(keyword):
    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "maxResults": 50,
        "order": "date",
        "key": YOUTUBE_API_KEY
    }

    url = "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(params)

    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }).encode("utf-8")

    request = urllib.request.Request(url, data=data, method="POST")

    with urllib.request.urlopen(request) as response:
        response.read()


config = load_json(CONFIG_FILE, {
    "keywords": [],
    "exclude_channels": {}
})

state = load_json(STATE_FILE, {
    "seen_video_ids": [],
    "initialized_keywords": [],
    "last_checked_at": None
})

seen_video_ids = set(state.get("seen_video_ids", []))
initialized_keywords = set(state.get("initialized_keywords", []))

new_videos = []

now = datetime.now(timezone.utc)
minimum_date = now - timedelta(days=MAX_AGE_DAYS)

for keyword in config.get("keywords", []):
    print(f"Kontroluji: {keyword}")

    excluded_channels = set(
        config.get("exclude_channels", {}).get(keyword, [])
    )

    try:
        results = youtube_search(keyword)
    except Exception as e:
        print(f"Chyba při hledání '{keyword}': {e}")
        continue

    current_video_ids = []

    for item in results.get("items", []):
        video_id = item["id"]["videoId"]
        snippet = item["snippet"]

        channel_id = snippet["channelId"]
        channel_title = snippet["channelTitle"]
        title = snippet["title"]
        published_at = snippet["publishedAt"]

        if channel_id in excluded_channels:
            print(f"Ignoruji vyloučený kanál: {channel_title}")
            continue

        published_date = datetime.fromisoformat(
            published_at.replace("Z", "+00:00")
        )

        if published_date < minimum_date:
            continue

        current_video_ids.append(video_id)

        if keyword not in initialized_keywords:
            continue

        if video_id not in seen_video_ids:
            new_videos.append({
                "video_id": video_id,
                "keyword": keyword,
                "channel_title": channel_title,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "published_at": published_at
            })

    if keyword not in initialized_keywords:
        print(
            f"První kontrola '{keyword}': "
            f"ukládám {len(current_video_ids)} videí jako základ."
        )

        initialized_keywords.add(keyword)

    seen_video_ids.update(current_video_ids)


new_videos.sort(key=lambda x: x["published_at"])

print(f"Nových videí: {len(new_videos)}")

for video in new_videos:
    message = (
        "🎬 Nové video na YouTube\n\n"
        f"🔎 {video['keyword']}\n"
        f"📺 {video['channel_title']}\n"
        f"📝 {video['title']}\n\n"
        f"{video['url']}"
    )

    try:
        send_telegram(message)
        print(f"Odesláno: {video['title']}")
    except Exception as e:
        print(f"Chyba při odesílání na Telegram: {e}")


state["seen_video_ids"] = list(seen_video_ids)[-500:]
state["initialized_keywords"] = list(initialized_keywords)
state["last_checked_at"] = now.isoformat()

save_json(STATE_FILE, state)

print("Kontrola dokončena.")
