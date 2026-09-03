#!/usr/bin/env python3

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests


TIMEOUT = 20

OUT_DIR = Path("data/tv_probe")
OUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept": (
        "application/json, application/xml, text/xml, "
        "text/html;q=0.9, */*;q=0.8"
    ),
    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
}


TODAY = datetime.now().strftime("%Y-%m-%d")


TEST_URLS = {
    "sledovanitv_epg": [
        "https://sledovanitv.cz/epg",
        (
            "https://sledovanitv.cz/epg/default/"
            f"{TODAY}?channel=channel%3Act4sport&interval=first"
        ),
        "https://api.sledovanitv.cz/epg",
    ],
    "ct_tv_program": [
        "https://www.ceskatelevize.cz/xml/tv-program/",
        "https://www.ceskatelevize.cz/tv-program/",
    ],
    "idnes_tv": [
        "https://tvprogram.idnes.cz/",
    ],
    "oneplay_tv": [
        "https://www.oneplay.cz/",
    ],
}


# ---------------------------------------------------------------------------
# Pomocné funkce
# ---------------------------------------------------------------------------

def safe_filename(name):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def save_text(name, text):
    path = OUT_DIR / f"{safe_filename(name)}.txt"

    with path.open("w", encoding="utf-8") as f:
        f.write(text)

    return path


def save_meta(name, data):
    path = OUT_DIR / f"{safe_filename(name)}.json"

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return path


def is_interesting_url(value):
    value_lower = value.lower()

    keywords = (
        "/api/",
        "api.",
        "/epg",
        "epg.",
        "/program",
        "program.",
        "/schedule",
        "schedule.",
        ".json",
        "graphql",
        "cms.jyxo",
    )

    return any(keyword in value_lower for keyword in keywords)


def extract_urls(text, base_url):
    """
    Najde URL adresy a relativní cesty v HTML/JS.
    """

    found = set()

    # Absolutní URL
    absolute_pattern = r'https?://[^"\'<>\s]+'

    for match in re.findall(absolute_pattern, text, flags=re.I):
        match = match.rstrip("),;]}")

        if is_interesting_url(match):
            found.add(match)

    # Relativní URL v uvozovkách
    relative_pattern = (
        r'["\']('
        r'/(?:api|epg|program|schedule|graphql)'
        r'[^"\'<>\s]*'
        r')["\']'
    )

    for match in re.findall(relative_pattern, text, flags=re.I):
        if is_interesting_url(match):
            found.add(urljoin(base_url, match))

    return sorted(found)


def extract_script_urls(text, base_url):
    """
    Najde <script src="..."> v HTML.
    """

    found = set()

    pattern = r'<script[^>]+src=["\']([^"\']+)["\']'

    for match in re.findall(pattern, text, flags=re.I):
        url = urljoin(base_url, match)

        if url.startswith("http://") or url.startswith("https://"):
            found.add(url)

    return sorted(found)


def print_response_summary(result):
    print(f"HTTP:         {result.get('status_code', 'ERROR')}")
    print(f"Final URL:    {result.get('final_url', '')}")
    print(f"Content-Type: {result.get('content_type', '')}")
    print(f"Velikost:     {result.get('content_length', 0):,} B")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def fetch(url):
    return requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT,
        allow_redirects=True,
    )


# ---------------------------------------------------------------------------
# Základní test URL
# ---------------------------------------------------------------------------

def test_url(source, url, preview_length=2000):
    print()
    print("=" * 80)
    print(f"ZDROJ: {source}")
    print(f"URL:   {url}")
    print("=" * 80)

    result = {
        "source": source,
        "url": url,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": False,
    }

    try:
        response = fetch(url)

        content_type = response.headers.get("content-type", "")
        text = response.text

        result.update(
            {
                "ok": response.ok,
                "status_code": response.status_code,
                "final_url": response.url,
                "content_type": content_type,
                "content_length": len(response.content),
                "headers": dict(response.headers),
            }
        )

        print_response_summary(result)

        filename = safe_filename(
            f"{source}_{len(text)}"
        )

        text_path = save_text(filename, text)
        meta_path = save_meta(filename, result)

        print(f"RAW:          {text_path}")
        print(f"Metadata:     {meta_path}")

        # Pouze krátká ukázka.
        print()
        print("--- UKÁZKA ODPOVĚDI ---")
        preview = text[:preview_length]

        # Ať se nám log nerozbije extrémně dlouhými řádky.
        preview = re.sub(r"\s+", " ", preview)

        print(preview)
        print("--- KONEC UKÁZKY ---")

        interesting = extract_urls(text, response.url)
        scripts = extract_script_urls(text, response.url)

        result["interesting_urls"] = interesting
        result["script_urls"] = scripts

        if interesting:
            print()
            print("--- API / EPG STOPY ---")

            for item in interesting[:50]:
                print(item)

        if scripts:
            print()
            print(f"--- JS SOUBORY ({len(scripts)}) ---")

            for item in scripts[:30]:
                print(item)

        save_meta(filename, result)

        return result

    except requests.RequestException as exc:
        result["error"] = str(exc)

        print(f"CHYBA: {exc}")

        return result


