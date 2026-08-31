import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


CHANNEL_ID = os.environ["YOUTUBE_CHANNEL_ID"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

RSS_URL = (
    f"https://www.youtube.com/feeds/videos.xml?"
    f"channel_id={CHANNEL_ID}"
)

STATE_FILE = "state.json"


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"videos": []}

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_videos():
    with urllib.request.urlopen(RSS_URL) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)

    namespace = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
    }

    videos = []

    for entry in root.findall("atom:entry", namespace):
        video_id = entry.find("yt:videoId", namespace).text
        title = entry.find("atom:title", namespace).text

        videos.append({
            "id": video_id,
            "title": title,
            "url": f"https://www.youtube.com/watch?v={video_id}"
        })

    return videos


def send_telegram(title, url):
    message = f"🎬 Nové video!\n\n{title}\n\n{url}"

    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message,
    }).encode()

    request = urllib.request.Request(api_url, data=data)

    with urllib.request.urlopen(request) as response:
        response.read()


def main():
    state = load_state()
    known_videos = set(state["videos"])

    videos = get_videos()

    new_videos = [
        video for video in videos
        if video["id"] not in known_videos
    ]

    # První spuštění:
    # uloží současná videa bez posílání starých upozornění.
    if not state["videos"]:
        state["videos"] = [video["id"] for video in videos]
        save_state(state)

        print("Initial setup completed.")
        return

    for video in reversed(new_videos):
        send_telegram(video["title"], video["url"])
        print(f"Sent: {video['title']}")

    state["videos"] = list(
        dict.fromkeys(
            state["videos"] + [video["id"] for video in videos]
        )
    )[-50:]

    save_state(state)


if __name__ == "__main__":
    main()
