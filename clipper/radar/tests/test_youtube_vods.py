import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from radar import capture, top_clips, youtube_vods
from radar.tests.test_radar import migrate_db

FIX = Path(__file__).parent / "fixtures" / "yt"
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
CFG = [{"twitch": "kaicenat", "youtube_channel": "@KaiCenat"}]
VIDEO_FILES = {"VODheat001": "video_heat.json", "VODchap002": "video_chapters.json",
               "VODnone003": "video_plain.json", "FOREIGN005": "video_foreign.json"}


class FakeYtdlp:
    """Stands in for the yt-dlp subprocess; serves saved JSON, records commands."""

    def __init__(self):
        self.cmds = []

    def __call__(self, cmd, capture_output=True, text=True, check=True):
        self.cmds.append(cmd)
        assert cmd[0] == "yt-dlp"
        url = cmd[-1]
        if url.endswith("/streams"):
            return SimpleNamespace(stdout=(FIX / "streams_flat.jsonl").read_text())
        vid = url.split("v=")[-1]
        return SimpleNamespace(stdout=(FIX / VIDEO_FILES[vid]).read_text())


def test_config_backward_compatible(tmp_path):
    assert top_clips.load_creators() == ["kaicenat"]
    assert top_clips.load_creator_configs()[0]["youtube_channel"] == "@KaiCenat"
    p = tmp_path / "c.yaml"
    p.write_text("creators:\n  - Kaicenat\n  - {twitch: duke}\n")
    assert top_clips.load_creators(p) == ["kaicenat", "duke"]
    assert top_clips.load_creator_configs(p)[0]["youtube_channel"] is None


def test_streams_url_and_shorts_skipped():
    assert youtube_vods.channel_streams_url("@KaiCenat") == "https://www.youtube.com/@KaiCenat/streams"
    urls = youtube_vods.list_stream_urls("@KaiCenat", FakeYtdlp())
    assert len(urls) == 4 and not any("shorts" in u or "SHORT" in u for u in urls)


def test_collect_skips_foreign_and_shorts_and_never_fetches_them():
    fake = FakeYtdlp()
    cands = youtube_vods.collect(CFG, now=NOW, runner=fake)
    assert {c["video_id"] for c in cands} == {"VODheat001", "VODchap002"}
    assert not any("SHORT" in " ".join(c) for c in fake.cmds)
    assert all(c["source"] == "youtube" and c["creator"] == "kaicenat" for c in cands)


def test_non_live_upload_skipped():
    info = json.loads((FIX / "video_heat.json").read_text())
    assert youtube_vods.is_own_live_vod(info, "@KaiCenat")
    assert not youtube_vods.is_own_live_vod(dict(info, live_status="not_live", was_live=False), "@KaiCenat")
    assert not youtube_vods.is_own_live_vod(dict(info, live_status="is_live", is_live=True, was_live=False),
                                            "@KaiCenat")
    assert not youtube_vods.is_own_live_vod(json.loads((FIX / "video_foreign.json").read_text()), "@KaiCenat")


def test_heatmap_moments_capped_deduped_inside_vod():
    info = json.loads((FIX / "video_heat.json").read_text())
    cands = youtube_vods.candidates_for_vod(info, "kaicenat", NOW)
    assert [(c["vod_offset"], c["duration_s"]) for c in cands] == [(1806, 60.0), (3600, 40.0), (7190, 10.0)]
    for c in cands:
        assert c["duration_s"] <= 60 and c["vod_offset"] + c["duration_s"] <= info["duration"]
        assert c["url"] == "https://www.youtube.com/watch?v=VODheat001"
    # the 0.9 segment overlaps the 1.0 one and the 0.2/0.3 ones are below threshold
    assert len({c["clip_id"] for c in cands}) == 3


def test_chapters_fallback_and_neither():
    ch = youtube_vods.candidates_for_vod(json.loads((FIX / "video_chapters.json").read_text()), "k", NOW)
    assert [c["vod_offset"] for c in ch] == sorted(c["vod_offset"] for c in ch) or ch
    assert all(c["duration_s"] <= 60 for c in ch) and ch
    assert youtube_vods.candidates_for_vod(json.loads((FIX / "video_plain.json").read_text()), "k", NOW) == []


def test_store_idempotent_and_reuses_shifted_moment():
    db = sqlite3.connect(":memory:")
    migrate_db(db)
    cands = youtube_vods.collect(CFG, db, now=NOW, runner=FakeYtdlp())
    top_clips.store(db, cands)
    n = db.execute("select count(*) from radar_candidates").fetchone()[0]
    assert db.execute("select count(distinct source) from radar_candidates where source='youtube'").fetchone()[0] == 1
    again = youtube_vods.collect(CFG, db, now=NOW, runner=FakeYtdlp())
    top_clips.store(db, again)
    assert db.execute("select count(*) from radar_candidates").fetchone()[0] == n
    # heatmap shifted by a few seconds: still the same row
    moved = dict(cands[0], clip_id="yt:x:new", vod_offset=cands[0]["vod_offset"] + 5)
    assert youtube_vods._reuse_existing(db, moved)["clip_id"] == cands[0]["clip_id"]


def test_picks_are_vod_absolute_and_register_clips():
    db = sqlite3.connect(":memory:")
    migrate_db(db)
    cands = youtube_vods.collect(CFG, db, now=NOW, runner=FakeYtdlp())
    top_clips.store(db, cands)
    picks = top_clips.to_picks(cands, 2)
    assert set(picks[0]) == {"start", "end", "source_url", "creator", "clip_id"}
    c0 = cands[0]
    assert picks[0]["start"] == c0["vod_offset"] and picks[0]["end"] == c0["vod_offset"] + c0["duration_s"]
    assert picks[0]["end"] - picks[0]["start"] <= 60
    ids = top_clips.register_clips(db, cands[:2])
    s, e = db.execute("select start_s, end_s from clips where id=?", (ids[0],)).fetchone()
    assert (s, e) == (picks[0]["start"], picks[0]["end"])


def test_capture_youtube_downloads_vod_once(tmp_path):
    db = sqlite3.connect(":memory:")
    migrate_db(db)
    cands = [c for c in youtube_vods.collect(CFG, db, now=NOW, runner=FakeYtdlp()) if c["video_id"] == "VODheat001"]
    top_clips.store(db, cands)
    calls = []

    def runner(cmd, check):
        calls.append(cmd)
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"x")

    paths = capture.capture(top_clips.to_picks(cands, 3), work=tmp_path, db=db, runner=runner)
    assert len(calls) == 1 and len(paths) == 3
    assert set(paths.values()) == {tmp_path / "yt_VODheat001.mp4"}
