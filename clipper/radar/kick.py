"""Kick source (#69, D45): a Kick channel's public clips and live status -> Radar candidates + Heat numbers.

Reads the public JSON that kick.com's own channel pages load (no key needed; the documented developer API,
api.kick.com/public/v1, needs an OAuth app and has no clips endpoint). Low volume: one page of 20 clips
per window (day + week) per channel per Radar pass, three pages per Heat measurement. If Kick answers with a challenge page or
403/429 instead of JSON, `KickBlocked` is raised and Kick is skipped for that pass: no bot-check
workarounds, ever.

Kick clips run up to 180 s and are made after the moment, so a clip longer than 60 s keeps its last 60 s
(`top_clips.pick_window`). Mature and non-public clips are skipped.
"""
import sys
import time
from datetime import datetime, timezone

import requests

from . import top_clips

API = "https://kick.com/api/v2/channels"
UA = "PRM-Clipper/1.0 (+https://waytooeasy.github.io)"
PAGE = 20           # clips per page (Kick's page size)
PAUSE_S = 0.5       # between pages


class KickBlocked(RuntimeError):
    """Kick answered with something other than JSON (challenge page, 403, 429, 503)."""


class Kick:
    def __init__(self, session=None, pause_s=PAUSE_S):
        self.http = session or requests.Session()
        self.pause_s = pause_s

    def _get(self, path, params=None):
        r = self.http.get(f"{API}/{path}", params=params or {}, timeout=20,
                          headers={"Accept": "application/json", "User-Agent": UA})
        ctype = r.headers.get("content-type", "")
        if r.status_code in (403, 429, 503) or (r.ok and "json" not in ctype):
            raise KickBlocked(f"{path}: HTTP {r.status_code} {ctype or 'no content-type'}")
        r.raise_for_status()
        return r.json()

    def get_clips(self, slug, window="week", max_pages=1):
        """Most-viewed clips of `slug` created in the last `window` ("day" | "week"), best first."""
        out, cursor = [], None
        for _ in range(max_pages):
            params = {"sort": "view", "time": window}
            if cursor:
                params["cursor"] = cursor
            d = self._get(f"{slug}/clips", params)
            clips = d.get("clips") or []
            out.extend(clips)
            cursor = d.get("nextCursor")
            if not cursor or len(clips) < PAGE:
                break
            if self.pause_s:
                time.sleep(self.pause_s)
        return out

    def is_live(self, slug):
        return bool((self._get(slug).get("livestream") or {}).get("is_live"))


def usable(raw):
    """Public, not marked mature."""
    return (raw.get("privacy") or "public") == "public" and not raw.get("is_mature")


def normalize(raw, slug, now):
    """Radar candidate (same keys as top_clips.normalize). video_id = Kick livestream id; Kick gives no
    VOD offset, so vod_offset stays None."""
    c = {
        "clip_id": raw["id"], "creator": slug.lower(), "broadcaster_id": None,
        "title": raw.get("title") or "", "url": f"https://kick.com/{slug.lower()}/clips/{raw['id']}",
        "video_id": str(raw["livestream_id"]) if raw.get("livestream_id") else None, "vod_offset": None,
        "duration_s": float(raw.get("duration") or 0),
        "view_count": int(raw.get("view_count") or raw.get("views") or 0),
        "created_at": raw["created_at"], "source": "kick",
    }
    c["views_per_hour"] = top_clips.score(c, now)
    return c


def same_moment(a, b, ids=None):
    """Same streamer and overlapping footage. A clip covers the `duration_s` seconds before it was created,
    on any platform, so this also catches one moment clipped on Twitch and on Kick (multistreamers like
    xQc). `ids` maps a login/slug (lowercase) to the streamer name."""
    def who(c):
        return (ids or {}).get(c["creator"].lower(), c["creator"]).lower()
    if who(a) != who(b):
        return False
    ea = top_clips.parse_ts(a["created_at"]).timestamp()
    eb = top_clips.parse_ts(b["created_at"]).timestamp()
    return ea - a["duration_s"] < eb and eb - b["duration_s"] < ea


def dedupe(cands, ids=None):
    """Keep the best-scoring clip of each moment, checking only pairs that involve a Kick clip (Twitch and
    YouTube pairs keep top_clips.dedupe's rules). Result is ranked by views per hour."""
    kept = []
    for c in sorted(cands, key=lambda x: x["views_per_hour"], reverse=True):
        if not any("kick" in (c.get("source"), k.get("source")) and same_moment(c, k, ids) for k in kept):
            kept.append(c)
    return kept


def collect(kick, slugs, min_candidates=None, now=None, windows=("day", "week"), allowed=None, log=None):
    """Per Kick channel: top clips of the day AND of the week, merged and ranked by views per hour.
    Unlike Twitch there is no "widen only when thin": a channel's day list is often 20 clips of 4-50
    views that would hide the week's real hit (28k views, 2026-10-19). `min_candidates` is kept for the
    shared call signature. A failing channel is logged and skipped; a block stops Kick for this pass."""
    now = now or datetime.now(timezone.utc)
    log = log or (lambda m: print(m, file=sys.stderr))
    out = []
    for slug in top_clips.filter_allowed(slugs, allowed):
        raw, blocked = {}, None
        try:
            for w in windows:
                for r in kick.get_clips(slug, w):
                    raw.setdefault(r["id"], r)
        except KickBlocked as e:
            blocked = e
        except Exception as e:  # noqa: BLE001 - one bad channel must not stop Radar
            log(f"[kick] {slug}: {type(e).__name__}: {e}")
        out.extend(dedupe([normalize(r, slug, now) for r in raw.values() if usable(r)]))
        if blocked:
            log(f"[kick] blocked, skipping Kick this pass: {blocked}")
            break
    return sorted(out, key=lambda x: x["views_per_hour"], reverse=True)
