"""Metrics puller: our own Shorts' public stats -> post_metrics. Offline: fake HTTP."""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import metrics  # noqa: E402

DB = Path(__file__).resolve().parents[2] / "db"
NOW = datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc)


def db():
    c = sqlite3.connect(":memory:")
    c.executescript((DB / "schema.sql").read_text())
    c.executescript((DB / "ledger.sql").read_text())
    for f in sorted((DB / "migrations").glob("*.sql")):
        c.executescript(f.read_text())
    c.execute("INSERT INTO creators (id, name) VALUES (1, 'x')")
    c.execute("INSERT INTO sources (id, creator_id, url) VALUES (1, 1, 'u')")
    c.execute("INSERT INTO accounts (id, platform, handle) VALUES (1, 'youtube', 'peakz')")
    for i, (vid, posted) in enumerate([("AAA", "2026-10-19 19:20:57"), ("BBB", "2026-10-19 23:30:00"),
                                       ("OLD", "2026-09-01 10:00:00")], 1):
        c.execute("INSERT INTO clips (id, source_id, start_s, end_s, state, title) VALUES (?, 1, 0, 20, 'published', ?)",
                  (i, f"t{i}"))
        c.execute("INSERT INTO radar_candidates (clip_id, creator, url, view_count, clip_created_at, views_per_hour,"
                  " clips_id) VALUES (?, 'valkyrae', 'u', 1, '2026-10-19T00:00:00Z', 1, ?)", (f"c{i}", i))
        c.execute("INSERT INTO posts (clip_id, account_id, platform_post_id, url, posted_at) VALUES (?,1,?,?,?)",
                  (i, vid, f"https://youtube.com/shorts/{vid}", posted))
    c.commit()
    return c


class FakeYT:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params["id"])
        items = [{"id": "AAA", "statistics": {"viewCount": "1234", "likeCount": "56", "commentCount": "7"}}]
        return NS(json=lambda: {"items": items}, raise_for_status=lambda: None)


def test_measures_recent_public_shorts_only():
    con, yt = db(), FakeYT()
    assert metrics.run(con, "key", yt, NOW) == 1                 # BBB still processing, OLD too old
    assert yt.calls == ["AAA,BBB"]
    row = con.execute("SELECT post_id, views, likes, comments, hours_since_post FROM post_metrics").fetchone()
    assert row[:4] == (1, 1234, 56, 7) and 4.6 < row[4] < 4.7


def test_throttled_to_hourly():
    con, yt = db(), FakeYT()
    metrics.run(con, "key", yt, NOW)
    assert metrics.run(con, "key", yt, NOW.replace(minute=30)) == 0 and yt.calls == ["AAA,BBB", "BBB"]


def test_no_key_no_calls():
    con, yt = db(), FakeYT()
    assert metrics.run(con, None, yt, NOW) == 0 and yt.calls == []


def test_report_lists_views_per_short():
    con = db()
    metrics.run(con, "key", FakeYT(), NOW)
    text = metrics.report(con)
    assert text.startswith("📈 3 Shorts · 1,234 views")
    assert "valkyrae: 1,234 views (" in text and "processing" in text
