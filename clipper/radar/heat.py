#!/usr/bin/env python3
"""Heat Index (D33): which streamers are worth a Shorts slot today. Writes `streamer_heat`.

Per streamer (all enabled watchlist entries with the same name are summed):
  D = views on clips created in the last 24 h      (Twitch: Get Clips; Kick: top week clips; YouTube: views of
                                                     own live VODs from 24 h)
  W = same, last 7 days;  B = W / 7 (daily baseline)
  momentum = (D + 1) / (B + 1)
  heat = ln(1 + D) * (1 + 0.5 * log2(momentum)) + 0.3 * ln(1 + B) + LIVE_BONUS * live_now
  opportunity = heat / (1 + 0.1 * saturation)
ln = natural log. The momentum factor is floored at MIN_MOMENTUM_FACTOR so a collapsing streamer
(momentum < 1/4) cannot score negative. saturation = competitor Shorts about the streamer in the last
24 h (Trend Scout); 0 when no data. Slots: see `allocate`.

With a fresh Shorts market scan (radar/market.py, D48) the opportunity follows what is popping instead:
  opportunity = sqrt(demand) * sqrt(min(1, D / SUPPLY_FULL)) * (LIVE_BOOST if live)
demand = views/hour of the top Shorts naming the streamer in 48 h (any channel); the second factor is
"is there fresh footage to clip" (Twitch/Kick clip views in 24 h). No demand -> no slot.

Usage (from clipper/, every 30 min):
  python -m radar.heat                 # poll, write streamer_heat, print table + today's allocation
  python -m radar.heat --allocation allocation.json   # also write slots for `radar.top_clips --allocation`
Env: TWITCH_CLIENT_ID/SECRET, CLIPPER_DB, CLIPPER_SATURATION (optional JSON {streamer: shorts_24h}).
"""
import argparse
import json
import math
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).parent
LIVE_BONUS = 1.0
MIN_MOMENTUM_FACTOR = 0.1
SUPPLY_FULL = 2000.0        # clip views in 24 h that count as plenty of fresh footage (D48)
LIVE_BOOST = 1.15
MIN_COVERAGE = 0.5          # market scan must cover half the watchlist, else the old formula is used


def log(msg):
    print(f"[heat] {msg}", file=sys.stderr)


# --- pure formulas ------------------------------------------------------------------------------

def compute_heat(D, W, live_now=False, saturation=0.0):
    """Heat Index row for one streamer (see module docstring)."""
    B = W / 7
    momentum = (D + 1) / (B + 1)
    factor = max(1 + 0.5 * math.log2(momentum), MIN_MOMENTUM_FACTOR)
    heat = math.log(1 + D) * factor + 0.3 * math.log(1 + B) + (LIVE_BONUS if live_now else 0.0)
    return {"D": D, "W": W, "B": B, "momentum": momentum, "live_now": int(bool(live_now)),
            "saturation": saturation, "heat": heat,
            "opportunity": heat / (1 + 0.1 * saturation)}


def market_opportunity(demand, D, live_now=False):
    """Follow the market (D48): Shorts demand, discounted when there is little fresh footage to clip."""
    supply = min(1.0, max(D, 0) / SUPPLY_FULL) ** 0.5
    return math.sqrt(max(demand or 0, 0)) * supply * (LIVE_BOOST if live_now else 1.0)


def apply_market(rows, market):
    """Replace each row's opportunity by the market formula when the scan covers enough streamers.
    Returns True if applied. Rows get a `demand` key (None when not applied)."""
    ms = (market or {}).get("streamers") or {}
    if not rows or len([n for n in rows if n in ms]) < MIN_COVERAGE * len(rows):
        for r in rows.values():
            r["demand"] = None
        return False
    for n, r in rows.items():
        d = float((ms.get(n) or {}).get("demand_vph") or 0)
        r["demand"] = d
        r["opportunity"] = market_opportunity(d, r["D"], r["live_now"])
    return True


