#!/usr/bin/env python3
"""One pipeline pass (D22, D27): radar -> capture -> writer/editor -> qc -> rerender -> visual check.

Safe to run every 20 min from a systemd timer: an exclusive non-blocking flock on $CLIPPER_LOCK
(default /opt/clipper/pipeline.lock) makes an overlapping pass exit at once; every stage only
picks clips in its own input state, so nothing is done twice. A stage that fails never stops the rest.

Usage (from clipper/): python run_pipeline.py
Env: CLIPPER_DB, CLIPPER_WORK, CLIPPER_CLIPS, CLIPPER_LOCK, WHISPER_MODEL, TWITCH_*, ANTHROPIC_API_KEY
"""
import fcntl
import json
import os
import random
import sqlite3
import subprocess
import sys
import time
import tempfile
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "editor")]

from radar import capture, heat, top_clips, youtube_vods  # noqa: E402
from radar import kick as kicksrc  # noqa: E402
import qc  # noqa: E402  (editor/ is on sys.path, same as clip.py and rerender.py)
import rerender  # noqa: E402
import visual_qa  # noqa: E402

DB = "/opt/clipper/db/clip.db"
LOCK = "/opt/clipper/pipeline.lock"
DAILY_CAP = qc.DAILY_CAP
HEAT_REFRESH_MIN = 30  # measure the Heat Index at most this often (D33); in between reuse the stored snapshot
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


def heat_allocation(con, now=None, tw=None, cfg=None, views=None, live=None):
    """Today's Heat Index allocation (D33): {"slots": {streamer: n}, "ids": {login/id: streamer}}.
    Measures (Twitch + yt-dlp, `heat.run`) at most every HEAT_REFRESH_MIN minutes; in between it
    re-allocates from the latest stored `streamer_heat` snapshot. Exploration is seeded per day."""
    now = now or datetime.now(timezone.utc)
    cfg = cfg or heat.load_watchlist()
    rng = random.Random(now.strftime("%Y-%m-%d"))
    cutoff = (now - timedelta(minutes=HEAT_REFRESH_MIN)).strftime("%Y-%m-%dT%H:%M:%SZ")
    stored = con.execute("SELECT streamer, opportunity FROM streamer_heat"
                         " WHERE ts=(SELECT MAX(ts) FROM streamer_heat) AND ts>=?", (cutoff,)).fetchall()
    if stored:
        slots = heat.allocate({r[0]: r[1] for r in stored}, cfg["cap"], heat.last_posted(con, cfg["streamers"]),
                              now, rng, cfg["max_per"], cfg["explore_days"], cfg["explore_top_n"])
    else:
        if views is None:
            from radar.twitch import Twitch
            views, live = heat.default_fetchers(tw or Twitch())
        from radar import market
        _, slots = heat.run(con, cfg, views, live, heat.load_saturation(), now, rng, market=market.load())
    return heat.allocation_doc(cfg, slots)


def radar_creators(watchlist=None, creators=None):
    """Creators Radar pulls from: creators.yaml entries plus every enabled Twitch login in the
    watchlist (D33), so each streamer the Heat Index gives a slot can actually be served. A watchlist
    streamer's YouTube channel rides along with its Twitch login. creators.yaml wins on duplicates."""
    out = list(creators if creators is not None else top_clips.load_creator_configs())
    seen = {c["twitch"] for c in out}
    wl = watchlist if watchlist is not None else heat.load_watchlist()
    for entries in wl["streamers"].values():
        yt = next((e["id"] for e in entries if e["platform"] == "youtube"), None)
        for e in entries:
            login = e["id"].lower()
            if e["platform"] == "twitch" and login not in seen:
                seen.add(login)
                out.append({"twitch": login, "youtube_channel": yt})
    return out


def youtube_moments(cfgs, con, now):
    """Most-replayed moments from the creators' own live VODs (D29)."""
    return youtube_vods.collect(cfgs, con, now) if cfgs else []


def watchlist_kick_slugs(watchlist=None):
    """Every enabled Kick channel in the watchlist (D45), lowercase."""
    wl = watchlist if watchlist is not None else heat.load_watchlist()
    return sorted({e["id"].lower() for entries in wl["streamers"].values() for e in entries
                   if e["platform"] == "kick"})


def kick_moments(slugs, now, min_candidates):
    """Top Kick clips of the given channels (D45)."""
    return kicksrc.collect(kicksrc.Kick(), slugs, min_candidates, now=now) if slugs else []


def paced_cap(cap, now):
    """How many clips may have been started by `now` (D48): the day's cap spread over the UTC day, one at
    00:00 then one more every 24 h / cap. Before, all 5 started right after midnight UTC and went up in one
    2.5 h burst with moments up to a day old; clip channels post through the day while moments are fresh."""
    sec = now.hour * 3600 + now.minute * 60 + now.second
    return min(cap, 1 + int(cap * sec / 86400))


