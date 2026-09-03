import sqlite3
from pathlib import Path
from models.sports_event import SportsEvent


class SQLiteStorage:
    def __init__(self, path: str = "data/sports_events.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self._create_schema()

    def _column_names(self):
        rows = self.conn.execute("PRAGMA table_info(sports_events)").fetchall()
        return {row[1] for row in rows}

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
                timezone TEXT,
                UNIQUE(source, source_id, start_datetime, name)
            )
            """
        )

        # Backward-compatible migration for an existing database.
        if "timezone" not in self._column_names():
            self.conn.execute("ALTER TABLE sports_events ADD COLUMN timezone TEXT")

        self.conn.commit()

    def upsert(self, event: SportsEvent):
        self.conn.execute(
            """
            INSERT INTO sports_events (
                source, source_id, sport, competition, name,
                start_datetime, end_datetime, location, country,
                source_url, discovered_at, timezone
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, source_id, start_datetime, name)
            DO UPDATE SET
                sport = excluded.sport,
                competition = excluded.competition,
                end_datetime = excluded.end_datetime,
                location = excluded.location,
                country = excluded.country,
                source_url = excluded.source_url,
                discovered_at = excluded.discovered_at,
                timezone = excluded.timezone
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
                event.timezone,
            ),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
