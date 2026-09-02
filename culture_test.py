import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re


SMS_URL = "https://www.smsticket.cz/mista/2033-kd-hronovicka-pardubice"
TICKETPORTAL_URL = "https://www.ticketportal.cz/venue/KD-Hronovicka-Hronovicka-406-Pardubice"
GOOUT_URL = "https://goout.net/cs/kulturni-dum-hronovicka/vzeofe/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    )
}


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    print(f"HTTP {response.status_code}: {url}")

    response.raise_for_status()

    return response.text


def parse_sms_ticket(html):
    soup = BeautifulSoup(html, "html.parser")

    events = []

    # Na stránce SMS Ticket jsou akce v blocích s odkazy.
    for link in soup.find_all("a", href=True):

        title = link.get_text(" ", strip=True)

        if not title:
            continue

        # Hledáme okolní text odkazu.
        parent = link.parent
        block = parent.get_text(" ", strip=True) if parent else ""

        # Rozšíříme hledání o několik nadřazených elementů.
        current = parent

        for _ in range(4):
            if current is None:
                break

            text = current.get_text(" ", strip=True)

            if len(text) > len(block):
                block = text

            current = current.parent

        # Cena
        price_match = re.search(
            r"(\d[\d\s]*)\s*Kč",
            block,
            re.IGNORECASE,
        )

        price = None

        if price_match:
            price = price_match.group(1).strip() + " Kč"

        # Datum ve formátu 15.10.2026
        date_match = re.search(
            r"(\d{1,2}\.\d{1,2}\.\d{4})",
            block,
        )

        date = date_match.group(1) if date_match else None

        # Čas
        time_match = re.search(
            r"(?:at\s*)?(\d{1,2}:\d{2})",
            block,
        )

        time = time_match.group(1) if time_match else None

        # Akce musí mít datum.
        if not date:
            continue

        # Ignorujeme navigační a obecné odkazy.
        ignored = [
            "more info",
            "more about venue",
            "menu",
            "tickets",
            "for attenders",
            "for organizers",
        ]

        if title.lower() in ignored:
            continue

        events.append(
            {
                "title": title,
                "date": date,
                "time": time,
                "price": price,
                "url": link.get("href"),
            }
        )

    # Deduplikace
    unique = {}

    for event in events:
        key = (
            event["title"],
            event["date"],
            event["time"],
        )

        unique[key] = event

    return list(unique.values())


def parse_ticketportal(html):
    soup = BeautifulSoup(html, "html.parser")

    events = []

    text = soup.get_text("\n", strip=True)

    # Ticketportal má jednotlivé akce jako odkazy.
    for link in soup.find_all("a", href=True):

        title = link.get_text(" ", strip=True)

        if not title:
            continue

        # Hledáme nadřazený blok.
        current = link.parent
        block = ""

        for _ in range(5):
            if current is None:
                break

            candidate = current.get_text(" ", strip=True)

            if len(candidate) > len(block):
                block = candidate

            current = current.parent

        # Datum Ticketportalu:
        # 4 Říj. 2026
        date_match = re.search(
            r"(\d{1,2})\s+"
            r"(Led\.|Ún\.|Bře\.|Dub\.|Kvě\.|Čvn\.|Čvc\.|Srp\.|"
            r"Zář\.|Říj\.|Lis\.|Pros\.)\s+"
            r"(\d{4})",
            block,
            re.IGNORECASE,
        )

        if not date_match:
            continue

        day = date_match.group(1)
        month = date_match.group(2)
        year = date_match.group(3)

        date = f"{day}. {month} {year}"

        # Čas
        time_match = re.search(
            r"\b(\d{1,2}:\d{2})\b",
            block,
        )

        time = time_match.group(1) if time_match else None

        # Stav prodeje
        if "vyprodáno" in block.lower():
            availability = "Vyprodáno"
        elif "koupit" in block.lower():
            availability = "V prodeji"
        else:
            availability = None

        ignored = [
            "KD Hronovická",
            "Pardubice",
            "Navigovat",
            "Koupit",
        ]

        if title in ignored:
            continue

        events.append(
            {
                "title": title,
                "date": date,
                "time": time,
                "availability": availability,
                "url": link.get("href"),
            }
        )

    unique = {}

    for event in events:
        key = (
            event["title"],
            event["date"],
            event["time"],
        )

        unique[key] = event

    return list(unique.values())


def test_goout(html):
    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text(" ", strip=True)

    if "Načítám" in text:
        return {
            "status": "JS_ONLY",
            "message": (
                "GoOut stránka se načetla, ale seznam akcí "
                "není dostupný v HTML."
            ),
        }

    return {
        "status": "HTML",
        "message": "GoOut obsahuje data přímo v HTML.",
    }


def print_sms(events):
    print()
    print("=" * 70)
    print("SMS TICKET")
    print("=" * 70)

    if not events:
        print("Nenalezeny žádné akce.")
        return

    for event in events:
        print()
        print(f"Název:   {event['title']}")
        print(f"Datum:   {event['date']}")
        print(f"Čas:     {event['time']}")
        print(f"Cena:    {event['price']}")
        print(f"URL:     {event['url']}")


def print_ticketportal(events):
    print()
    print("=" * 70)
    print("TICKETPORTAL")
    print("=" * 70)

    if not events:
        print("Nenalezeny žádné akce.")
        return

    for event in events:
        print()
        print(f"Název:        {event['title']}")
        print(f"Datum:        {event['date']}")
        print(f"Čas:          {event['time']}")
        print(f"Dostupnost:   {event['availability']}")
        print(f"URL:          {event['url']}")


def main():

    print("=" * 70)
    print("TEST MONITORU – KULTURA / KD HRONOVICKÁ")
    print("=" * 70)
    print()

    # SMS Ticket
    try:
        html = get_page(SMS_URL)
        events = parse_sms_ticket(html)
        print_sms(events)

    except Exception as e:
        print()
        print("SMS Ticket CHYBA:")
        print(repr(e))

    # Ticketportal
    try:
        html = get_page(TICKETPORTAL_URL)
        events = parse_ticketportal(html)
        print_ticketportal(events)

    except Exception as e:
        print()
        print("Ticketportal CHYBA:")
        print(repr(e))

    # GoOut
    try:
        html = get_page(GOOUT_URL)
        result = test_goout(html)

        print()
        print("=" * 70)
        print("GOOUT")
        print("=" * 70)
        print()
        print(f"Stav:     {result['status']}")
        print(f"Výsledek: {result['message']}")

    except Exception as e:
        print()
        print("GoOut CHYBA:")
        print(repr(e))


if __name__ == "__main__":
    main()
