import pathlib
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
DB = pathlib.Path(__file__).resolve().parents[2] / "db"


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript((DB / "schema.sql").read_text())
    c.executescript((DB / "ledger.sql").read_text())
    for f in sorted((DB / "migrations").glob("*.sql")):
        c.executescript(f.read_text())
    c.execute("INSERT INTO creators (id, name) VALUES (1, 'Kai Cenat')")
    c.execute("INSERT INTO sources (id, creator_id, url) VALUES (1, 1, 'https://x/vod')")
    c.commit()
    return c


@pytest.fixture
def add_clip(con):
    def _add(state="qc_passed", hooks='["h one","h two","h three"]', path=None):
        cur = con.execute(
            "INSERT INTO clips (source_id, start_s, end_s, state, hooks_json, context_line, file_path)"
            " VALUES (1, 0, 30, ?, ?, 'Kai loses it', ?)", (state, hooks, path))
        con.commit()
        return cur.lastrowid
    return _add