def allocate(opportunity, cap=5, last_posted=None, now=None, rng=None, max_per=2,
             explore_days=3, explore_top_n=15):
    """Daily slots per streamer: {name: n}, sum <= cap, each <= max_per.

    1 exploration slot goes to a random streamer from the top `explore_top_n` by opportunity that was
    not posted in `explore_days` days (`last_posted`: name -> aware datetime). The rest are split
    proportionally to opportunity (D'Hondt: deterministic, never over max_per). Streamers with
    opportunity <= 0 get nothing. `rng` is a random.Random (seed it in tests).
    """
    rng = rng or random.Random()
    now = now or datetime.now(timezone.utc)
    last_posted = last_posted or {}
    live = {n: o for n, o in opportunity.items() if o > 0}
    slots = {}
    remaining = cap
    if remaining > 0:
        top = sorted(live, key=lambda n: (-live[n], n))[:explore_top_n]
        cutoff = now - timedelta(days=explore_days)
        eligible = [n for n in top if last_posted.get(n) is None or last_posted[n] < cutoff]
        if eligible:
            slots[rng.choice(eligible)] = 1
            remaining -= 1
    while remaining > 0:
        open_ = [n for n in live if slots.get(n, 0) < max_per]
        if not open_:
            break
        n = max(open_, key=lambda n: (live[n] / (slots.get(n, 0) + 1), n))
        slots[n] = slots.get(n, 0) + 1
        remaining -= 1
    return slots


# --- config -------------------------------------------------------------------------------------

def load_watchlist(path=None):
    """-> {"cap", "max_per", "explore_days", "explore_top_n", "streamers": {name: [entries]}}.
    Disabled entries are dropped; a streamer with no enabled entry is dropped."""
    cfg = yaml.safe_load(Path(path or HERE / "config" / "watchlist.yaml").read_text())
    streamers = {}
    for e in cfg.get("streamers", []):
        if e.get("disabled"):
            continue
        streamers.setdefault(str(e["name"]), []).append(
            {"platform": str(e["platform"]).lower(), "id": str(e["id"])})
    return {"cap": int(cfg.get("daily_cap", 5)), "max_per": int(cfg.get("max_per_streamer", 2)),
            "explore_days": int(cfg.get("explore_days", 3)),
            "explore_top_n": int(cfg.get("explore_top_n", 15)), "streamers": streamers}


def load_saturation(path=None):
    """{lowercase streamer: competitor Shorts in 24 h}. Missing/invalid file -> {} (saturation 0)."""
    path = path or os.environ.get("CLIPPER_SATURATION")
    if not path:
        return {}
    try:
        return {str(k).lower(): float(v) for k, v in json.loads(Path(path).read_text()).items()}
    except (OSError, ValueError, AttributeError):
        return {}


# --- network (small injectable functions) -------------------------------------------------------

def twitch_views(tw, login, now):
    """(D, W) from Get Clips over 7 days: D = views of clips created in the last 24 h."""
    clips = tw.get_clips(tw.broadcaster_id(login), now - timedelta(days=7), now)
    return clip_views(clips, now)


def clip_views(clips, now):
    D = W = 0
    for c in clips:
        v = int(c.get("view_count") or 0)
        W += v
        if datetime.fromisoformat(c["created_at"].replace("Z", "+00:00")) >= now - timedelta(days=1):
            D += v
    return D, W


def youtube_views(channel, now, runner=None):
    """(D, W) = views of the channel's own live VODs from the last 24 h / 7 d (yt-dlp metadata only)."""
    from . import youtube_vods as yv
    kw = {"runner": runner} if runner else {}
    D = W = 0
    for info in yv.own_vod_infos(channel, **kw):
        t = yv._vod_time(info)
        if not yv.is_own_live_vod(info, channel) or t is None or t < now - timedelta(days=7):
            continue
        v = int(info.get("view_count") or 0)
        W += v
        if t >= now - timedelta(days=1):
            D += v
    return D, W


def youtube_live(channel, runner=None):
    from . import youtube_vods as yv
    kw = {"runner": runner} if runner else {}
    try:
        info = yv.video_info(yv.channel_streams_url(channel).rsplit("/streams", 1)[0] + "/live", **kw)
    except Exception:  # noqa: BLE001 - no live stream makes yt-dlp fail
        return False
    return bool(info.get("is_live"))


KICK_PAGES = 3   # top 60 clips of the week per Kick channel; the tail adds little


def kick_views(kc, slug, now, pages=KICK_PAGES):
    """(D, W) from the channel's most-viewed Kick clips of the last 7 days (D = those from the last 24 h)."""
    return clip_views(kc.get_clips(slug, "week", max_pages=pages), now)


