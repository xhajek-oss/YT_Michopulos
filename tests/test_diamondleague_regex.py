from datetime import timezone

from scrapers.diamondleague import (
    MAIN_PROGRAM_RE,
    TIME_RE,
    _extract_program_start,
    _make_event,
)


def test_regex_matches_real_brussels_main_program():
    match = MAIN_PROGRAM_RE.search("20h: Main program")
    assert match is not None
    assert match.group("hour") == "20"


def test_time_regex_formats():
    assert TIME_RE.search("20h")
    assert TIME_RE.search("17h30")
    assert TIME_RE.search("18:42")
    assert TIME_RE.search("18.42")


def test_extract_real_brussels_program():
    text = """
    Programme
    17h: Doors open at King Baudouin Stadium
    17h30: Pre-program
    19h: Opening ceremony
    20h: Main program
    22h05: Laser and light show
    """
    assert _extract_program_start([text]) == (20, 0)


def test_brussels_main_program_to_utc():
    meeting = {
        "year": 2026,
        "month": 9,
        "day": 4,
        "city": "Brussels",
        "country": "BEL",
        "timezone": "Europe/Brussels",
    }
    event = _make_event(
        meeting,
        20,
        0,
        "https://brussels.diamondleague.com/en/programme-results/",
    )

    assert event.start_datetime.tzinfo == timezone.utc
    assert event.start_datetime.hour == 18
    assert event.start_datetime.minute == 0
