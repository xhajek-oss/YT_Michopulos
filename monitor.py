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
    directory = os.path.dirname(filename)

    if directory:
        os.makedirs(directory, exist_ok=True)

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

    url = (
        "https://www.googleapis.com/youtube/v3/search?"
        + urllib.parse.urlencode(params)
    )

    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def send_telegram(message):
    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        method="POST"
    )

    with urllib.request.urlopen(request) as response:
        response.read()


def is_david_svoboda_video(title, description):
    title_lower = title.lower()
    text = f"{title} {description}".lower()

    relevant_words = [
        "ukrajina",
        "ukrajině",
        "ukrajinu",
        "ukrajinsk",
        "ukrajinista",
        "ukrajin",
        "ukrajinc",
        "rusko",
        "rusk",
        "putin",
        "zelensky",
        "zelenskyj",
        "válka",
        "invaze",
        "krym",
        "donbas",
        "kyjev",
        "kyjiv",
        "bander",
        "petljur",
        "upa"
    ]

    identity_words = [
        "ukrajinista",
        "historik",
        "historie",
        "historikem",
        "historika",
        "ukrajiny",
        "ukrajins"
    ]

    wrong_person_words = [
        "advokát",
        "advokacie",
        "právník",
        "právní",
        "soudce",
        "soud",
        "fotbal",
        "football",
        "hokej",
        "tenis",
        "atletika",
        "atlet",
        "olympiáda",
        "olympi",
        "sportovec",
        "reprezentace",
        "liga",
        "gól",
        "gol",
        "trenér",
        "zápas",
        "mistrovství",
        "pětiboji",
        "pětiboj"
    ]

    matched_relevant = [
        word for word in relevant_words
        if word in text
    ]

    matched_identity = [
        word for word in identity_words
        if word in text
    ]

    matched_wrong_person = [
        word for word in wrong_person_words
        if word in title_lower
    ]

    if matched_wrong_person:
        return False, (
            "jiný David Svoboda: "
            + ", ".join(matched_wrong_person)
        )

    if not matched_relevant:
        return False, "bez tématu Ukrajina/Rusko"

    if not matched_identity:
        return False, (
            "chybí označení historik/ukrajinista"
        )

    return True, (
        "relevantní: "
        + ", ".join(matched_relevant)
    )


def get_david_svoboda_results():
    search_queries = [
        "David Svoboda Ukrajina",
        "David Svoboda ukrajinista",
        "David Svoboda historik"
    ]

    all_results = {}

    for search_query in search_queries:

        print("")
        print(
            f"Hledám Davida Svobodu přes: "
            f"{search_query}"
        )

        try:
            results = youtube_search(search_query)

        except Exception as e:
            print(
                f"Chyba při hledání "
                f"'{search_query}': {e}"
            )
            continue

        print(
            f"Výsledků: "
            f"{len(results.get('items', []))}"
        )

        for item in results.get("items", []):

            video_id = item["id"]["videoId"]

            if video_id not in all_results:
                all_results[video_id] = item

    return list(all_results.values())


config = load_json(CONFIG_FILE, {
    "keywords": [],
    "exclude_channels": {}
})

state = load_json(STATE_FILE, {
    "seen_video_ids": [],
    "initialized_keywords": [],
    "last_checked_at": None
})

seen_video_ids = set(
    state.get("seen_video_ids", [])
)

initialized_keywords = set(
    state.get("initialized_keywords", [])
)

new_videos = []

now = datetime.now(timezone.utc)

minimum_date = now - timedelta(
    days=MAX_AGE_DAYS
)


for keyword in config.get("keywords", []):

    print("")
    print("--------------------------------")
    print(f"Kontroluji: {keyword}")
    print("--------------------------------")

    excluded_channels = set(
        config.get("exclude_channels", {}).get(keyword, [])
    )

    if keyword == "David Svoboda":

        items = get_david_svoboda_results()

        print("")
        print(
            f"Celkem unikátních výsledků: "
            f"{len(items)}"
        )

    else:

        try:
            results = youtube_search(keyword)
            items = results.get("items", [])

        except Exception as e:
            print(
                f"Chyba při hledání "
                f"'{keyword}': {e}"
            )
            continue

    current_video_ids = []

    for item in items:

        video_id = item["id"]["videoId"]
        snippet = item["snippet"]

        channel_id = snippet["channelId"]
        channel_title = snippet["channelTitle"]
        title = snippet["title"]
        description = snippet.get("description", "")
        published_at = snippet["publishedAt"]

        published_date = datetime.fromisoformat(
            published_at.replace("Z", "+00:00")
        )

        print("")
        print(f"VIDEO: {title}")
        print(f"KANÁL: {channel_title}")
        print(f"DATUM: {published_at}")

        if channel_id in excluded_channels:

            print(
                "❌ VYŘAZENO: vyloučený kanál"
            )

            continue

        if published_date < minimum_date:

            print(
                f"❌ VYŘAZENO: starší než "
                f"{MAX_AGE_DAYS} dny"
            )

            continue

        if keyword == "David Svoboda":

            relevant, reason = is_david_svoboda_video(
                title,
                description
            )

            if not relevant:

                print(
                    f"❌ VYŘAZENO: {reason}"
                )

                continue

            print(
                f"✅ RELEVANTNÍ: {reason}"
            )

        else:

            print("✅ RELEVANTNÍ")

        current_video_ids.append(video_id)

        if keyword not in initialized_keywords:

            print(
                "ℹ️ Pouze základ – "
                "video nebude odesláno."
            )

            continue

        if video_id in seen_video_ids:

            print(
                "ℹ️ Už bylo zaznamenáno."
            )

            continue

        print(
            "🆕 NOVÉ VIDEO – "
            "bude odesláno na Telegram."
        )

        new_videos.append({
            "video_id": video_id,
            "keyword": keyword,
            "channel_title": channel_title,
            "title": title,
            "url": (
                "https://www.youtube.com/watch?v="
                + video_id
            ),
            "published_at": published_at
        })

    if keyword not in initialized_keywords:

        print("")
        print(
            f"První kontrola '{keyword}': "
            f"ukládám {len(current_video_ids)} "
            f"videí jako základ."
        )

        initialized_keywords.add(keyword)

    seen_video_ids.update(current_video_ids)


new_videos.sort(
    key=lambda x: x["published_at"]
)

print("")
print("================================")
print(f"Nových videí: {len(new_videos)}")
print("================================")


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

        print(
            f"📨 Odesláno: {video['title']}"
        )

    except Exception as e:

        print(
            f"Chyba při odesílání na Telegram: {e}"
        )


state["seen_video_ids"] = list(
    seen_video_ids
)[-500:]

state["initialized_keywords"] = list(
    initialized_keywords
)

state["last_checked_at"] = now.isoformat()

save_json(
    STATE_FILE,
    state
)

print("")
print("Kontrola dokončena.")
