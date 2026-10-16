"""Trend Scout stats: views/hour, patterns, streamer leaderboard, daily ranking + weights.

Pure functions over the video dicts from scout_data (and Twitch clip dicts); no I/O.
"""
import re
import statistics
from collections import Counter, defaultdict
from datetime import timedelta, timezone

ASUNCION = timezone(timedelta(hours=-3))  # Paraguay: permanent UTC-3 since Oct 2024
LENGTH_BUCKETS = [(15, "<=15s"), (30, "16-30s"), (45, "31-45s"), (60, "46-60s")]
HASHTAG_STOP = {"shorts", "short", "fyp", "viral", "funny", "clips", "clip", "trending", "live",
                "stream", "streamer", "twitch", "youtube", "fypシ", "foryou", "memes", "meme"}
TOP_N = 20


def age_hours(published, now):
    return max((now - published).total_seconds() / 3600, 1.0)  # floor 1 h: new uploads don't explode


def vph(video, now):
    return video["views"] / age_hours(video["published"], now)


def within(videos, now, hours):
    return [v for v in videos if timedelta(0) <= now - v["published"] <= timedelta(hours=hours)]


def top_videos(videos, now, n=TOP_N, days=7):
    """Top n by views/hour among Shorts of the last `days` (duration unknown counts as a Short)."""
    pool = [v for v in within(videos, now, days * 24)
            if v.get("duration_s") is None or v["duration_s"] <= 180]
    return sorted(pool, key=lambda v: vph(v, now), reverse=True)[:n]


def length_bucket(duration_s):
    if duration_s is None:
        return "unknown"
    for limit, name in LENGTH_BUCKETS:
        if duration_s <= limit:
            return name
    return ">60s"


# --- streamer detection -------------------------------------------------------------------

def build_matchers(aliases, extra_names=()):
    """name -> compiled regex. Aliases from config; every extra name matches itself."""
    table = {n: list(a) for n, a in (aliases or {}).items()}
    for n in extra_names:
        table.setdefault(n, [])
    return {n: re.compile(r"(?<![a-z0-9])(?:%s)(?![a-z0-9])" % "|".join(
        re.escape(a.lower()) for a in sorted({n.lower(), *[x.lower() for x in al]}, key=len, reverse=True)))
        for n, al in table.items()}


def streamers_in(video, matchers):
    """Streamers named in the title/hashtags; falls back to the channel's lone streamer."""
    text = video["title"].lower()
    found = [n for n, rx in matchers.items() if rx.search(text)]
    if not found and len(video.get("default_streamers") or []) == 1:
        found = list(video["default_streamers"])
    return found


def rising_candidates(videos, matchers, min_videos=2):
    """#hashtags that are not a known streamer or generic tag: possible new streamers."""
    c, chans = Counter(), defaultdict(set)
    for v in videos:
        for tag in {t.lower() for t in re.findall(r"#(\w+)", v["title"])}:
            if tag in HASHTAG_STOP or any(rx.fullmatch(tag) for rx in matchers.values()):
                continue
            c[tag] += 1
            chans[tag].add(v["channel"])
    return [{"tag": t, "videos": n, "channels": len(chans[t])}
            for t, n in c.most_common() if n >= min_videos]


# --- patterns ------------------------------------------------------------------------------

def title_template(title, matchers):
    t = title.lower()
    for rx in matchers.values():
        t = rx.sub("{S}", t)
    t = re.sub(r"#\w+", "", t)
    t = re.sub(r"\d+", "{N}", t)
    return re.sub(r"\s+", " ", t).strip()


def patterns(top, matchers, now):
    hours_utc, hours_py = defaultdict(list), defaultdict(list)
    lengths, streamers, templates = defaultdict(list), Counter(), []
    for v in top:
        p = v["published"]
        hours_utc[p.hour].append(vph(v, now))
        hours_py[p.astimezone(ASUNCION).hour].append(vph(v, now))
        lengths[length_bucket(v.get("duration_s"))].append(vph(v, now))
        streamers.update(streamers_in(v, matchers))
        templates.append({"template": title_template(v["title"], matchers), "vph": round(vph(v, now), 1)})

    def agg(d):
        return sorted(({"key": k, "videos": len(x), "avg_vph": round(statistics.mean(x), 1)}
                       for k, x in d.items()), key=lambda r: -r["avg_vph"])
    return {"title_templates": templates, "length_buckets": agg(lengths),
            "upload_hour_utc": agg(hours_utc), "upload_hour_asuncion": agg(hours_py),
            "streamers": streamers.most_common()}


