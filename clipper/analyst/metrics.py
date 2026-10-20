"""Metrics puller (D35: after launch): public stats of our own Shorts -> post_metrics.

Runs as the first-hour stage of every pipeline pass (run_pipeline "metrics"), throttled to once per
MIN_INTERVAL_MIN per post. Uses the YouTube Data API key (videos.list statistics, 1 quota unit per
50 videos): views, likes, comments. D53: every 6 h the owner-only YouTube Analytics (read-only token
$YOUTUBE_ANALYTICS_TOKEN, separate from the upload token) adds engaged views ("stayed" = engaged/views,
the viewed-vs-swiped proxy), average view % and subscribers gained per Short -> post_analytics.

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


# --- YouTube Analytics (owner data, read-only token, D53) -------------------------------------------

ANALYTICS_TOKEN = "/opt/clipper/youtube_analytics_token.json"
ANALYTICS_SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly",
                    "https://www.googleapis.com/auth/youtube.readonly"]
ANALYTICS_EVERY_H = 6
FULL = "views,engagedViews,averageViewDuration,averageViewPercentage,likes,subscribersGained"
BASIC = "views,averageViewDuration,averageViewPercentage,likes,subscribersGained"


def analytics_service(token_file=None):
    """YouTube Analytics v2 client from the read-only token (refreshed and saved back), or None."""
    p = token_file or os.environ.get("YOUTUBE_ANALYTICS_TOKEN", ANALYTICS_TOKEN)
    if not os.path.exists(p):
        return None
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(p, ANALYTICS_SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        with open(p, "w") as f:
            f.write(creds.to_json())
        os.chmod(p, 0o600)
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)


def analytics_due(con, now, every_h=ANALYTICS_EVERY_H):
    last = con.execute("SELECT MAX(measured_at) FROM post_analytics").fetchone()[0]
    return not last or (now - _utc(last)).total_seconds() >= every_h * 3600


def pull_analytics(con, service, now=None):
    """Lifetime analytics of every posted Short (30 days) -> post_analytics. -> rows written."""
    now = now or datetime.now(timezone.utc)
    posts = con.execute("SELECT id, platform_post_id, posted_at FROM posts WHERE platform_post_id IS NOT NULL"
                        " AND platform_post_id != ''").fetchall()
    posts = [p for p in posts if (now - _utc(p[2])).total_seconds() <= MAX_AGE_DAYS * 86400]
    if not posts or service is None:
        return 0
    start = min(_utc(p[2]) for p in posts).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    by_vid = {p[1]: p[0] for p in posts}
    rows, metrics = None, FULL
    for metrics in (FULL, BASIC):                    # engagedViews is newer; fall back if the API rejects it
        try:
            rows = service.reports().query(ids="channel==MINE", startDate=start, endDate=end, metrics=metrics,
                                           dimensions="video", filters="video==" + ",".join(by_vid),
                                           maxResults=200).execute()
            break
        except Exception as e:  # noqa: BLE001
            if metrics == BASIC or "engagedViews" not in str(e):
                raise
    cols = [h["name"] for h in rows.get("columnHeaders", [])]
    n = 0
    with con:
        for r in rows.get("rows") or []:
            d = dict(zip(cols, r))
            pid = by_vid.get(d.get("video"))
            if pid is None:
                continue
            con.execute("INSERT INTO post_analytics (post_id, measured_at, through_date, views, engaged_views,"
                        " avg_view_s, avg_view_pct, likes, subs_gained) VALUES (?,?,?,?,?,?,?,?,?)",
                        (pid, now.strftime("%Y-%m-%d %H:%M:%S"), end, d.get("views"), d.get("engagedViews"),
                         d.get("averageViewDuration"), d.get("averageViewPercentage"), d.get("likes"),
                         d.get("subscribersGained")))
            n += 1
    return n


def run_analytics(con, now=None, service=None, token_file=None):
    """Every ANALYTICS_EVERY_H hours when the analytics token exists. -> rows written or a skip reason."""
    now = now or datetime.now(timezone.utc)
    if not analytics_due(con, now):
        return "fresh"
    service = service or analytics_service(token_file)
    if service is None:
        return "skipped: no analytics token"
    return pull_analytics(con, service, now)


def _analytics_bit(con, post_id):
    """' · stayed 61% · watched 72%' from the latest post_analytics row, '' when none yet."""
    try:
        a = con.execute("SELECT views, engaged_views, avg_view_pct FROM post_analytics WHERE post_id = ?"
                        " ORDER BY measured_at DESC, id DESC LIMIT 1", (post_id,)).fetchone()
    except sqlite3.Error:                      # migration 012 not applied yet
        return ""
    if not a:
        return ""
    bits = []
    if a[0] and a[1] is not None:
        bits.append(f"stayed {100 * a[1] / a[0]:.0f}%")
    if a[2] is not None:
        bits.append(f"watched {a[2]:.0f}%")
    return (" · " + " · ".join(bits)) if bits else ""


def report(con, limit=15):
    """Per-Short table: latest views, views/hour since posting, likes, stay/watch % (analytics), title."""
    rows = con.execute(
        "SELECT p.url, p.posted_at, r.creator, c.title, m.views, m.likes, m.comments, m.hours_since_post, p.id"
        " FROM posts p JOIN clips c ON c.id = p.clip_id"
        " LEFT JOIN radar_candidates r ON r.clips_id = c.id"
        " LEFT JOIN post_metrics m ON m.id = (SELECT id FROM post_metrics WHERE post_id = p.id"
        "                                      ORDER BY measured_at DESC, id DESC LIMIT 1)"
        " ORDER BY p.posted_at DESC LIMIT ?", (limit,)).fetchall()
    if not rows:
        return "No Shorts posted yet."
    total = sum(r[4] or 0 for r in rows)
    lines = [f"📈 {len(rows)} Shorts · {total:,} views"]
    for url, posted, creator, title, views, likes, comments, h, pid in rows:
        vph = f"{views / h:,.0f}/h" if views is not None and h else "-"
        v = f"{views:,}" if views is not None else "processing"
        lines.append(f"• {creator or '?'}: {v} views ({vph}), {likes or 0} likes{_analytics_bit(con, pid)}"
                     f" · {(title or '')[:40]}\n  {url}")
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
