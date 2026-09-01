import os
import urllib.parse
import urllib.request
import json

API_KEY = os.environ["YOUTUBE_API_KEY"]
KEYWORD = "Michopulos"

params = {
    "part": "snippet",
    "q": KEYWORD,
    "type": "video",
    "maxResults": 5,
    "order": "date",
    "key": API_KEY,
}

url = "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(params)

print(f"Hledám na YouTube: {KEYWORD}")
print()

with urllib.request.urlopen(url) as response:
    data = json.load(response)

for i, item in enumerate(data.get("items", []), start=1):
    video_id = item["id"]["videoId"]
    title = item["snippet"]["title"]
    published = item["snippet"]["publishedAt"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    print(f"{i}. {title}")
    print(f"   Publikováno: {published}")
    print(f"   {video_url}")
    print()
