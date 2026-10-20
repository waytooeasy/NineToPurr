"""QC v1 (D27, D8): moves clips `edited -> qc_passed` or leaves them with `last_error` set.

Rules: rendered file <= 60 s, no duplicate file (sha256) in our library, at most 5 clips
passed per UTC day. `music_risk` does not block; it stays on the row and the Telegram message flags it.
Run (from clipper/): python -m editor.qc
"""
import hashlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

MAX_S = 60.0
DAILY_CAP = 6   # D52: the most active top clippers post ~6/day (2026-10-20)
DEFAULT_DB = "/opt/clipper/db/clip.db"


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def probe_duration(path):
    """Length in seconds from ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True).stdout
    return float(out.strip())


def passed_today(con):
    return con.execute("SELECT COUNT(*) FROM clips WHERE date(qc_passed_at)=date('now') AND state!='killed'"
                       ).fetchone()[0]


def problems(con, row, probe=probe_duration, cap=DAILY_CAP):
    """(list of reasons the clip fails QC, sha256 of its file or None)."""
    path = row["file_path"]
    if not path or not Path(path).is_file():
        return ["file missing"], None
    found = []
    try:
        dur = probe(path)
    except Exception:  # no ffprobe: fall back to the cut length in the DB
        dur = row["duration_s"]
    if dur is None or dur > MAX_S:
        found.append(f"duration {dur} s over {MAX_S:.0f} s" if dur is not None else "duration unknown")
    digest = file_hash(path)
    dup = con.execute("SELECT id FROM clips WHERE file_hash=? AND id!=? LIMIT 1", (digest, row["id"])).fetchone()
    if dup:
        found.append(f"duplicate of clip {dup[0]}")
    if passed_today(con) >= cap:
        found.append(f"daily cap {cap} reached")
    return found, digest


def run(con, probe=probe_duration, cap=DAILY_CAP):
    """QC every `edited` clip. Returns {'passed': [ids], 'failed': {id: reason}}."""
    con.row_factory = sqlite3.Row
    res = {"passed": [], "failed": {}}
    for row in con.execute("SELECT id, file_path, duration_s FROM clips WHERE state='edited' ORDER BY id").fetchall():
        found, digest = problems(con, row, probe, cap)
        if found:
            reason = "qc: " + "; ".join(found)
            con.execute("UPDATE clips SET last_error=? WHERE id=?", (reason[:500], row["id"]))
            res["failed"][row["id"]] = reason
        else:
            cur = con.execute(
                "UPDATE clips SET state='qc_passed', state_changed_at=datetime('now'), qc_passed_at=datetime('now'),"
                " file_hash=?, last_error=NULL WHERE id=? AND state='edited'", (digest, row["id"]))
            if cur.rowcount:
                res["passed"].append(row["id"])
        con.commit()
    return res


def main():
    con = sqlite3.connect(os.environ.get("CLIPPER_DB", DEFAULT_DB), timeout=30)
    print(run(con))


if __name__ == "__main__":
    sys.exit(main())
