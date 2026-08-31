import os
import urllib.parse
import urllib.request
import urllib.error
import json


BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def telegram_request(method, data=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    if data:
        data = urllib.parse.urlencode(data).encode()

    request = urllib.request.Request(url, data=data)

    try:
        with urllib.request.urlopen(request) as response:
            return response.read().decode()

    except urllib.error.HTTPError as error:
        body = error.read().decode()
        print(f"Telegram API HTTP error: {error.code}")
        print(f"Telegram response: {body}")
        raise


print("Testing Telegram bot...")

# 1. Ověříme token
print("Checking bot token...")

result = telegram_request("getMe")

print(result)

# 2. Pošleme testovací zprávu
print("Sending test message...")

result = telegram_request(
    "sendMessage",
    {
        "chat_id": CHAT_ID,
        "text": "🧪 Test z GitHub Actions funguje! ✅",
    },
)

print(result)

print("SUCCESS")
