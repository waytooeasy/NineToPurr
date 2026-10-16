#!/usr/bin/env python3
"""Download picked clips with yt-dlp into $CLIPPER_WORK (default /opt/clipper/work).

Usage (from clipper/): python -m radar.capture picks.json
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def work_dir():
    return Path(os.environ.get("CLIPPER_WORK", "/opt/clipper/work"))


PAD_S = 3                      # seconds of padding either side of a YouTube pick window
MAX_FILESIZE_MB = 150          # size cap for one downloaded window (a <=66 s clip at 720p is far below)


def youtube_id(url):
    """Video id for a YouTube URL, None for non-YouTube URLs (Twitch clips).

    Raises ValueError for a YouTube URL with no video id (e.g. /watch without v=)."""
    u = urlparse(url)
    host = u.hostname or ""
    if not (host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")):
        return None
    if host == "youtu.be":
        vid = u.path.strip("/")
    else:
        vid = (parse_qs(u.query).get("v") or [""])[0]
        parts = u.path.strip("/").split("/")
        if not vid and len(parts) == 2 and parts[0] in ("live", "embed", "shorts"):
            vid = parts[1]
    if not vid:
        raise ValueError(f"YouTube URL without a video id: {url}")
    return vid


def section(pick, pad=PAD_S):
    """(sec_start, sec_end) VOD-absolute window to download: the pick plus `pad` s each side."""
    return max(0, int(pick["start"]) - pad), int(pick["end"] + 0.999) + pad


def _cleanup(out):
    for f in out.parent.glob(out.name + "*"):
        f.unlink(missing_ok=True)


def download_section(pick, out, runner, max_mb=MAX_FILESIZE_MB):
    """Download only the pick window into `out` via a temp file; enforce the size cap, clean up on failure."""
    s, e = section(pick)
    tmp = out.with_name(out.stem + ".tmp.mp4")
    _cleanup(tmp)
    try:
        runner(["yt-dlp", "-f", "b[height<=720][ext=mp4]/b[height<=720]/b",
                "--download-sections", f"*{s}-{e}", "--force-keyframes-at-cuts",
                "--max-filesize", f"{max_mb}M", "--merge-output-format", "mp4",
                "-o", str(tmp), pick["source_url"]], check=True)
        if not tmp.exists():
            raise RuntimeError(f"yt-dlp produced no file for {pick['clip_id']} (over size cap?)")
        if tmp.stat().st_size > max_mb * 1024 * 1024:
            raise RuntimeError(f"{pick['clip_id']}: download exceeds {max_mb} MB cap")
        tmp.replace(out)
    finally:
        _cleanup(tmp)
    return out


def capture(picks, work=None, db=None, runner=subprocess.run):
    """Download each pick. YouTube picks (D29) get only their padded window, one file per pick; the file
    starts at section(pick)[0], so file-relative times are start/end minus that. Twitch: one file per clip."""
    work = Path(work) if work else work_dir()
    work.mkdir(parents=True, exist_ok=True)
    paths = {}
    for p in picks:
        yt = youtube_id(p["source_url"])
        if yt:
            s, e = section(p)
            out = work / f"yt_{yt}_{s}_{e}.mp4"
            if not out.exists():
                download_section(p, out, runner)
        else:
            out = work / f"{p['clip_id']}.mp4"
            if not out.exists():
                runner(["yt-dlp", "-f", "b[ext=mp4]/b", "--merge-output-format", "mp4",
                        "-o", str(out), p["source_url"]], check=True)
        paths[p["clip_id"]] = out
        if db is not None:
            db.execute("UPDATE radar_candidates SET status='captured', file_path=?, "
                       "updated_at=datetime('now') WHERE clip_id=? AND status='found'",
                       (str(out), p["clip_id"]))
            db.execute("UPDATE clips SET state='captured', file_path=?, state_changed_at=datetime('now') "
                       "WHERE state='found' AND id=(SELECT clips_id FROM radar_candidates WHERE clip_id=?)",
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
    paths = capture(picks, db=connect())
    for p in picks:  # YouTube files hold only the window: make picks.json times file-relative for the Editor
        if youtube_id(p["source_url"]):
            off = section(p)[0]
            p["start"], p["end"] = p["start"] - off, p["end"] - off
    Path(argv[0]).write_text(json.dumps(picks, indent=2))
    for cid, path in paths.items():
        print(cid, path)


if __name__ == "__main__":
    main()
