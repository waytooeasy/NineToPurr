"""End-to-end, offline: fresh DB -> one pipeline pass (Twitch + YouTube sources) -> `qc_passed`
-> Telegram approval logic -> `approved` -> publisher `run_once` with a fake uploader -> `published`.

Mocked: Twitch API, yt-dlp (metadata and downloads), Whisper, the LLM. Real: SQLite + migrations,
ffmpeg/ffprobe on a tiny synthetic video, QC, the bot's handlers (fake Telegram), the scheduler.
"""
import asyncio
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

CLIPPER = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CLIPPER), str(CLIPPER / "editor"), str(CLIPPER / "db"), str(CLIPPER / "publisher")]

import approvals  # noqa: E402
import approve_bot  # noqa: E402
import clip  # noqa: E402
import migrate  # noqa: E402
import qc  # noqa: E402
import rerender  # noqa: E402
import run_pipeline  # noqa: E402
import upload  # noqa: E402
import writer  # noqa: E402
from radar.tests.test_pipeline_radar import FakeTwitch, KAI, fake_youtube  # noqa: E402

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                reason="needs ffmpeg + ffprobe")

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)   # the radar fixtures are dated around this
CHAT = 111
TRANSCRIPT = "[0.0-2.0] chat what is happening\n[3.5-6.0] he just lost the whole bet"


@pytest.fixture(scope="module")
def synthetic_video(tmp_path_factory):
    """8 s, 320x180, with a sine tone: stands in for every yt-dlp download."""
    out = tmp_path_factory.mktemp("media") / "synthetic.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=15:d=8",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=8", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(out)], check=True)
    return out


