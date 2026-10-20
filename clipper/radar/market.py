"""Shorts market scan (D48): what is popping on YouTube Shorts per watchlist streamer right now.

Lucas 2026-10-20: "follow what's popping and trending, don't reinvent the rule". The Heat Index used to rank
streamers by their Twitch clip views (supply) only, so it gave slots to Valkyrae (~400 views/h on all
Shorts about her in 48 h) instead of Jynxzi (108k) or CaseOh (46k). This scan measures demand: for each
streamer, the most-viewed Shorts that name them, any channel, published in the last 48 h.

Metadata only (search.list ~100 units + videos.list 1 unit per streamer); never downloads a video.
A full scan runs once a day from the pipeline (`run_pipeline.market_step`); every REFRESH_H hours in
between, the REFRESH_TOP streamers with the most demand (the ones Radar posts) are re-scanned (`refresh`, D54)
so popping titles and matched moments follow the market within hours. Writes market.json:
  {"updated": iso (full scan), "refreshed": iso (last refresh), "window_h": 48, "streamers": {name:
   {"demand_vph", "shorts": [top 10 by views/hour: {"id", "title", "channel", "views", "vph", "dur",
   "hour_utc", "published", "en", "desc"}], "dur_median", "hashtags"}}}
Consumers: heat.py (demand-driven opportunity), the Writer (popping titles for the same streamer),
the publisher (the streamer's own sub-market hashtags), radar/match.py (the same moments, D54).
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

API = "https://www.googleapis.com/youtube/v3"
MARKET_FILE = "/opt/clipper/formats/market.json"
WATCHLIST = Path(__file__).parent / "config" / "watchlist.yaml"
WINDOW_H = 48
TOP = 10
MAX_AGE_H = 24          # rescan once a day
STALE_H = 72            # older than this: consumers ignore it
REFRESH_H = 6           # re-scan the top streamers this often between full scans (D54)
REFRESH_TOP = 8         # ~8 x 101 units per refresh; the full scan is ~30 x 101 of the 10k/day
TAG = re.compile(r"#(\w+)", re.UNICODE)
# Names that are ordinary words or famous non-streamers: a mention only counts next to a streaming word.
AMBIGUOUS = {"sketch", "shroud", "lacy", "marlon", "tarik", "ludwig", "sam", "summit"}
CONTEXT = re.compile(r"(?<![a-z0-9])(stream|streams|streamer|streaming|twitch|kick|clip|clips|chat|live)(?![a-z0-9])")
EN_WORDS = {"the", "a", "an", "to", "and", "is", "are", "his", "her", "he", "she", "him", "me", "my", "you", "your",
            "it", "on", "in", "of", "for", "this", "that", "after", "before", "with", "gets", "got", "when", "was",
            "bro", "why", "how", "what", "who", "can't", "not", "just", "up", "out", "at", "by", "has", "have", "so",
            "no", "way", "did", "does", "says", "said", "finally", "first", "about", "like", "now", "they", "them",
            "we", "from", "into", "over", "too", "very", "all", "never", "every", "be", "made", "makes"}
# Common words of the other languages that show up in this niche's search results (ID, DE, ES, FR, PT)
FOREIGN_WORDS = {"ist", "und", "der", "die", "das", "nicht", "mit", "auf", "tapi", "malah", "cuma", "yang", "dan",
                 "siapa", "sangka", "lawan", "dengan", "ini", "itu", "que", "los", "las", "con", "para", "por", "el",
                 "una", "une", "et", "les", "des", "est", "pas", "não", "uma", "com", "reaksi", "kamera"}


def log(msg):
    print(f"[market] {msg}", file=sys.stderr)


def flat(s):
    return re.sub(r"[\W_]+", "", str(s or "").lower())


def path():
    return Path(os.environ.get("CLIPPER_MARKET", MARKET_FILE))


def watchlist_names(wl_path=None):
    """{streamer name: {lowercase aliases: 'kai cenat', 'kaicenat', every watchlist id}}."""
    cfg = yaml.safe_load(Path(wl_path or WATCHLIST).read_text()) or {}
    out = {}
    for e in cfg.get("streamers", []):
        if e.get("disabled"):
            continue
        n = str(e["name"])
        out.setdefault(n, {n.lower(), flat(n)}).add(str(e["id"]).lower().lstrip("@"))
    return out


def name_for(login, wl_path=None):
    """Watchlist streamer name for a Radar creator login/slug ('caseoh_' -> 'CaseOh'), else None."""
    key = flat(str(login or "").lstrip("@"))
    for n, al in watchlist_names(wl_path).items():
        if key in {flat(a) for a in al}:
            return n
    return None


def _word(a, t):
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])", t))


def mentions(text, aliases, others=(), context_text=None):
    """True if the text names the streamer as a whole word (or #tag). A name that is also an ordinary word
    or a famous non-streamer (AMBIGUOUS) only counts when `context_text` (title + tags) is about streaming:
    a streaming word or another watchlist streamer. "#sketch" on a DIY video or "Marlon Wayans" is not."""
    t = str(text or "").lower()
    if not any(_word(a, t) for a in aliases if a):
        return False
    if aliases & AMBIGUOUS:
        c = str(context_text if context_text is not None else text).lower()
        return bool(CONTEXT.search(c)) or any(_word(o, c) for o in others if o and len(o) >= 4)
    return True


def is_english(title):
    t = str(title or "")
    letters = [c for c in t if c.isalpha()]
    if not letters or sum(c.isascii() for c in letters) / len(letters) < 0.9:
        return False
    words = {w.strip(".,!?'\"").lower() for w in t.split()}
    return bool(words & EN_WORDS) and not words & FOREIGN_WORDS


def _dur(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)) if m else None


def _hashtags(shorts, others, min_channels=2):
    """Hashtags of the top Shorts (title + description), weighted by views/hour. Kept only when at least
    `min_channels` channels use it (so one moment's tag, e.g. #joebart on a CaseOh clip, is not copied onto
    every clip); another streamer's tag is dropped (a clip only gets its own streamer's tag)."""
    w, chans = {}, {}
    for s in shorts:
        for t in {x.lower() for x in TAG.findall(f"{s['title']} {s.get('desc', '')}")}:
            if t in others:
                continue
            w[t] = w.get(t, 0) + s["vph"]
            chans.setdefault(t, set()).add(s.get("channel"))
    keep = [t for t in w if len(chans[t]) >= min_channels]
    return [f"#{t}" for t in sorted(keep, key=lambda t: (-w[t], t))][:6]


def scan_streamer(name, aliases, key, session, now, others=frozenset(), other_aliases=frozenset()):
    """Top English Shorts naming `name` in the last WINDOW_H hours (any channel) + demand = sum of their
    views/hour. English only: we post for the English market (drops reposts in other languages)."""
    after = (now - timedelta(hours=WINDOW_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = session.get(f"{API}/search", timeout=30, params={
        "part": "id", "q": name, "type": "video", "videoDuration": "short", "order": "viewCount",
        "publishedAfter": after, "maxResults": 25, "relevanceLanguage": "en", "key": key})
    r.raise_for_status()
    ids = [i["id"]["videoId"] for i in r.json().get("items", []) if i.get("id", {}).get("videoId")]
    shorts = []
    if ids:
        v = session.get(f"{API}/videos", timeout=30, params={
            "part": "snippet,contentDetails,statistics", "id": ",".join(ids), "key": key})
        v.raise_for_status()
        for it in v.json().get("items", []):
            sn, st = it.get("snippet", {}), it.get("statistics", {})
            tags = " ".join(sn.get("tags") or [])
            if not mentions(f"{sn.get('title', '')} {sn.get('description', '')} {tags}", aliases, other_aliases,
                            context_text=f"{sn.get('title', '')} {tags} {(sn.get('description') or '')[:120]}"):
                continue                       # search is loose: keep Shorts that actually name the streamer
            if not is_english(sn.get("title")):
                continue
            pub = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            age = max((now - pub).total_seconds() / 3600, 0.5)
            views = int(st.get("viewCount", 0) or 0)
            shorts.append({"id": it["id"], "title": sn.get("title", ""), "channel": sn.get("channelTitle", ""),
                           "views": views, "vph": round(views / age), "dur": _dur(it.get("contentDetails", {}).get("duration")),
                           "hour_utc": pub.hour, "published": pub.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "en": is_english(sn.get("title")),
                           "desc": (sn.get("description") or "")[:200]})
    shorts.sort(key=lambda s: -s["vph"])
    top = shorts[:TOP]
    durs = sorted(s["dur"] for s in top if s["dur"])
    return {"demand_vph": sum(s["vph"] for s in top), "shorts": top,
            "dur_median": durs[len(durs) // 2] if durs else None, "hashtags": _hashtags(top, others)}


def _scan_names(names, todo, key, session, now):
    """{name: scan} for the names in `todo`. A failing streamer is logged and left out; a 403 (quota) stops."""
    out = {}
    for n in todo:
        al = names[n]
        other_al = {a for m, al2 in names.items() if m != n for a in al2} - al
        others = {flat(a) for a in other_al} - {flat(a) for a in al}
        try:
            out[n] = scan_streamer(n, al, key, session, now, others, other_al)
        except Exception as e:  # noqa: BLE001 - quota/network: keep the rest
            log(f"{n}: {type(e).__name__}")
            if "403" in str(e):              # quota exhausted: stop, keep what we have
                break
    return out


def scan(key, session=None, now=None, wl_path=None):
    """Scan every watchlist streamer. A failing streamer is logged and left out."""
    import requests
    session = session or requests.Session()
    now = now or datetime.now(timezone.utc)
    names = watchlist_names(wl_path)
    out = _scan_names(names, list(names), key, session, now)
    return {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "window_h": WINDOW_H, "streamers": out}


def refresh(data, key, session=None, now=None, wl_path=None, top=REFRESH_TOP):
    """Re-scan the `top` streamers by demand between full scans (D54); the others keep the full scan's data.
    A streamer whose re-scan fails keeps its previous entry."""
    import requests
    session = session or requests.Session()
    now = now or datetime.now(timezone.utc)
    names = watchlist_names(wl_path)
    ranked = sorted(data["streamers"], key=lambda n: -(data["streamers"][n].get("demand_vph") or 0))
    new = _scan_names(names, [n for n in ranked if n in names][:top], key, session, now)
    return {**data, "streamers": {**data["streamers"], **new}, "refreshed": now.strftime("%Y-%m-%dT%H:%M:%SZ")}


def _iso(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def fresh_at(data):
    """Time of the newest market data in `data` (full scan or refresh)."""
    return max(_iso(t) for t in (data.get("updated"), data.get("refreshed")) if t)


def refresh_due(data, now=None, every_h=REFRESH_H):
    now = now or datetime.now(timezone.utc)
    return now - fresh_at(data) >= timedelta(hours=every_h)


def load(p=None, now=None, max_age_h=STALE_H):
    """market.json if present and fresher than max_age_h, else None."""
    p = Path(p or path())
    try:
        d = json.loads(p.read_text())
        t = datetime.fromisoformat(d["updated"].replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    now = now or datetime.now(timezone.utc)
    return d if now - t <= timedelta(hours=max_age_h) and d.get("streamers") else None


def due(p=None, now=None):
    return load(p, now, MAX_AGE_H) is None


def write(data, p=None):
    p = Path(p or path())
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)
    return data


MIN_LEN_S, MAX_LEN_S = 8, 60


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def target_length(login, market=None, wl_path=None, min_n=3):
    """Seconds the top clippers post for this creator's streamer right now (median length of their popping
    English Shorts, D51); the market-wide median when that streamer has fewer than `min_n`; None without a scan."""
    m = market if market is not None else load()
    if not m:
        return None
    name = name_for(login, wl_path)
    own = [s["dur"] for s in (m["streamers"].get(name) or {}).get("shorts", []) if s.get("en") and s.get("dur")]
    if len(own) < min_n:
        own = [s["dur"] for st in m["streamers"].values() for s in st.get("shorts", []) if s.get("en") and s.get("dur")]
    t = _median(own)
    return None if t is None else max(MIN_LEN_S, min(MAX_LEN_S, int(t)))


def popping_titles(login, n=5, market=None, wl_path=None):
    """Today's most popping English Short titles for this creator's streamer (for the Writer)."""
    m = market if market is not None else load()
    name = name_for(login, wl_path)
    if not m or not name or name not in m["streamers"]:
        return name, []
    return name, [{"title": s["title"], "vph": s["vph"], "dur": s["dur"]}
                  for s in m["streamers"][name]["shorts"] if s.get("en")][:n]
