# Sports Events Scraper

MVP scraper for public sports event dates.

Targets:
- HC Dynamo
- Biathlon World
- IIHF
- Diamond League
- World Athletics

The project separates API discovery (Playwright) from normal scraping.
Only public scheduling data is targeted. Authentication, CAPTCHA bypass,
anti-bot bypass, purchases and protected actions are out of scope.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Run

```bash
python main.py
```

Run API discovery:

```bash
python -m discovery.api_discovery
```

Run tests:

```bash
pytest
```

The SQLite database is created at `data/sports_events.db`.
