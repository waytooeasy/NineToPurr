"""Hashtags the top clip channels use today (Lucas 2026-10-19: "find what hashtags are popping and use em").

Input: the Trend Scout's competitor Shorts (metadata only: title from RSS, description + tags from
videos.list). Over the most-viewed Shorts of the last 7 days, weighted by views:
- title_share: share of views on Shorts with a hashtag in the title (NexxoRecaps: "... 😭 #ishowspeed")
- generic: hashtags that name no streamer (#shorts, #twitch ...), used by at least 2 channels so one
  channel's own brand tag never counts, most-viewed first
- streamers: {streamer: the tag the market uses for them} (#ishowspeed, #kaicenat ...)
- keywords: plain video tags (the hidden "tags" field) that name no streamer
Writes hashtags.json next to library.md (trends branch); run_pipeline copies it to $CLIPPER_HASHTAGS
and the publisher uses it. A clip only ever gets its own streamer's tag: other streamers' tags on it
would be misleading metadata.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

TOP_N = 40
DAYS = 7
MAX_GENERIC = 6
MAX_KEYWORDS = 8
TAG = re.compile(r"#(\w+)", re.UNICODE)


def flat(s):
    """'Kai Cenat' / '#KaiCenat' / 'kai_cenat' -> 'kaicenat'."""
    return re.sub(r"[\W_]+", "", str(s or "").lower())


def tags_in(text):
    return {t.lower() for t in TAG.findall(text or "")}


def streamer_names(aliases=None, logins=()):
    """{streamer: {flat aliases}} from competitors.yaml aliases + watchlist names/logins."""
    out = defaultdict(set)
    for name, al in (aliases or {}).items():
        out[name] |= {flat(name), *(flat(a) for a in al or [])}
    for n in logins:
        out[n].add(flat(n))
    return {n: {a for a in s if a} for n, s in out.items()}


def _owner(tag, names):
    """(streamer, exact) if the tag names a streamer: exact = the tag IS one of their names."""
    for n, al in names.items():
        if tag in al:
            return n, True
    for n, al in names.items():
        if any(len(a) >= 4 and a in tag for a in al):
            return n, False
    return None, False


def _ranked(counter):
    """Keys by weight, ties alphabetical (Counter order on ties follows set order, which varies by run)."""
    return [k for k, _ in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))]


def summarize(videos, names, now, top_n=TOP_N, days=DAYS):
    recent = [v for v in videos if v.get("published") and v["published"] >= now - timedelta(days=days)]
    top = sorted(recent, key=lambda v: v.get("views") or 0, reverse=True)[:top_n]
    total = sum(v.get("views") or 0 for v in top) or 1
    weight, chans = Counter(), defaultdict(set)
    per_streamer = defaultdict(Counter)
    kw_weight, kw_videos = Counter(), Counter()
    in_title, title_counts = 0, []
    brands = {flat(v.get("channel")) for v in top}
    for v in top:
        w = v.get("views") or 0
        tt = tags_in(v.get("title"))
        if tt:
            in_title += w
            title_counts.append(len(tt))
        for t in tt | tags_in(v.get("description")):
            owner, exact = _owner(t, names)
            if owner:
                if exact:
                    per_streamer[owner][t] += w
                continue
            if t in brands:
                continue
            weight[t] += w
            chans[t].add(v.get("channel"))
        for k in {str(x).strip().lower() for x in v.get("tags") or [] if str(x).strip()}:
            if _owner(flat(k), names)[0] or flat(k) in brands:
                continue
            kw_weight[k] += w
            kw_videos[k] += 1
    generic = [f"#{t}" for t in _ranked(weight) if len(chans[t]) >= 2][:MAX_GENERIC]
    keywords = [k for k in _ranked(kw_weight) if kw_videos[k] >= 2][:MAX_KEYWORDS]
    title_counts.sort()
    return {
        "updated": f"{now:%Y-%m-%d}", "sample": len(top),
        "title_share": round(in_title / total, 3),
        "title_tags": title_counts[len(title_counts) // 2] if title_counts else 0,
        "generic": generic,
        "streamers": {n: f"#{_ranked(c)[0]}" for n, c in sorted(per_streamer.items())},
        "keywords": keywords,
    }


def write(path, summary):
    Path(path).write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
