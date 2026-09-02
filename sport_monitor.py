import os
import re
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

TIMEZONE = ZoneInfo("Europe/Prague")

DYNAMO_URL = "https://www.hcdynamo.cz/matches/MUZ"
ONEPLAY_HOCKEY_URL = "https://www.oneplay.cz/sport/hokej"

IDNES_SEARCH_URL = "https://www.google.com/search"
SLEDOVANITV_SEARCH_URL = "https://www.google.com/search"

CT_BIATHLON_URL = "https://www.ceskatelevize.cz/tv-program/Biatlon/"
CT_ATHLETICS_URL = "https://www.ceskatelevize.cz/tv-program/Atletika/"

CONFIG_FILE = "sport_config.json"
STATE_FILE = "data/sport_state.json"

REQUEST_TIMEOUT = 30

# ---------------------------------------------------------

# HTTP

# ---------------------------------------------------------

HEADERS = {
"User-Agent": (
"Mozilla/5.0 (X11; Linux x86_64) "
"AppleWebKit/537.36 (KHTML, like Gecko) "
"Chrome/138.0 Safari/537.36"
),
"Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
}

def get_url(url, params=None):
response = requests.get(
url,
params=params,
headers=HEADERS,
timeout=REQUEST_TIMEOUT,
)
response.raise_for_status()
return response.text

# ---------------------------------------------------------

# JSON / STATE

# ---------------------------------------------------------

def load_json(filename, default):
if not os.path.exists(filename):
return default

```
try:
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)
except Exception:
    return default
```

def save_json(filename, data):
directory = os.path.dirname(filename)

```
if directory:
    os.makedirs(directory, exist_ok=True)

with open(filename, "w", encoding="utf-8") as f:
    json.dump(
        data,
        f,
        ensure_ascii=False,
        indent=2,
    )
```

# ---------------------------------------------------------

# TEXT HELPERS

# ---------------------------------------------------------

def normalize_text(text):
text = text.replace("\xa0", " ")
text = re.sub(r"\s+", " ", text)
return text.strip()

def normalize_team_name(name):
name = normalize_text(name).lower()

```
replacements = {
    "hc dynamo pardubice": "dynamo pardubice",
    "dynamo pardubice": "dynamo pardubice",
    "hc dyn. pardubice": "dynamo pardubice",
    "gks tychy": "gks tychy",
}

return replacements.get(name, name)
```

def teams_match(text, team_a, team_b):
normalized = normalize_text(text).lower()

```
a = normalize_team_name(team_a)
b = normalize_team_name(team_b)

return a in normalized and b in normalized
```

def is_live_broadcast(text):
text = normalize_text(text).lower()

```
recording_words = [
    "záznam",
    "zaznam",
    "replay",
    "repríza",
    "repriza",
    "ze záznamu",
    "ze zaznamu",
]

for word in recording_words:
    if word in text:
        return False

live_words = [
    "přímý přenos",
    "primy prenos",
    "živě",
    "zive",
    "live",
    "živý přenos",
    "zivy prenos",
]

return any(word in text for word in live_words)
```

def clean_channel_name(channel):
channel = normalize_text(channel)

```
replacements = {
    "Sport 1": "Sport1",
    "Sport 2": "Sport2",
    "Sport 3": "Sport3",
    "Sport 4": "Sport4",
    "Oneplay Sport 1": "Oneplay Sport 1",
    "Oneplay Sport 2": "Oneplay Sport 2",
    "Oneplay Sport 3": "Oneplay Sport 3",
    "Oneplay Sport 4": "Oneplay Sport 4",
}

return replacements.get(channel, channel)
```

def is_oneplay_sport(channel):
channel = channel.lower()

```
return bool(
    re.search(
        r"\boneplay\s+sport\s*[1-4]\b",
        channel,
    )
)
```

# ---------------------------------------------------------

# DYNAMO

# ---------------------------------------------------------

