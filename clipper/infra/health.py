"""Health alerts to Telegram (Lucas 2026-10-27: know when something breaks without opening a Claude session).

Run as a pipeline stage (every pass, ~20 min). Each problem alerts at most once per REPEAT_S:
- disk over DISK_ALERT full (the 2026-10-27 outage: killed runs filled 38 GB),
- YouTube cookie file missing or empty (every Short download fails),
- remake runs failing: >= FAIL_ALERT failures in the last 6 h, with the most common error,
- no remake made in 24 h while Shorts are being tried.
State (last alert per problem) lives in a small JSON file next to the DB.
"""
import json
import os
import shutil
import time
from collections import Counter
from pathlib import Path

DISK_ALERT = 0.85
FAIL_ALERT = 3
REPEAT_S = 6 * 3600


def problems(con, env=None, disk=None, now=None):
    """[(key, message)] of what is wrong right now."""
    e = os.environ if env is None else env
    out = []
    du = disk or shutil.disk_usage(Path(e.get("CLIPPER_DB", "/opt/clipper/db/clip.db")).parent)
    used = du.used / du.total
    if used >= DISK_ALERT:
        out.append(("disk", f"💾 VM disk {used:.0%} full ({du.free / 1e9:.1f} GB free). Leftover media? "
                            "Remake runs sweep it; if it keeps rising, ask Claude."))
    ck = Path(e.get("YTDLP_COOKIES", "/opt/clipper/youtube_cookies.txt"))
    if not ck.is_file() or ck.stat().st_size == 0:
        out.append(("cookies", "🍪 YouTube cookie file missing or empty: clipper Shorts can't be downloaded. "
                               "Re-export it (RDP: yt-dlp --cookies-from-browser chrome ...)."))
    try:
        rows = con.execute("SELECT status, last_error FROM remakes WHERE updated_at >= datetime('now', '-6 hours')"
                           ).fetchall()
        fails = [r[1] or "" for r in rows if r[0] == "failed"]
        if len(fails) >= FAIL_ALERT:
            top, n = Counter(f.split("\n")[0][:120] for f in fails).most_common(1)[0]
            out.append(("fails", f"⚠️ {len(fails)} remake runs failed in 6 h. Most common ({n}x): {top}"))
        tried = con.execute("SELECT COUNT(*) FROM remakes WHERE updated_at >= datetime('now', '-24 hours')"
                            ).fetchone()[0]
        done = con.execute("SELECT COUNT(*) FROM remakes WHERE status = 'done' AND updated_at >= "
                           "datetime('now', '-24 hours')").fetchone()[0]
        if tried >= 5 and done == 0:
            out.append(("no_remakes", f"🐢 No remake made in 24 h ({tried} Shorts tried). Check skips/failures."))
    except Exception:  # noqa: BLE001 - no remakes table yet: nothing to say
        pass
    return out


def check(con, alert, state_path, env=None, disk=None, now=None):
    """Alert each current problem unless it was alerted in the last REPEAT_S. Returns the keys alerted."""
    now = now or time.time()
    p = Path(state_path)
    try:
        state = json.loads(p.read_text())
    except (OSError, ValueError):
        state = {}
    sent = []
    current = problems(con, env, disk, now)
    for key, msg in current:
        if key not in state or now - state[key] >= REPEAT_S:
            if alert(msg):
                state[key] = now
                sent.append(key)
    for key in list(state):                     # solved: the next time it breaks, alert at once
        if key not in {k for k, _ in current}:
            state.pop(key)
    try:
        p.write_text(json.dumps(state))
    except OSError:
        pass
    return sent