def default_fetchers(tw=None, kc=None):
    """(views(entry, now) -> (D, W), live(entry) -> bool) backed by Twitch, yt-dlp and Kick (D45).
    The Kick client is made on first use."""
    kick = {"client": kc}

    def kick_client():
        if kick["client"] is None:
            from .kick import Kick
            kick["client"] = Kick()
        return kick["client"]

    def views(e, now):
        if e["platform"] == "twitch":
            return twitch_views(tw, e["id"], now)
        if e["platform"] == "youtube":
            return youtube_views(e["id"], now)
        if e["platform"] == "kick":
            return kick_views(kick_client(), e["id"], now)
        return 0, 0

    def live(e):
        if e["platform"] == "twitch":
            return tw.is_live(e["id"])
        if e["platform"] == "youtube":
            return youtube_live(e["id"])
        if e["platform"] == "kick":
            return kick_client().is_live(e["id"])
        return False
    return views, live


# --- run ----------------------------------------------------------------------------------------

def measure(streamers, views, live, saturation, now):
    """{name: heat row}. A failing platform is logged and counts as 0 views / not live."""
    rows = {}
    for name, entries in streamers.items():
        D = W = 0
        is_live = False
        for e in entries:
            try:
                d, w = views(e, now)
                D, W = D + d, W + w
                is_live = is_live or bool(live(e))
            except Exception as ex:  # noqa: BLE001 - one bad entry must not stop the run
                log(f"{name} ({e['platform']}:{e['id']}): {type(ex).__name__}")
        rows[name] = compute_heat(D, W, is_live, saturation.get(name.lower(), 0.0))
    return rows


def write_rows(db, rows, now):
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    db.executemany(
        """INSERT OR REPLACE INTO streamer_heat
           (streamer, ts, D, W, B, momentum, live_now, saturation, heat, opportunity, demand)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [(n, ts, r["D"], r["W"], r["B"], r["momentum"], r["live_now"], r["saturation"],
          r["heat"], r["opportunity"], r.get("demand")) for n, r in rows.items()])
    db.commit()


def last_posted(db, streamers):
    """{streamer name: latest posts.posted_at (aware datetime)} via posts -> clips -> sources -> creators.
    creators.name is matched case-insensitively against the streamer name (spaces removed) or any
    watchlist id."""
    names = {}
    for name, entries in streamers.items():
        for key in {name.lower(), name.lower().replace(" ", ""), *(e["id"].lower().lstrip("@") for e in entries)}:
            names[key] = name
    out = {}
    for cname, ts in db.execute(
            """SELECT lower(c.name), max(p.posted_at) FROM posts p
               JOIN clips cl ON cl.id = p.clip_id JOIN sources s ON s.id = cl.source_id
               JOIN creators c ON c.id = s.creator_id GROUP BY lower(c.name)"""):
        n = names.get(cname) or names.get(cname.replace(" ", ""))
        if not n or not ts:
            continue
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        if n not in out or t > out[n]:
            out[n] = t
    return out


def run(db, cfg, views, live, saturation, now, rng=None, market=None):
    """Measure, store, allocate. Returns (rows, slots). `market`: radar/market.py scan (D48) or None."""
    rows = measure(cfg["streamers"], views, live, saturation, now)
    apply_market(rows, market)
    write_rows(db, rows, now)
    slots = allocate({n: r["opportunity"] for n, r in rows.items()}, cfg["cap"],
                     last_posted(db, cfg["streamers"]), now, rng, cfg["max_per"],
                     cfg["explore_days"], cfg["explore_top_n"])
    return rows, slots


def allocation_doc(cfg, slots):
    """JSON for `top_clips --allocation`: slots per streamer + watchlist id -> streamer map."""
    ids = {}
    for name, entries in cfg["streamers"].items():
        for e in entries:
            ids[e["id"].lower().lstrip("@")] = name
        ids[name.lower()] = name
    return {"slots": slots, "ids": ids}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", help="watchlist.yaml path")
    ap.add_argument("--allocation", metavar="FILE", help="write today's slots as JSON")
    a = ap.parse_args(argv)
    from .twitch import Twitch
    from .top_clips import connect
    cfg = load_watchlist(a.config)
    now = datetime.now(timezone.utc)
    views, live = default_fetchers(Twitch())
    db = connect()
    from . import market
    rows, slots = run(db, cfg, views, live, load_saturation(), now, market=market.load())
    for n, r in sorted(rows.items(), key=lambda kv: -kv[1]["opportunity"]):
        print(f"{n:<16} opp {r['opportunity']:6.2f} heat {r['heat']:6.2f} D {r['D']:>8.0f} "
              f"B {r['B']:>8.0f} mom {r['momentum']:5.2f} live {r['live_now']} sat {r['saturation']:.0f} "
              f"slots {slots.get(n, 0)}")
    if a.allocation:
        Path(a.allocation).write_text(json.dumps(allocation_doc(cfg, slots), indent=2))
        print(f"wrote {a.allocation}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
