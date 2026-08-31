import os
import urllib.parse
import urllib.request


BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


# --------------------------------------------------
# SIMULACE NOVÉHO YOUTUBE VIDEA
# --------------------------------------------------

video_title = "Petros Michopulos – Testovací video"

video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


message = f"""🎬 NOVÉ VIDEO

Nalezeno nové video obsahující:
Michopulos

📺 {video_title}

🔗 {video_url}
"""


# --------------------------------------------------
# ODESLÁNÍ DO TELEGRAMU
# --------------------------------------------------

telegram_url = (
    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
)

data = urllib.parse.urlencode({
    "chat_id": CHAT_ID,
    "text": message,
}).encode()


request = urllib.request.Request(
    telegram_url,
    data=data
)


with urllib.request.urlopen(request) as response:
    result = response.read().decode()


print("Telegram response:")
print(result)

print("✅ Test dokončen.")
