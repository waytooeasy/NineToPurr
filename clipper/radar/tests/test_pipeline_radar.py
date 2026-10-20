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


def test_radar_creators_covers_every_watchlist_twitch_login():
    wl = {"streamers": {
        "Kai Cenat": [{"platform": "twitch", "id": "kaicenat"}, {"platform": "youtube", "id": "@KaiCenatLive"}],
        "IShowSpeed": [{"platform": "twitch", "id": "IShowSpeed"}, {"platform": "youtube", "id": "@IShowSpeed"}],
        "Sykkuno": [{"platform": "twitch", "id": "sykkuno"}],
    }}
    got = run_pipeline.radar_creators(wl, [{"twitch": "kaicenat", "youtube_channel": "@KaiCenatLive"}])
    assert got == [{"twitch": "kaicenat", "youtube_channel": "@KaiCenatLive"},   # creators.yaml first, no dupe
                   {"twitch": "ishowspeed", "youtube_channel": "@IShowSpeed"},
                   {"twitch": "sykkuno", "youtube_channel": None}]


def test_radar_creators_real_config_serves_every_heat_streamer():
    wl = heat.load_watchlist()
    logins = {c["twitch"] for c in run_pipeline.radar_creators()}
    for name, entries in wl["streamers"].items():
        tw = [e["id"].lower() for e in entries if e["platform"] == "twitch"]
        assert not tw or set(tw) & logins, name


def test_default_radar_step_serves_heat_slots_outside_creators_yaml(con, monkeypatch):
    # The first VM pass (2026-10-19) gave slots to Sykkuno/Valkyrae/xQc while creators.yaml only listed
    # kaicenat -> 0 picks. With the default creator list a slot for a watchlist streamer is served.
    monkeypatch.setattr(run_pipeline, "radar_creators", lambda: [KAI, {"twitch": "other", "youtube_channel": None}])
    ids = run_pipeline.radar_step(con, FakeTwitch(), None, allocate=lambda c, n: {"slots": {"Other": 1},
                                  "ids": {"other": "Other"}}, youtube=fake_youtube, now=NOW)
    rows = registered(con)
    assert len(ids) == 1 and rows[0]["creator"] == "other"


class FakeGit:
    def __init__(self, show="# Format library\n", fail=False):
        self.cmds, self.show, self.fail = [], show, fail

    def __call__(self, cmd, **kw):
        import subprocess
        self.cmds.append(cmd)
        if self.fail:
            raise subprocess.CalledProcessError(128, cmd)
        return type("R", (), {"stdout": self.show if cmd[3] == "show" else ""})()


def test_refresh_formats_copies_trends_library(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_STYLE", str(tmp_path / "style.json"))
    p = tmp_path / "formats" / "library.md"
    git = FakeGit("# Format library (updated today)\n")
    assert run_pipeline.refresh_formats(p, repo=tmp_path, runner=git) == "updated"  # style.json not JSON
    assert p.read_text() == "# Format library (updated today)\n"
    assert git.cmds[0][3:5] == ["fetch", "-q"] and git.cmds[1][-1] == run_pipeline.FORMATS_REF


def test_refresh_formats_skips_when_fresh_and_keeps_old_copy_on_error(tmp_path):
    p = tmp_path / "library.md"
    p.write_text("old")
    git = FakeGit()
    assert run_pipeline.refresh_formats(p, repo=tmp_path, runner=git) == "fresh" and git.cmds == []
    later = p.stat().st_mtime + run_pipeline.FORMATS_MAX_AGE_S + 1
    assert run_pipeline.refresh_formats(p, repo=tmp_path, runner=FakeGit(fail=True), now=later).startswith("error")
    assert p.read_text() == "old"


class FakeGitStyle(FakeGit):
    def __call__(self, cmd, **kw):
        r = super().__call__(cmd, **kw)
        if cmd[3] == "show" and cmd[-1] == run_pipeline.STYLE_REF:
            return type("R", (), {"stdout": '{"caption": {"highlight": "#00FF66"}}'})()
        return r


def test_refresh_formats_also_copies_todays_style(tmp_path, monkeypatch):
    sp = tmp_path / "style.json"
    monkeypatch.setenv("CLIPPER_STYLE", str(sp))
    assert run_pipeline.refresh_formats(tmp_path / "library.md", repo=tmp_path, runner=FakeGitStyle()) == "updated (+style)"
    assert "#00FF66" in sp.read_text()


class FakeGitHashtags(FakeGit):
    def __call__(self, cmd, **kw):
        r = super().__call__(cmd, **kw)
        if cmd[3] == "show" and cmd[-1] == run_pipeline.HASHTAGS_REF:
            return type("R", (), {"stdout": '{"generic": ["#shorts", "#twitch"], "title_share": 0.9}'})()
        return r


def test_refresh_formats_also_copies_todays_hashtags(tmp_path, monkeypatch):
    hp = tmp_path / "hashtags.json"
    monkeypatch.setenv("CLIPPER_HASHTAGS", str(hp))
    monkeypatch.setenv("CLIPPER_STYLE", str(tmp_path / "style.json"))
    run_pipeline.refresh_formats(tmp_path / "library.md", repo=tmp_path, runner=FakeGitHashtags())
    assert "#twitch" in hp.read_text()