def extract_date_time(text):
patterns = [
r"\b(?:po|út|ut|st|čt|ct|pá|pa|so|ne)\s+"
r"(\d{1,2}).\s*(\d{1,2}).\s*(\d{4})[,\s]+"
r"(\d{1,2}):(\d{2})",

```
    r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})[,\s]+"
    r"(\d{1,2}):(\d{2})",
]

for pattern in patterns:
    match = re.search(pattern, text, re.IGNORECASE)

    if not match:
        continue

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))
    hour = int(match.group(4))
    minute = int(match.group(5))

    try:
        return datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=TIMEZONE,
        )
    except ValueError:
        pass

return None
```

def find_team_names_near_date(text):
"""
Pokusí se najít dvojici týmů v okolí data zápasu.

```
Dynamo web používá různé HTML komponenty.
Proto nejdříve hledáme typické názvy týmů v celém
textu a následně kombinujeme datum + následující
týmové informace.
"""

known_opponents = [
    "GKS Tychy",
    "Rögle BK",
    "Växjö Lakers",
    "Vaxjo Lakers",
    "KooKoo",
    "SaiPa",
    "Bordeaux",
    "Hradec Králové",
    "Mountfield HK",
    "HC Sparta Praha",
    "HC Kometa Brno",
    "HC Škoda Plzeň",
    "Bílí Tygři Liberec",
    "Oceláři Třinec",
    "HC Vítkovice Ridera",
    "BK Mladá Boleslav",
    "HC Olomouc",
    "HC Energie Karlovy Vary",
    "Rytíři Kladno",
    "Motor České Budějovice",
    "Dukla Jihlava",
    "HC Litvínov",
]

for opponent in known_opponents:
    if opponent.lower() in text.lower():
        return "Dynamo Pardubice", opponent

return None
```

def parse_dynamo_matches():
print()
print("=== DYNAMO PARDUBICE ===")
print(f"Zdroj: {DYNAMO_URL}")

```
try:
    html = get_url(DYNAMO_URL)
except Exception as e:
    print(f"Chyba při načítání Dynama: {e}")
    return []

soup = BeautifulSoup(html, "html.parser")

# -----------------------------------------------------
# 1. JSON-LD
# -----------------------------------------------------

matches = []

for script in soup.find_all(
    "script",
    attrs={"type": "application/ld+json"},
):
    raw = script.string

    if not raw:
        continue

    try:
        data = json.loads(raw)
    except Exception:
        continue

    objects = data if isinstance(data, list) else [data]

    for obj in objects:
        if not isinstance(obj, dict):
            continue

        start_date = obj.get("startDate")
        name = obj.get("name", "")

        if not start_date or not name:
            continue

        if "dynamo" not in name.lower():
            continue

        try:
            dt = datetime.fromisoformat(
                start_date.replace("Z", "+00:00")
            )

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TIMEZONE)
            else:
                dt = dt.astimezone(TIMEZONE)

        except Exception:
            continue

        parts = re.split(
            r"\s+(?:vs\.?|–|-|—)\s+",
            name,
            flags=re.IGNORECASE,
        )

        if len(parts) != 2:
            continue

        home = normalize_text(parts[0])
        away = normalize_text(parts[1])

        matches.append(
            {
                "sport": "hockey",
                "competition": "HC Dynamo Pardubice",
                "home": home,
                "away": away,
                "datetime": dt,
                "tv_channel": None,
                "tv_confirmed": False,
            }
        )

if matches:
    print(f"JSON-LD nalezených zápasů: {len(matches)}")
    return deduplicate_matches(matches)

# -----------------------------------------------------
# 2. Textová fallback metoda
# -----------------------------------------------------

text = normalize_text(soup.get_text(" ", strip=True))

date_matches = list(
    re.finditer(
        r"\b(?:po|út|ut|st|čt|ct|pá|pa|so|ne)\s+"
        r"\d{1,2}\.\s*\d{1,2}\.\s*\d{4}[,\s]+"
        r"\d{1,2}:\d{2}",
        text,
        re.IGNORECASE,
    )
)

print(f"Datumové bloky nalezené v textu: {len(date_matches)}")

for match in date_matches:
    date_text = match.group(0)
    dt = extract_date_time(date_text)

    if not dt:
        continue

    start = max(0, match.start() - 300)
    end = min(len(text), match.end() + 500)

    nearby = text[start:end]

    if "dynamo pardubice" not in nearby.lower():
        continue

    teams = find_team_names_near_date(nearby)

    if not teams:
        continue

    home, away = teams

    matches.append(
        {
            "sport": "hockey",
            "competition": "HC Dynamo Pardubice",
            "home": home,
            "away": away,
            "datetime": dt,
            "tv_channel": None,
            "tv_confirmed": False,
        }
    )