def market_step(now=None, key=None):
    """Daily Shorts market scan (radar/market.py, D48): demand per streamer + today's popping titles."""
    from radar import market
    if not market.due(now=now):
        return "fresh"
    key = key or os.environ.get("YOUTUBE_API_KEY")
    if not key:
        return "skipped: no YOUTUBE_API_KEY"
    data = market.scan(key, now=now)
    if not data["streamers"]:
        return "error: empty scan"
    market.write(data)
    return f"scanned {len(data['streamers'])} streamers"


def _slots_left(con, alloc):
    """Allocated slots minus clips already started today for the same streamer (not killed)."""
    ids = {k.lower(): v for k, v in alloc["ids"].items()}
    used = {}
    for (name,) in con.execute(
            "SELECT cr.name FROM clips c JOIN sources s ON s.id=c.source_id JOIN creators cr ON cr.id=s.creator_id"
            " WHERE date(c.created_at)=date('now') AND c.state!='killed'"):
        key = ids.get(name.lower(), name)
        used[key] = used.get(key, 0) + 1
    return {n: max(0, k - used.get(n, 0)) for n, k in alloc["slots"].items()}


def radar_step(con, twitch=None, creators=None, cap=DAILY_CAP, allocate=heat_allocation,
               youtube=youtube_moments, now=None, kick=kick_moments, kick_from=None, pace=False):
    """Register today's picks: Heat slots (D33) across creators, each creator's moments from Twitch top
    clips + YouTube VOD most-replayed windows (D29) + Kick top clips (D45), ranked by score, never more
    than the daily cap.

    `creators`: logins or {"twitch", "youtube_channel"} dicts (default `radar_creators()`:
    creators.yaml + every watchlist Twitch login).
    `kick_from`: Kick channel slugs (default: the watchlist's Kick channels when `creators` is the
    default, none when a creator list is passed in).
    `allocate(con, now)` -> allocation doc or None; if it fails the pass falls back to ranking all
    creators (the cap still holds). Injectable so tests never touch the network.
    `pace=True` (the live pipeline): starts are spread over the day (`paced_cap`)."""
    now = now or datetime.now(timezone.utc)
    started = con.execute("SELECT COUNT(*) FROM clips WHERE date(created_at)=date('now') AND state!='killed'"
                          ).fetchone()[0]
    limit = paced_cap(cap, now) if pace else cap
    want = max(0, limit - started)  # at the cap we still pull + store, but start nothing new
    cfgs = [c if isinstance(c, dict) else {"twitch": c, "youtube_channel": None}
            for c in (creators or radar_creators())]
    alloc = slots = allowed = None
    try:
        alloc = allocate(con, now)
    except Exception:  # noqa: BLE001 - no heat data must not stop Radar
        traceback.print_exc()
    if alloc:
        slots = _slots_left(con, alloc)
        allowed = [n for n, k in slots.items() if k > 0]
        allowed += [login for login, name in alloc["ids"].items() if slots.get(name, 0) > 0]
    if twitch is None:
        from radar.twitch import Twitch
        twitch = Twitch()
    cands = top_clips.collect(twitch, [c["twitch"] for c in cfgs], max(10, want), now=now, allowed=allowed)
    yt_cfgs = [c for c in cfgs if c.get("youtube_channel") and top_clips.filter_allowed([c["twitch"]], allowed)]
    try:
        cands += youtube(yt_cfgs, con, now)
    except Exception:  # noqa: BLE001 - a yt-dlp failure keeps the Twitch picks
        traceback.print_exc()
    slugs = kick_from if kick_from is not None else (watchlist_kick_slugs() if creators is None else [])
    slugs = top_clips.filter_allowed(slugs, allowed)
    if slugs:
        try:
            cands += kick(slugs, now, max(10, want))
        except Exception:  # noqa: BLE001 - a Kick failure keeps the other picks
            traceback.print_exc()
    cands = kicksrc.dedupe(cands, alloc["ids"] if alloc else None)  # one moment on Twitch + Kick -> one pick
    top_clips.store(con, cands)
    fresh = [c for c in cands
             if con.execute("SELECT clips_id FROM radar_candidates WHERE clip_id=?", (c["clip_id"],)).fetchone()[0] is None]
    if alloc:
        fresh = top_clips.apply_allocation(fresh, slots, alloc["ids"])
    return top_clips.register_clips(con, fresh[:want])


