import os
import json
import base64
import urllib.parse
import urllib.request


TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GH_TOKEN = os.environ["GH_TOKEN"]

CONFIG_FILE = "config.json"

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


def get_keywords(config):
    return config.get("keywords", [])


def handle_command(text):

    parts = text.strip().split(maxsplit=2)

    if not parts:
        return

    command = parts[0].lower()

    if command != "/yt":
        return

    # ---------------------------------------------------------
    # /yt
    # ---------------------------------------------------------

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

    keywords = get_keywords(config)

    # ---------------------------------------------------------
    # /yt seznam
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # /yt pridej JMENO
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # /yt odeber JMENO
    # ---------------------------------------------------------

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

        # Odstraníme případné výjimky
        # spojené s tímto klíčovým slovem.
        exclude_channels = config.get(
            "exclude_channels",
            {}
        )

        exclude_channels.pop(
            keyword,
            None
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

    # ---------------------------------------------------------
    # Neznámý příkaz
    # ---------------------------------------------------------

    send_message(
        "❓ Neznámý YouTube příkaz.\n\n"
        "Použij:\n"
        "/yt seznam\n"
        "/yt pridej JMENO\n"
        "/yt odeber JMENO"
    )


def main():

    print("YouTube Telegram bot spuštěn.")

    offset = None

    while True:

        data = {
            "timeout": 50,
            "allowed_updates": json.dumps(
                ["message"]
            ),
        }

        if offset is not None:
            data["offset"] = offset

        updates = telegram_request(
            "getUpdates",
            data,
        )

        for update in updates.get(
            "result",
            []
        ):

            offset = update["update_id"] + 1

            message = update.get(
                "message"
            )

            if not message:
                continue

            chat_id = str(
                message["chat"]["id"]
            )

            # Bezpečnost:
            # reagujeme pouze na tvůj Telegram chat.
            if chat_id != str(
                TELEGRAM_CHAT_ID
            ):
                continue

            text = message.get(
                "text",
                ""
            )

            if text.startswith("/yt"):

                try:
                    handle_command(text)

                except Exception as e:

                    print(
                        f"Chyba: {e}"
                    )

                    send_message(
                        "❌ Nastala chyba při "
                        "zpracování příkazu."
                    )


if __name__ == "__main__":
    main()
