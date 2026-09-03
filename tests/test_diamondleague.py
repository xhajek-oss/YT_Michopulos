from datetime import timezone

from scrapers.diamondleague import (
    _extract_calendar,
    _extract_program_start,
    _make_event,
)


def test_extract_calendar_and_timezone():
    text = """
    Calendar 2026
    16 May Shanghai/Keqiao (CHN)
    04 June Rome (ITA)
    04-05 September Brussels (BEL)
    """

    meetings = _extract_calendar(text, 2026)

    assert len(meetings) == 3
    assert meetings[0]["city"] == "Shanghai/Keqiao"
    assert meetings[0]["timezone"] == "Asia/Shanghai"
    assert meetings[1]["timezone"] == "Europe/Rome"
    assert meetings[2]["timezone"] == "Europe/Brussels"


def test_extract_program_start_ignores_doors_open():
    texts = [
        """
        17h: Doors open at King Baudouin Stadium
        18:42 Women's 400m hurdles
        19:05 Men's pole vault
        """
    ]

    assert _extract_program_start(texts) == (18, 42)


def test_event_is_stored_in_utc():
    meeting = {
        "year": 2026,
        "month": 9,
        "day": 4,
        "city": "Brussels",
        "country": "BEL",
        "timezone": "Europe/Brussels",
    }

    event = _make_event(meeting, 18, 42, "https://brussels.diamondleague.com/")

    assert event.timezone == "Europe/Brussels"
    assert event.start_datetime.tzinfo == timezone.utc
    # Brussels is UTC+2 on 4 September 2026.
    assert event.start_datetime.hour == 16
    assert event.start_datetime.minute == 42
