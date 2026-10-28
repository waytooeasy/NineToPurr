"""Trend scan (D65): popping stream Shorts on YouTube, found without a streamer list.

Lucas 2026-10-28: "we dont follow certain streamers, we follow whats popular, whats trending". The market scan
(D48) only searches for Shorts that name the ~34 watchlist streamers. A sizing run the same day: 7 broad searches
found 108 Shorts at >= 1500 views/h in 48 h, and 96 of them were about streamers not on the list.

Each scan: a few broad YouTube searches (most viewed Shorts of the last WINDOW_H hours), English only, <= 60 s, then
who is in it: a watchlist name, a twitch.tv / kick.com link or "twitch: name" in the description, a hashtag or the
clip channel's own name ("Asmongold Shorts"). A hashtag or channel name only counts when Twitch says it is a
partner or affiliate (so #funny or a football "free kick" never becomes a streamer); a Kick name only when it's
linked. Shorts with nobody identified are dropped. Metadata only (~4 x 101 units a scan, every EVERY_H hours).
Writes trending.json: {"updated", "window_h", "shorts": [{"id", "title", "channel", "views", "vph", "dur",
"published", "en", "desc", "streamer", "logins", "kicks", "how"}]}. The remake engine (remake/run.candidates)
tries them like the market's own popping Shorts.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import market as M

TREND_FILE = "/opt/clipper/formats/trending.json"
QUERIES = tuple(q.strip() for q in os.environ.get("TREND_QUERIES", "twitch|kick streamer|streamer|stream clip").split("|")
                if q.strip())
EVERY_H = 6
WINDOW_H = M.WINDOW_H
MIN_VPH = 1500
MIN_S, MAX_S = M.MIN_LEN_S, M.MAX_LEN_S
STALE_H = 24
OUR_CHANNEL = "Peakz Recaps"
LOGIN = r"[A-Za-z0-9_]{3,25}"
# hashtags and channel words that are never a streamer
GENERIC = {"shorts", "short", "shortsviral", "shortsfeed", "shortvideo", "viral", "viralvideo", "fyp", "foryou",
           "foryoupage", "fy", "trending", "trend", "funny", "funnyvideo", "funnymoments", "memes", "meme", "comedy",
           "humor", "lol", "twitch", "twitchclips", "twitchstreamer", "twitchtv", "kick", "kickstreamer", "kickclips",
           "kickstreaming", "stream", "streamer", "streamers", "streaming", "streamclips", "livestream", "live", "clip",
           "clips", "gaming", "gamer", "gameplay", "game", "games", "youtube", "youtuber", "youtubeshorts", "tiktok",
           "explore", "explorepage", "edit", "edits", "reaction", "react", "irl", "usa", "new", "best", "highlights",
           "moments", "entertainment", "fortnite", "minecraft", "roblox", "valorant", "gta", "gta5", "cod", "warzone",
           "apex", "nba", "nfl", "football", "soccer", "basketball", "podcast", "news", "music", "rap", "prank", "fail",
           "fails", "wow", "omg", "bruh", "fun", "love", "trendingshorts", "xyzbca", "subscribe"}
CHANNEL_WORDS = {"shorts", "short", "clips", "clip", "clipz", "clipper", "clippers", "tv", "highlights", "daily",
                 "live", "vods", "vod", "moments", "fan", "fans", "official", "channel", "best", "of", "the", "yt",
                 "archive", "hub", "uncut", "plus", "extra", "edits", "recaps", "world"}


def log(msg):
    print(f"[trend] {msg}", file=sys.stderr)


def path():
    return Path(os.environ.get("CLIPPER_TRENDING", TREND_FILE))


def english(title, desc=""):
    """English like the market scan; a title made only of hashtags is judged by its description."""
    if M.is_english(title):
        return True
    t = str(title or "")
    if t.strip() and all(w.startswith("#") for w in t.split()):
        letters = [c for c in t if c.isalpha()]
        return bool(letters) and all(c.isascii() for c in letters) and (not str(desc).strip() or M.is_english(desc))
    return False


def leads(title, desc, tags, channel):
    """Who might be in a Short, best evidence first: [(kind, value)] with kind 'twitch' | 'kick' (linked or
    'twitch: name') or 'guess' (a hashtag or the clip channel's name: kept only if Twitch knows a streamer by it)."""
    text = f"{title} {desc}"
    out = [("twitch", m.lower()) for m in re.findall(r"twitch\.tv/(" + LOGIN + ")", text, re.I)]
    out += [("twitch", m.lower()) for m in re.findall(r"\btwitch\s*[:\-|]\s*@?(" + LOGIN + ")", text, re.I)]
    out += [("kick", m.lower()) for m in re.findall(r"kick\.com/([A-Za-z0-9_-]{3,25})", text, re.I)]
    out += [("kick", m.lower()) for m in re.findall(r"\bkick\s*[:\-|]\s*@?(" + LOGIN + ")", text, re.I)]
    out = [(k, v) for k, v in out if v not in {"videos", "directory", "video", "clips", "p", "search"}]
    tagtext = f"{title} {str(desc)[:300]} {' '.join('#' + t for t in tags or [])}"
    for t in re.findall(r"#(\w+)", tagtext):
        t = t.lower()
        if re.fullmatch(r"[a-z0-9_]{4,25}", t) and t not in GENERIC:
            out.append(("guess", t))
    words = [w for w in re.findall(r"[a-z0-9_]+", str(channel or "").lower()) if w not in CHANNEL_WORDS]
    if words and 4 <= len("".join(words)) <= 25:
        out.append(("guess", "".join(words)))
    seen, uniq = set(), []
    for k, v in out:
        if (k, v) not in seen:
            seen.add((k, v))
            uniq.append((k, v))
    return uniq


def twitch_users(tw, logins, cache):
    """{login: {'name', 'type'}} for the logins Twitch knows (100 per call, cached across the scan)."""
    need = [lg for lg in dict.fromkeys(logins) if lg not in cache]
    for i in range(0, len(need), 100):
        batch = need[i:i + 100]
        for lg in batch:
            cache[lg] = None
        try:
            for u in tw._get("users", {"login": batch}).get("data", []):
                cache[u["login"].lower()] = {"name": u.get("display_name") or u["login"],
                                             "type": u.get("broadcaster_type") or ""}
        except Exception as e:  # noqa: BLE001 - one bad login must not drop the batch for good
            log(f"twitch users: {e}")
    return {lg: cache[lg] for lg in logins if cache.get(lg)}


def identify(sn, tw, wl, cache):
    """(streamer name, twitch logins, kick slugs, how) for a Short's snippet, or None when nobody is identified."""
    title, desc, tags = sn.get("title", ""), sn.get("description") or "", sn.get("tags") or []
    text = f"{title} {desc} {' '.join(tags)}"
    ctx = f"{title} {' '.join(tags)} {desc[:120]}"
    others = {a for al in wl.values() for a in al}
    for name, al in wl.items():     # a watchlist streamer named in it: the market scan's own rule
        if M.mentions(text, al, others - al, context_text=ctx):
            return name, [], [], "watchlist"
    ls = leads(title, desc, tags, sn.get("channelTitle"))
    kicks = [v for k, v in ls if k == "kick"]
    named = [v for k, v in ls if k == "twitch"]
    guesses = [v for k, v in ls if k == "guess"]
    known = twitch_users(tw, named + guesses, cache) if tw is not None and (named or guesses) else {}
    logins = [lg for lg in named if lg in known]
    logins += [lg for lg in guesses if lg in known and known[lg]["type"] in ("partner", "affiliate")
               and lg not in logins]
    if not logins and not kicks:
        return None
    if logins:
        name, how = known[logins[0]]["name"], "linked" if logins[0] in named else "hashtag/channel"
    else:
        name, how = kicks[0], "kick link"
    from_wl = M.name_for(logins[0] if logins else kicks[0])
    return (from_wl or name), logins, kicks, how


def scan(key, tw=None, session=None, now=None, wl_path=None, queries=QUERIES):
    import requests
    session = session or requests
    now = now or datetime.now(timezone.utc)
    after = (now - timedelta(hours=WINDOW_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = []
    for q in queries:
        r = session.get(f"{M.API}/search", timeout=30, params={
            "part": "id", "q": q, "type": "video", "videoDuration": "short", "order": "viewCount",
            "publishedAfter": after, "maxResults": 50, "relevanceLanguage": "en", "key": key})
        r.raise_for_status()
        ids += [i["id"]["videoId"] for i in r.json().get("items", []) if i.get("id", {}).get("videoId")]
    ids = list(dict.fromkeys(ids))
    wl = M.watchlist_names(wl_path)
    popping = []
    for i in range(0, len(ids), 50):
        v = session.get(f"{M.API}/videos", timeout=30, params={
            "part": "snippet,contentDetails,statistics", "id": ",".join(ids[i:i + 50]), "key": key})
        v.raise_for_status()
        for it in v.json().get("items", []):
            sn, st = it.get("snippet", {}), it.get("statistics", {})
            dur = M._dur(it.get("contentDetails", {}).get("duration"))
            pub = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            views = int(st.get("viewCount", 0) or 0)
            vph = round(views / max((now - pub).total_seconds() / 3600, 0.5))
            if (sn.get("channelTitle") == OUR_CHANNEL or not dur or not MIN_S <= dur <= MAX_S or vph < MIN_VPH
                    or not english(sn.get("title"), sn.get("description"))):
                continue
            popping.append((it, sn, dur, pub, views, vph))
    cache, shorts = {}, []
    if tw is not None:   # every name of every Short in one Twitch call per 100
        names = [v for _, sn, *_ in popping for k, v in leads(sn.get("title", ""), sn.get("description") or "",
                                                               sn.get("tags") or [], sn.get("channelTitle"))
                 if k in ("twitch", "guess")]
        twitch_users(tw, names, cache)
    for it, sn, dur, pub, views, vph in popping:
        who = identify(sn, tw, wl, cache)
        if not who:
            continue
        name, logins, kicks, how = who
        shorts.append({"id": it["id"], "title": sn.get("title", ""), "channel": sn.get("channelTitle", ""),
                       "views": views, "vph": vph, "dur": dur, "published": pub.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "en": True, "desc": (sn.get("description") or "")[:200], "streamer": name,
                       "logins": logins, "kicks": kicks, "how": how})
    shorts.sort(key=lambda s: -s["vph"])
    return {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "window_h": WINDOW_H, "found": len(ids), "shorts": shorts}


def load(p=None, now=None, max_age_h=STALE_H):
    """trending.json if fresher than max_age_h, else None."""
    try:
        d = json.loads(Path(p or path()).read_text())
        t = datetime.fromisoformat(d["updated"].replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    now = now or datetime.now(timezone.utc)
    return d if now - t <= timedelta(hours=max_age_h) else None


def due(p=None, now=None):
    return load(p, now, EVERY_H) is None


def write(data, p=None):
    return M.write(data, p or path())