def _picks(con, state, file_relative=False):
    """Picks in `state` per D23. start/end come from clips.start_s/end_s: Twitch 0 -> duration, YouTube
    VOD-absolute. `file_relative=True` (Editor, after capture) shifts YouTube picks into the downloaded
    window file, which starts at capture.section(pick)[0]."""
    rows = con.execute(
        "SELECT c.id, c.start_s, c.end_s, r.clip_id, r.creator, r.url, r.duration_s, r.source FROM clips c"
        " JOIN radar_candidates r ON r.clips_id=c.id"
        f" WHERE c.state=? AND {RETRY_OK}"
        " ORDER BY c.id", (state,)).fetchall()
    picks = []
    for r in rows:
        start = r["start_s"] if r["start_s"] is not None else 0
        end = r["end_s"] if r["end_s"] is not None else start + min(r["duration_s"] or top_clips.MAX_PICK_S,
                                                                    top_clips.MAX_PICK_S)
        if file_relative and r["source"] == "youtube":
            off = capture.section({"start": start, "end": end})[0]
            start, end = start - off, end - off
        picks.append({"start": start, "end": end, "source_url": r["url"], "creator": r["creator"],
                      "clip_id": r["clip_id"], "_row": r["id"]})
    return picks


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
    picks = [{k: v for k, v in p.items() if k != "_row"} for p in _picks(con, "captured", file_relative=True)]
    if not picks:
        return 0
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "picks.json"
        f.write_text(json.dumps(picks))
        clip.main(["--picks", str(f), "--auto", "--model", model,
                   "--out", out or os.environ.get("CLIPPER_CLIPS", "/opt/clipper/clips")])
    return len(picks)


FORMATS_REF = "origin/trends:clipper/formats/library.md"
STYLE_REF = "origin/trends:clipper/formats/style.json"
HASHTAGS_REF = "origin/trends:clipper/formats/hashtags.json"
FORMATS_MAX_AGE_S = 6 * 3600


def refresh_formats(path=None, repo=None, runner=subprocess.run, max_age_s=FORMATS_MAX_AGE_S, now=None):
    """Copy the Trend Scout's latest format library (trends branch) to $CLIPPER_FORMATS for the
    Writer, at most every 6 h. Best effort: on any git error the old copy stays. -> 'fresh' |
    'updated' | 'error: ...'."""
    p = Path(path or os.environ.get("CLIPPER_FORMATS", "/opt/clipper/formats/library.md"))
    repo = str(repo or HERE.parent)
    now = now or time.time()
    if p.exists() and now - p.stat().st_mtime < max_age_s:
        return "fresh"
    try:
        runner(["git", "-C", repo, "fetch", "-q", "origin", "trends:refs/remotes/origin/trends"],
               capture_output=True, text=True, check=True, timeout=120)
        out = runner(["git", "-C", repo, "show", FORMATS_REF],
                     capture_output=True, text=True, check=True, timeout=60).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        return f"error: {type(e).__name__}"
    if not out.strip():
        return "error: empty library"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out, encoding="utf-8")
    except OSError as e:
        return f"error: {type(e).__name__}"
    try:  # today's market hashtags (hashtag scout); optional, the publisher has a default
        ht = runner(["git", "-C", repo, "show", HASHTAGS_REF], capture_output=True, text=True, check=True,
                    timeout=60).stdout
        json.loads(ht)
        hp = Path(os.environ.get("CLIPPER_HASHTAGS", "/opt/clipper/formats/hashtags.json"))
        hp.parent.mkdir(parents=True, exist_ok=True)
        hp.write_text(ht, encoding="utf-8")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError):
        pass
    try:  # today's caption style (style scout); optional, the renderer has a default
        st = runner(["git", "-C", repo, "show", STYLE_REF], capture_output=True, text=True, check=True,
                    timeout=60).stdout
        json.loads(st)
        sp = Path(os.environ.get("CLIPPER_STYLE", "/opt/clipper/formats/style.json"))
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(st, encoding="utf-8")
        return "updated (+style)"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError):
        return "updated"


def metrics_step(con):
    """Public stats of our own Shorts -> post_metrics (analyst/metrics.py), each at most hourly."""
    sys.path.insert(0, str(HERE / "analyst"))
    import metrics
    return metrics.run(con, os.environ.get("YOUTUBE_API_KEY"))


def run_pass(con, steps=None):
    """Run each stage; return {stage: result or 'error: ...'}. `steps` lets tests inject mocks."""
    model = os.environ.get("WHISPER_MODEL", "small")
    steps = steps or {
        "formats": refresh_formats,
        "metrics": lambda: metrics_step(con),
        "market": market_step,                 # daily: what's popping on Shorts per streamer (D48)
        "radar": lambda: radar_step(con, pace=True),
        "capture": lambda: capture_step(con),
        "editor": lambda: editor_step(con, model),
        "qc": lambda: qc.run(con),
        "rerender": lambda: rerender.run(con, model, os.environ.get("CLIPPER_CLIPS", "/opt/clipper/clips")),
        "vqa": lambda: visual_qa.run(con),   # look at the finished Short before it can post
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
