import os
import re
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

TIMEZONE = ZoneInfo("Europe/Prague")

DYNAMO_URL = "https://www.hcdynamo.cz/matches/MUZ"

WORLD_ATHLETICS_URL = (
"https://worldathletics.org/competition/calendar-results"
)

CT_BIATHLON_URL = (
"https://www.ceskatelevize.cz/tv-program/Biatlon/"
)

CT_ATHLETICS_URL = (
"https://www.ceskatelevize.cz/tv-program/Atletika/"
)

ONEPLAY_HOCKEY_URL = (
"https://www.oneplay.cz/sport/hokej"
)

CONFIG_FILE = "sport_config.json"
STATE_FILE = "data/sport_state.json"

REQUEST_TIMEOUT = 30

HEADERS = {
"User-Agent": (
"Mozilla/5.0 (X11; Linux x86_64) "
"AppleWebKit/537.36 "
"(KHTML, like Gecko) "
"Chrome/138.0 Safari/537.36"
),
"Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
}

# =========================================================

# HTTP

# =========================================================

def get_url(url, params=None):
response = requests.get(
url,
params=params,
headers=HEADERS,
timeout=REQUEST_TIMEOUT,
)

```
response.raise_for_status()

return response.text
```

# =========================================================

# JSON

# =========================================================

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

# =========================================================

# TEXT

# =========================================================

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
}

return replacements.get(name, name)
```

def teams_match(text, team_a, team_b):
text = normalize_text(text).lower()

```
a = normalize_team_name(team_a)
b = normalize_team_name(team_b)

return a in text and b in text
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
    "živý přenos",
    "zivy prenos",
    "live",
]

return any(
    word in text
    for word in live_words
)
```

def clean_channel_name(channel):
channel = normalize_text(channel)

```
replacements = {
    "Sport 1": "Sport1",
    "Sport 2": "Sport2",
    "Sport 3": "Sport3",
    "Sport 4": "Sport4",
}

return replacements.get(
    channel,
    channel,
)
```

def is_oneplay_sport(channel):
return bool(
re.search(
r"\boneplay\s+sport\s*[1-4]\b",
channel,
re.IGNORECASE,
)
)

# =========================================================

# DYNAMO

# =========================================================

def extract_date_time(text):
patterns = [
r"\b(?:po|út|ut|st|čt|ct|pá|pa|so|ne)\s+"
r"(\d{1,2}).\s*(\d{1,2}).\s*(\d{4})"
r"[,\s]+(\d{1,2}):(\d{2})",

```
    r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})"
    r"[,\s]+(\d{1,2}):(\d{2})",
]

for pattern in patterns:
    match = re.search(
        pattern,
        text,
        re.IGNORECASE,
    )

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
        continue

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
    print(
        f"Chyba při načítání Dynama: {e}"
    )
    return []

soup = BeautifulSoup(
    html,
    "html.parser",
)

matches = []

# -----------------------------------------------------
# JSON-LD
# -----------------------------------------------------

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

    objects = (
        data
        if isinstance(data, list)
        else [data]
    )

    for obj in objects:
        if not isinstance(obj, dict):
            continue

        start_date = obj.get(
            "startDate"
        )

        name = obj.get(
            "name",
            "",
        )

        if not start_date or not name:
            continue

        if "dynamo" not in name.lower():
            continue

        try:
            dt = datetime.fromisoformat(
                start_date.replace(
                    "Z",
                    "+00:00",
                )
            )

            if dt.tzinfo is None:
                dt = dt.replace(
                    tzinfo=TIMEZONE
                )
            else:
                dt = dt.astimezone(
                    TIMEZONE
                )

        except Exception:
            continue

        parts = re.split(
            r"\s+(?:vs\.?|–|-|—)\s+",
            name,
            flags=re.IGNORECASE,
        )

        if len(parts) != 2:
            continue

        matches.append(
            {
                "sport": "hockey",
                "competition": (
                    "HC Dynamo Pardubice"
                ),
                "home": normalize_text(
                    parts[0]
                ),
                "away": normalize_text(
                    parts[1]
                ),
                "datetime": dt,
                "tv_channel": None,
                "tv_confirmed": False,
            }
        )

