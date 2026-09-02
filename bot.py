import os
import json
import base64
import urllib.parse
import urllib.request
from datetime import datetime, timezone


TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GH_TOKEN = os.environ["GH_TOKEN"]
YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]


CONFIG_FILE = "config.json"
STATE_FILE = "data/seen_videos.json"

GITHUB_REPO = "xhajek-oss/YT_Michopulos"
GITHUB_BRANCH = "main"


def telegram_request(method, data=None):
    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/{method}"
    )

    if data is not None:
        encoded = urllib.parse.urlencode(data).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=encoded,
            method="POST",
        )
    else:
        request = urllib.request.Request(url)

    with urllib.request.urlopen(request) as response:
        return json.load(response)


def send_message(text):
    telegram_request(
        "sendMessage",
        {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
        },
    )


def github_request(method, path, data=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/{path}"

    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "YT-Michopulos-Bot",
    }

    body = None

    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )

    with urllib.request.urlopen(request) as response:
        return json.load(response)


def load_config_from_github():
    result = github_request(
        "GET",
        f"contents/{CONFIG_FILE}?ref={GITHUB_BRANCH}",
    )

    decoded = base64.b64decode(
        result["content"]
    ).decode("utf-8")

    config = json.loads(decoded)

    return config, result["sha"]


def save_config_to_github(config, sha):
    content = json.dumps(
        config,
        ensure_ascii=False,
        indent=2,
    )

    encoded = base64.b64encode(
        content.encode("utf-8")
    ).decode("utf-8")

    github_request(
        "PUT",
        f"contents/{CONFIG_FILE}",
        {
            "message": "Update YouTube monitoring keywords",
            "content": encoded,
            "sha": sha,
            "branch": GITHUB_BRANCH,
        },
    )


def handle_command(text):
    parts = text.strip().split(maxsplit=2)

    if not parts:
        return

    command = parts[0].lower()

    if command != "/yt":
        return

    if len(parts) == 1:
        send_message(
            "📺 YouTube monitoring\n\n"
            "Dostupné příkazy:\n"
            "/yt seznam\n"
            "/yt pridej JMENO\n"
            "/yt odeber JMENO"
        )
        return

    action = parts[1].lower()

    config, sha = load_config_from_github()

    keywords = config.get("keywords", [])

    if action == "seznam":

        if not keywords:
            send_message(
                "📺 YouTube monitoring\n\n"
                "Momentálně nesleduji žádná klíčová slova."
            )
            return

        message = (
            "📺 YouTube monitoring\n\n"
            "Sleduji:\n"
        )

        for keyword in keywords:
            message += f"• {keyword}\n"

        send_message(message)
        return

    if action == "pridej":

        if len(parts) < 3:
            send_message(
                "Použití:\n"
                "/yt pridej JMENO"
            )
            return

        keyword = parts[2].strip()

        if keyword in keywords:
            send_message(
                f"ℹ️ „{keyword}“ už sleduji."
            )
            return

        keywords.append(keyword)

        config["keywords"] = keywords

        save_config_to_github(
            config,
            sha,
        )

        send_message(
            f"✅ Přidáno: {keyword}\n\n"
            f"📺 YouTube monitoring nyní sleduje "
            f"{len(keywords)} klíčových slov."
        )

        return

    if action == "odeber":

        if len(parts) < 3:
            send_message(
                "Použití:\n"
                "/yt odeber JMENO"
            )
            return

        keyword = parts[2].strip()

        if keyword not in keywords:
            send_message(
                f"ℹ️ „{keyword}“ není v seznamu."
            )
            return

        keywords.remove(keyword)

        config["keywords"] = keywords

        exclude_channels = config.get(
            "exclude_channels",
            {},
        )

        exclude_channels.pop(
            keyword,
            None,
        )

        config["exclude_channels"] = exclude_channels

        save_config_to_github(
            config,
            sha,
        )

        send_message(
            f"✅ Odebráno: {keyword}"
        )

        return

    send_message(
        "❓ Neznámý YouTube příkaz.\n\n"
        "Použij:\n"
        "/yt seznam\n"
        "/yt pridej JMENO\n"
        "/yt odeber JMENO"
    )


