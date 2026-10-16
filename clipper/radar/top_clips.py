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


def load_creators(path=None):
    cfg = yaml.safe_load(Path(path or HERE / "config" / "creators.yaml").read_text())
    return [str(c).lower() for c in cfg["creators"]]


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


def collect(tw, creators, min_candidates, now=None, days=(1, 7)):
    """Per creator: last 24 h; widen to 7 days if fewer than min_candidates after dedupe."""
    now = now or datetime.now(timezone.utc)
    allc = []
    for login in creators:
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
        db.execute(
            """INSERT INTO radar_candidates (clip_id, creator, broadcaster_id, title, url, video_id,
                   vod_offset, duration_s, view_count, clip_created_at, views_per_hour)
               VALUES (:clip_id,:creator,:broadcaster_id,:title,:url,:video_id,:vod_offset,
                   :duration_s,:view_count,:created_at,:views_per_hour)
               ON CONFLICT(clip_id) DO UPDATE SET view_count=excluded.view_count,
                   views_per_hour=excluded.views_per_hour, updated_at=datetime('now')""", c)
    db.commit()


def to_picks(cands, n):
    """Editor format. start/end are seconds inside the downloaded Twitch clip file."""
    return [{"start": 0, "end": min(c["duration_s"] or MAX_PICK_S, MAX_PICK_S),
             "source_url": c["url"], "creator": c["creator"], "clip_id": c["clip_id"]}
            for c in cands[:n]]


def connect(path=None):
    return sqlite3.connect(path or os.environ.get("CLIPPER_DB", "/opt/clipper/db/clip.db"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--picks", type=int, metavar="N", help="write picks.json with top N")
    ap.add_argument("--out", default="picks.json")
    ap.add_argument("--min-candidates", type=int, default=10,
                    help="widen to 7 days if fewer per creator")
    ap.add_argument("--config", help="creators.yaml path")
    a = ap.parse_args(argv)

    from .twitch import Twitch
    cands = collect(Twitch(), load_creators(a.config), max(a.min_candidates, a.picks or 0))
    store(connect(), cands)
    for i, c in enumerate(cands, 1):
        print(f"{i:>3}. {c['views_per_hour']:>9.1f} v/h  {c['view_count']:>7} views  "
              f"{c['creator']}  {c['title'][:50]!r}  {c['url']}")
    if a.picks:
        Path(a.out).write_text(json.dumps(to_picks(cands, a.picks), indent=2))
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
