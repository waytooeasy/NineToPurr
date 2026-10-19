#!/usr/bin/env python3
"""Radar v1: Twitch top clips -> score (views/hour) -> dedupe -> radar_candidates -> picks.json.

Usage (from clipper/):
  python -m radar.top_clips                 # pull, store, print ranked list
  python -m radar.top_clips --picks 5       # also write picks.json with the top 5
Env: TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, CLIPPER_DB (default /opt/clipper/db/clip.db)
"""
import argparse
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

import yaml

HERE = Path(__file__).parent
MIN_AGE_H = 0.25          # floor so a 1-minute-old clip doesn't win on noise
TITLE_SIM = 0.8
NO_VOD_WINDOW_S = 300     # no VOD offset: same creator + similar title within 5 min
MAX_PICK_S = 60           # STRATEGY hard cap


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_creator_configs(path=None):
    """[{"twitch": login, "youtube_channel": "@Handle" | None}]. Entries are a plain Twitch login
    string or a mapping with `twitch` (or `login`) and optional `youtube_channel`."""
    cfg = yaml.safe_load(Path(path or HERE / "config" / "creators.yaml").read_text())
    out = []
    for c in cfg["creators"]:
        if isinstance(c, dict):
            login = c.get("twitch") or c.get("login")
            yt = c.get("youtube_channel")
            out.append({"twitch": str(login).lower(), "youtube_channel": str(yt) if yt else None})
        else:
            out.append({"twitch": str(c).lower(), "youtube_channel": None})
    return out


def load_creators(path=None):
    return [c["twitch"] for c in load_creator_configs(path)]


def score(clip, now):
    hours = max((now - parse_ts(clip["created_at"])).total_seconds() / 3600, MIN_AGE_H)
    return clip["view_count"] / hours


def normalize(raw, creator, now):
    off = raw.get("vod_offset")
    c = {
        "clip_id": raw["id"], "creator": creator, "broadcaster_id": raw.get("broadcaster_id"),
        "title": raw.get("title") or "", "url": raw["url"],
        "video_id": raw.get("video_id") or None,
        "vod_offset": off if isinstance(off, int) else None,
        "duration_s": float(raw.get("duration") or 0),
        "view_count": int(raw.get("view_count") or 0), "created_at": raw["created_at"],
    }
    c["views_per_hour"] = score(c, now)
    return c


def _has_vod(c):
    return bool(c["video_id"]) and c["vod_offset"] is not None


def _same_moment(a, b):
    if a["creator"] != b["creator"]:
        return False
    if _has_vod(a) and _has_vod(b):
        if a["video_id"] != b["video_id"]:
            return False
        return (a["vod_offset"] < b["vod_offset"] + b["duration_s"]
                and b["vod_offset"] < a["vod_offset"] + a["duration_s"])
    # no usable VOD offset on at least one side: title similarity + created_at within 5 min
    dt = abs((parse_ts(a["created_at"]) - parse_ts(b["created_at"])).total_seconds())
    sim = SequenceMatcher(None, a["title"].lower(), b["title"].lower()).ratio()
    return dt <= NO_VOD_WINDOW_S and sim >= TITLE_SIM


def dedupe(clips):
    """Keep the best-scoring clip of each group covering the same moment."""
    kept = []
    for c in sorted(clips, key=lambda x: x["views_per_hour"], reverse=True):
        if not any(_same_moment(c, k) for k in kept):
            kept.append(c)
    return kept


def filter_allowed(creators, allowed=None):
    """Heat Index hook (D33): keep only creators in `allowed` (case-insensitive). None = no filter."""
    if allowed is None:
        return list(creators)
    ok = {a.lower() for a in allowed}
    return [c for c in creators if c.lower() in ok]


def apply_allocation(cands, slots, ids=None):
    """Rank moments only within allocated streamers: from a ranked list keep the best `slots[streamer]`
    per streamer. `ids` maps a creator login (lowercase) to its streamer name; default = the login."""
    left = {k.lower(): n for k, n in slots.items()}
    out = []
    for c in cands:
        key = (ids or {}).get(c["creator"].lower(), c["creator"]).lower()
        if left.get(key, 0) > 0:
            left[key] -= 1
            out.append(c)
    return out


def collect(tw, creators, min_candidates, now=None, days=(1, 7), allowed=None):
    """Per creator: last 24 h; widen to 7 days if fewer than min_candidates after dedupe.
    `allowed`: optional creator allow-list (Heat Index allocation); None = all."""
    now = now or datetime.now(timezone.utc)
    allc = []
    for login in filter_allowed(creators, allowed):
        bid = tw.broadcaster_id(login)
        found = []
        for d in days:
            raw = tw.get_clips(bid, now - timedelta(days=d), now)
            found = dedupe([normalize(r, login, now) for r in raw])
            if len(found) >= min_candidates:
                break
        allc.extend(found)
    return sorted(allc, key=lambda x: x["views_per_hour"], reverse=True)


