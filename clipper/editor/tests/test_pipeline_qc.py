"""QC v1, re-render loop and one pipeline pass, offline: Twitch, yt-dlp, Writer LLM, Whisper, ffmpeg are mocked."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

CLIPPER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(CLIPPER), str(CLIPPER / "editor"), str(CLIPPER / "db")]

import clip  # noqa: E402
import migrate  # noqa: E402
import qc  # noqa: E402
import rerender  # noqa: E402
import run_pipeline  # noqa: E402
import writer  # noqa: E402

RAW = json.loads((CLIPPER / "radar/tests/fixtures/clips_page1.json").read_text())["data"][0]
PLAN = {"score": 0.8, "in": 0.0, "out": 30.0,
        "hooks": ["He lost the bet", "Chat did this to Kai", "Kai regrets everything"],
        "context_line": "Kai lost a bet to chat",
        "title": "Kai Cenat loses the bet", "music_risk": True}


# No Heat Index / yt-dlp in the legacy single-source tests.
OFFLINE = dict(allocate=lambda con, now: None, youtube=lambda cfgs, con, now: [])


class FakeTwitch:
    def broadcaster_id(self, login):
        return "641972806"

    def get_clips(self, bid, start, end):
        return [RAW]


@pytest.fixture
def env(tmp_path, monkeypatch):
    db_file = tmp_path / "clip.db"
    migrate.migrate(db_file)
    monkeypatch.setenv("CLIPPER_DB", str(db_file))
    monkeypatch.setenv("CLIPPER_WORK", str(tmp_path / "work"))
    monkeypatch.setenv("CLIPPER_CLIPS", str(tmp_path / "clips"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "clips").mkdir()
    con = run_pipeline.connect(db_file)
    yield con
    con.close()


def add_clip(con, n, state="edited", path=None, **cols):
    """A clips row (with creator + source) in `state`."""
    con.execute("INSERT OR IGNORE INTO creators (name) VALUES ('kaicenat')")
    cid = con.execute("SELECT id FROM creators").fetchone()[0]
    con.execute("INSERT INTO sources (creator_id, url) VALUES (?, ?)", (cid, f"https://x/{n}"))
    sid = con.execute("SELECT id FROM sources WHERE url=?", (f"https://x/{n}",)).fetchone()[0]
    cur = con.execute("INSERT INTO clips (source_id, start_s, end_s, state, file_path) VALUES (?,0,30,?,?)",
                      (sid, state, str(path) if path else None))
    for k, v in cols.items():
        con.execute(f"UPDATE clips SET {k}=? WHERE id=?", (v, cur.lastrowid))
    con.commit()
    return cur.lastrowid


def mp4(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def row(con, cid):
    return con.execute("SELECT * FROM clips WHERE id=?", (cid,)).fetchone()


# ---- QC -----------------------------------------------------------------------------------

def test_qc_passes_good_clip_and_flags_nothing_for_music(env, tmp_path):
    cid = add_clip(env, 1, path=mp4(tmp_path, "a.mp4", b"aaa"), music_risk=1)
    res = qc.run(env, probe=lambda p: 42.0)
    r = row(env, cid)
    assert res["passed"] == [cid] and r["state"] == "qc_passed"
    assert r["file_hash"] and r["qc_passed_at"] and r["last_error"] is None
    assert r["music_risk"] == 1  # passes, stays flagged for Telegram


def test_qc_blocks_over_60s(env, tmp_path):
    cid = add_clip(env, 1, path=mp4(tmp_path, "a.mp4", b"aaa"))
    res = qc.run(env, probe=lambda p: 61.0)
    assert cid in res["failed"] and row(env, cid)["state"] == "edited"
    assert "duration" in row(env, cid)["last_error"]


def test_qc_blocks_duplicate_file(env, tmp_path):
    a = add_clip(env, 1, path=mp4(tmp_path, "a.mp4", b"same"))
    b = add_clip(env, 2, path=mp4(tmp_path, "b.mp4", b"same"))
    res = qc.run(env, probe=lambda p: 20.0)
    assert res["passed"] == [a] and b in res["failed"]
    assert f"duplicate of clip {a}" in row(env, b)["last_error"] and row(env, b)["state"] == "edited"
    qc.run(env, probe=lambda p: 20.0)  # a second pass must not deadlock or pass the duplicate
    assert row(env, b)["state"] == "edited"


def test_qc_daily_cap_and_next_day(env, tmp_path):
    ids = [add_clip(env, i, path=mp4(tmp_path, f"{i}.mp4", bytes([i]))) for i in range(1, qc.DAILY_CAP + 3)]
    res = qc.run(env, probe=lambda p: 20.0)
    assert len(res["passed"]) == qc.DAILY_CAP and set(res["failed"]) == set(ids[qc.DAILY_CAP:])
    assert f"daily cap {qc.DAILY_CAP}" in row(env, ids[qc.DAILY_CAP])["last_error"]
    env.execute("UPDATE clips SET qc_passed_at=datetime('now','-1 day')")  # yesterday's don't count
    env.commit()
    assert len(qc.run(env, probe=lambda p: 20.0)["passed"]) == 2


def test_qc_missing_file_and_probe_fallback(env, tmp_path):
    gone = add_clip(env, 1, path=tmp_path / "nope.mp4")
    ok = add_clip(env, 2, path=mp4(tmp_path, "b.mp4", b"b"))

    def no_ffprobe(p):
        raise FileNotFoundError("ffprobe")
    res = qc.run(env, probe=no_ffprobe)  # falls back to DB duration (30 s)
    assert "file missing" in row(env, gone)["last_error"] and res["passed"] == [ok]


# ---- re-render loop -----------------------------------------------------------------------

def fake_render(video, pick, ass, out):
    Path(out).write_bytes(("hook:" + pick["hook"]).encode())


def test_rerender_uses_new_hook_and_requeues(env, tmp_path, monkeypatch):
    src = mp4(tmp_path, "src.mp4", b"source")
    short = mp4(tmp_path, "short.mp4", b"old")
    cid = add_clip(env, 1, state="needs_rerender", path=short, hook_text="Lucas's better hook",
                   context_line="Kai lost a bet", approval_sent_at="2026-10-16 10:00:00", file_hash="old")
    env.execute("INSERT INTO radar_candidates (clip_id, creator, url, view_count, clip_created_at, views_per_hour,"
                " file_path, clips_id) VALUES ('ClipA','kaicenat','u',1,'2026-10-16T10:00:00Z',1,?,?)", (str(src), cid))
    env.commit()
    monkeypatch.setattr(clip, "transcribe", lambda v, w, m: [{"s": 1.0, "e": 1.5, "w": "hi"}])
    monkeypatch.setattr(clip, "render", fake_render)

    res = rerender.run(env)
    r = row(env, cid)
    assert res["done"] == [cid] and r["state"] == "qc_passed"
    assert r["approval_sent_at"] is None and r["file_hash"] != "old"
    assert short.read_bytes() == b"hook:Lucas's better hook" and not list(tmp_path.glob("*.rr.mp4"))


def test_rerender_failure_sets_error_and_leaves_state(env, tmp_path):
    cid = add_clip(env, 1, state="needs_rerender", path=tmp_path / "s.mp4", hook_text="x")
    env.execute("INSERT INTO radar_candidates (clip_id, creator, url, view_count, clip_created_at, views_per_hour,"
                " file_path, clips_id) VALUES ('ClipA','k','u',1,'2026-10-16T10:00:00Z',1,'/nope.mp4',?)", (cid,))
    env.commit()
    res = rerender.run(env)
    assert cid in res["failed"] and row(env, cid)["state"] == "needs_rerender"
    assert "captured source missing" in row(env, cid)["last_error"]
    assert rerender.run(env) == {"done": [], "failed": {}}  # backed off for 2 h


# ---- pipeline -----------------------------------------------------------------------------

def mock_media(monkeypatch, tmp_path):
    def fake_transcribe(video, work, model):
        (work / "transcript.txt").write_text("[0.0-5.0] hello there")
        return [{"s": 1.0, "e": 1.5, "w": "hello"}]
    monkeypatch.setattr(clip, "transcribe", fake_transcribe)
    monkeypatch.setattr(clip, "render", fake_render)
    monkeypatch.setattr(writer, "write_clip", lambda win, creator, meta=None, clip_id=None: PLAN)


def ytdlp(cmd, check):
    Path(cmd[cmd.index("-o") + 1]).write_bytes(b"twitch clip")


def test_pass_walks_found_to_qc_passed(env, tmp_path, monkeypatch):
    mock_media(monkeypatch, tmp_path)
    report = run_pipeline.run_pass(env, steps={
        "radar": lambda: run_pipeline.radar_step(env, FakeTwitch(), ["kaicenat"], **OFFLINE),
        "capture": lambda: run_pipeline.capture_step(env, runner=ytdlp),
        "editor": lambda: run_pipeline.editor_step(env, out=str(tmp_path / "clips")),
        "qc": lambda: qc.run(env, probe=lambda p: 30.0),
        "rerender": lambda: rerender.run(env),
    })
    assert not any(str(v).startswith("error") for v in report.values()), report
    r = env.execute("SELECT * FROM clips").fetchone()
    assert r["state"] == "qc_passed" and r["last_error"] is None
    assert r["hook_text"] == PLAN["hooks"][0] and r["music_risk"] == 1 and r["file_hash"]
    assert Path(r["file_path"]).read_bytes() == b"hook:He lost the bet"

    # Second pass is a no-op: nothing is redone, no duplicate row.
    calls = []
    monkeypatch.setattr(writer, "write_clip", lambda *a, **k: calls.append(1) or PLAN)
    run_pipeline.run_pass(env, steps={
        "radar": lambda: run_pipeline.radar_step(env, FakeTwitch(), ["kaicenat"], **OFFLINE),
        "capture": lambda: run_pipeline.capture_step(env, runner=ytdlp),
        "editor": lambda: run_pipeline.editor_step(env, out=str(tmp_path / "clips")),
        "qc": lambda: qc.run(env, probe=lambda p: 30.0),
    })
    assert env.execute("SELECT COUNT(*) FROM clips").fetchone()[0] == 1 and not calls


def test_edit_hook_loop_back_to_qc_passed(env, tmp_path, monkeypatch):
    """qc_passed -> (Lucas edits hook) needs_rerender -> pass -> qc_passed, resent."""
    mock_media(monkeypatch, tmp_path)
    run_pipeline.radar_step(env, FakeTwitch(), ["kaicenat"], **OFFLINE)
    run_pipeline.capture_step(env, runner=ytdlp)
    run_pipeline.editor_step(env, out=str(tmp_path / "clips"))
    qc.run(env, probe=lambda p: 30.0)
    env.execute("UPDATE clips SET approval_sent_at=datetime('now')")
    env.execute("UPDATE clips SET state='needs_rerender', hook_text='New hook'")  # what the bot does
    env.commit()
    run_pipeline.run_pass(env, steps={"rerender": lambda: rerender.run(env)})
    r = env.execute("SELECT * FROM clips").fetchone()
    assert r["state"] == "qc_passed" and r["approval_sent_at"] is None
    assert Path(r["file_path"]).read_bytes() == b"hook:New hook"


def test_capture_failure_marks_only_that_clip(env, tmp_path):
    run_pipeline.radar_step(env, FakeTwitch(), ["kaicenat"], **OFFLINE)

    def boom(cmd, check):
        raise RuntimeError("yt-dlp exploded")
    assert run_pipeline.capture_step(env, runner=boom) == 0
    r = env.execute("SELECT state, last_error FROM clips").fetchone()
    assert r["state"] == "found" and "yt-dlp exploded" in r["last_error"]


def test_radar_respects_daily_cap(env):
    for i in range(qc.DAILY_CAP):
        add_clip(env, i, state="captured")
    assert run_pipeline.radar_step(env, FakeTwitch(), ["kaicenat"], **OFFLINE) == []


def test_stage_error_does_not_stop_pass(env):
    def bad():
        raise RuntimeError("twitch down")
    report = run_pipeline.run_pass(env, steps={"radar": bad, "qc": lambda: qc.run(env)})
    assert report["radar"].startswith("error") and report["qc"] == {"passed": [], "failed": {}}


def test_lock_blocks_second_pass(tmp_path):
    lock = tmp_path / "p.lock"
    with run_pipeline.locked(lock) as first:
        assert first
        with run_pipeline.locked(lock) as second:
            assert second is False
    with run_pipeline.locked(lock) as again:
        assert again