# --- leaderboard ---------------------------------------------------------------------------

def leaderboard(videos, matchers, now, hours, tracked=()):
    """Per streamer over the last `hours`: shorts, views, avg/total views/hour, crowding.

    crowding = number of distinct clip channels posting that streamer. test_slot = above-median
    avg views/hour with <=2 clippers and not already tracked by Radar.
    """
    rows = defaultdict(lambda: {"shorts": 0, "views": 0, "vph": [], "channels": set()})
    for v in within(videos, now, hours):
        for s in streamers_in(v, matchers):
            r = rows[s]
            r["shorts"] += 1
            r["views"] += v["views"]
            r["vph"].append(vph(v, now))
            r["channels"].add(v["channel"])
    out = [{"streamer": s, "shorts": r["shorts"], "views": r["views"],
            "total_vph": round(sum(r["vph"]), 1), "avg_vph": round(statistics.mean(r["vph"]), 1),
            "clippers": len(r["channels"])} for s, r in rows.items()]
    med = statistics.median([r["avg_vph"] for r in out]) if out else 0
    tracked_l = {t.lower() for t in tracked}
    for r in out:
        r["tracked"] = r["streamer"].lower() in tracked_l
        r["test_slot"] = r["avg_vph"] > med and r["clippers"] <= 2 and not r["tracked"]
    return sorted(out, key=lambda r: -r["total_vph"])


# --- Twitch clips + ranking (D33) -------------------------------------------------------------

def clip_velocity(clips, now):
    """Sum of clip views/hour for one streamer's Twitch clips (created_at RFC3339 or datetime)."""
    from datetime import datetime
    total = 0.0
    for c in clips:
        created = c["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        total += c.get("view_count", 0) / age_hours(created, now)
    return round(total, 1)


def _norm(values):
    top = max(values.values(), default=0)
    return {k: round(v / top, 3) if top else 0.0 for k, v in values.items()}


def build_ranking(clip_vel, lb24, previous):
    """creators_ranking.json rows. score = clip velocity x Shorts velocity / clip channels.

    A streamer with Twitch clips but no competitor Shorts yet scores with Shorts velocity 1
    (unproven, never zero) so Radar still sees fresh names. trend: new / up / down vs `previous`
    (list of earlier rows); a streamer entering the top 5 that wasn't in the previous top 5 is `new`.
    """
    shorts = {r["streamer"]: r for r in lb24}
    names = set(clip_vel) | set(shorts)
    scores = {}
    for n in names:
        sv = shorts[n]["total_vph"] if n in shorts else 1.0
        crowd = max(shorts[n]["clippers"], 1) if n in shorts else 1
        scores[n] = round(clip_vel.get(n, 0.0) * sv / crowd, 1)
    weights = _norm(scores)
    ranked = sorted(names, key=lambda n: -scores[n])
    prev = {r["streamer"]: r for r in previous or []}
    prev_top5 = {r["streamer"] for r in sorted(previous or [], key=lambda r: -r["score"])[:5]}
    rows = []
    for i, n in enumerate(ranked):
        p = prev.get(n)
        if p is None or (i < 5 and n not in prev_top5 and previous):
            trend = "new"
        else:
            trend = "up" if scores[n] > p["score"] else "down"
        rows.append({"streamer": n, "platform": "twitch" if n in clip_vel else "youtube",
                     "score": scores[n], "weight": weights[n], "trend": trend})
    return rows


def build_weights(lb24, lb7):
    """creator_weights.json: streamer -> 0..1. score = 7d views x 24h momentum / crowding."""
    v24 = {r["streamer"]: r["total_vph"] for r in lb24}
    scores = {}
    for r in lb7:
        base7 = r["total_vph"] or 1.0
        momentum = min(max(v24.get(r["streamer"], 0.0) / base7, 0.1), 5.0)
        scores[r["streamer"]] = r["views"] * momentum / max(r["clippers"], 1)
    return _norm(scores)


def weekly_recommendations(lb7, weights, tracked, top_k=10):
    """add: untracked streamers in the 7d top_k by weight. drop: tracked with weight < 0.05 / unseen."""
    tracked_l = {t.lower(): t for t in tracked}
    ranked = sorted(weights, key=lambda s: -weights[s])
    add = [s for s in ranked[:top_k] if s.lower() not in tracked_l]
    drop = [t for low, t in tracked_l.items()
            if weights.get(next((s for s in weights if s.lower() == low), ""), 0.0) < 0.05]
    return {"add": add, "drop": drop}