# -----------------------------------------------------
# Text fallback
# -----------------------------------------------------

if not matches:
    text = normalize_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    date_pattern = re.compile(
        r"\b(?:po|út|ut|st|čt|ct|pá|pa|so|ne)\s+"
        r"\d{1,2}\.\s*\d{1,2}\.\s*\d{4}"
        r"[,\s]+\d{1,2}:\d{2}",
        re.IGNORECASE,
    )

    dates = list(
        date_pattern.finditer(text)
    )

    print(
        f"Datumové bloky: {len(dates)}"
    )

    for date_match in dates:
        dt = extract_date_time(
            date_match.group(0)
        )

        if not dt:
            continue

        start = max(
            0,
            date_match.start() - 400,
        )

        end = min(
            len(text),
            date_match.end() + 600,
        )

        nearby = text[start:end]

        if (
            "dynamo pardubice"
            not in nearby.lower()
        ):
            continue

        # Pokusíme se najít soupeře.
        candidate = nearby

        team_patterns = [
            r"Dynamo Pardubice\s+"
            r"(?:VS|vs|–|-|—)\s+"
            r"([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"
            r"a-záčďéěíňóřšťúůýž"
            r"0-9 .&'-]+)",

            r"([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"
            r"a-záčďéěíňóřšťúůýž"
            r"0-9 .&'-]+)\s+"
            r"(?:VS|vs|–|-|—)\s+"
            r"Dynamo Pardubice",
        ]

        opponent = None

        for pattern in team_patterns:
            m = re.search(
                pattern,
                candidate,
            )

            if m:
                opponent = normalize_text(
                    m.group(1)
                )
                break

        if not opponent:
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

            for known in known_opponents:
                if known.lower() in candidate.lower():
                    opponent = known
                    break

        if not opponent:
            continue

        matches.append(
            {
                "sport": "hockey",
                "competition": (
                    "HC Dynamo Pardubice"
                ),
                "home": (
                    "Dynamo Pardubice"
                ),
                "away": opponent,
                "datetime": dt,
                "tv_channel": None,
                "tv_confirmed": False,
            }
        )

matches = deduplicate_matches(
    matches
)

print(
    f"Výsledných zápasů Dynamo: "
    f"{len(matches)}"
)

for event in matches:
    print(
        event["datetime"].strftime(
            "%Y-%m-%d %H:%M"
        ),
        event["home"],
        "vs",
        event["away"],
    )

return matches
```

def deduplicate_matches(matches):
result = {}

```
for event in matches:
    dt = event["datetime"]

    key = (
        dt.strftime(
            "%Y-%m-%d %H:%M"
        ),
        normalize_team_name(
            event["home"]
        ),
        normalize_team_name(
            event["away"]
        ),
    )

    result[key] = event

return list(
    result.values()
)
```

# =========================================================

# TV SEARCH

# =========================================================

def google_search(
query,
domain=None,
):
if domain:
query = (
f"site:{domain} {query}"
)

```
params = {
    "q": query,
    "hl": "cs",
    "num": 10,
}

try:
    return get_url(
        "https://www.google.com/search",
        params=params,
    )
except Exception as e:
    print(
        f"Vyhledávání selhalo: {e}"
    )
    return ""
```

def extract_search_text(html):
if not html:
return ""

```
soup = BeautifulSoup(
    html,
    "html.parser",
)

return normalize_text(
    soup.get_text(
        " ",
        strip=True,
    )
)
```

# =========================================================

# ONEPLAY

# =========================================================

def verify_oneplay(event):
home = event["home"]
away = event["away"]
date = event["datetime"].date()

```
query = (
    f'"{home}" "{away}" '
    f'{date.day}.{date.month}.{date.year}'
)

