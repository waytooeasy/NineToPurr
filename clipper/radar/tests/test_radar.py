import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar import capture, top_clips
from radar.twitch import Twitch

FIX = Path(__file__).parent / "fixtures"
DB_DIR = Path(__file__).resolve().parents[2] / "db"
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def migrate_db(db):
    for f in ["schema.sql", "ledger.sql", *sorted(p.relative_to(DB_DIR).as_posix() for p in (DB_DIR / "migrations").glob("*.sql"))]:
        db.executescript((DB_DIR / f).read_text())


def fx(name):
    return json.loads((FIX / name).read_text())


class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    """Serves saved Twitch responses; records calls."""

    def __init__(self):
        self.calls = []
        self.token_posts = 0

    def post(self, url, params=None, timeout=None):
        self.token_posts += 1
        return Resp({"access_token": "tok", "expires_in": 5000000, "token_type": "bearer"})

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, dict(params)))
        assert headers["Authorization"] == "Bearer tok"
        if url.endswith("/users"):
            return Resp(fx("users.json"))
        return Resp(fx("clips_page2.json") if params.get("after") else fx("clips_page1.json"))


@pytest.fixture
def tw(tmp_path):
    return Twitch("cid", "secret", session=FakeSession(), cache_path=tmp_path / "tok.json")


def test_token_cached_and_secret_not_in_requests(tw, tmp_path):
    tw.broadcaster_id("kaicenat")
    tw.get_clips("1", NOW, NOW)
    assert tw.http.token_posts == 1
    tw2 = Twitch("cid", "secret", session=FakeSession(), cache_path=tmp_path / "tok.json")
    tw2.broadcaster_id("kaicenat")
    assert tw2.http.token_posts == 0  # read from disk cache


def test_broadcaster_id_and_pagination(tw):
    assert tw.broadcaster_id("kaicenat") == "641972806"
    clips = tw.get_clips("641972806", NOW, NOW)
    assert [c["id"] for c in clips] == ["ClipA", "ClipB", "ClipC", "ClipD", "ClipE"]
    assert tw.http.calls[-1][1]["after"] == "abc123"


def test_score_is_views_per_hour():
    c = top_clips.normalize(fx("clips_page1.json")["data"][0], "kaicenat", NOW)
    assert c["views_per_hour"] == pytest.approx(12000 / 2)  # 2 h old


def test_dedupe_vod_overlap_and_no_vod_title():
    raw = fx("clips_page1.json")["data"] + fx("clips_page2.json")["data"]
    cands = top_clips.dedupe([top_clips.normalize(r, "kaicenat", NOW) for r in raw])
    ids = [c["clip_id"] for c in cands]
    assert "ClipB" not in ids and "ClipE" not in ids  # overlapping VOD window / similar title in 5 min
    assert ids == ["ClipA", "ClipD", "ClipC"]  # ranked by views/hour


def test_no_vod_far_apart_not_deduped():
    a = top_clips.normalize(fx("clips_page2.json")["data"][0], "k", NOW)
    b = dict(a, clip_id="X", created_at="2026-10-16T11:30:00Z")
    assert not top_clips._same_moment(a, b)


def test_collect_widens_when_thin(tw):
    top_clips.collect(tw, ["kaicenat"], min_candidates=10, now=NOW)
    clip_calls = [p for u, p in tw.http.calls if u.endswith("/clips") and "after" not in p]
    assert len(clip_calls) == 2  # 24 h, then 7 days
    assert clip_calls[1]["started_at"] == "2026-10-09T12:00:00Z"


def test_collect_no_widen_when_enough(tw):
    top_clips.collect(tw, ["kaicenat"], min_candidates=2, now=NOW)
    clip_calls = [p for u, p in tw.http.calls if u.endswith("/clips") and "after" not in p]
    assert len(clip_calls) == 1


def test_store_migration_and_picks(tw):
    db = sqlite3.connect(":memory:")
    migrate_db(db)
    cands = top_clips.collect(tw, ["kaicenat"], 2, now=NOW)
    top_clips.store(db, cands)
    top_clips.store(db, cands)  # idempotent
    assert db.execute("select count(*) from radar_candidates").fetchone()[0] == len(cands)
    picks = top_clips.to_picks(cands, 2)
    assert len(picks) == 2
    assert set(picks[0]) == {"start", "end", "source_url", "creator", "clip_id"}
    assert picks[0]["clip_id"] == "ClipA" and picks[0]["end"] <= 60


def test_load_creators():
    assert "kaicenat" in top_clips.load_creators()


def test_capture_runs_ytdlp_and_marks_captured(tmp_path):
    db = sqlite3.connect(":memory:")
    migrate_db(db)
    top_clips.store(db, [top_clips.normalize(fx("clips_page1.json")["data"][0], "kaicenat", NOW)])
    calls = []
    paths = capture.capture([{"clip_id": "ClipA", "source_url": "https://clips.twitch.tv/ClipA"}],
                            work=tmp_path, db=db, runner=lambda cmd, check: calls.append(cmd))
    assert calls[0][0] == "yt-dlp" and calls[0][-1] == "https://clips.twitch.tv/ClipA"
    assert paths["ClipA"] == tmp_path / "ClipA.mp4"
    assert db.execute("select status from radar_candidates").fetchone()[0] == "captured"


def test_register_clips_found_and_linked(tmp_path):
    db = sqlite3.connect(":memory:")
    migrate_db(db)
    cands = top_clips.collect(Twitch("cid", "secret", session=FakeSession(), cache_path=tmp_path / "t.json"),
                              ["kaicenat"], 2, now=NOW)
    top_clips.store(db, cands)
    ids = top_clips.register_clips(db, cands[:2])
    assert len(ids) == 2
    assert top_clips.register_clips(db, cands[:2]) == []  # idempotent
    state, end_s = db.execute("select state, end_s from clips where id=?", (ids[0],)).fetchone()
    assert state == "found" and end_s <= 60
    linked = db.execute("select clips_id from radar_candidates where clip_id=?", (cands[0]["clip_id"],)).fetchone()[0]
    assert linked == ids[0]
    assert db.execute("select count(*) from radar_candidates where clips_id is null").fetchone()[0] == len(cands) - 2