@pytest.fixture
def env(tmp_path, monkeypatch):
    db_file = tmp_path / "db" / "clip.db"           # parent dir does not exist: migrate creates it
    monkeypatch.setenv("CLIPPER_DB", str(db_file))
    monkeypatch.setenv("CLIPPER_WORK", str(tmp_path / "work"))
    monkeypatch.setenv("CLIPPER_CLIPS", str(tmp_path / "clips"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "clips").mkdir()
    assert migrate.main(["--db", str(db_file)]) is None
    con = run_pipeline.connect(db_file)
    yield con
    con.close()


def mock_externals(monkeypatch, synthetic_video):
    """Whisper, the LLM and the yt-dlp download runner. Returns the recorded yt-dlp commands."""
    def fake_transcribe(video, work, model):
        (work / "transcript.txt").write_text(TRANSCRIPT)
        return [{"s": 0.2, "e": 0.6, "w": "chat"}, {"s": 3.6, "e": 4.0, "w": "bet"}]
    monkeypatch.setattr(clip, "transcribe", fake_transcribe)

    calls = []

    def fake_llm(prompt, schema, system=None, clip_id=None):
        calls.append(clip_id)
        n = len(calls)                                # distinct hooks -> distinct captions -> distinct files
        return {"score": 0.8, "in": 0.0, "out": 40.0,
                "hooks": [f"He lost it {n}", f"Chat did this {n}", f"Kai regrets {n}"],
                "context_line": "Kai lost a bet to chat", "title": f"kaicenat loses the bet {n}",
                "music_risk": False}
    monkeypatch.setattr(writer, "llm", fake_llm)

    cmds = []

    def fake_ytdlp(cmd, check):
        cmds.append(cmd)
        shutil.copy(synthetic_video, cmd[cmd.index("-o") + 1])
    return cmds, calls, fake_ytdlp


def make_ctx(con):
    app = NS(bot_data={"con": con, "chat_id": CHAT, "pending_edit": None}, bot=AsyncMock())
    return NS(application=app)


def tap(data):
    q = NS(data=data, answer=AsyncMock(), edit_message_reply_markup=AsyncMock(),
           message=NS(reply_text=AsyncMock()))
    return NS(callback_query=q, effective_chat=NS(id=CHAT)), q


def test_fresh_db_to_published(env, tmp_path, monkeypatch, synthetic_video):
    # --- 0. fresh DB came from migrate.py, and a second run has nothing to do
    versions = [r[0] for r in env.execute("SELECT version FROM schema_migrations ORDER BY version")]
    assert versions[0] == "001_base" and "003_approvals" in versions
    assert migrate.migrate(tmp_path / "db" / "clip.db") == []

    # --- 1. one pipeline pass: radar (Twitch + YouTube) -> capture -> editor -> qc
    cmds, llm_calls, fake_ytdlp = mock_externals(monkeypatch, synthetic_video)
    report = run_pipeline.run_pass(env, steps={
        "radar": lambda: run_pipeline.radar_step(env, FakeTwitch(), [KAI], allocate=lambda c, n: None,
                                                 youtube=fake_youtube, now=NOW),
        "capture": lambda: run_pipeline.capture_step(env, runner=fake_ytdlp),
        "editor": lambda: run_pipeline.editor_step(env, out=str(tmp_path / "clips")),
        "qc": lambda: qc.run(env),
        "rerender": lambda: rerender.run(env),
    })
    assert not any(str(v).startswith("error") for v in report.values()), report

    sources = {r[0] for r in env.execute("SELECT source FROM radar_candidates")}
    assert sources == {"twitch", "youtube"}
    assert any("--download-sections" in c for c in cmds) and any("--download-sections" not in c for c in cmds)
    rows = env.execute("SELECT * FROM clips ORDER BY id").fetchall()
    assert rows and all(r["state"] == "qc_passed" and r["last_error"] is None for r in rows), \
        [(r["id"], r["state"], r["last_error"]) for r in rows]
    assert len(llm_calls) == len(rows) and None not in llm_calls   # Writer ran once per clip, tagged with clips.id
    for r in rows:
        assert Path(r["file_path"]).stat().st_size > 0 and r["file_hash"] and r["qc_passed_at"]
        assert len(json.loads(r["hooks_json"])) == 3 and r["context_line"] and r["title"]
    assert len({r["file_hash"] for r in rows}) == len(rows)

    # a second pass redoes nothing
    llm_calls.clear()
    run_pipeline.run_pass(env, steps={"capture": lambda: run_pipeline.capture_step(env, runner=fake_ytdlp),
                                      "editor": lambda: run_pipeline.editor_step(env, out=str(tmp_path / "clips")),
                                      "qc": lambda: qc.run(env)})
    assert not llm_calls and env.execute("SELECT COUNT(*) FROM clips").fetchone()[0] == len(rows)

    # --- 2. approval gate: the bot sends every qc_passed clip, Lucas taps hook 2 on the first
    ctx = make_ctx(env)
    assert asyncio.run(approve_bot.push_pending(ctx.application)) == len(rows)
    assert ctx.application.bot.send_video.await_count == len(rows)
    assert asyncio.run(approve_bot.push_pending(ctx.application)) == 0
    first = rows[0]["id"]
    upd, q = tap(f"a:{first}:2")
    asyncio.run(approve_bot.on_button(upd, ctx))
    r = env.execute("SELECT state, hook_text, hooks_json FROM clips WHERE id=?", (first,)).fetchone()
    assert r["state"] == "approved" and r["hook_text"] == json.loads(r["hooks_json"])[1]
    audit = env.execute("SELECT decision, hook_index, chosen_hook FROM approvals WHERE clip_id=?", (first,)).fetchone()
    assert tuple(audit) == ("approved", 2, r["hook_text"])
    asyncio.run(approve_bot.on_button(tap(f"a:{first}:2")[0], ctx))  # double tap changes nothing
    assert env.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 1

    # --- 3. publisher: nothing uploads until a clip is approved; then one upload per due slot
    cfg = upload.Config(tz="UTC", window_start="00:00", window_end="23:59", max_per_day=5, min_gap_hours=2)
    uploaded, alerts = [], []

    def fake_uploader(path, body):
        uploaded.append((path, body))
        return "vid_e2e_1"
    now = datetime(2026, 10, 16, 12, 30, tzinfo=timezone.utc)
    msg = upload.run_once(env, cfg, fake_uploader, alerts.append, now=now)
    assert msg == f"uploaded clip {first}: https://youtube.com/shorts/vid_e2e_1", msg
    assert alerts == [] and len(uploaded) == 1
    path, body = uploaded[0]
    assert path == rows[0]["file_path"] and body["snippet"]["title"] == rows[0]["title"]
    assert "#Shorts" in body["snippet"]["description"] and body["status"]["privacyStatus"] == "public"

    r = env.execute("SELECT state, last_error FROM clips WHERE id=?", (first,)).fetchone()
    assert r["state"] == "published" and r["last_error"] is None
    post = env.execute("SELECT platform_post_id, url FROM posts WHERE clip_id=?", (first,)).fetchone()
    assert tuple(post) == ("vid_e2e_1", "https://youtube.com/shorts/vid_e2e_1")

    # the unapproved clips stay put; a later pass with no approved clip uploads nothing
    later = datetime(2026, 10, 16, 15, 0, tzinfo=timezone.utc)
    assert upload.run_once(env, cfg, fake_uploader, alerts.append, now=later) == "no approved clips to upload"
    assert len(uploaded) == 1
    left = [r[0] for r in env.execute("SELECT state FROM clips WHERE id != ?", (first,))]
    assert left and set(left) == {"qc_passed"}