print()
print(
    f"Oneplay: {home} vs {away}"
)

html = google_search(
    query,
    "oneplay.cz",
)

text = extract_search_text(
    html
)

if not teams_match(
    text,
    home,
    away,
):
    print(
        "Oneplay: zápas nenalezen."
    )
    return None

channel_match = re.search(
    r"\b(Oneplay\s+Sport\s*[1-4])\b",
    text,
    re.IGNORECASE,
)

if not channel_match:
    print(
        "Oneplay: kanál Oneplay Sport "
        "1-4 nenalezen."
    )
    return None

channel = channel_match.group(1)

channel = normalize_text(
    channel
)

if not is_oneplay_sport(
    channel
):
    return None

if any(
    word in text.lower()
    for word in [
        "záznam",
        "zaznam",
        "replay",
    ]
):
    print(
        "Oneplay: nalezen záznam."
    )
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

# =========================================================

# IDNES

# =========================================================

def verify_idnes(event):
home = event["home"]
away = event["away"]
date = event["datetime"].date()

```
query = (
    f'"{home}" "{away}" '
    f'{date.day}.{date.month}.{date.year} '
    f'"Přímý přenos"'
)

print()
print(
    f"iDNES: {home} vs {away}"
)

html = google_search(
    query,
    "tvprogram.idnes.cz",
)

text = extract_search_text(
    html
)

if not teams_match(
    text,
    home,
    away,
):
    print(
        "iDNES: zápas nenalezen."
    )
    return None

if not is_live_broadcast(
    text
):
    print(
        "iDNES: není potvrzen "
        "přímý přenos."
    )
    return None

patterns = [
    r"\bSport\s*[1-4]\b",
    r"\bČT sport\b",
    r"\bNova Sport\s*[1-6]\b",
    r"\bOneplay Sport\s*[1-4]\b",
]

for pattern in patterns:
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

print(
    "iDNES: kanál nenalezen."
)

return None
```

# =========================================================

# SLEDOVANITV

# =========================================================

def verify_sledovanitv(event):
home = event["home"]
away = event["away"]
date = event["datetime"].date()

```
query = (
    f'"{home}" "{away}" '
    f'{date.day}.{date.month}.{date.year}'
)

print()
print(
    f"SledovaniTV: {home} vs {away}"
)

html = google_search(
    query,
    "sledovanitv.cz",
)

text = extract_search_text(
    html
)

if not teams_match(
    text,
    home,
    away,
):
    print(
        "SledovaniTV: zápas nenalezen."
    )
    return None

if not is_live_broadcast(
    text
):
    print(
        "SledovaniTV: není potvrzen "
        "přímý přenos."
    )
    return None

patterns = [
    r"\bSport\s*[1-4]\b",
    r"\bČT sport\b",
    r"\bNova Sport\s*[1-6]\b",
    r"\bOneplay Sport\s*[1-4]\b",
]

for pattern in patterns:
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
            f"SledovaniTV potvrzuje: "
            f"{channel}"
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

# =========================================================

# TV DOUBLE CHECK

# =========================================================

def verify_tv(event):
print()
print("=== TV OVĚŘENÍ ===")

```
# -----------------------------------------------------
# ONEPLAY VÝJIMKA
# -----------------------------------------------------

oneplay = verify_oneplay(
    event
)

if oneplay:
    channel = oneplay["channel"]

    if is_oneplay_sport(
        channel
    ):
        print(
            "→ Oneplay Sport: "
            "jedno potvrzení stačí."
        )

        event["tv_channel"] = channel
        event["tv_confirmed"] = True

        return event

# -----------------------------------------------------
# DVA NEZÁVISLÉ ZDROJE
# -----------------------------------------------------

source_a = verify_idnes(
    event
)

source_b = verify_sledovanitv(
    event
)

if not source_a or not source_b:
    print(
        "→ TV NEPOTVRZENO: "
        "chybí dva nezávislé zdroje."
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
        "→ TV NEPOTVRZENO: "
        "zdroje se rozcházejí."
    )

    event["tv_channel"] = None
    event["tv_confirmed"] = False

    return event

