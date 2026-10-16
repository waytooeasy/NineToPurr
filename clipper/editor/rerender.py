"""Re-render loop (D27): `needs_rerender -> qc_passed` with the hook Lucas edited in Telegram.

Re-cuts the captured source with the new `hook_text` (same start/end, same context line), swaps the
Short in place, refreshes `file_hash`, clears `approval_sent_at` so the bot sends it again.
Run (from clipper/): python -m editor.rerender
"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import clip  # noqa: E402
import qc  # noqa: E402


def fail(con, clip_id, msg):
    con.execute("UPDATE clips SET last_error=?, state_changed_at=datetime('now') WHERE id=?", (msg[:500], clip_id))
    con.commit()


def rerender_one(con, row, model="small", out_dir=None):
    hook = (row["hook_text"] or "").strip()
    if not hook:
        raise ValueError("no hook_text to render")
    source = row["source_file"]
    if not source or not Path(source).is_file():
        raise FileNotFoundError(f"captured source missing: {source}")
    work = clip.work_root() / str(row["radar_id"])
    work.mkdir(parents=True, exist_ok=True)
    words = clip.transcribe(source, work, model)
    pick = clip.cap_pick({"start": row["start_s"], "end": row["end_s"], "hook": hook,
                          "context_line": row["context_line"]})
    mp4 = Path(row["file_path"]) if row["file_path"] else Path(out_dir) / f"{row['radar_id']}_01_en.mp4"
    mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp = mp4.with_name(mp4.stem + ".rr.mp4")
    ass = work / f"{mp4.stem}.rr.ass"
    clip.build_ass(words, pick, ass)
    clip.render(source, pick, ass, tmp)
    os.replace(tmp, mp4)
    return mp4


def run(con, model="small", out_dir=None):
    """Re-render every `needs_rerender` clip. Returns {'done': [ids], 'failed': {id: error}}."""
    con.row_factory = sqlite3.Row
    res = {"done": [], "failed": {}}
    rows = con.execute(
        "SELECT c.id, c.hook_text, c.context_line, c.start_s, c.end_s, c.file_path,"
        " r.clip_id AS radar_id, r.file_path AS source_file"
        " FROM clips c JOIN radar_candidates r ON r.clips_id = c.id"
        " WHERE c.state='needs_rerender'"
        " AND (c.last_error IS NULL OR c.state_changed_at < datetime('now','-2 hours'))"
        " ORDER BY c.id").fetchall()
    for row in rows:
        try:
            mp4 = rerender_one(con, row, model, out_dir)
            digest = qc.file_hash(mp4)
        except Exception as e:  # one bad clip must not stop the rest
            fail(con, row["id"], f"rerender: {e}")
            res["failed"][row["id"]] = str(e)
            continue
        cur = con.execute(
            "UPDATE clips SET state='qc_passed', state_changed_at=datetime('now'), file_path=?, file_hash=?,"
            " approval_sent_at=NULL, last_error=NULL WHERE id=? AND state='needs_rerender'",
            (str(mp4), digest, row["id"]))
        con.commit()
        if cur.rowcount:
            res["done"].append(row["id"])
    return res


def main():
    con = sqlite3.connect(os.environ.get("CLIPPER_DB", clip.DEFAULT_DB), timeout=30)
    print(run(con, os.environ.get("WHISPER_MODEL", "small"),
              os.environ.get("CLIPPER_CLIPS", "/opt/clipper/clips")))


if __name__ == "__main__":
    main()
