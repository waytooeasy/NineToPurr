#!/usr/bin/env python3
"""One pipeline pass (D22, D27): radar -> capture -> writer/editor -> qc -> rerender.

Safe to run every 20 min from a systemd timer: an exclusive non-blocking flock on $CLIPPER_LOCK
(default /opt/clipper/pipeline.lock) makes an overlapping pass exit at once; every stage only
picks clips in its own input state, so nothing is done twice. A stage that fails never stops the rest.

Usage (from clipper/): python run_pipeline.py
Env: CLIPPER_DB, CLIPPER_WORK, CLIPPER_CLIPS, CLIPPER_LOCK, WHISPER_MODEL, TWITCH_*, ANTHROPIC_API_KEY
"""
import fcntl
import json
import os
import sqlite3
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "editor")]

from radar import capture, top_clips  # noqa: E402
import qc  # noqa: E402  (editor/ is on sys.path, same as clip.py and rerender.py)
import rerender  # noqa: E402

DB = "/opt/clipper/db/clip.db"
LOCK = "/opt/clipper/pipeline.lock"
DAILY_CAP = qc.DAILY_CAP
# A clip whose step failed is retried after 2 h, not every pass (each Writer retry costs API money).
RETRY_OK = "(c.last_error IS NULL OR c.state_changed_at < datetime('now','-2 hours'))"


@contextmanager
def locked(path):
    """Yield True when we hold the lock, False when another pass runs."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "w")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        f.close()  # releases the flock


def connect(path=None):
    con = sqlite3.connect(path or os.environ.get("CLIPPER_DB", DB), timeout=30)  # the bot writes too
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def set_error(con, clip_id, msg):
    con.execute("UPDATE clips SET last_error=?, state_changed_at=datetime('now') WHERE id=?", (msg[:500], clip_id))
    con.commit()


def radar_step(con, twitch=None, creators=None, cap=DAILY_CAP):
    """Pull Twitch clips, store them, register as many new ones as today's cap has room for."""
    started = con.execute("SELECT COUNT(*) FROM clips WHERE date(created_at)=date('now') AND state!='killed'"
                          ).fetchone()[0]
    want = max(0, cap - started)  # at the cap we still pull + store, but start nothing new
    if twitch is None:
        from radar.twitch import Twitch
        twitch = Twitch()
    cands = top_clips.collect(twitch, creators or top_clips.load_creators(), max(10, want))
    top_clips.store(con, cands)
    fresh = [c for c in cands
             if con.execute("SELECT clips_id FROM radar_candidates WHERE clip_id=?", (c["clip_id"],)).fetchone()[0] is None]
    return top_clips.register_clips(con, fresh[:want])


def _picks(con, state):
    rows = con.execute(
        "SELECT c.id, r.clip_id, r.creator, r.url, r.duration_s FROM clips c"
        " JOIN radar_candidates r ON r.clips_id=c.id"
        f" WHERE c.state=? AND {RETRY_OK}"
        " ORDER BY c.id", (state,)).fetchall()
    return [{"start": 0, "end": min(r["duration_s"] or top_clips.MAX_PICK_S, top_clips.MAX_PICK_S),
             "source_url": r["url"], "creator": r["creator"], "clip_id": r["clip_id"], "_row": r["id"]}
            for r in rows]


def capture_step(con, runner=None):
    """found -> captured. One pick at a time so a failed download only marks that clip."""
    done = 0
    for p in _picks(con, "found"):
        try:
            kw = {"runner": runner} if runner else {}
            capture.capture([{k: v for k, v in p.items() if k != "_row"}], db=con, **kw)
            done += 1
        except Exception as e:
            set_error(con, p["_row"], f"capture: {e}")
    return done


def editor_step(con, model="small", out=None):
    """captured -> drafted -> edited (Writer + Whisper + ffmpeg, all in editor/clip.py)."""
    import clip
    picks = [{k: v for k, v in p.items() if k != "_row"} for p in _picks(con, "captured")]
    if not picks:
        return 0
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "picks.json"
        f.write_text(json.dumps(picks))
        clip.main(["--picks", str(f), "--auto", "--model", model,
                   "--out", out or os.environ.get("CLIPPER_CLIPS", "/opt/clipper/clips")])
    return len(picks)


def run_pass(con, steps=None):
    """Run each stage; return {stage: result or 'error: ...'}. `steps` lets tests inject mocks."""
    model = os.environ.get("WHISPER_MODEL", "small")
    steps = steps or {
        "radar": lambda: radar_step(con),
        "capture": lambda: capture_step(con),
        "editor": lambda: editor_step(con, model),
        "qc": lambda: qc.run(con),
        "rerender": lambda: rerender.run(con, model, os.environ.get("CLIPPER_CLIPS", "/opt/clipper/clips")),
    }
    report = {}
    for name, fn in steps.items():
        try:
            report[name] = fn()
        except Exception as e:  # keep going: later stages still have work from earlier passes
            traceback.print_exc()
            report[name] = f"error: {e}"
    return report


def main():
    with locked(os.environ.get("CLIPPER_LOCK", LOCK)) as got:
        if not got:
            print("another pipeline pass is running; exiting")
            return 0
        con = connect()
        try:
            print(json.dumps(run_pass(con), default=str))
        finally:
            con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
