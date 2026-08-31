import os
import urllib.parse
import urllib.request


BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


message = """🧪 TEST

GitHub Actions právě úspěšně spustil Python skript.

Telegram propojení funguje! ✅
"""


url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

data = urllib.parse.urlencode({
    "chat_id": CHAT_ID,
    "text": message,
}).encode()


request = urllib.request.Request(url, data=data)

with urllib.request.urlopen(request) as response:
    result = response.read().decode()

print(result)