def store(db, cands):
    for c in cands:
        c = {"broadcaster_id": None, **c, "source": c.get("source", "twitch")}
        db.execute(
            """INSERT INTO radar_candidates (clip_id, creator, broadcaster_id, title, url, video_id,
                   vod_offset, duration_s, view_count, clip_created_at, views_per_hour, source)
               VALUES (:clip_id,:creator,:broadcaster_id,:title,:url,:video_id,:vod_offset,
                   :duration_s,:view_count,:created_at,:views_per_hour,:source)
               ON CONFLICT(clip_id) DO UPDATE SET view_count=excluded.view_count,
                   views_per_hour=excluded.views_per_hour, updated_at=datetime('now')""", c)
    db.commit()


def register_clips(db, cands):
    """Chosen candidates become `clips` rows with state='found' (D22); radar_candidates.clips_id links them.
    Idempotent: a candidate that already has a clips row is skipped. Returns the new clips ids."""
    ids = []
    for c in cands:
        row = db.execute("SELECT clips_id FROM radar_candidates WHERE clip_id=?", (c["clip_id"],)).fetchone()
        if row is None or row[0] is not None:
            continue
        kick = c.get("source") == "kick"
        db.execute("INSERT OR IGNORE INTO creators (name, main_platform, channel_url) VALUES (?, ?, ?)",
                   (c["creator"], "kick" if kick else "twitch",
                    f"https://kick.com/{c['creator']}" if kick else f"https://twitch.tv/{c['creator']}"))
        start_s, end_s = pick_window(c)
        creator_id = db.execute("SELECT id FROM creators WHERE name=?", (c["creator"],)).fetchone()[0]
        db.execute("INSERT OR IGNORE INTO sources (creator_id, url, title, source_views) VALUES (?,?,?,?)",
                   (creator_id, c["url"], c["title"], c["view_count"]))
        source_id = db.execute("SELECT id FROM sources WHERE url=?", (c["url"],)).fetchone()[0]
        cur = db.execute(
            "INSERT INTO clips (source_id, start_s, end_s, picked_by, state, state_changed_at) "
            "VALUES (?, ?, ?, 'ai', 'found', datetime('now'))",
            (source_id, start_s, end_s))
        db.execute("UPDATE radar_candidates SET clips_id=? WHERE clip_id=?", (cur.lastrowid, c["clip_id"]))
        ids.append(cur.lastrowid)
    db.commit()
    return ids


def pick_window(c):
    """(start, end) in seconds inside the file behind source_url.
    Twitch: the source is the clip itself, so 0 -> duration. YouTube (D29): the source is the whole
    live VOD, so start/end are VOD-absolute. Kick (D45): the clip itself, but Kick clips run up to 180 s
    and end on the moment, so a longer clip keeps its last MAX_PICK_S seconds."""
    dur = min(c["duration_s"] or MAX_PICK_S, MAX_PICK_S)
    if c.get("source") == "youtube":
        start = c["vod_offset"]
        return start, start + dur
    if c.get("source") == "kick" and (c["duration_s"] or 0) > MAX_PICK_S:
        return c["duration_s"] - MAX_PICK_S, c["duration_s"]
    return 0, dur


def to_picks(cands, n):
    """Editor format (D23). start/end are seconds inside the file for source_url (see pick_window)."""
    out = []
    for c in cands[:n]:
        start, end = pick_window(c)
        out.append({"start": start, "end": end, "source_url": c["url"],
                    "creator": c["creator"], "clip_id": c["clip_id"]})
    return out


def connect(path=None):
    return sqlite3.connect(path or os.environ.get("CLIPPER_DB", "/opt/clipper/db/clip.db"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--picks", type=int, metavar="N", help="write picks.json with top N")
    ap.add_argument("--out", default="picks.json")
    ap.add_argument("--min-candidates", type=int, default=10,
                    help="widen to 7 days if fewer per creator")
    ap.add_argument("--config", help="creators.yaml path")
    ap.add_argument("--youtube", action="store_true",
                    help="also add moments from creators' own YouTube live VODs (D29)")
    ap.add_argument("--allocation", metavar="FILE",
                    help="allocation.json from `python -m radar.heat`: rank only allocated streamers (D33)")
    a = ap.parse_args(argv)

    alloc = json.loads(Path(a.allocation).read_text()) if a.allocation else None
    ids = alloc.get("ids") if alloc else None
    allowed = None
    if alloc:
        allowed = [k for k, n in alloc["slots"].items() if n > 0]
        allowed += [login for login, name in (ids or {}).items() if name in allowed]
    from .twitch import Twitch
    cands = collect(Twitch(), load_creators(a.config), max(a.min_candidates, a.picks or 0), allowed=allowed)
    db = connect()
    if a.youtube:
        from . import youtube_vods
        yt_cfgs = [c for c in load_creator_configs(a.config)
                   if filter_allowed([c["twitch"]], allowed)]
        cands = sorted(cands + youtube_vods.collect(yt_cfgs, db),
                       key=lambda x: x["views_per_hour"], reverse=True)
    store(db, cands)
    if alloc:
        cands = apply_allocation(cands, alloc["slots"], ids)
    for i, c in enumerate(cands, 1):
        print(f"{i:>3}. {c['views_per_hour']:>9.1f} v/h  {c['view_count']:>7} views  "
              f"{c['creator']}  {c['title'][:50]!r}  {c['url']}")
    if a.picks:
        register_clips(db, cands[:a.picks])
        Path(a.out).write_text(json.dumps(to_picks(cands, a.picks), indent=2))
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
