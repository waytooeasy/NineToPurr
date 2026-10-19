"""Metrics puller (D35: after launch): public stats of our own Shorts -> post_metrics.

Runs as the first-hour stage of every pipeline pass (run_pipeline "metrics"), throttled to once per
MIN_INTERVAL_MIN per post. Uses the YouTube Data API key (videos.list statistics, 1 quota unit per
50 videos): views, likes, comments. Engaged views / swipe-away need the YouTube Analytics API and a
token with yt-analytics.readonly (not granted yet; our token is upload-only).

    python clipper/analyst/metrics.py            # pull once now (needs YOUTUBE_API_KEY, CLIPPER_DB)
    python clipper/analyst/metrics.py --report   # print the per-Short table
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone

API = "https://www.googleapis.com/youtube/v3/videos"
MAX_AGE_DAYS = 30          # stop polling a Short after this
MIN_INTERVAL_MIN = 55      # at most ~hourly per Short
DEFAULT_DB = "/opt/clipper/db/clip.db"


def _utc(s):
    return datetime.fromisoformat(s.replace("Z", "").replace("T", " ")).replace(tzinfo=timezone.utc)


def due_posts(con, now, max_age_days=MAX_AGE_DAYS, min_interval_min=MIN_INTERVAL_MIN):
    """YouTube posts younger than max_age_days whose last measurement is older than min_interval_min."""
    rows = con.execute(
        "SELECT p.id, p.platform_post_id, p.posted_at,"
        " (SELECT MAX(measured_at) FROM post_metrics m WHERE m.post_id = p.id) AS last"
        " FROM posts p WHERE p.platform_post_id IS NOT NULL AND p.platform_post_id != ''").fetchall()
    out = []
    for r in rows:
        age_h = (now - _utc(r[2])).total_seconds() / 3600
        if age_h > max_age_days * 24:
            continue
        if r[3] and (now - _utc(r[3])).total_seconds() < min_interval_min * 60:
            continue
        out.append({"post_id": r[0], "video_id": r[1], "age_h": round(age_h, 2)})
    return out


def fetch_stats(video_ids, key, session=None):
    """{video_id: {"views", "likes", "comments"}} for public videos (missing = private/processing)."""
    import requests
    http = session or requests
    out = {}
    for i in range(0, len(video_ids), 50):
        r = http.get(API, params={"part": "statistics", "id": ",".join(video_ids[i:i + 50]), "key": key},
                     timeout=20)
        r.raise_for_status()
        for it in r.json().get("items", []):
            st = it.get("statistics", {})
            out[it["id"]] = {k: int(st[f]) if st.get(f) is not None else None
                             for k, f in (("views", "viewCount"), ("likes", "likeCount"),
                                          ("comments", "commentCount"))}
    return out


def run(con, key, session=None, now=None):
    """Measure every due Short once. -> number of rows written."""
    now = now or datetime.now(timezone.utc)
    due = due_posts(con, now)
    if not due or not key:
        return 0
    stats = fetch_stats([d["video_id"] for d in due], key, session)
    n = 0
    with con:
        for d in due:
            s = stats.get(d["video_id"])
            if s is None:
                continue
            con.execute("INSERT INTO post_metrics (post_id, measured_at, hours_since_post, views, likes, comments)"
                        " VALUES (?,?,?,?,?,?)",
                        (d["post_id"], now.strftime("%Y-%m-%d %H:%M:%S"), d["age_h"], s["views"], s["likes"],
                         s["comments"]))
            n += 1
    return n


def report(con, limit=15):
    """Per-Short table: latest views, views/hour since posting, likes, streamer, title."""
    rows = con.execute(
        "SELECT p.url, p.posted_at, r.creator, c.title, m.views, m.likes, m.comments, m.hours_since_post"
        " FROM posts p JOIN clips c ON c.id = p.clip_id"
        " LEFT JOIN radar_candidates r ON r.clips_id = c.id"
        " LEFT JOIN post_metrics m ON m.id = (SELECT id FROM post_metrics WHERE post_id = p.id"
        "                                      ORDER BY measured_at DESC, id DESC LIMIT 1)"
        " ORDER BY p.posted_at DESC LIMIT ?", (limit,)).fetchall()
    if not rows:
        return "No Shorts posted yet."
    total = sum(r[4] or 0 for r in rows)
    lines = [f"📈 {len(rows)} Shorts · {total:,} views"]
    for url, posted, creator, title, views, likes, comments, h in rows:
        vph = f"{views / h:,.0f}/h" if views is not None and h else "-"
        v = f"{views:,}" if views is not None else "processing"
        lines.append(f"• {creator or '?'}: {v} views ({vph}), {likes or 0} likes · {(title or '')[:40]}\n  {url}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    con = sqlite3.connect(os.environ.get("CLIPPER_DB", DEFAULT_DB), timeout=30)
    if a.report:
        print(report(con))
        return 0
    print(f"measured {run(con, os.environ.get('YOUTUBE_API_KEY'))} Shorts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