def process_telegram_updates():
    print("Kontroluji Telegram...")

    updates = telegram_request(
        "getUpdates",
        {
            "timeout": 0,
            "allowed_updates": json.dumps(["message"]),
        },
    )

    updates_list = updates.get(
        "result",
        [],
    )

    print(
        f"Nalezeno nových Telegram zpráv: "
        f"{len(updates_list)}"
    )

    last_update_id = None

    for update in updates_list:

        update_id = update["update_id"]

        if (
            last_update_id is None
            or update_id > last_update_id
        ):
            last_update_id = update_id

        message = update.get("message")

        if not message:
            continue

        chat_id = str(
            message["chat"]["id"]
        )

        if chat_id != str(TELEGRAM_CHAT_ID):
            continue

        text = message.get(
            "text",
            "",
        )

        if not text.startswith("/yt"):
            continue

        try:
            handle_command(text)

        except Exception as error:
            print(
                f"Chyba při zpracování příkazu: "
                f"{error}"
            )

            send_message(
                "❌ Nastala chyba při zpracování příkazu."
            )

    if last_update_id is not None:
        telegram_request(
            "getUpdates",
            {
                "offset": last_update_id + 1,
                "timeout": 0,
                "allowed_updates": json.dumps(["message"]),
            },
        )

    print("Telegram kontrola dokončena.")


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


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "seen_video_ids": [],
            "last_checked_at": None,
        }

    with open(
        STATE_FILE,
        "r",
        encoding="utf-8",
    ) as file:
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


def check_youtube():
    print("Kontroluji YouTube...")

    config, _ = load_config_from_github()

    state = load_state()

    keywords = config.get(
        "keywords",
        [],
    )

    exclude_channels = config.get(
        "exclude_channels",
        {},
    )

    seen_video_ids = state.get(
        "seen_video_ids",
        [],
    )

    first_run = len(seen_video_ids) == 0

    all_seen_ids = set(seen_video_ids)

    new_videos = []

    for keyword in keywords:

        print(
            f"Kontroluji: {keyword}"
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

        for item in result.get(
            "items",
            [],
        ):

            video_id = item.get(
                "id",
                {},
            ).get(
                "videoId"
            )

            snippet = item.get(
                "snippet",
                {},
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

            if channel_id in excluded_ids:
                print(
                    f"Ignoruji vyloučený kanál: "
                    f"{channel_title}"
                )
                continue

            if video_id in all_seen_ids:
                continue

            new_videos.append(
                {
                    "video_id": video_id,
                    "keyword": keyword,
                    "title": title,
                    "channel_title": channel_title,
                }
            )

            all_seen_ids.add(video_id)

    if first_run:

        print(
            "První spuštění - ukládám nalezená "
            "videa jako základ."
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
                f"https://www.youtube.com/watch?v="
                f"{video['video_id']}"
            )

            try:
                send_message(message)

                print(
                    f"Telegram: odesláno - "
                    f"{video['title']}"
                )

            except Exception as error:
                print(
                    f"Chyba při Telegram notifikaci: "
                    f"{error}"
                )

    updated_seen_ids = list(all_seen_ids)

    if len(updated_seen_ids) > 500:
        updated_seen_ids = updated_seen_ids[-500:]

    save_state(
        {
            "seen_video_ids": updated_seen_ids,
            "last_checked_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }
    )

    print("YouTube kontrola dokončena.")


def main():
    print("================================")
    print("YT Michopulos - jednorázový běh")
    print("================================")

    try:
        process_telegram_updates()

    except Exception as error:
        print(
            f"Telegram chyba: {error}"
        )

    try:
        check_youtube()

    except Exception as error:
        print(
            f"YouTube chyba: {error}"
        )

    print("Běh dokončen.")


if __name__ == "__main__":
    main()
