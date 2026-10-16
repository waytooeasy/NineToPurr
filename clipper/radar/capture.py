#!/usr/bin/env python3
"""Download picked clips with yt-dlp into $CLIPPER_WORK (default /opt/clipper/work).

Usage (from clipper/): python -m radar.capture picks.json
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def work_dir():
    return Path(os.environ.get("CLIPPER_WORK", "/opt/clipper/work"))


def capture(picks, work=None, db=None, runner=subprocess.run):
    work = Path(work) if work else work_dir()
    work.mkdir(parents=True, exist_ok=True)
    paths = {}
    for p in picks:
        out = work / f"{p['clip_id']}.mp4"
        if not out.exists():
            runner(["yt-dlp", "-f", "b[ext=mp4]/b", "--merge-output-format", "mp4",
                    "-o", str(out), p["source_url"]], check=True)
        paths[p["clip_id"]] = out
        if db is not None:
            db.execute("UPDATE radar_candidates SET status='captured', file_path=?, "
                       "updated_at=datetime('now') WHERE clip_id=? AND status='found'",
                       (str(out), p["clip_id"]))
    if db is not None:
        db.commit()
    return paths


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        sys.exit("usage: python -m radar.capture picks.json")
    from .top_clips import connect
    picks = json.loads(Path(argv[0]).read_text())
    for cid, path in capture(picks, db=connect()).items():
        print(cid, path)


if __name__ == "__main__":
    main()