# ---------------------------------------------------------------------------
# Analýza JavaScriptu
# ---------------------------------------------------------------------------

def inspect_javascript(source, page_url, script_urls):
    """
    Stáhne několik JS bundle souborů a hledá v nich API/EPG endpointy.

    To je důležité hlavně u:
      - SledovaniTV
      - Oneplay
      - iDNES
    """

    if not script_urls:
        return []

    print()
    print("=" * 80)
    print(f"ANALÝZA JAVASCRIPTU: {source}")
    print("=" * 80)

    results = []

    # Nechceme stáhnout stovky bundle souborů.
    for index, script_url in enumerate(script_urls[:15], start=1):

        try:
            response = fetch(script_url)

            if not response.ok:
                continue

            text = response.text

            # Zajímá nás pouze JS, ne obrázky/fonty atd.
            content_type = response.headers.get("content-type", "").lower()

            if (
                "javascript" not in content_type
                and not script_url.lower().endswith(".js")
            ):
                continue

            interesting = extract_urls(text, script_url)

            # Další běžné API cesty, které nemusí být v uvozovkách.
            extra_patterns = [
                r'["\']([^"\']*/api/[^"\']*)["\']',
                r'["\']([^"\']*/epg[^"\']*)["\']',
                r'["\']([^"\']*/graphql[^"\']*)["\']',
                r'["\']([^"\']*cms\.jyxo\.cz[^"\']*)["\']',
                r'["\']([^"\']*api[^"\']*epg[^"\']*)["\']',
            ]

            found = set(interesting)

            for pattern in extra_patterns:
                for match in re.findall(pattern, text, flags=re.I):
                    if match:
                        found.add(match)

            found = sorted(found)

            filename = (
                f"{source}_js_{index}"
            )

            save_text(filename, text)

            meta = {
                "source": source,
                "script_url": script_url,
                "status_code": response.status_code,
                "content_type": content_type,
                "content_length": len(response.content),
                "interesting_urls": found,
            }

            save_meta(filename, meta)

            result = {
                "script_url": script_url,
                "status_code": response.status_code,
                "content_length": len(response.content),
                "interesting_urls": found,
            }

            results.append(result)

            if found:
                print()
                print(f"JS #{index}: {script_url}")

                for item in found[:50]:
                    print(f"  {item}")

        except requests.RequestException as exc:
            print(f"JS chyba: {script_url}")
            print(f"  {exc}")

    return results


# ---------------------------------------------------------------------------
# Speciální test SledovaniTV
# ---------------------------------------------------------------------------

