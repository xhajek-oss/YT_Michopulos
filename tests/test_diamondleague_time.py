from scrapers.diamondleague import _extract_program_start


def test_main_program_hour_only():
    text = """
    17h: Doors open at King Baudouin Stadium
    17h30: Pre-program
    19h: Opening ceremony
    20h: Main program
    22h05: Laser and light show
    """
    assert _extract_program_start([text]) == (20, 0)


def test_main_program_with_minutes():
    assert _extract_program_start(["20h15: Main programme"]) == (20, 15)


def test_event_time_fallback():
    text = "18:42 Women's 400m hurdles 19:05 Men's pole vault"
    assert _extract_program_start([text]) == (18, 42)
