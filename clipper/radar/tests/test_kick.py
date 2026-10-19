"""Kick source (#69, D45). Offline: saved kick.com clip JSON, fake HTTP session, fake Kick client."""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

CLIPPER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(CLIPPER), str(CLIPPER / "editor")]

import run_pipeline  # noqa: E402
from radar import capture, heat, kick, top_clips  # noqa: E402
from radar.tests.test_pipeline_radar import FakeTwitch, fake_youtube  # noqa: E402
from radar.tests.test_radar import FIX, migrate_db  # noqa: E402

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
WEEK = json.loads((FIX / "kick" / "clips_week.json").read_text())


class Resp:
    def __init__(self, body, status=200, ctype="application/json"):
        self.body, self.status_code, self.headers = body, status, {"content-type": ctype}
        self.ok = status < 400

    def json(self):
        return self.body

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, *resps):
        self.resps, self.calls = list(resps), []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        return self.resps.pop(0)


class FakeKick:
    """Saved week clips for every slug; `day` = the same clips (ids unique per slug)."""

    def __init__(self, clips=None, fail=None, live=()):
        self.clips, self.fail, self.live, self.calls = clips or WEEK["clips"], fail or {}, set(live), []

    def get_clips(self, slug, window="week", max_pages=1):
        self.calls.append((slug, window, max_pages))
        if slug in self.fail:
            raise self.fail[slug]
        return [dict(c, id=f"{slug}-{c['id']}") for c in self.clips]

    def is_live(self, slug):
        return slug in self.live


@pytest.fixture
def con():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    migrate_db(db)
    yield db
    db.close()


# --- client --------------------------------------------------------------------------------------

def test_get_clips_pages_by_cursor_and_stops_on_short_page():
    full = {"clips": [WEEK["clips"][0]] * kick.PAGE, "nextCursor": "c1"}
    s = FakeSession(Resp(full), Resp({"clips": WEEK["clips"][:3], "nextCursor": "c2"}))
    got = kick.Kick(session=s, pause_s=0).get_clips("adinross", "week", max_pages=5)
    assert len(got) == kick.PAGE + 3 and len(s.calls) == 2           # short page = last page
    (url, p1, h), (_, p2, _) = s.calls
    assert url == "https://kick.com/api/v2/channels/adinross/clips"
    assert p1 == {"sort": "view", "time": "week"} and p2["cursor"] == "c1"
    assert h["User-Agent"] == kick.UA and h["Accept"] == "application/json"


@pytest.mark.parametrize("resp", [Resp("<html>Just a moment...</html>", 200, "text/html"),
                                  Resp({}, 403), Resp({}, 429)])
def test_challenge_or_block_raises_kick_blocked(resp):
    with pytest.raises(kick.KickBlocked):
        kick.Kick(session=FakeSession(resp), pause_s=0).get_clips("adinross")


def test_is_live_reads_channel_livestream():
    k = kick.Kick(session=FakeSession(Resp({"slug": "a", "livestream": {"is_live": True}}),
                                      Resp({"slug": "a", "livestream": None})), pause_s=0)
    assert k.is_live("a") is True and k.is_live("a") is False


# --- candidates ----------------------------------------------------------------------------------

def test_normalize_matches_radar_candidate_shape():
    c = kick.normalize(WEEK["clips"][0], "AdinRoss", NOW)
    assert c["creator"] == "adinross" and c["source"] == "kick"
    assert c["url"] == "https://kick.com/adinross/clips/clip_01M53XKZ7J7VGSNTGTHP6T7JHM"
    assert c["video_id"] == "132725881" and c["vod_offset"] is None
    assert c["duration_s"] == 70.0 and c["view_count"] == 28208
    assert c["views_per_hour"] == pytest.approx(28208 / ((NOW - top_clips.parse_ts(c["created_at"])).total_seconds() / 3600))


def test_mature_and_private_clips_are_skipped():
    clips = [dict(WEEK["clips"][0], is_mature=True), dict(WEEK["clips"][1], privacy="private"), WEEK["clips"][2]]
    got = kick.collect(FakeKick(clips), ["adinross"], 1, now=NOW)
    assert [c["clip_id"] for c in got] == ["adinross-" + WEEK["clips"][2]["id"]]


def test_overlapping_kick_clips_count_once():
    # "pp" (163 s, made 00:02:15) and "faceoff" (180 s, made 00:03:03) cover the same footage.
    got = {c["title"] for c in kick.collect(FakeKick(), ["adinross"], 1, now=NOW)}
    assert "pp" in got and "faceoff" not in got
    assert {"opgkepor", "AMANDA AND ?", "Michael Beasley 👀", "gg"} <= got


def test_collect_widens_day_to_week_and_respects_allowed():
    fk = FakeKick()
    kick.collect(fk, ["adinross", "n3on"], 50, now=NOW, allowed=["adinross"])
    assert fk.calls == [("adinross", "day", 1), ("adinross", "week", 1)]


def test_a_block_stops_kick_for_the_pass_and_a_bad_slug_is_skipped():
    logs = []
    fk = FakeKick(fail={"gone": ValueError("404"), "n3on": kick.KickBlocked("403")})
    got = kick.collect(fk, ["gone", "adinross", "n3on", "clavicular"], 1, now=NOW, log=logs.append)
    assert {c["creator"] for c in got} == {"adinross"}
    assert [s for s, _, _ in fk.calls] == ["gone", "adinross", "n3on"]   # nothing after the block
    assert len(logs) == 2


