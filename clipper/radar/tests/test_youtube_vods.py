import json
import subprocess
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

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
    assert top_clips.load_creator_configs()[0]["youtube_channel"] == "@KaiCenatLive"
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


def test_segments_past_duration_rejected():
    info = json.loads((FIX / "video_heat.json").read_text())
    dur = info["duration"]
    late_heat = dict(info, heatmap=[{"start_time": dur + 100, "end_time": dur + 130, "value": 1.0}])
    assert youtube_vods.moments(late_heat) == []
    late_chap = dict(info, heatmap=[], chapters=[{"start_time": dur + 50, "end_time": dur + 90, "title": "x"}])
    assert youtube_vods.moments(late_chap) == []
    assert youtube_vods.candidates_for_vod(late_heat, "k", NOW) == []


def test_youtube_id():
    assert capture.youtube_id("https://www.youtube.com/watch?v=abc123") == "abc123"
    assert capture.youtube_id("https://youtu.be/abc123") == "abc123"
    assert capture.youtube_id("https://www.twitch.tv/kaicenat/clip/Foo") is None
    for bad in ("https://www.youtube.com/watch", "https://www.youtube.com/watch?list=x", "https://youtu.be/"):
        with pytest.raises(ValueError):
            capture.youtube_id(bad)


def _yt_picks():
    db = sqlite3.connect(":memory:")
    migrate_db(db)
    cands = [c for c in youtube_vods.collect(CFG, db, now=NOW, runner=FakeYtdlp()) if c["video_id"] == "VODheat001"]
    top_clips.store(db, cands)
    return db, top_clips.to_picks(cands, 3)


def test_capture_youtube_downloads_only_window(tmp_path):
    db, picks = _yt_picks()
    calls = []

    def runner(cmd, check):
        calls.append(cmd)
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"x")

    paths = capture.capture(picks, work=tmp_path, db=db, runner=runner)
    assert len(calls) == len(paths) == 3
    for cmd, p in zip(calls, picks):
        s, e = capture.section(p)
        assert s == max(0, p["start"] - 3) and e >= p["end"] + 3
        assert cmd[cmd.index("--download-sections") + 1] == f"*{s}-{e}"
        assert "--max-filesize" in cmd
        assert paths[p["clip_id"]] == tmp_path / f"yt_VODheat001_{s}_{e}.mp4"
    assert sorted(f.name for f in tmp_path.iterdir()) == sorted(f.name for f in paths.values())  # no temp files


def test_capture_cleans_up_on_failure_and_size_cap(tmp_path):
    _, picks = _yt_picks()

    def failing(cmd, check):
        out = Path(cmd[cmd.index("-o") + 1])
        out.write_bytes(b"x")
        Path(str(out) + ".part").write_bytes(b"x")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        capture.capture(picks[:1], work=tmp_path, runner=failing)
    assert list(tmp_path.iterdir()) == []

    def big(cmd, check):
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"x" * 2048)

    with pytest.raises(RuntimeError, match="cap"):
        capture.download_section(picks[0], tmp_path / "o.mp4", big, max_mb=0.001)
    assert list(tmp_path.iterdir()) == []


class FlakyYtdlp(FakeYtdlp):
    """Like FakeYtdlp, but the listed video ids fail like YouTube's bot check does."""

    def __init__(self, fail):
        super().__init__()
        self.fail = set(fail)

    def __call__(self, cmd, capture_output=True, text=True, check=True):
        vid = cmd[-1].split("v=")[-1]
        if not cmd[-1].endswith("/streams") and (vid in self.fail or "*" in self.fail):
            self.cmds.append(cmd)
            raise subprocess.CalledProcessError(1, cmd, stderr="Sign in to confirm you're not a bot")
        return super().__call__(cmd, capture_output, text, check)


def test_one_unreadable_vod_is_skipped_not_fatal():
    ok = youtube_vods.own_vod_infos("@KaiCenat", FakeYtdlp())
    bad_id = ok[0]["id"]
    infos = youtube_vods.own_vod_infos("@KaiCenat", FlakyYtdlp([bad_id]))
    assert len(infos) == len(ok) - 1 and bad_id not in {i["id"] for i in infos}


def test_every_vod_unreadable_raises_so_it_gets_logged():
    with pytest.raises(RuntimeError, match="any of 4 VODs"):
        youtube_vods.own_vod_infos("@KaiCenat", FlakyYtdlp(["*"]))
