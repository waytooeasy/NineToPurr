"""run_pipeline Radar wiring (issue #47): Heat slots (D33) + Twitch clips + YouTube VOD moments (D29),
D23 start/end per source. Offline: Twitch, yt-dlp and the Heat fetchers are fakes."""
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

CLIPPER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(CLIPPER), str(CLIPPER / "editor")]

import run_pipeline  # noqa: E402
from radar import heat, top_clips, youtube_vods  # noqa: E402
from radar.tests.test_radar import FIX, migrate_db  # noqa: E402
from radar.tests.test_youtube_vods import FakeYtdlp  # noqa: E402

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
RAW = json.loads((FIX / "clips_page1.json").read_text())["data"]
KAI = {"twitch": "kaicenat", "youtube_channel": "@KaiCenat"}
ALLOC = {"slots": {"Kai Cenat": 2, "Other": 1},
         "ids": {"kaicenat": "Kai Cenat", "kai cenat": "Kai Cenat", "other": "Other", "skipped": "Skipped"}}


class FakeTwitch:
    """Same saved clips for every login, ids made unique per login."""

    def broadcaster_id(self, login):
        return login

    def get_clips(self, bid, start, end):
        return [dict(r, id=f"{bid}-{r['id']}", broadcaster_id=bid) for r in RAW]


def fake_youtube(cfgs, con, now):
    return youtube_vods.collect(cfgs, con, now=NOW, runner=FakeYtdlp())


@pytest.fixture
def con():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    migrate_db(db)
    yield db
    db.close()


def step(con, creators, alloc=ALLOC, **kw):
    return run_pipeline.radar_step(con, FakeTwitch(), creators, allocate=lambda c, n: alloc,
                                   youtube=fake_youtube, now=NOW, **kw)


def registered(con):
    return con.execute(
        "SELECT r.creator, r.source, r.clip_id, r.vod_offset, r.duration_s, c.start_s, c.end_s, c.state"
        " FROM clips c JOIN radar_candidates r ON r.clips_id=c.id ORDER BY c.id").fetchall()


def test_heat_slots_limit_creators_and_mix_sources(con):
    ids = step(con, [KAI, "other", "skipped"])
    rows = registered(con)
    assert len(ids) == len(rows) == 3
    assert {r["creator"] for r in rows} == {"kaicenat", "other"}  # "skipped" has no slot
    assert [r["creator"] for r in rows].count("kaicenat") == 2
    assert [r["creator"] for r in rows].count("other") == 1
    assert {r["source"] for r in rows} == {"youtube", "twitch"}


def test_start_end_follow_d23_per_source(con):
    step(con, [KAI, "other"])
    for r in registered(con):
        if r["source"] == "youtube":  # VOD-absolute, never 0
            assert r["start_s"] == r["vod_offset"] > 0
            assert r["end_s"] == r["vod_offset"] + r["duration_s"]
        else:  # the clip is the file
            assert (r["start_s"], r["end_s"]) == (0, r["duration_s"])
        assert r["end_s"] - r["start_s"] <= top_clips.MAX_PICK_S


def test_daily_cap_holds(con):
    assert len(step(con, [KAI, "other"], cap=2)) == 2
    assert step(con, [KAI, "other"], cap=2) == []  # at the cap: pull + store, start nothing


def test_slots_used_today_are_not_reused(con):
    assert len(step(con, [KAI, "other"])) == 3
    assert step(con, [KAI, "other"]) == []  # Kai 2/2 and Other 1/1 already started today
    assert len(registered(con)) == 3


def test_killed_clip_frees_its_slot(con):
    step(con, [KAI, "other"])
    con.execute("UPDATE clips SET state='killed' WHERE id=(SELECT clips_id FROM radar_candidates"
                " WHERE creator='other')")
    con.commit()
    again = step(con, [KAI, "other"])
    assert len(again) == 1
    assert {r["creator"] for r in registered(con) if r["state"] == "found"} == {"kaicenat", "other"}


def test_no_youtube_channel_means_twitch_only(con):
    step(con, ["kaicenat", "other"])
    assert {r["source"] for r in registered(con)} == {"twitch"}


def test_heat_failure_falls_back_to_all_creators_within_cap(con):
    def boom(c, n):
        raise RuntimeError("heat down")
    ids = run_pipeline.radar_step(con, FakeTwitch(), [KAI, "other", "skipped"], allocate=boom,
                                  youtube=fake_youtube, now=NOW, cap=4)
    assert len(ids) == len(registered(con)) == 4  # unfiltered ranking, still capped


def test_youtube_failure_keeps_twitch_picks(con):
    def boom(cfgs, c, n):
        raise RuntimeError("yt-dlp down")
    ids = run_pipeline.radar_step(con, FakeTwitch(), [KAI, "other"], allocate=lambda c, n: ALLOC,
                                  youtube=boom, now=NOW)
    assert ids and {r["source"] for r in registered(con)} == {"twitch"}


def test_picks_found_is_vod_absolute_and_captured_is_file_relative(con):
    step(con, [KAI, "other"])
    found = {p["clip_id"]: p for p in run_pipeline._picks(con, "found")}
    rows = {r["clip_id"]: r for r in registered(con)}
    assert set(found) == set(rows)
    con.execute("UPDATE clips SET state='captured'")
    con.commit()
    rel = {p["clip_id"]: p for p in run_pipeline._picks(con, "captured", file_relative=True)}
    for cid, r in rows.items():
        p, q = found[cid], rel[cid]
        assert (p["start"], p["end"]) == (r["start_s"], r["end_s"])
        assert p["source_url"] and "_row" in p
        if r["source"] == "youtube":
            pad = 3  # capture.PAD_S: the window file starts 3 s before the pick
            assert (q["start"], q["end"]) == (pad, pad + r["duration_s"])
        else:
            assert (q["start"], q["end"]) == (0, r["duration_s"])
    unshifted = run_pipeline._picks(con, "captured")  # capture_step input stays absolute
    assert any(p["start"] > 60 for p in unshifted)


def test_heat_allocation_measures_then_reuses_snapshot(con):
    calls = []

    def views(e, now):
        calls.append(e["id"])
        return (5000, 20000) if e["id"] == "kaicenat" else (100, 700)
    cfg = heat.load_watchlist()
    first = run_pipeline.heat_allocation(con, NOW, cfg=cfg, views=views, live=lambda e: False)
    n = len(calls)
    assert n > 0 and 0 < sum(first["slots"].values()) <= cfg["cap"]
    assert first["ids"]["kaicenat"] == "Kai Cenat" and first["slots"].get("Kai Cenat")
    assert max(first["slots"].values()) <= cfg["max_per"]
    again = run_pipeline.heat_allocation(con, NOW + timedelta(minutes=10), cfg=cfg, views=views,
                                         live=lambda e: False)
    assert len(calls) == n and sum(again["slots"].values()) <= cfg["cap"]  # no re-measure inside 30 min
    run_pipeline.heat_allocation(con, NOW + timedelta(minutes=45), cfg=cfg, views=views, live=lambda e: False)
    assert len(calls) == 2 * n  # stale snapshot -> measure again