def test_same_moment_on_twitch_and_kick_is_one_pick():
    tw = {"creator": "xqc", "source": "twitch", "created_at": "2026-10-17T03:15:00Z", "duration_s": 30.0,
          "views_per_hour": 900.0, "clip_id": "tw"}
    k_same = dict(kick.normalize(WEEK["clips"][0], "xqc", NOW), views_per_hour=500.0)    # made 03:14:42, 70 s
    k_other = dict(k_same, clip_id="later", created_at="2026-10-17T05:00:00Z")
    got = [c["clip_id"] for c in kick.dedupe([k_same, tw, k_other])]
    assert got == ["tw", "later"]
    # different streamers never collapse; ids map a slug to its streamer name
    assert not kick.same_moment(tw, dict(k_same, creator="adinross"))
    assert kick.same_moment(dict(tw, creator="xqcow"), k_same, ids={"xqcow": "xQc", "xqc": "xQc"})


# --- window, registration, capture ----------------------------------------------------------------

@pytest.mark.parametrize("dur,window", [(45.0, (0, 45.0)), (62.0, (2.0, 62.0)), (180.0, (120.0, 180.0))])
def test_long_kick_clip_keeps_its_last_60_s(dur, window):
    assert top_clips.pick_window({"source": "kick", "duration_s": dur, "vod_offset": None}) == window


def test_register_kick_clip_creates_kick_creator(con):
    c = kick.normalize(WEEK["clips"][4], "adinross", NOW)   # 163 s
    top_clips.store(con, [c])
    top_clips.register_clips(con, [c])
    cr = con.execute("SELECT name, main_platform, channel_url FROM creators").fetchone()
    assert tuple(cr) == ("adinross", "kick", "https://kick.com/adinross")
    row = con.execute("SELECT c.start_s, c.end_s, r.source FROM clips c JOIN radar_candidates r"
                      " ON r.clips_id=c.id").fetchone()
    assert tuple(row) == (103.0, 163.0, "kick")


def test_capture_downloads_the_whole_kick_clip(tmp_path):
    cmds = []

    def runner(cmd, check):
        cmds.append(cmd)
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"x")
    url = "https://kick.com/adinross/clips/clip_01M53XKZ7J7VGSNTGTHP6T7JHM"
    paths = capture.capture([{"clip_id": "clip_01M53XKZ7J7VGSNTGTHP6T7JHM", "source_url": url,
                              "start": 10, "end": 70}], work=tmp_path, runner=runner)
    assert paths["clip_01M53XKZ7J7VGSNTGTHP6T7JHM"].name == "clip_01M53XKZ7J7VGSNTGTHP6T7JHM.mp4"
    assert cmds[0][-1] == url and "--download-sections" not in cmds[0]


# --- Heat Index ------------------------------------------------------------------------------------

def test_kick_views_split_24h_and_week():
    fk = FakeKick()
    D, W = heat.kick_views(fk, "adinross", NOW)
    assert W == sum(c["view_count"] for c in WEEK["clips"])
    assert D == 28208                                       # only "opgkepor" is from the last 24 h
    assert fk.calls == [("adinross", "week", heat.KICK_PAGES)]


def test_default_fetchers_route_kick_entries():
    views, live = heat.default_fetchers(tw=None, kc=FakeKick(live={"adinross"}))
    e = {"platform": "kick", "id": "adinross"}
    assert views(e, NOW)[1] > 0 and live(e) is True
    assert live({"platform": "kick", "id": "n3on"}) is False


# --- pipeline wiring -------------------------------------------------------------------------------

ALLOC = {"slots": {"Kai Cenat": 1, "Adin Ross": 1},
         "ids": {"kaicenat": "Kai Cenat", "kai cenat": "Kai Cenat", "adinross": "Adin Ross", "adin ross": "Adin Ross",
                 "n3on": "N3on"}}


def fake_kick_moments(slugs, now, n):
    return kick.collect(FakeKick(), slugs, n, now=NOW)


def test_radar_step_serves_a_kick_slot(con):
    ids = run_pipeline.radar_step(con, FakeTwitch(), ["kaicenat"], allocate=lambda c, n: ALLOC,
                                  youtube=fake_youtube, now=NOW, kick=fake_kick_moments,
                                  kick_from=["adinross", "n3on"])
    rows = con.execute("SELECT r.creator, r.source, c.start_s, c.end_s, r.duration_s FROM clips c"
                       " JOIN radar_candidates r ON r.clips_id=c.id ORDER BY c.id").fetchall()
    assert len(ids) == 2
    assert {(r["creator"], r["source"]) for r in rows} == {("kaicenat", "twitch"), ("adinross", "kick")}
    k = next(r for r in rows if r["source"] == "kick")
    assert k["end_s"] - k["start_s"] <= top_clips.MAX_PICK_S and k["end_s"] == k["duration_s"]
    assert not con.execute("SELECT 1 FROM radar_candidates WHERE creator='n3on'").fetchone()   # no slot


def test_kick_failure_keeps_twitch_picks(con):
    def boom(slugs, now, n):
        raise RuntimeError("kick down")
    ids = run_pipeline.radar_step(con, FakeTwitch(), ["kaicenat"], allocate=lambda c, n: ALLOC,
                                  youtube=fake_youtube, now=NOW, kick=boom, kick_from=["adinross"])
    assert ids


def test_explicit_creator_list_never_calls_kick(con):
    def must_not_run(slugs, now, n):
        raise AssertionError("Kick called")
    run_pipeline.radar_step(con, FakeTwitch(), ["kaicenat"], allocate=lambda c, n: ALLOC,
                            youtube=fake_youtube, now=NOW, kick=must_not_run)


def test_watchlist_kick_slugs_real_config():
    slugs = run_pipeline.watchlist_kick_slugs()
    assert {"adinross", "xqc"} <= set(slugs) and slugs == sorted(set(slugs))
