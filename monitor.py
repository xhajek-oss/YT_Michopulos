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
# JSON
# ============================================================

def load_json(filename, default):
    if not os.path.exists(filename):
        return default

    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename, data):
    directory = os.path.dirname(filename)

    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# YOUTUBE
# ============================================================

def youtube_search(query):
    url = "https://www.googleapis.com/youtube/v3/search"

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

    return response.json().get("items", [])


def youtube_get_video_details(video_ids):
    """
    Načte délku videí přes YouTube videos.list API.

    Vrací:

        {
            "video_id": {
                "duration_seconds": 123,
                "duration": "PT2M3S"
            }
        }
    """

    if not video_ids:
        return {}

    url = "https://www.googleapis.com/youtube/v3/videos"

    details = {}

    # YouTube API umožňuje maximálně 50 ID
    # v jednom requestu.
    for i in range(0, len(video_ids), 50):

        batch = video_ids[i:i + 50]

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

            video_id = item.get("id")

            duration = (
                item.get(
                    "contentDetails",
                    {},
                ).get("duration")
            )

            if not video_id or not duration:
                continue

            duration_seconds = parse_iso8601_duration(
                duration
            )

            details[video_id] = {
                "duration_seconds": duration_seconds,
                "duration": duration,
            }

    return details