if (
    not source_a["live"]
    or not source_b["live"]
):
    print(
        "→ TV NEPOTVRZENO: "
        "nejde o potvrzený live přenos."
    )

    event["tv_channel"] = None
    event["tv_confirmed"] = False

    return event

print(
    f"→ TV POTVRZENO: {channel_a}"
)

event["tv_channel"] = channel_a
event["tv_confirmed"] = True

return event
```

# =========================================================

# ATLETIKA

# =========================================================

ATHLETICS_ALLOWED = [
"diamond league",
"diamantová liga",
"world athletics championships",
"world championships",
"world indoor championships",
"world indoor",
"mistrovství světa",
"mistrovství evropy",
"european athletics championships",
"european championships",
"european indoor championships",
"halové mistrovství světa",
"halové mistrovství evropy",
]

CZECH_ATHLETICS_ALLOWED = [
"ostrava golden spike",
"zlatá tretra",
"golden spike",
"memoriál josefa odložila",
"memorial josefa odložila",
"josef odložil memorial",
"olympic hopes",
"czech athletics",
"mistrovství české republiky",
"mistrovství čr",
"mčr",
]

def is_allowed_athletics_event(
text
):
text = normalize_text(
text
).lower()

```
for phrase in ATHLETICS_ALLOWED:
    if phrase in text:
        return True

for phrase in CZECH_ATHLETICS_ALLOWED:
    if phrase in text:
        return True

return False
```

def parse_athletics():
print()
print("=== ATLETIKA ===")
print(
"Kategorie: Diamond League, "
"ME/MS, halové ME/MS, "
"významné české mítinky"
)

```
try:
    html = get_url(
        WORLD_ATHLETICS_URL
    )
except Exception as e:
    print(
        f"World Athletics chyba: {e}"
    )
    return []

soup = BeautifulSoup(
    html,
    "html.parser",
)

text = normalize_text(
    soup.get_text(
        " ",
        strip=True,
    )
)

events = []

# -----------------------------------------------------
# Hledání dat v oficiálním kalendáři
# -----------------------------------------------------

date_patterns = [
    re.compile(
        r"\b(\d{1,2})\s+"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+(\d{4})\b",
        re.IGNORECASE,
    ),

    re.compile(
        r"\b(\d{1,2})\.\s*"
        r"(\d{1,2})\.\s*"
        r"(\d{4})\b"
    ),
]

found_dates = []

for pattern in date_patterns:
    for match in pattern.finditer(
        text
    ):
        try:
            if match.lastindex == 3:
                if match.group(2).isalpha():
                    month_names = {
                        "jan": 1,
                        "feb": 2,
                        "mar": 3,
                        "apr": 4,
                        "may": 5,
                        "jun": 6,
                        "jul": 7,
                        "aug": 8,
                        "sep": 9,
                        "oct": 10,
                        "nov": 11,
                        "dec": 12,
                    }

                    month = month_names[
                        match.group(2).lower()
                    ]

                    dt = datetime(
                        int(match.group(3)),
                        month,
                        int(match.group(1)),
                        12,
                        0,
                        tzinfo=TIMEZONE,
                    )

                else:
                    dt = datetime(
                        int(match.group(3)),
                        int(match.group(2)),
                        int(match.group(1)),
                        12,
                        0,
                        tzinfo=TIMEZONE,
                    )

                found_dates.append(
                    (
                        match.start(),
                        match.end(),
                        dt,
                    )
                )

        except Exception:
            continue

# -----------------------------------------------------
# Pro každý nalezený datum zkusíme najít
# okolní název soutěže.
# -----------------------------------------------------