matches = deduplicate_matches(matches)

print(f"Výsledných zápasů Dynamo: {len(matches)}")

for match in matches:
    print(
        f"  {match['datetime'].strftime('%Y-%m-%d %H:%M')} "
        f"{match['home']} vs {match['away']}"
    )

return matches
```

def deduplicate_matches(matches):
result = {}
dynamo_names = {
"dynamo pardubice",
"hc dynamo pardubice",
}

```
for match in matches:
    dt = match["datetime"]

    home = normalize_team_name(match["home"])
    away = normalize_team_name(match["away"])

    if home in dynamo_names:
        key = (
            dt.strftime("%Y-%m-%d %H:%M"),
            home,
            away,
        )
    elif away in dynamo_names:
        key = (
            dt.strftime("%Y-%m-%d %H:%M"),
            away,
            home,
        )
    else:
        key = (
            dt.strftime("%Y-%m-%d %H:%M"),
            home,
            away,
        )

    result[key] = match

return list(result.values())
```

# ---------------------------------------------------------

# WEB SEARCH

# ---------------------------------------------------------

def google_search(query, domain=None):
if domain:
query = f"site:{domain} {query}"

```
params = {
    "q": query,
    "hl": "cs",
    "num": 10,
}

try:
    html = get_url(
        IDNES_SEARCH_URL,
        params=params,
    )
except Exception as e:
    print(f"Vyhledávání selhalo: {e}")
    return ""

return html
```

def extract_google_result_text(html):
if not html:
return ""

```
soup = BeautifulSoup(html, "html.parser")

return normalize_text(
    soup.get_text(" ", strip=True)
)
```

# ---------------------------------------------------------

# ONEPLAY TV

# ---------------------------------------------------------

def verify_oneplay(event):
home = event["home"]
away = event["away"]
date = event["datetime"].date()

```
query = (
    f'"{home}" "{away}" '
    f'{date.strftime("%-d.%-m.%Y")}'
)

print()
print(
    f"TV Oneplay: {home} vs {away} "
    f"{date.isoformat()}"
)

try:
    html = get_url(ONEPLAY_HOCKEY_URL)
except Exception as e:
    print(f"Oneplay chyba: {e}")
    return None

soup = BeautifulSoup(html, "html.parser")
text = normalize_text(soup.get_text(" ", strip=True))

if not teams_match(text, home, away):
    print("Oneplay: konkrétní zápas nenalezen.")
    return None

# Hledáme Oneplay Sport 1-4 v blízkosti zápasu.
team_pos = text.lower().find(
    normalize_team_name(home)
)

if team_pos < 0:
    team_pos = text.lower().find(
        normalize_team_name(away)
    )

nearby = text[
    max(0, team_pos - 300):
    min(len(text), team_pos + 700)
]

if not is_live_broadcast(nearby):
    # Oneplay hokejová stránka nemusí obsahovat
    # doslovné "živě". Pokud je zápas uveden přímo
    # v aktuálním sportovním přehledu, pokračujeme.
    print(
        "Oneplay: zápas nalezen, ale "
        "explicitní live text nebyl nalezen."
    )

channel_match = re.search(
    r"\b(Oneplay\s+Sport\s*[1-4])\b",
    nearby,
    re.IGNORECASE,
)

if not channel_match:
    print("Oneplay: Oneplay Sport 1-4 nenalezen.")
    return None

channel = clean_channel_name(
    channel_match.group(1)
)

if not is_oneplay_sport(channel):
    return None

print(
    f"Oneplay potvrzuje: {channel}"
)

return {
    "source": "Oneplay",
    "channel": channel,
    "live": True,
}
```

# ---------------------------------------------------------

# iDNES

# ---------------------------------------------------------

def verify_idnes(event):
home = event["home"]
away = event["away"]
date = event["datetime"].date()

```
query = (
    f'"{home}" "{away}" '
    f'{date.strftime("%d.%m.%Y")} '
    f'Přímý přenos'
)

print()
print(
    f"TV iDNES: {home} vs {away} "
    f"{date.isoformat()}"
)

html = google_search(
    query,
    "tvprogram.idnes.cz",
)

text = extract_google_result_text(html)

