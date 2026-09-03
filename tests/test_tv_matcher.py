import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from matching.tv_matcher import score_pair


def row(**kwargs):
    base = dict(
        id=1,
        sport="athletics",
        competition="World Athletics Ultimate Championship",
        name="400m Hurdles Women",
        location="Budapest",
        country="Hungary",
        start_datetime="2026-09-12T16:15:00+00:00",
        end_datetime=None,
        channel="ČT2",
        title="Atletika: World Athletics Ultimate Championship 2026",
        description=None,
    )
    base.update(kwargs)
    keys = list(base)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema = ",".join(f'"{k}" TEXT' for k in keys)
    conn.execute(f"CREATE TABLE x ({schema})")
    cols = ",".join(f'"{k}"' for k in keys)
    placeholders = ",".join("?" for _ in keys)
    conn.execute(
        f"INSERT INTO x ({cols}) VALUES ({placeholders})",
        tuple(base[k] for k in keys),
    )
    return conn.execute("SELECT * FROM x").fetchone()


def test_broad_athletics_block_matches_specific_event():
    event = row()
    tv = row(id=2, start_datetime="2026-09-12T16:00:00+00:00")
    result = score_pair(event, tv)
    assert result.score >= 70
    assert result.status == "match"
    assert "time_overlap" in result.reasons


def test_wrong_sport_is_rejected():
    event = row()
    tv = row(
        id=2,
        channel="Oneplay Sport 2",
        title="ELH: HC Dynamo Pardubice - Mountfield HK",
        description="Hokej",
        start_datetime="2026-09-12T16:00:00+00:00",
    )
    result = score_pair(event, tv)
    assert result.status == "no_match"
    assert result.score == 0


def test_far_time_is_rejected():
    event = row()
    tv = row(id=2, start_datetime="2026-09-13T12:00:00+00:00")
    result = score_pair(event, tv)
    assert result.status == "no_match"