def parse_iso8601_duration(duration):
    """
    Převod ISO 8601 délky YouTube videa
    na sekundy.

    Příklady:

        PT30S
        PT5M
        PT1H2M3S
    """

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
    """
    Hezký zápis délky videa.
    """

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
    """
    Získá Spotify access token pomocí
    Client Credentials Flow.

    Token platí omezenou dobu a Spotify ho
    používá pro následné API požadavky.
    """

    url = (
        "https://accounts.spotify.com/"
        "api/token"
    )

    response = requests.post(
        url,
        data={
            "grant_type": "client_credentials",
        },
        auth=(
            SPOTIFY_CLIENT_ID,
            SPOTIFY_CLIENT_SECRET,
        ),
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    return data["access_token"]


def normalize_text(text):
    """
    Normalizace textu pro porovnávání názvů.

    Odstraní například rozdíl:

        Ukrajina
        ukrajina
        UKRAJINA

    a také diakritiku.
    """

    if not text:
        return ""

    text = text.lower()

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        c
        for c in text
        if not unicodedata.combining(c)
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


def spotify_search_episode(
    title,
    channel_title,
    access_token,
):
    """
    Hledá odpovídající podcastovou epizodu
    na Spotify.

    Vrací:

        {
            "name": "...",
            "url": "...",
            "score": 0.85
        }

    nebo None.
    """

    url = (
        "https://api.spotify.com/"
        "v1/search"
    )

    headers = {
        "Authorization": (
            f"Bearer {access_token}"
        ),
    }

    # --------------------------------------------------------
    # 1. HLEDÁNÍ PODLE NÁZVU VIDEA
    # --------------------------------------------------------

    queries = [
        title,
        f"{title} {channel_title}",
    ]

    all_episodes = {}

    for query in queries:

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

        data = response.json()

        episodes = (
            data
            .get("episodes", {})
            .get("items", [])
        )

        for episode in episodes:

            episode_id = episode.get(
                "id"
            )

            if episode_id:
                all_episodes[
                    episode_id
                ] = episode

    episodes = list(
        all_episodes.values()
    )

    if not episodes:

        print(
            "Spotify: žádná epizoda"
        )

        return None

    normalized_title = normalize_text(
        title
    )

    title_words = set(
        normalized_title.split()
    )

    # Odstraníme velmi krátká slova.
    title_words = {
        word
        for word in title_words
        if len(word) >= 4
    }

    best_episode = None
    best_score = 0.0

    # --------------------------------------------------------
    # 2. POROVNÁNÍ NÁZVŮ
    # --------------------------------------------------------

    for episode in episodes:

        spotify_name = episode.get(
            "name",
            "",
        )

        normalized_spotify_name = (
            normalize_text(
                spotify_name
            )
        )

        if not normalized_spotify_name:
            continue

        spotify_words = set(
            normalized_spotify_name.split()
        )

        # ----------------------------------------------------
        # PŘESNÁ SHODA
        # ----------------------------------------------------

        if (
            normalized_spotify_name
            == normalized_title
        ):

            return {
                "name": spotify_name,
                "url": episode.get(
                    "external_urls",
                    {},
                ).get("spotify"),
                "score": 1.0,
            }

        # ----------------------------------------------------
        # SHODA SLOV
        # ----------------------------------------------------

        if not title_words:
            continue

        common_words = (
            title_words
            & spotify_words
        )

        score = (
            len(common_words)
            / len(title_words)
        )

        # ----------------------------------------------------
        # BONUS ZA ČÁST NÁZVU
        # ----------------------------------------------------

        if (
            normalized_title
            in normalized_spotify_name
        ):
            score = max(
                score,
                0.85,
            )

        if score > best_score:

            best_score = score
            best_episode = episode

    # --------------------------------------------------------
    # 3. MINIMÁLNÍ POŽADOVANÁ SHODA
    # --------------------------------------------------------

    # Čím vyšší číslo, tím menší riziko
    # špatného přiřazení Spotify epizody.

    MIN_SPOTIFY_MATCH_SCORE = 0.60

    if (
        best_episode
        and best_score
        >= MIN_SPOTIFY_MATCH_SCORE
    ):

        spotify_url = (
            best_episode
            .get("external_urls", {})
            .get("spotify")
        )

        if spotify_url:

            print(
                "Spotify: nalezeno"
            )

            print(
                f"  Název: "
                f"{best_episode.get('name')}"
            )

            print(
                f"  Shoda: "
                f"{best_score:.2f}"
            )

            print(
                f"  URL: "
                f"{spotify_url}"
            )

            return {
                "name": best_episode.get(
                    "name",
                    "",
                ),
                "url": spotify_url,
                "score": best_score,
            }

    print(
        "Spotify: vhodná shoda nenalezena"
    )

    if best_episode:

        print(
            f"  Nejlepší kandidát: "
            f"{best_episode.get('name')}"
        )

        print(
            f"  Shoda: "
            f"{best_score:.2f}"
        )

    return None


def find_spotify_link(
    title,
    channel_title,
):
    """
    Bezpečné vyhledání Spotify.

    Pokud Spotify nefunguje, vrací None,
    aby se monitoring YouTube nezastavil.
    """

    try:

        print(
            "→ Kontroluji Spotify..."
        )

        access_token = (
            spotify_get_access_token()
        )

        result = spotify_search_episode(
            title=title,
            channel_title=channel_title,
            access_token=access_token,
        )

        if result:
            return result

        return None

    except Exception as e:

        print(
            f"Spotify ERROR: {e}"
        )

        print(
            "→ Pokračuji přes YouTube."
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
        f"Minimální délka videa: "
        f"{format_duration(MIN_DURATION_SECONDS)}"
    )

    # ========================================================
    # KEYWORDS
    # ========================================================

    for keyword in config.get(
        "keywords",
        [],
    ):

        exclude_channels = set(
            config.get(
                "exclude_channels",
                {},
            ).get(
                keyword,
                [],
            )
        )

        print()
        print(
            f"=== {keyword} ==="
        )

        # ====================================================
        # VYHLEDÁNÍ VIDEÍ
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
                        .get("id", {})
                        .get("videoId")
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
        # NAČTENÍ DÉLEK
        # ====================================================

        video_ids = []

        for item in results:

            video_id = (
                item
                .get("id", {})
                .get("videoId")
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
        # ZPRACOVÁNÍ
        # ====================================================

        keyword_initialized = (
            keyword
            in initialized_keywords
        )

        for item in results:

            video_id = (
                item
                .get("id", {})
                .get("videoId")
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

            channel_title = (
                snippet.get(
                    "channelTitle",
                    "Neznámý kanál",
                )
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
            # VYLOUČENÝ KANÁL
            # =================================================

            if channel_id in exclude_channels:

                print(
                    "→ VYŘAZENO: "
                    "vyloučený kanál"
                )

                continue

            # =================================================
            # STÁŘÍ
            # =================================================

            if age > max_age:

                print(
                    "→ VYŘAZENO: "
                    "video je starší "
                    "než limit"
                )

                continue

            # =================================================
            # DÉLKA
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

                # Uložíme jako známé,
                # aby se příště znovu
                # nezpracovávalo.

                seen_video_ids.add(
                    video_id
                )

                continue

            # =================================================
            # PRVNÍ KONTROLA
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
            # DUPLICITA
            # =================================================

            if video_id in seen_video_ids:

                print(
                    "→ VYŘAZENO: "
                    "video už bylo "
                    "oznámeno"
                )

                continue

            # =================================================
            # NOVÉ VIDEO
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
                )
            )

            spotify_url = None

            if spotify_result:

                spotify_url = (
                    spotify_result["url"]
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
            # ULOŽENÍ NOVÉHO VIDEA
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

        # ----------------------------------------------------
        # SPOTIFY
        # ----------------------------------------------------

        if video.get(
            "spotify_url"
        ):

            link_text = (
                "🎧 Spotify:\n"
                f"{video['spotify_url']}"
            )

        # ----------------------------------------------------
        # YOUTUBE
        # ----------------------------------------------------

        else:

            link_text = (
                "▶️ YouTube:\n"
                f"{video['youtube_url']}"
            )

        # ----------------------------------------------------
        # TELEGRAM MESSAGE
        # ----------------------------------------------------

        message = (
            "🎬 Nové video\n\n"

            f"{video['title']}\n\n"

            "Kanál: "
            f"{video['channel_title']}\n"

            "Délka: "
            f"{video['duration']}\n"

            "Publikováno: "
            f"{video['published_at']}\n\n"

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
    # ULOŽENÍ STAVU
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
