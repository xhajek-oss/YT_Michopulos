import os
import json
import requests
from datetime import datetime, timezone, timedelta

YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

CONFIG_FILE = "config.json"
STATE_FILE = "data/seen_videos.json"

# Kontrolujeme videa maximálně 36 hodin zpětně.

# To dává rezervu při kontrole 1× denně.

MAX_AGE_DAYS = 1.5

MAX_RESULTS = 50

# David Svoboda – ukrajinista/historik.

# Hledáme ho více způsoby a napříč různými YouTube kanály.

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

```
with open(filename, "r", encoding="utf-8") as f:
    return json.load(f)
```

def save_json(filename, data):
directory = os.path.dirname(filename)

```
if directory:
    os.makedirs(directory, exist_ok=True)

with open(filename, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

def youtube_search(query):
url = "https://www.googleapis.com/youtube/v3/search"

```
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
```

def send_telegram(message):
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

```
data = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": message,
    "disable_web_page_preview": False,
}

response = requests.post(url, data=data, timeout=30)
response.raise_for_status()
```

def main():
config = load_json(
CONFIG_FILE,
{
"keywords": [],
"exclude_channels": {},
},
)

```
state = load_json(
    STATE_FILE,
    {
        "seen_video_ids": [],
        "initialized_keywords": [],
        "last_checked_at": None,
    },
)

seen_video_ids = set(state.get("seen_video_ids", []))
initialized_keywords = set(state.get("initialized_keywords", []))

now = datetime.now(timezone.utc)
max_age = timedelta(days=MAX_AGE_DAYS)

all_new_videos = []

print(f"Kontrola: {now.isoformat()}")
print(f"Limit stáří videa: {MAX_AGE_DAYS} dne")

for keyword in config.get("keywords", []):
    exclude_channels = set(
        config.get("exclude_channels", {}).get(keyword, [])
    )

    print()
    print(f"=== {keyword} ===")

    # Některá jména hledáme pomocí více dotazů.
    if keyword in SEARCH_QUERIES:
        queries = SEARCH_QUERIES[keyword]

        print("Hledám přes:")
        for query in queries:
            print(f"  - {query}")

        results_by_id = {}

        for query in queries:
            results = youtube_search(query)

            print(f"Výsledků pro '{query}': {len(results)}")

            for item in results:
                video_id = item.get("id", {}).get("videoId")

                if video_id:
                    # Stejné video nalezené více dotazy uložíme pouze jednou.
                    results_by_id[video_id] = item

        results = list(results_by_id.values())

        print(f"Celkem unikátních výsledků: {len(results)}")

    else:
        results = youtube_search(keyword)

        print(f"Výsledků: {len(results)}")

    # Pokud je jméno v monitoru poprvé,
    # aktuální videa pouze uložíme jako výchozí stav.
    # Starší videa tak nezpůsobí lavinu notifikací.
    keyword_initialized = keyword in initialized_keywords

    for item in results:
        video_id = item.get("id", {}).get("videoId")
        snippet = item.get("snippet", {})

        if not video_id:
            continue

        title = snippet.get("title", "Bez názvu")
        channel_title = snippet.get(
            "channelTitle",
            "Neznámý kanál"
        )
        channel_id = snippet.get("channelId")
        published_at = snippet.get("publishedAt")

        if not published_at:
            continue

        published = datetime.fromisoformat(
            published_at.replace("Z", "+00:00")
        )

        age = now - published

        print()
        print(f"VIDEO: {title}")
        print(f"KANÁL: {channel_title}")
        print(f"DATUM: {published_at}")

        # Vyloučené kanály.
        if channel_id in exclude_channels:
            print("→ VYŘAZENO: vyloučený kanál")
            continue

        # Příliš stará videa.
        if age > max_age:
            print("→ VYŘAZENO: video je starší než limit")
            continue

        # První kontrola nového jména:
        # video se uloží, ale Telegram se neposílá.
        if not keyword_initialized:
            print("→ PRVNÍ KONTROLA: uloženo jako výchozí stav")
            seen_video_ids.add(video_id)
            continue

        # Video už bylo dříve oznámeno.
        if video_id in seen_video_ids:
            print("→ VYŘAZENO: video už bylo oznámeno")
            continue

        video_url = f"https://www.youtube.com/watch?v={video_id}"

        all_new_videos.append(
            {
                "keyword": keyword,
                "title": title,
                "channel_title": channel_title,
                "published_at": published_at,
                "url": video_url,
                "video_id": video_id,
            }
        )

        seen_video_ids.add(video_id)

        print("→ NOVÉ VIDEO")

    initialized_keywords.add(keyword)

print()
print(f"Nových videí: {len(all_new_videos)}")

# Odeslání nových videí do Telegramu.
for video in all_new_videos:
    message = (
        f"🎬 Nové video\n\n"
        f"{video['title']}\n\n"
        f"Kanál: {video['channel_title']}\n"
        f"Publikováno: {video['published_at']}\n\n"
        f"{video['url']}"
    )

    try:
        send_telegram(message)
        print(f"Telegram OK: {video['title']}")
    except Exception as e:
        print(f"Telegram ERROR: {e}")

# Uchováváme posledních 500 oznámených videí.
state["seen_video_ids"] = list(seen_video_ids)[-500:]

state["initialized_keywords"] = list(initialized_keywords)

state["last_checked_at"] = now.isoformat()

save_json(STATE_FILE, state)

print("Stav uložen.")
```

if **name** == "**main**":
main()