if not teams_match(text, home, away):
    print("iDNES: zápas nenalezen.")
    return None

if not is_live_broadcast(text):
    print("iDNES: nenalezen přímý přenos.")
    return None

channel_patterns = [
    r"\bSport\s*[1-4]\b",
    r"\bČT sport\b",
    r"\bNova Sport\s*[1-6]\b",
    r"\bOneplay Sport\s*[1-4]\b",
]

for pattern in channel_patterns:
    match = re.search(
        pattern,
        text,
        re.IGNORECASE,
    )

    if match:
        channel = clean_channel_name(
            match.group(0)
        )

        print(
            f"iDNES potvrzuje: {channel}"
        )

        return {
            "source": "iDNES",
            "channel": channel,
            "live": True,
        }

print("iDNES: kanál nenalezen.")
return None
```

# ---------------------------------------------------------

# SLEDOVANITV

# ---------------------------------------------------------

def verify_sledovanitv(event):
home = event["home"]
away = event["away"]
date = event["datetime"].date()

```
query = (
    f'"{home}" "{away}" '
    f'{date.strftime("%-d.%-m.%Y")}'
)

print()
print(
    f"TV SledovaniTV: {home} vs {away} "
    f"{date.isoformat()}"
)

html = google_search(
    query,
    "sledovanitv.cz",
)

text = extract_google_result_text(html)

if not teams_match(text, home, away):
    print("SledovaniTV: zápas nenalezen.")
    return None

if not is_live_broadcast(text):
    print(
        "SledovaniTV: nalezen pouze záznam "
        "nebo bez potvrzení živého přenosu."
    )
    return None

channel_patterns = [
    r"\bSport\s*[1-4]\b",
    r"\bČT sport\b",
    r"\bNova Sport\s*[1-6]\b",
    r"\bOneplay Sport\s*[1-4]\b",
]

for pattern in channel_patterns:
    match = re.search(
        pattern,
        text,
        re.IGNORECASE,
    )

    if match:
        channel = clean_channel_name(
            match.group(0)
        )

        print(
            f"SledovaniTV potvrzuje: {channel}"
        )

        return {
            "source": "SledovaniTV",
            "channel": channel,
            "live": True,
        }

print(
    "SledovaniTV: kanál nenalezen."
)

return None
```

# ---------------------------------------------------------

# TV DOUBLE CHECK

# ---------------------------------------------------------

def verify_tv(event):
"""
Pravidla:

```
1. Oneplay Sport 1-4:
   Jeden potvrzený údaj z Oneplay stačí.

2. Ostatní kanály:
   Musí existovat dvě nezávislá potvrzení
   stejného kanálu.

3. Záznam:
   Nikdy se nepovažuje za potvrzení.

4. Pokud si zdroje odporují:
   kanál se neuvede.
