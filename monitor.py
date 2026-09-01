import os
import json
import urllib.parse
import urllib.request

YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KEYWORD = "Michopulos"

# 1. Vyhledání nejnovějšího videa na YouTube
params = {
    "part": "snippet",
    "q": KEYWORD,
    "type": "video",
    "maxResults": 1,
    "order": "date",
    "key": YOUTUBE_API_KEY,
}

url = "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(params)

with urllib.request.urlopen(url) as response:
    data = json.load(response)

items = data.get("items", [])

if not items:
    print(f"Nenalezeno žádné video pro: {KEYWORD}")
    raise SystemExit(0)

video = items[0]
video_id = video["id"]["videoId"]
title = video["snippet"]["title"]
published = video["snippet"]["publishedAt"]
video_url = f"https://www.youtube.com/watch?v={video_id}"

print("Nalezeno:")
print(title)
print(video_url)

# 2. Odeslání zprávy do Telegramu
message = (
    f"🎬 Nové vyhledávání YouTube\n\n"
    f"🔎 Hledaný výraz: {KEYWORD}\n"
    f"📺 {title}\n"
    f"📅 {published}\n\n"
    f"🔗 {video_url}"
)

telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

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

print("Telegram response:", result)