def probe_sledovanitv():
    """
    Otestuje konkrétní EPG stránku pro ČT sport.

    Tuto cestu jsme už našli přímo v HTML SledovaniTV:
      /epg/default/YYYY-MM-DD?channel=channel%3Act4sport&interval=first
    """

    url = (
        "https://sledovanitv.cz/epg/default/"
        f"{TODAY}?channel=channel%3Act4sport&interval=first"
    )

    print()
    print("=" * 80)
    print("SLEDOVANITV – KONKRÉTNÍ ČT SPORT EPG")
    print("=" * 80)

    try:
        response = fetch(url)

        print(f"HTTP:         {response.status_code}")
        print(f"Final URL:    {response.url}")
        print(
            f"Content-Type: "
            f"{response.headers.get('content-type', '')}"
        )
        print(f"Velikost:     {len(response.content):,} B")

        text = response.text

        path = save_text(
            f"sledovanitv_ctsport_{TODAY}",
            text,
        )

        meta = {
            "url": url,
            "final_url": response.url,
            "status_code": response.status_code,
            "content_type": response.headers.get(
                "content-type", ""
            ),
            "content_length": len(response.content),
            "checked_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        save_meta(
            f"sledovanitv_ctsport_{TODAY}",
            meta,
        )

        print(f"RAW:          {path}")

        # Hledáme eventId.
        event_ids = sorted(
            set(
                re.findall(
                    r'eventId[^"\']*["\']?[:=]\s*["\']?([^"\'&<>\s]+)',
                    text,
                    flags=re.I,
                )
            )
        )

        # Obecnější hledání ct4sport eventů.
        ct_events = sorted(
            set(
                re.findall(
                    r'ct4sport:[^"\'<>\s]+',
                    text,
                    flags=re.I,
                )
            )
        )

        if event_ids:
            print()
            print("--- EVENT ID ---")
            for item in event_ids[:20]:
                print(item)

        if ct_events:
            print()
            print("--- ČT SPORT EVENTY ---")
            for item in ct_events[:30]:
                print(item)

        print()
        print("--- UKÁZKA ---")
        print(
            re.sub(
                r"\s+",
                " ",
                text[:3000],
            )
        )

        return {
            "url": url,
            "status_code": response.status_code,
            "content_type": response.headers.get(
                "content-type", ""
            ),
            "content_length": len(response.content),
            "event_ids": event_ids,
            "ct_events": ct_events,
        }

    except requests.RequestException as exc:
        print(f"CHYBA: {exc}")

        return {
            "url": url,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Hledání potenciálních API URL
# ---------------------------------------------------------------------------

def probe_interesting_endpoints(results):
    """
    Z již nalezených HTML/JS stop zkusí pouze bezpečné
    GET requesty na endpointy, které vypadají jako API/EPG.

    Nezkouší náhodné URL.
    """

    candidates = set()

    for result in results:
        for url in result.get("interesting_urls", []):
            if url.startswith("http://") or url.startswith("https://"):
                candidates.add(url)

    if not candidates:
        return []

    print()
    print("=" * 80)
    print("TEST NALEZENÝCH API ENDPOINTŮ")
    print("=" * 80)

    tested = []

    # Limit kvůli Actions.
    for url in sorted(candidates)[:30]:

        # Vynecháme samotné HTML stránky.
        parsed = urlparse(url)

        if parsed.path in ("", "/"):
            continue

        try:
            response = fetch(url)

            content_type = response.headers.get(
                "content-type",
                "",
            )

            item = {
                "url": url,
                "status_code": response.status_code,
                "final_url": response.url,
                "content_type": content_type,
                "content_length": len(response.content),
            }

            tested.append(item)

            print(
                f"{response.status_code:3} | "
                f"{len(response.content):9,} B | "
                f"{content_type[:35]:35} | "
                f"{url}"
            )

            # Pokud je to JSON, uložíme ho zvlášť.
            if (
                "json" in content_type.lower()
                or response.text.lstrip().startswith("{")
                or response.text.lstrip().startswith("[")
            ):
                filename = (
                    "api_result_"
                    + str(len(tested))
                )

                save_text(
                    filename,
                    response.text,
                )

        except requests.RequestException as exc:
            print(
                f"ERR | {url} | {exc}"
            )

    return tested


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("TV PROBE")
    print("=" * 80)
    print(
        f"Čas: "
        f"{datetime.now().astimezone().isoformat()}"
    )
    print(f"Datum testu: {TODAY}")
    print(f"Výstup: {OUT_DIR}")
    print()

    all_results = []

    # -------------------------------------------------------
    # 1. Základní URL
    # -------------------------------------------------------

    for source, urls in TEST_URLS.items():

        for index, url in enumerate(urls, start=1):

            result = test_url(
                f"{source}_{index}",
                url,
            )

            all_results.append(result)

    # -------------------------------------------------------
    # 2. Speciální SledovaniTV test
    # -------------------------------------------------------

    sledovani_result = probe_sledovanitv()

    all_results.append(
        {
            "source": "sledovanitv_ctsport_special",
            **sledovani_result,
        }
    )

    # -------------------------------------------------------
    # 3. Analýza JS bundle souborů
    # -------------------------------------------------------

    js_results = []

    for result in all_results:

        source = result.get("source", "")
        page_url = result.get("final_url", result.get("url", ""))
        scripts = result.get("script_urls", [])

        if scripts:
            js_result = inspect_javascript(
                source,
                page_url,
                scripts,
            )

            js_results.extend(js_result)

    # -------------------------------------------------------
    # 4. Test nalezených API endpointů
    # -------------------------------------------------------

    api_results = probe_interesting_endpoints(
        all_results
    )

    # -------------------------------------------------------
    # 5. Finální summary
    # -------------------------------------------------------

    summary = {
        "checked_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "date": TODAY,
        "results": all_results,
        "javascript_results": js_results,
        "api_results": api_results,
    }

    summary_path = OUT_DIR / "summary.json"

    with summary_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            summary,
            f,
            ensure_ascii=False,
            indent=2,
        )

    # -------------------------------------------------------
    # Výpis
    # -------------------------------------------------------

    print()
    print("=" * 80)
    print("SHRNUTÍ")
    print("=" * 80)

    for result in all_results:

        status = result.get(
            "status_code",
            "ERROR",
        )

        content_type = result.get(
            "content_type",
            "",
        )

        size = result.get(
            "content_length",
            0,
        )

        print(
            f"{result.get('source', ''):35} "
            f"{str(status):>8} "
            f"{size:>10,} B "
            f"{content_type[:35]}"
        )

    print()
    print(
        f"JS analýz:       {len(js_results)}"
    )
    print(
        f"API endpointů:   {len(api_results)}"
    )
    print(
        f"Souhrn uložen:   {summary_path}"
    )

    print()
    print("=" * 80)
    print("HOTOVO")
    print("=" * 80)


if __name__ == "__main__":
    main()