for start, end, dt in found_dates:
    nearby_start = max(
        0,
        start - 500,
    )

    nearby_end = min(
        len(text),
        end + 800,
    )

    nearby = text[
        nearby_start:nearby_end
    ]

    if not is_allowed_athletics_event(
        nearby
    ):
        continue

    title = "Atletika"

    for phrase in [
        "Diamond League",
        "Diamantová liga",
        "World Athletics Championships",
        "World Championships",
        "World Indoor Championships",
        "European Athletics Championships",
        "European Indoor Championships",
        "Mistrovství světa",
        "Mistrovství Evropy",
        "Halové mistrovství světa",
        "Halové mistrovství Evropy",
        "Zlatá tretra",
        "Golden Spike",
        "Memoriál Josefa Odložila",
    ]:
        if phrase.lower() in nearby.lower():
            title = phrase
            break

    events.append(
        {
            "sport": "Atletika",
            "competition": title,
            "home": title,
            "away": "",
            "datetime": dt,
            "tv_channel": None,
            "tv_confirmed": False,
        }
    )

# -----------------------------------------------------
# Fallback: ČT atletický program
# -----------------------------------------------------

if not events:
    try:
        html = get_url(
            CT_ATHLETICS_URL
        )

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        ct_text = normalize_text(
            soup.get_text(
                " ",
                strip=True,
            )
        )

        if ct_text:
            print(
                "ČT Atletika načtena jako "
                "záložní zdroj."
            )

    except Exception as e:
        print(
            f"ČT atletika chyba: {e}"
        )

events = deduplicate_matches(
    events
)

print(
    f"Vybraných atletických událostí: "
    f"{len(events)}"
)

return events
```

# =========================================================

# BIATLON

# =========================================================

def parse_biathlon():
print()
print("=== BIATLON ===")

```
try:
    html = get_url(
        CT_BIATHLON_URL
    )
except Exception as e:
    print(
        f"ČT biatlon chyba: {e}"
    )
    return []

soup = BeautifulSoup(
    html,
    "html.parser",
)

text = normalize_text(
    soup.get_text(
        " ",
        strip=True,
    )
)

events = []

patterns = [
    re.compile(
        r"\b(\d{1,2})\.\s*"
        r"(\d{1,2})\.\s*"
        r"(\d{4})"
        r".{0,300}?"
        r"(\d{1,2}):(\d{2})",
        re.IGNORECASE,
    ),
]

