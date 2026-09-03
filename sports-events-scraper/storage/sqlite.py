import sqlite3
from pathlib import Path
from models.sports_event import SportsEvent


class SQLiteStorage:
    def __init__(self, path: str = "data/sports_events.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self._create_schema()

    def _create_schema(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sports_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_id TEXT,
                sport TEXT NOT NULL,
                competition TEXT NOT NULL,
                name TEXT NOT NULL,
                start_datetime TEXT NOT NULL,
                end_datetime TEXT,
                location TEXT,
                country TEXT,
                source_url TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                UNIQUE(source, source_id, start_datetime, name)
            )
            """
        )
        self.conn.commit()

    def upsert(self, event: SportsEvent):
        self.conn.execute(
            """
            INSERT OR IGNORE INTO sports_events (
                source, source_id, sport, competition, name,
                start_datetime, end_datetime, location, country,
                source_url, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.source,
                event.source_id,
                event.sport,
                event.competition,
                event.name,
                event.start_datetime.isoformat(),
                event.end_datetime.isoformat() if event.end_datetime else None,
                event.location,
                event.country,
                event.source_url,
                event.discovered_at.isoformat(),
            ),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