"""

print()
print(
    "=== TV OVĚŘENÍ ==="
)

oneplay = verify_oneplay(event)

# Výjimka Oneplay Sport.
if oneplay:
    channel = oneplay["channel"]

    if is_oneplay_sport(channel):
        print(
            "→ Oneplay Sport výjimka: "
            "1 zdroj stačí."
        )

        event["tv_channel"] = channel
        event["tv_confirmed"] = True

        return event

# Běžné kanály:
# kontrolujeme dva nezávislé zdroje.
source_a = verify_idnes(event)
source_b = verify_sledovanitv(event)

if not source_a or not source_b:
    print(
        "→ TV NEPOTVRZENO: chybí dva nezávislé zdroje."
    )

    event["tv_channel"] = None
    event["tv_confirmed"] = False

    return event

channel_a = clean_channel_name(
    source_a["channel"]
)
channel_b = clean_channel_name(
    source_b["channel"]
)

print(
    f"Zdroj A: {channel_a}"
)
print(
    f"Zdroj B: {channel_b}"
)

if channel_a != channel_b:
    print(
        "→ TV NEPOTVRZENO: zdroje se rozcházejí."
    )

    event["tv_channel"] = None
    event["tv_confirmed"] = False

    return event

if not source_a["live"] or not source_b["live"]:
    print(
        "→ TV NEPOTVRZENO: jeden zdroj není live."
    )

    event["tv_channel"] = None
    event["tv_confirmed"] = False

    return event

print(
    f"→ TV POTVRZENO DVĚMA ZDROJI: {channel_a}"
)

event["tv_channel"] = channel_a
event["tv_confirmed"] = True

return event
```

# ---------------------------------------------------------

# ČT PROGRAM

# ---------------------------------------------------------

def parse_ct_program(url, sport_name):
print()
print(
f"=== ČT PROGRAM – {sport_name} ==="
)
print(f"Zdroj: {url}")

```
try:
    html = get_url(url)
except Exception as e:
    print(
        f"ČT chyba: {e}"
    )
    return []

soup = BeautifulSoup(html, "html.parser")

text = normalize_text(
    soup.get_text(" ", strip=True)
)

events = []

# ČT stránka se může měnit.
# Proto hledáme především datum + čas
# a sportovní kontext.
date_pattern = re.compile(
    r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})"
    r".{0,100}?"
    r"(\d{1,2}):(\d{2})",
    re.IGNORECASE,
)

for match in date_pattern.finditer(text):
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))
    hour = int(match.group(4))
    minute = int(match.group(5))

    try:
        dt = datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=TIMEZONE,
        )
    except ValueError:
        continue

    start = max(
        0,
        match.start() - 300,
    )
    end = min(
        len(text),
        match.end() + 500,
    )

    nearby = text[start:end]

    if sport_name.lower() not in nearby.lower():
        continue

    events.append(
        {
            "sport": sport_name,
            "competition": sport_name,
            "home": sport_name,
            "away": "",
            "datetime": dt,
            "tv_channel": "ČT sport",
            "tv_confirmed": True,
        }
    )

return deduplicate_matches(
    events
)
```

# ---------------------------------------------------------

# SPORT EVENTS

# ---------------------------------------------------------

def get_sport_events(config):
events = []

```
if config.get("dynamo_pardubice", False):
    dynamo_events = parse_dynamo_matches()

    for event in dynamo_events:
        event = verify_tv(event)
        events.append(event)

if config.get("diamond_league", False):
    athletics = parse_ct_program(
        CT_ATHLETICS_URL,
        "Atletika",
    )

    events.extend(
        athletics
    )

if config.get("biathlon", False):
    biathlon = parse_ct_program(
        CT_BIATHLON_URL,
        "Biatlon",
    )

    events.extend(
        biathlon
    )

# MS v hokeji je zatím vypnuté.
# Pokud se zapne, bude potřeba ještě
# explicitně určit rozsah:
# všechny zápasy / pouze ČR.
if config.get(
    "world_hockey_championship",
    False,
):
    print()
    print(
        "MS V HOKEJI JE ZAPNUTÉ, "
        "ALE ROZSAH SLEDOVÁNÍ NENÍ IMPLEMENTOVÁN."
    )

return sorted(
    events,
    key=lambda event: event["datetime"],
)
```

# ---------------------------------------------------------

# FORMAT

# ---------------------------------------------------------

def format_event(event):
dt = event["datetime"].astimezone(
TIMEZONE
)

```
home = event["home"]
away = event["away"]

if away:
    title = f"{home} vs {away}"
else:
    title = home

lines = [
    title,
    f"📅 {dt.strftime('%Y-%m-%d')}",
    f"🕐 {dt.strftime('%H:%M')}",
]

if event.get("tv_confirmed") and event.get(
    "tv_channel"
):
    lines.append(
        f"📺 {event['tv_channel']}"
    )

return "\n".join(lines)
```

# ---------------------------------------------------------

# DAILY MESSAGE

# ---------------------------------------------------------

def make_daily_message(events, now):
today = now.date()

```
todays_events = [
    event
    for event in events
    if event["datetime"].astimezone(
        TIMEZONE
    ).date() == today
]

if not todays_events:
    return None

groups = {
    "Dynamo Pardubice": [],
    "Atletika": [],
    "Biatlon": [],
    "MS v hokeji": [],
}

for event in todays_events:
    sport = event["sport"]

    if sport == "hockey":
        groups["Dynamo Pardubice"].append(
            event
        )
    elif sport == "Atletika":
        groups["Atletika"].append(
            event
        )
    elif sport == "Biatlon":
        groups["Biatlon"].append(
            event
        )
    else:
        groups["MS v hokeji"].append(
            event
        )

lines = [
    "🔔 SPORT DNES",
    "",
]

section_emojis = {
    "Dynamo Pardubice": "🏒",
    "Atletika": "🏃",
    "Biatlon": "🎿",
    "MS v hokeji": "🏒",
}

for section, section_events in groups.items():
    if not section_events:
        continue

    lines.append(
        f"{section_emojis[section]} {section}"
    )
    lines.append("")

    for event in section_events:
        lines.append(
            format_event(event)
        )
        lines.append("")

return "\n".join(lines).strip()
```

# ---------------------------------------------------------

# WEEKLY MESSAGE

# ---------------------------------------------------------

def make_weekly_message(events, now):
monday = now.date() - timedelta(
days=now.weekday()
)

```
sunday = monday + timedelta(
    days=6
)

week_events = [
    event
    for event in events
    if monday
    <= event["datetime"].astimezone(
        TIMEZONE
    ).date()
    <= sunday
]

if not week_events:
    return None

lines = [
    "📅 SPORT – PŘEHLED TÝDNE",
    "",
]

groups = {
    "Dynamo Pardubice": [],
    "Atletika": [],
    "Biatlon": [],
    "MS v hokeji": [],
}

for event in week_events:
    sport = event["sport"]

    if sport == "hockey":
        groups["Dynamo Pardubice"].append(
            event
        )
    elif sport == "Atletika":
        groups["Atletika"].append(
            event
        )
    elif sport == "Biatlon":
        groups["Biatlon"].append(
            event
        )
    else:
        groups["MS v hokeji"].append(
            event
        )

section_emojis = {
    "Dynamo Pardubice": "🏒",
    "Atletika": "🏃",
    "Biatlon": "🎿",
    "MS v hokeji": "🏒",
}

total = 0

for section, section_events in groups.items():
    if not section_events:
        continue

    lines.append(
        f"{section_emojis[section]} {section}"
    )
    lines.append("")

    for event in section_events:
        lines.append(
            format_event(event)
        )
        lines.append("")

        total += 1

lines.append(
    f"Celkem {total} přenosů"
)

return "\n".join(lines).strip()
```

# ---------------------------------------------------------

# TELEGRAM

# ---------------------------------------------------------

def send_telegram(message):
url = (
f"https://api.telegram.org/"
f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
)

```
data = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": message,
    "disable_web_page_preview": False,
}

response = requests.post(
    url,
    data=data,
    timeout=REQUEST_TIMEOUT,
)

response.raise_for_status()
```

# ---------------------------------------------------------

# MAIN

# ---------------------------------------------------------

def main():
import sys

```
mode = "daily"

if len(sys.argv) > 1:
    mode = sys.argv[1].lower()

if mode not in {
    "daily",
    "weekly",
}:
    print(
        "Neznámý režim. Použij daily nebo weekly."
    )
    raise SystemExit(1)

print()
print(
    "======================================"
)
print(
    "SPORT MONITOR"
)
print(
    "======================================"
)
print(
    f"Režim: {mode}"
)

now = datetime.now(
    TIMEZONE
)

print(
    f"Aktuální čas: {now.isoformat()}"
)

config = load_json(
    CONFIG_FILE,
    {
        "dynamo_pardubice": True,
        "diamond_league": True,
        "biathlon": True,
        "world_hockey_championship": False,
    },
)

print()
print(
    "Konfigurace:"
)
print(
    json.dumps(
        config,
        ensure_ascii=False,
        indent=2,
    )
)

events = get_sport_events(
    config
)

print()
print(
    f"Celkem nalezených sportovních událostí: "
    f"{len(events)}"
)

if mode == "daily":
    message = make_daily_message(
        events,
        now,
    )
else:
    message = make_weekly_message(
        events,
        now,
    )

if not message:
    print()
    print(
        "Žádné relevantní sportovní události."
    )
    print(
        "Telegram se neposílá."
    )
    return

print()
print(
    "--------------------------------------"
)
print(
    "ZPRÁVA:"
)
print(
    "--------------------------------------"
)
print(message)
print(
    "--------------------------------------"
)

try:
    send_telegram(message)
    print(
        "Telegram OK."
    )
except Exception as e:
    print(
        f"Telegram ERROR: {e}"
    )
    raise
```

if **name** == "**main**":
main()
