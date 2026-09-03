```python
import os
import json
import re
import unicodedata
import requests

from datetime import datetime, timezone, timedelta


# ============================================================
# SECRETS
# ============================================================

YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SPOTIFY_CLIENT_ID = os.environ["SPOTIFY_CLIENT_ID"]
SPOTIFY_CLIENT_SECRET = os.environ["SPOTIFY_CLIENT_SECRET"]


# ============================================================
# CONFIG
# ============================================================

CONFIG_FILE = "config.json"
STATE_FILE = "data/seen_videos.json"

MAX_AGE_DAYS = 1.5
MAX_RESULTS = 50

# Videa dlouhá 5 minut nebo méně budou vyřazena.
MIN_DURATION_SECONDS = 5 * 60


# ============================================================
# SPOTIFY NASTAVENÍ
# ============================================================

# Maximální rozdíl mezi datem YouTube a Spotify.
#
# Například:
#
# YouTube: 3. 9.
# Spotify: 2. 9.
#
# => OK
#
# YouTube: 3. 9.
# Spotify: 20. 8.
#
# => nepravděpodobná shoda
#
SPOTIFY_MAX_DATE_DIFFERENCE_DAYS = 14


# Minimální skóre podobnosti názvu.
#
# 0.80 = velmi přísné
# 0.70 = přísné
# 0.60 = rozumné
#
SPOTIFY_MIN_SCORE = 0.70


# ============================================================
# YOUTUBE SEARCH QUERIES
# ============================================================

SEARCH_QUERIES = {
    "David Svoboda": [
        "David Svoboda Ukrajina",
        "David Svoboda ukrajinista",
        "David Svoboda historik",
    ]
}


# ============================================================
# BĚŽNÁ SLOVA, KTERÁ NECHCEME PŘI POROVNÁNÍ
# ============================================================

STOP_WORDS = {
    "a",
    "ale",
    "ani",
    "asi",
    "co",
    "jak",
    "jako",
    "je",
    "jsou",
    "na",
    "nad",
    "ne",
    "nebo",
    "o",
    "od",
    "pod",
    "po",
    "pro",
    "před",
    "se",
    "si",
    "s",
    "to",
    "u",
    "v",
    "ve",
    "za",
    "ze",

    "the",
    "and",
    "or",
    "of",
    "in",
    "on",
    "with",
    "to",
    "for",
    "from",
    "is",
    "are",
}


# ============================================================
# JSON
# ============================================================

def load_json(filename, default):
    if not os.path.exists(filename):
        return default

    with open(
        filename,
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def save_json(filename, data):
    directory = os.path.dirname(filename)

    if directory:
        os.makedirs(
            directory,
            exist_ok=True,
        )

    with open(
        filename,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# TEXT
# ============================================================

def normalize_text(text):
    """
    Normalizace textu:

    - malá písmena
    - odstranění diakritiky
    - odstranění interpunkce
    - odstranění přebytečných mezer
    """

    if not text:
        return ""

    text = text.lower()

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = re.sub(
        r"[^\w\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def get_significant_words(text):
    """
    Vrací pouze významná slova.

    Například:

        "David Svoboda: Co se děje na Ukrajině?"

    =>

        {"david", "svoboda", "deje", "ukrajine"}
    """

    normalized = normalize_text(text)

    words = normalized.split()

    return {
        word
        for word in words
        if len(word) >= 3
        and word not in STOP_WORDS
    }


# ============================================================
# YOUTUBE
# ============================================================

def youtube_search(query):
    url = (
        "https://www.googleapis.com/"
        "youtube/v3/search"
    )

    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": MAX_RESULTS,
        "order": "date",
        "key": YOUTUBE_API_KEY,
    }

    response = requests.get(
        url,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return response.json().get(
        "items",
        [],
    )


def youtube_get_video_details(video_ids):

    if not video_ids:
        return {}

    url = (
        "https://www.googleapis.com/"
        "youtube/v3/videos"
    )

    details = {}

    for i in range(
        0,
        len(video_ids),
        50,
    ):

        batch = video_ids[
            i:i + 50
        ]

        params = {
            "part": "contentDetails",
            "id": ",".join(batch),
            "key": YOUTUBE_API_KEY,
        }

        response = requests.get(
            url,
            params=params,
            timeout=30,
        )

        response.raise_for_status()

        for item in response.json().get(
            "items",
            [],
        ):

            video_id = item.get(
                "id"
            )

            duration = (
                item
                .get(
                    "contentDetails",
                    {},
                )
                .get(
                    "duration"
                )
            )

            if not video_id or not duration:
                continue

            duration_seconds = (
                parse_iso8601_duration(
                    duration
                )
            )

            details[video_id] = {
                "duration_seconds":
                    duration_seconds,
                "duration":
                    duration,
            }

    return details


def parse_iso8601_duration(duration):

    match = re.fullmatch(
        r"PT"
        r"(?:(\d+)H)?"
        r"(?:(\d+)M)?"
        r"(?:(\d+)S)?",
        duration,
    )

    if not match:
        return 0

    hours = int(
        match.group(1) or 0
    )

    minutes = int(
        match.group(2) or 0
    )

    seconds = int(
        match.group(3) or 0
    )

    return (
        hours * 3600
        + minutes * 60
        + seconds
    )


def format_duration(seconds):

    hours = seconds // 3600

    minutes = (
        seconds % 3600
    ) // 60

    remaining_seconds = (
        seconds % 60
    )

    if hours:

        return (
            f"{hours}:"
            f"{minutes:02d}:"
            f"{remaining_seconds:02d}"
        )

    return (
        f"{minutes}:"
        f"{remaining_seconds:02d}"
    )


# ============================================================
# SPOTIFY
# ============================================================

def spotify_get_access_token():

    url = (
        "https://accounts.spotify.com/"
        "api/token"
    )

    response = requests.post(
        url,
        data={
            "grant_type":
                "client_credentials",
        },
        auth=(
            SPOTIFY_CLIENT_ID,
            SPOTIFY_CLIENT_SECRET,
        ),
        timeout=30,
    )

    response.raise_for_status()

    return response.json()[
        "access_token"
    ]


def spotify_search(
    query,
    access_token,
):

    url = (
        "https://api.spotify.com/"
        "v1/search"
    )

    headers = {
        "Authorization":
            f"Bearer {access_token}",
    }

    params = {
        "q": query,
        "type": "episode",
        "limit": 10,
        "market": "CZ",
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    return (
        response.json()
        .get("episodes", {})
        .get("items", [])
    )


def parse_spotify_date(date_string):

    if not date_string:
        return None

    try:

        # Spotify může vracet:
        #
        # 2026
        # 2026-09
        # 2026-09-03
        #

        if len(date_string) == 4:

            return datetime.strptime(
                date_string,
                "%Y",
            ).date()

        if len(date_string) == 7:

            return datetime.strptime(
                date_string,
                "%Y-%m",
            ).date()

        return datetime.strptime(
            date_string,
            "%Y-%m-%d",
        ).date()

    except ValueError:

        return None


def calculate_title_score(
    youtube_title,
    spotify_title,
):
    """
    Vypočítá podobnost názvů.

    Používáme:

    1. přesnou shodu
    2. podíl společných slov
    3. zda je jeden název obsažen
       v druhém
    """

    youtube_normalized = normalize_text(
        youtube_title
    )

    spotify_normalized = normalize_text(
        spotify_title
    )

    if not youtube_normalized:
        return 0.0

    if not spotify_normalized:
        return 0.0

    # Přesná shoda.
    if (
        youtube_normalized
        == spotify_normalized
    ):

        return 1.0

    youtube_words = get_significant_words(
        youtube_title
    )

    spotify_words = get_significant_words(
        spotify_title
    )

    if not youtube_words:
        return 0.0

    common_words = (
        youtube_words
        & spotify_words
    )

    word_score = (
        len(common_words)
        / len(youtube_words)
    )

    # Pokud je celý YouTube název
    # obsažený ve Spotify názvu.
    if (
        youtube_normalized
        in spotify_normalized
    ):

        word_score = max(
            word_score,
            0.90,
        )

    # Pokud je Spotify název obsažený
    # v YouTube názvu.
    if (
        spotify_normalized
        in youtube_normalized
    ):

        word_score = max(
            word_score,
            0.90,
        )

    return word_score


def calculate_person_score(
    person_name,
    youtube_title,
    spotify_episode,
):
    """
    Kontrola konkrétní osoby.

    Pro Davida Svobodu chceme vidět
    jeho jméno v názvu Spotify epizody
    nebo názvu pořadu.
    """

    if not person_name:
        return 1.0

    person_words = get_significant_words(
        person_name
    )

    if not person_words:
        return 1.0

    spotify_title = spotify_episode.get(
        "name",
        "",
    )

    show = spotify_episode.get(
        "show",
        {},
    )

    show_name = show.get(
        "name",
        "",
    )

    combined = (
        f"{spotify_title} "
        f"{show_name}"
    )

    spotify_words = get_significant_words(
        combined
    )

    matched = (
        person_words
        & spotify_words
    )

    if not matched:
        return 0.0

    return (
        len(matched)
        / len(person_words)
    )


def calculate_date_score(
    youtube_date,
    spotify_date_string,
):
    """
    Kontrola data vydání.

    Čím menší rozdíl mezi YouTube
    a Spotify, tím lepší skóre.
    """

    spotify_date = parse_spotify_date(
        spotify_date_string
    )

    if not youtube_date:
        return 0.0

    if not spotify_date:
        return 0.5

    difference = abs(
        (
            youtube_date.date()
            - spotify_date
        ).days
    )

    if difference <= 1:
        return 1.0

    if difference <= 3:
        return 0.90

    if difference <= 7:
        return 0.80

    if difference <= 14:
        return 0.65

    return 0.0


def find_best_spotify_episode(
    title,
    channel_title,
    published,
    person_name,
    access_token,
):
    """
    Najde nejlepší Spotify kandidát.

    Kandidát musí splnit:

    - rozumnou podobnost názvu
    - správné datum
    - pokud je známá osoba,
      musí se její jméno objevit
      v Spotify názvu nebo pořadu
    """

    # --------------------------------------------------------
    # VYHLEDÁVACÍ DOTAZY
    # --------------------------------------------------------

    queries = []

    # Nejdůležitější je samotný název.
    queries.append(title)

    # Potom název + osoba.
    if person_name:

        queries.append(
            f"{title} {person_name}"
        )

    # Nakonec název + YouTube kanál.
    if channel_title:

        queries.append(
            f"{title} {channel_title}"
        )

    all_candidates = {}

    for query in queries:

        print(
            f"Spotify search: {query}"
        )

        episodes = spotify_search(
            query=query,
            access_token=access_token,
        )

        for episode in episodes:

            episode_id = episode.get(
                "id"
            )

            if episode_id:

                all_candidates[
                    episode_id
                ] = episode

    candidates = list(
        all_candidates.values()
    )

    if not candidates:

        print(
            "Spotify: žádní kandidáti"
        )

        return None

    # --------------------------------------------------------
    # VYHODNOCENÍ
    # --------------------------------------------------------

    best = None
    best_score = 0.0

    for episode in candidates:

        spotify_title = episode.get(
            "name",
            "",
        )

        spotify_release_date = (
            episode.get(
                "release_date",
                "",
            )
        )

        spotify_url = (
            episode
            .get(
                "external_urls",
                {},
            )
            .get(
                "spotify"
            )
        )

        if not spotify_url:
            continue

        # -----------------------------------------------
        # TITLE SCORE
        # -----------------------------------------------

        title_score = calculate_title_score(
            title,
            spotify_title,
        )

        # -----------------------------------------------
        # PERSON SCORE
        # -----------------------------------------------

        person_score = calculate_person_score(
            person_name,
            title,
            episode,
        )

        # Pokud osoba existuje a není
        # nalezena, kandidáta rovnou vyřadíme.
        if (
            person_name
            and person_score < 1.0
        ):

            print(
                f"Spotify kandidát vyřazen "
                f"(osoba): {spotify_title}"
            )

            continue

        # -----------------------------------------------
        # DATE SCORE
        # -----------------------------------------------

        date_score = calculate_date_score(
            published,
            spotify_release_date,
        )

        # Pokud je Spotify epizoda
        # příliš daleko od YouTube data,
        # nepovažujeme ji za stejnou epizodu.
        if date_score == 0.0:

            print(
                f"Spotify kandidát vyřazen "
                f"(datum): {spotify_title}"
            )

            continue

        # -----------------------------------------------
        # CELKOVÉ SKÓRE
        # -----------------------------------------------

        # Název má největší váhu.
        #
        # Datum je druhý důležitý signál.
        #
        total_score = (
            title_score * 0.75
            + date_score * 0.25
        )

        print(
            "Spotify kandidát:"
        )

        print(
            f"  {spotify_title}"
        )

        print(
            f"  title score: "
            f"{title_score:.2f}"
        )

        print(
            f"  date score: "
            f"{date_score:.2f}"
        )

        print(
            f"  total score: "
            f"{total_score:.2f}"
        )

        if total_score > best_score:

            best_score = total_score
            best = episode

    # --------------------------------------------------------
    # VÝSLEDEK
    # --------------------------------------------------------

    if not best:

        print(
            "Spotify: žádná dostatečně "
            "dobrá shoda"
        )

        return None

    if best_score < SPOTIFY_MIN_SCORE:

        print(
            "Spotify: nejlepší kandidát "
            "nesplnil minimální skóre"
        )

        print(
            f"  Skóre: "
            f"{best_score:.2f}"
        )

        return None

    spotify_url = (
        best
        .get(
            "external_urls",
            {},
        )
        .get(
            "spotify"
        )
    )

    if not spotify_url:
        return None

    print()
    print(
        "★★★★★ SPOTIFY SHODA ★★★★★"
    )

    print(
        f"Název: "
        f"{best.get('name')}"
    )

    print(
        f"Datum: "
        f"{best.get('release_date')}"
    )

    print(
        f"Skóre: "
        f"{best_score:.2f}"
    )

    print(
        f"URL: "
        f"{spotify_url}"
    )

    return {
        "name": best.get(
            "name",
            "",
        ),
        "url": spotify_url,
        "release_date": best.get(
            "release_date",
            "",
        ),
        "score": best_score,
    }


def find_spotify_link(
    title,
    channel_title,
    published,
    person_name,
):
    """
    Bezpečné hledání Spotify.

    Pokud se Spotify nepodaří ověřit,
    vrací None.
    """

    try:

        print(
            "→ Kontroluji Spotify..."
        )

        access_token = (
            spotify_get_access_token()
        )

        result = (
            find_best_spotify_episode(
                title=title,
                channel_title=channel_title,
                published=published,
                person_name=person_name,
                access_token=access_token,
            )
        )

        return result

    except Exception as e:

        print(
            f"Spotify ERROR: {e}"
        )

        print(
            "→ Spotify nedostupné, "
            "použiji YouTube."
        )

        return None


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": False,
    }

    response = requests.post(
        url,
        data=data,
        timeout=30,
    )

    response.raise_for_status()


# ============================================================
# MAIN
# ============================================================

def main():

    config = load_json(
        CONFIG_FILE,
        {
            "keywords": [],
            "exclude_channels": {},
        },
    )

    state = load_json(
        STATE_FILE,
        {
            "seen_video_ids": [],
            "initialized_keywords": [],
            "last_checked_at": None,
        },
    )

    seen_video_ids = set(
        state.get(
            "seen_video_ids",
            [],
        )
    )

    initialized_keywords = set(
        state.get(
            "initialized_keywords",
            [],
        )
    )

    now = datetime.now(
        timezone.utc
    )

    max_age = timedelta(
        days=MAX_AGE_DAYS
    )

    all_new_videos = []

    print(
        f"Kontrola: "
        f"{now.isoformat()}"
    )

    print(
        f"Limit stáří videa: "
        f"{MAX_AGE_DAYS} dne"
    )

    print(
        "Minimální délka videa: "
        f"{format_duration(MIN_DURATION_SECONDS)}"
    )

    print(
        "Spotify minimální skóre: "
        f"{SPOTIFY_MIN_SCORE}"
    )

    # ========================================================
    # KEYWORDS
    # ========================================================

    for keyword in config.get(
        "keywords",
        [],
    ):

        exclude_channels = set(
            config
            .get(
                "exclude_channels",
                {},
            )
            .get(
                keyword,
                [],
            )
        )

        print()
        print(
            f"=== {keyword} ==="
        )

        # ====================================================
        # YOUTUBE SEARCH
        # ====================================================

        if keyword in SEARCH_QUERIES:

            queries = SEARCH_QUERIES[
                keyword
            ]

            print(
                "Hledám přes:"
            )

            for query in queries:

                print(
                    f"  - {query}"
                )

            results_by_id = {}

            for query in queries:

                results = youtube_search(
                    query
                )

                print(
                    f"Výsledků pro "
                    f"'{query}': "
                    f"{len(results)}"
                )

                for item in results:

                    video_id = (
                        item
                        .get(
                            "id",
                            {},
                        )
                        .get(
                            "videoId"
                        )
                    )

                    if video_id:

                        results_by_id[
                            video_id
                        ] = item

            results = list(
                results_by_id.values()
            )

            print(
                "Celkem unikátních "
                f"výsledků: {len(results)}"
            )

        else:

            results = youtube_search(
                keyword
            )

            print(
                f"Výsledků: "
                f"{len(results)}"
            )

        # ====================================================
        # YOUTUBE DETAILS
        # ====================================================

        video_ids = []

        for item in results:

            video_id = (
                item
                .get(
                    "id",
                    {},
                )
                .get(
                    "videoId"
                )
            )

            if video_id:

                video_ids.append(
                    video_id
                )

        video_details = (
            youtube_get_video_details(
                video_ids
            )
        )

        print(
            "Načteno délek videí: "
            f"{len(video_details)}"
        )

        # ====================================================
        # PROCESS VIDEOS
        # ====================================================

        keyword_initialized = (
            keyword
            in initialized_keywords
        )

        for item in results:

            video_id = (
                item
                .get(
                    "id",
                    {},
                )
                .get(
                    "videoId"
                )
            )

            snippet = item.get(
                "snippet",
                {},
            )

            if not video_id:
                continue

            title = snippet.get(
                "title",
                "Bez názvu",
            )

            channel_title = snippet.get(
                "channelTitle",
                "Neznámý kanál",
            )

            channel_id = snippet.get(
                "channelId"
            )

            published_at = snippet.get(
                "publishedAt"
            )

            if not published_at:
                continue

            published = datetime.fromisoformat(
                published_at.replace(
                    "Z",
                    "+00:00",
                )
            )

            age = now - published

            print()
            print(
                f"VIDEO: {title}"
            )

            print(
                f"KANÁL: "
                f"{channel_title}"
            )

            print(
                f"DATUM: "
                f"{published_at}"
            )

            # =================================================
            # EXCLUDED CHANNEL
            # =================================================

            if (
                channel_id
                in exclude_channels
            ):

                print(
                    "→ VYŘAZENO: "
                    "vyloučený kanál"
                )

                continue

            # =================================================
            # AGE
            # =================================================

            if age > max_age:

                print(
                    "→ VYŘAZENO: "
                    "video je starší "
                    "než limit"
                )

                continue

            # =================================================
            # DURATION
            # =================================================

            details = video_details.get(
                video_id
            )

            if not details:

                print(
                    "→ VYŘAZENO: "
                    "nepodařilo se "
                    "zjistit délku"
                )

                continue

            duration_seconds = details[
                "duration_seconds"
            ]

            duration_text = format_duration(
                duration_seconds
            )

            print(
                f"DÉLKA: "
                f"{duration_text}"
            )

            if (
                duration_seconds
                <= MIN_DURATION_SECONDS
            ):

                print(
                    "→ VYŘAZENO: "
                    "video má 5 minut "
                    "nebo méně"
                )

                seen_video_ids.add(
                    video_id
                )

                continue

            # =================================================
            # FIRST CHECK
            # =================================================

            if not keyword_initialized:

                print(
                    "→ PRVNÍ KONTROLA: "
                    "uloženo jako "
                    "výchozí stav"
                )

                seen_video_ids.add(
                    video_id
                )

                continue

            # =================================================
            # DUPLICATE
            # =================================================

            if video_id in seen_video_ids:

                print(
                    "→ VYŘAZENO: "
                    "video už bylo "
                    "oznámeno"
                )

                continue

            # =================================================
            # NEW VIDEO
            # =================================================

            video_url = (
                "https://www.youtube.com/watch?v="
                f"{video_id}"
            )

            # =================================================
            # SPOTIFY
            # =================================================

            spotify_result = (
                find_spotify_link(
                    title=title,
                    channel_title=channel_title,
                    published=published,
                    person_name=keyword,
                )
            )

            spotify_url = None
            spotify_name = None

            if spotify_result:

                spotify_url = (
                    spotify_result["url"]
                )

                spotify_name = (
                    spotify_result["name"]
                )

                final_url = spotify_url

                print(
                    "→ POUŽIJI SPOTIFY"
                )

            else:

                final_url = video_url

                print(
                    "→ POUŽIJI YOUTUBE"
                )

            # =================================================
            # STORE
            # =================================================

            all_new_videos.append(
                {
                    "keyword": keyword,
                    "title": title,
                    "channel_title": channel_title,
                    "published_at": published_at,
                    "duration_seconds": duration_seconds,
                    "duration": duration_text,
                    "url": final_url,
                    "youtube_url": video_url,
                    "spotify_url": spotify_url,
                    "spotify_name": spotify_name,
                    "video_id": video_id,
                }
            )

            seen_video_ids.add(
                video_id
            )

            print(
                "→ NOVÉ VIDEO"
            )

        initialized_keywords.add(
            keyword
        )

    # ========================================================
    # TELEGRAM
    # ========================================================

    print()
    print(
        "Nových videí: "
        f"{len(all_new_videos)}"
    )

    for video in all_new_videos:

        if video.get(
            "spotify_url"
        ):

            link_text = (
                "🎧 Spotify:\n"
                f"{video['spotify_url']}"
            )

            if video.get(
                "spotify_name"
            ):

                source_text = (
                    "Zdroj: Spotify"
                )

        else:

            link_text = (
                "▶️ YouTube:\n"
                f"{video['youtube_url']}"
            )

            source_text = (
                "Zdroj: YouTube"
            )

        message = (
            "🎬 Nové video\n\n"

            f"{video['title']}\n\n"

            "Kanál: "
            f"{video['channel_title']}\n"

            "Délka: "
            f"{video['duration']}\n"

            "Publikováno: "
            f"{video['published_at']}\n"

            f"{source_text}\n\n"

            f"{link_text}"
        )

        try:

            send_telegram(
                message
            )

            print(
                "Telegram OK: "
                f"{video['title']}"
            )

        except Exception as e:

            print(
                "Telegram ERROR: "
                f"{e}"
            )

    # ========================================================
    # SAVE STATE
    # ========================================================

    state["seen_video_ids"] = list(
        seen_video_ids
    )[-500:]

    state["initialized_keywords"] = list(
        initialized_keywords
    )

    state["last_checked_at"] = (
        now.isoformat()
    )

    save_json(
        STATE_FILE,
        state
    )

    print(
        "Stav uložen."
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
```
