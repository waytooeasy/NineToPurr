"""Market hashtags on every upload (Lucas 2026-10-19: "find what hashtags are popping and use em").

Reads $CLIPPER_HASHTAGS (default /opt/clipper/formats/hashtags.json), written daily by the Trend Scout
(analyst/hashtag_scout.py) from the top clip channels' Shorts, and applies it the way they do:
- title: the streamer's tag at the end when most top Shorts carry one ("... 😭 #ishowspeed"), unless the
  Writer already put it there; the title stays <= 100 characters
- description: the story line, then the streamer's tag + today's popping generic tags (+ #Shorts)
- tags: streamer name + the market's plain keywords
Only the clip's own streamer is ever tagged (other streamers' tags would be misleading metadata).
A Kick clip gets #kick instead of #twitch. No file yet -> today's research default (NexxoRecaps:
streamer tag in the title, #shorts).
"""
import json
import os
import re
from pathlib import Path

import yaml

HASHTAGS_FILE = "/opt/clipper/formats/hashtags.json"
WATCHLIST = Path(__file__).resolve().parents[1] / "radar" / "config" / "watchlist.yaml"
DEFAULT = {"title_share": 1.0, "generic": ["#shorts"], "streamers": {}, "keywords": []}
TITLE_MAX = 100
TAGS_MAX_CHARS = 450          # YouTube allows 500 for all tags together
TAG = re.compile(r"#(\w+)", re.UNICODE)


def flat(s):
    return re.sub(r"[\W_]+", "", str(s or "").lower())


def load(path=None):
    """Today's market hashtags; missing or broken file -> DEFAULT."""
    p = Path(path or os.environ.get("CLIPPER_HASHTAGS", HASHTAGS_FILE))
    try:
        d = json.loads(p.read_text())
        return {**DEFAULT, **{k: d[k] for k in DEFAULT if k in d}}
    except (OSError, ValueError, TypeError):
        return dict(DEFAULT)


def _names(watchlist=None):
    try:
        cfg = yaml.safe_load(Path(watchlist or WATCHLIST).read_text())
        return {str(e["id"]).lower().lstrip("@"): str(e["name"]) for e in cfg.get("streamers", [])}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def streamer_for(con, clip_id, watchlist=None):
    """{"name", "login", "platform"} of the clip's streamer, or None."""
    row = con.execute("SELECT cr.name, cr.main_platform FROM clips c JOIN sources s ON s.id = c.source_id"
                      " JOIN creators cr ON cr.id = s.creator_id WHERE c.id = ?", (clip_id,)).fetchone()
    if not row or not row[0]:
        return None
    login = str(row[0])
    return {"name": _names(watchlist).get(login.lower(), login), "login": login,
            "platform": (row[1] or "twitch").lower()}


def streamer_tag(streamer, market):
    """The market's tag for this streamer (e.g. #ishowspeed), else #<name without spaces>."""
    by_flat = {flat(k): v for k, v in (market.get("streamers") or {}).items()}
    return (market.get("streamers") or {}).get(streamer["name"]) or by_flat.get(flat(streamer["name"])) \
        or f"#{flat(streamer['name']) or flat(streamer['login'])}"


def _uniq(tags):
    seen, out = set(), []
    for t in tags:
        k = flat(t)
        if k and k not in seen:
            seen.add(k)
            out.append(t)
    return out


def apply(snippet, context_line, streamer, market):
    """Hashtags on title/description/tags of a videos.insert snippet (returns a new snippet)."""
    sn = dict(snippet)
    own = streamer_tag(streamer, market) if streamer else None
    title = sn["title"]
    if own and market.get("title_share", 0) >= 0.5 and flat(own) not in {flat(t) for t in TAG.findall(title)}:
        if len(title) + 1 + len(own) <= TITLE_MAX:
            title = f"{title} {own}"
    sn["title"] = title
    generic = list(market.get("generic") or [])
    if streamer and streamer["platform"] == "kick":
        generic = [g for g in generic if flat(g) != "twitch"] + ["#kick"]
    line = _uniq(([own] if own else []) + generic + ["#Shorts"])
    sn["description"] = "\n\n".join([p for p in [(context_line or "").strip(), " ".join(line)] if p])
    kw = ([streamer["name"]] if streamer else []) + list(sn.get("tags") or []) + list(market.get("keywords") or [])
    tags, size = [], 0
    for t in _uniq(kw):
        if size + len(t) + 1 > TAGS_MAX_CHARS:
            break
        tags.append(t)
        size += len(t) + 1
    sn["tags"] = tags
    return sn