for pattern in patterns:
    for match in pattern.finditer(
        text
    ):
        try:
            dt = datetime(
                int(match.group(3)),
                int(match.group(2)),
                int(match.group(1)),
                int(match.group(4)),
                int(match.group(5)),
                tzinfo=TIMEZONE,
            )
        except Exception:
            continue

        nearby = text[
            max(
                0,
                match.start() - 300,
            ):
            min(
                len(text),
                match.end() + 500,
            )
        ]

        if "biatlon" not in nearby.lower():
            continue

        events.append(
            {
                "sport": "Biatlon",
                "competition": "Biatlon",
                "home": "Biatlon",
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

# =========================================================

# EVENTS

# =========================================================

def get_sport_events(config):
events = []

```
if config.get(
    "dynamo_pardubice",
    False,
):
    events.extend(
        parse_dynamo_matches()
    )

    # TV kontrolujeme pouze u Dynama.
    updated = []

    for event in events:
        if event["sport"] == "hockey":
            updated.append(
                verify_tv(event)
            )
        else:
            updated.append(event)

    events = updated

if config.get(
    "diamond_league",
    False,
):
    events.extend(
        parse_athletics()
    )

if config.get(
    "biathlon",
    False,
):
    events.extend(
        parse_biathlon()
    )

# MS v hokeji zatím zůstává vypnuté.
if config.get(
    "world_hockey_championship",
    False,
):
    print()
    print(
        "MS V HOKEJI JE ZAPNUTÉ, "
        "ALE ROZSAH SLEDOVÁNÍ NENÍ "
        "DEFINOVÁN."
    )

return sorted(
    events,
    key=lambda event: event["datetime"],
)
```

# =========================================================

# FORMAT

# =========================================================

def format_event(event):
dt = event["datetime"].astimezone(
TIMEZONE
)

```
if event["away"]:
    title = (
        f"{event['home']} "
        f"vs "
        f"{event['away']}"
    )
else:
    title = event["home"]

lines = [
    title,
    f"📅 {dt.strftime('%Y-%m-%d')}",
    f"🕐 {dt.strftime('%H:%M')}",
]

if (
    event.get("tv_confirmed")
    and event.get("tv_channel")
):
    lines.append(
        f"📺 {event['tv_channel']}"
    )

return "\n".join(lines)
```

# =========================================================

# DAILY

# =========================================================

def make_daily_message(
events,
now,
):
today = now.date()

```
todays_events = [
    event
    for event in events
    if event["datetime"]
    .astimezone(TIMEZONE)
    .date()
    == today
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
    if event["sport"] == "hockey":
        groups[
            "Dynamo Pardubice"
        ].append(event)

    elif event["sport"] == "Atletika":
        groups[
            "Atletika"
        ].append(event)

    elif event["sport"] == "Biatlon":
        groups[
            "Biatlon"
        ].append(event)

    else:
        groups[
            "MS v hokeji"
        ].append(event)

emojis = {
    "Dynamo Pardubice": "🏒",
    "Atletika": "🏃",
    "Biatlon": "🎿",
    "MS v hokeji": "🏒",
}

lines = [
    "🔔 SPORT DNES",
    "",
]

for section, section_events in groups.items():
    if not section_events:
        continue

    lines.append(
        f"{emojis[section]} {section}"
    )
    lines.append("")

    for event in section_events:
        lines.append(
            format_event(event)
        )
        lines.append("")

return "\n".join(
    lines
).strip()
```

# =========================================================

# WEEKLY

# =========================================================

def make_weekly_message(
events,
now,
):
monday = (
now.date()
- timedelta(
days=now.weekday()
)
)

```
sunday = monday + timedelta(
    days=6
)

week_events = [
    event
    for event in events
    if monday
    <= event["datetime"]
    .astimezone(TIMEZONE)
    .date()
    <= sunday
]

if not week_events:
    return None

groups = {
    "Dynamo Pardubice": [],
    "Atletika": [],
    "Biatlon": [],
    "MS v hokeji": [],
}

for event in week_events:
    if event["sport"] == "hockey":
        groups[
            "Dynamo Pardubice"
        ].append(event)

    elif event["sport"] == "Atletika":
        groups[
            "Atletika"
        ].append(event)

    elif event["sport"] == "Biatlon":
        groups[
            "Biatlon"
        ].append(event)

    else:
        groups[
            "MS v hokeji"
        ].append(event)

emojis = {
    "Dynamo Pardubice": "🏒",
    "Atletika": "🏃",
    "Biatlon": "🎿",
    "MS v hokeji": "🏒",
}

lines = [
    "📅 SPORT – PŘEHLED TÝDNE",
    "",
]

total = 0

for section, section_events in groups.items():
    if not section_events:
        continue

    lines.append(
        f"{emojis[section]} {section}"
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

return "\n".join(
    lines
).strip()
```

# =========================================================

# TELEGRAM

# =========================================================

def send_telegram(message):
url = (
"https://api.telegram.org/"
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

# =========================================================

# MAIN

# =========================================================

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
        "Použij daily nebo weekly."
    )
    raise SystemExit(1)

now = datetime.now(
    TIMEZONE
)

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

print(
    f"Čas: {now.isoformat()}"
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
print("Konfigurace:")
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
    f"Celkem událostí: "
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
        "Žádné relevantní události."
    )
    print(
        "Telegram se neposílá."
    )
    return

print()
print(
    "======================================"
)
print(
    "ZPRÁVA PRO TELEGRAM"
)
print(
    "======================================"
)

print(message)

print(
    "======================================"
)

send_telegram(
    message
)

print(
    "Telegram OK."
)
```

if **name** == "**main**":
main()
