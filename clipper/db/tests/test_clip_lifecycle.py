"""One clip walks found -> captured -> drafted -> edited through Radar + Editor code (offline, LLM mocked)."""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

CLIPPER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(CLIPPER), str(CLIPPER / "editor"), str(CLIPPER / "db")]

import clip  # noqa: E402
import migrate  # noqa: E402
import writer  # noqa: E402
from radar import capture, top_clips  # noqa: E402

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
RAW = json.loads((CLIPPER / "radar/tests/fixtures/clips_page1.json").read_text())["data"][0]
PLAN = {"score": 0.8, "in": 0.0, "out": 30.0,
        "hooks": ["He lost the bet", "Chat did this to Kai", "Kai regrets everything"],
        "context_line": "Kai lost a bet to chat",
        "title": "Kai Cenat loses the bet", "music_risk": True}


def state(db_file):
    c = sqlite3.connect(db_file)
    try:
        return c.execute("SELECT state FROM clips").fetchone()[0]
    finally:
        c.close()


def seed_work(tmp_path):
    work = tmp_path / "work" / "ClipA"
    work.mkdir(parents=True)
    (work / "words.json").write_text(json.dumps([{"s": 1.0, "e": 1.5, "w": "hello"}]))
    (work / "transcript.txt").write_text("[0.0-5.0] hello there")


def test_found_captured_drafted_edited(tmp_path, monkeypatch):
    db_file = tmp_path / "clip.db"
    migrate.migrate(db_file)
    monkeypatch.setenv("CLIPPER_DB", str(db_file))
    monkeypatch.chdir(tmp_path)

    # Radar: store + choose -> clips row 'found'
    db = sqlite3.connect(db_file)
    cand = top_clips.normalize(RAW, "kaicenat", NOW)
    top_clips.store(db, [cand])
    top_clips.register_clips(db, [cand])
    picks = top_clips.to_picks([cand], 1)
    assert state(db_file) == "found"

    # Capture: fake yt-dlp writes the file
    def fake_ytdlp(cmd, check):
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"x")
    paths = capture.capture(picks, work=tmp_path / "w", db=db, runner=fake_ytdlp)
    assert state(db_file) == "captured"
    assert db.execute("SELECT file_path FROM clips").fetchone()[0] == str(paths["ClipA"])
    db.close()

    # Editor: pre-seeded transcript, mocked Writer + render
    seed_work(tmp_path)
    monkeypatch.setattr(writer, "write_clip", lambda win, creator, meta=None, clip_id=None: PLAN)
    seen = {}

    def fake_render(video, pick, ass, out):
        seen["state_at_render"] = state(db_file)
        Path(out).write_bytes(b"mp4")
    monkeypatch.setattr(clip, "render", fake_render)

    picks_file = tmp_path / "picks.json"
    picks_file.write_text(json.dumps(picks))
    clip.main(["--picks", str(picks_file), "--auto", "--creator", "Kai Cenat"])

    assert seen["state_at_render"] == "drafted"
    c = sqlite3.connect(db_file)
    c.row_factory = sqlite3.Row
    r = c.execute("SELECT * FROM clips").fetchone()
    assert r["state"] == "edited"
    assert r["file_path"].endswith("ClipA_01_en.mp4") and Path(r["file_path"]).exists()
    assert r["model_score"] == 0.8 and r["context_line"] == "Kai lost a bet to chat"
    assert json.loads(r["hooks_json"]) == PLAN["hooks"] and r["hook_text"] == PLAN["hooks"][0]
    assert r["title"] == "Kai Cenat loses the bet" and r["music_risk"] == 1
    assert (tmp_path / "clips_log.csv").exists()  # CSV stays as the debug log
    c.close()


def test_no_db_file_still_renders(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_DB", str(tmp_path / "missing.db"))
    monkeypatch.chdir(tmp_path)
    seed_work(tmp_path)
    monkeypatch.setattr(writer, "write_clip", lambda win, creator, meta=None, clip_id=None: PLAN)
    monkeypatch.setattr(clip, "download", lambda src, w: tmp_path / "v.mp4")
    monkeypatch.setattr(clip, "render", lambda v, p, a, o: Path(o).write_bytes(b"m"))
    pf = tmp_path / "p.json"
    pf.write_text(json.dumps([{"start": 0, "end": 30, "source_url": "https://clips.twitch.tv/ClipA",
                               "creator": "kaicenat", "clip_id": "ClipA"}]))
    clip.main(["--picks", str(pf), "--auto", "--creator", "Kai Cenat"])
    assert (tmp_path / "clips" / "ClipA_01_en.mp4").exists()
    assert not (tmp_path / "missing.db").exists()
