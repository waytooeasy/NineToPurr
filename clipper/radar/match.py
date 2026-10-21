"""Same moments as the top clippers (D54, Lucas 2026-10-20: "always follow the clippers, same clips").

The market scan (radar/market.py) knows which Shorts about each streamer are popping right now; each is a
moment a top clipper cut from the stream. This finds the streamer's own clip of that moment on Twitch/Kick
(their footage, never the clipper's video): Claude Haiku compares the popping Shorts (title, description,
length, when posted) with the streamer's most-viewed clips of the last 7 days (title, when made, views,
length). Matches go to `moment_matches` (migration 013); Radar posts those moments first (ranked by the
clipper Short's views/hour), the Writer paraphrases that clipper's title with synonyms (never identical)
and cuts to that Short's length. Runs once per market scan/refresh, for the streamers Radar posts.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

MODEL = "claude-haiku-5-5"
TOP_STREAMERS = 8
MAX_CLIPS = 40
CLIP_DAYS = 4           # Shorts are <= 48 h old and clippers post within a day or two of the moment
POOL_VIEWS, POOL_FRESH = 25, 15
MAX_SHORTS = 10
MIN_CONF = 0.8          # only "same" passes; "related" (same stream or guest, maybe another moment) doesn't
VERDICT = {"same": 0.9, "related": 0.6}   # a verdict, not a number: the model's 0-1 scores were not calibrated
KEEP_H = 72
DB_TS = "%Y-%m-%d %H:%M:%S"
PROMPT = """You match YouTube Shorts made by clip channels to {streamer}'s own stream clips of the SAME moment.

SHORTS (popping right now; other channels cut them from {streamer}'s stream):
{shorts}

STREAM CLIPS ({streamer}'s own Twitch/Kick clips of the last 4 days, most viewed first):
{clips}

For each Short, name the stream clip of the same moment and how it matches, or null. Stream clip titles are
typed fast by viewers, often a word or two, with slang.
- "same": both titles point at the same event through a shared distinctive detail (the same action, quote,
  reaction, person or thing). E.g. Short "Kai Says He Will NEVER Eat Sushi Again" ~ clip "no more sushi";
  Short "Kai Can't Stop Praising His Mom's Cooking" ~ clip "kai glazing moms food".
- "related": the same stream, guest or topic, but the titles may be different moments. E.g. Short "Kai Votes
  For X" ~ clip "KAI VOTES FOR Y" (another vote); Short "Guest Talks Food With Kai" ~ clip "guest hits 5 shots".
The clip must be made before the Short was posted ("?" = unknown time: judge by the titles); clippers post
within hours or a day or two of the moment. Titles that say nothing ("lol", "W", "om", emotes, the stream
title) never match.
Answer with JSON only: [{{"short": "S0", "clip": "C3" or null, "match": "same" | "related"}}]"""


LAYOUT_PROMPT = (
    "This is the thumbnail of a YouTube Short cut from a livestream. Which layout does it use? \"full\": the video "
    "fills the whole vertical frame; \"fit\": a wider video panel across the middle with blurred or plain bars "
    "above and below; \"stack\": two stacked panels (e.g. a face cam over the game or screen). Answer with JSON "
    "only: {\"layout\": \"full\" | \"fit\" | \"stack\"}"
)


def log(msg):
    print(f"[match] {msg}", file=sys.stderr)


def _ts(s):
    """ISO ('2026-10-20T13:00:00Z') or DB ('2026-10-20 13:00:00', UTC) -> aware datetime."""
    s = str(s).strip().replace(" ", "T").replace("Z", "+00:00")
    t = datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def anthropic_ask(prompt):
    import anthropic  # lazy
    msg = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=900, thinking={"type": "disabled"},
                                                messages=[{"role": "user", "content": prompt}])
    try:
        import llm  # editor/ is on sys.path in the pipeline: cost goes to llm_usage
        llm.log_usage("anthropic", MODEL, llm._usage_dict(msg.usage))
    except Exception:  # noqa: BLE001 - cost logging must never stop matching
        pass
    return "".join(b.text for b in msg.content if b.type == "text")


def parse(text):
    m = re.search(r"\[.*\]", text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else []
    except ValueError:
        return []
    return [x for x in d if isinstance(x, dict)] if isinstance(d, list) else []


def _short_line(i, s):
    desc = " ".join(str(s.get("desc") or "").split())[:160]
    return (f"S{i}: \"{s.get('title', '')}\"" + (f" | desc: {desc}" if desc else "")
            + f" | {s.get('dur') or '?'} s | posted {s.get('published') or '?'}")


def _clip_line(j, c):
    return (f"C{j}: \"{c.get('title', '')}\" | made {str(c.get('created_at', ''))[:16]}"
            f" | {c.get('view_count', 0)} views | {float(c.get('duration_s') or 0):.0f} s")


def _index(v, letter):
    return int(str(v).strip().upper().lstrip(letter))


def pool(clips, n_views=POOL_VIEWS, n_fresh=POOL_FRESH):
    """The clips the model sees: the most viewed plus the fastest rising (views/hour) not among them, so
    yesterday's moment is not hidden by last week's big clips (VM dry run 2026-10-20: Jynxzi's top 40 by
    views were mostly from one stream 5 days before his popping Shorts). Most viewed first."""
    by_views = sorted(clips, key=lambda c: -int(c.get("view_count") or 0))
    out = by_views[:n_views]
    seen = {c["clip_id"] for c in out}
    for c in sorted(clips, key=lambda c: -float(c.get("views_per_hour") or 0)):
        if len(out) >= n_views + n_fresh:
            break
        if c["clip_id"] not in seen:
            seen.add(c["clip_id"])
            out.append(c)
    return sorted(out, key=lambda c: -int(c.get("view_count") or 0))


def match_streamer(name, shorts, clips, ask=anthropic_ask, min_conf=MIN_CONF):
    """[(short, clip, confidence)] for the popping Shorts that show one of the stream clips."""
    shorts, clips = list(shorts)[:MAX_SHORTS], list(clips)[:MAX_CLIPS]
    if not shorts or not clips:
        return []
    prompt = PROMPT.format(streamer=name, shorts="\n".join(_short_line(i, s) for i, s in enumerate(shorts)),
                           clips="\n".join(_clip_line(j, c) for j, c in enumerate(clips)))
    out = []
    for x in parse(ask(prompt)):
        if x.get("clip") is None:
            continue
        try:
            si, cj = _index(x.get("short"), "S"), _index(x["clip"], "C")
            conf = VERDICT.get(str(x.get("match", "")).strip().lower())
            conf = float(x.get("confidence") or 0) if conf is None else conf
        except (TypeError, ValueError):
            continue
        if not (0 <= si < len(shorts) and 0 <= cj < len(clips)) or conf < min_conf:
            continue
        s, c = shorts[si], clips[cj]
        try:
            if s.get("published") and _ts(c["created_at"]) > _ts(s["published"]):
                continue                               # a clip made after the Short can't be its source
        except (KeyError, ValueError):
            continue
        out.append((s, c, conf))
    return out


def thumb_layout(short_id, look=None, fetch=None):
    """The layout of a Short from its thumbnail (public image, never the video): full / fit / stack, or None."""
    try:
        if look is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                return None
            import visual_qa  # editor/ is on sys.path in the pipeline
            look = lambda b: visual_qa.anthropic_vision([b], LAYOUT_PROMPT)  # noqa: E731
        if fetch is None:
            import urllib.request
            fetch = lambda sid: urllib.request.urlopen(f"https://i.ytimg.com/vi/{sid}/oar2.jpg", timeout=15).read()  # noqa: E731
        img = fetch(short_id)
        m = re.search(r"\{.*\}", look(img) or "", re.S)
        v = json.loads(m.group(0)).get("layout") if m else None
        return v if v in ("full", "fit", "stack") else None
    except Exception:  # noqa: BLE001 - our own layout choice is the fallback
        return None


def due(con, since):
    """True when no match run happened since `since` (aware datetime of the newest market data)."""
    last = con.execute("SELECT MAX(ran_at) FROM match_runs").fetchone()[0]
    return not last or _ts(last) < since


def store(con, name, matches, now, layouts=None):
    with con:
        for s, c, conf in matches:
            con.execute("INSERT OR REPLACE INTO moment_matches (short_id, streamer, clip_id, confidence, short_title,"
                        " short_vph, short_dur, candidate_json, matched_at, layout) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (s["id"], name, c["clip_id"], conf, s.get("title"), s.get("vph"), s.get("dur"),
                         json.dumps(c, ensure_ascii=False), now.strftime(DB_TS), (layouts or {}).get(s["id"])))


def run(con, market, streamers, clips_for, now=None, ask=anthropic_ask, layout_of=thumb_layout):
    """Match the popping English Shorts of `streamers` ([name]) to their own clips (`clips_for(name)` ->
    Radar candidates). One failing streamer is logged and skipped."""
    now = now or datetime.now(timezone.utc)
    found = tried = 0
    for name in streamers:
        shorts = [s for s in ((market or {}).get("streamers", {}).get(name) or {}).get("shorts", []) if s.get("en")]
        if not shorts:
            continue
        try:
            clips = pool(clips_for(name))
            ms = match_streamer(name, shorts, clips, ask)
        except Exception as e:  # noqa: BLE001 - one streamer must not stop the rest
            log(f"{name}: {type(e).__name__}: {e}")
            continue
        tried += 1
        store(con, name, ms, now, {s["id"]: layout_of(s["id"]) for s, _, _ in ms})
        found += len(ms)
    with con:
        con.execute("INSERT INTO match_runs (ran_at) VALUES (?)", (now.strftime(DB_TS),))
        con.execute("DELETE FROM moment_matches WHERE matched_at < ?",
                    ((now - timedelta(hours=KEEP_H)).strftime(DB_TS),))
    return {"streamers": tried, "matches": found}


def candidates(con, now=None, keep_h=KEEP_H):
    """Radar candidates of the matched moments, each with `match` = {short_id, title, dur, vph} of the most
    popping clipper Short that shows it (one entry per stream clip)."""
    now = now or datetime.now(timezone.utc)
    rows = con.execute("SELECT short_id, short_title, short_vph, short_dur, candidate_json, layout FROM moment_matches"
                       " WHERE matched_at >= ? ORDER BY short_vph DESC",
                       ((now - timedelta(hours=keep_h)).strftime(DB_TS),)).fetchall()
    out = {}
    for sid, title, vph, dur, cj, lay in rows:
        c = json.loads(cj)
        if c["clip_id"] not in out:
            c["match"] = {"short_id": sid, "title": title, "dur": dur, "vph": float(vph or 0), "layout": lay}
            out[c["clip_id"]] = c
    return list(out.values())


def fill_layouts(con, layout_of=thumb_layout, limit=5):
    """Classify matched Shorts that have no layout yet (matched before migration 014, or a failed look); a look
    that fails twice is stored as 'unknown' so it isn't retried every pass. Returns how many were filled."""
    try:
        rows = con.execute("SELECT short_id, layout FROM moment_matches WHERE layout IS NULL OR layout = 'retry'"
                           " LIMIT ?", (limit,)).fetchall()
    except Exception:  # noqa: BLE001 - table/column missing on an old DB
        return 0
    n = 0
    with con:
        for sid, prev in rows:
            lay = layout_of(sid) or ("unknown" if prev == "retry" else "retry")
            con.execute("UPDATE moment_matches SET layout=? WHERE short_id=?", (lay, sid))
            n += lay in ("full", "fit", "stack")
    return n


def nearby_layout(con, clip_id, window_s=600):
    """Layout of the most popping matched clipper Short whose clip is from the same stream within `window_s`
    of this clip: the clipper framed that scene (Ron's fry clip sits 32 s from the matched 'Jason asks Ron
    out' clip, and the clipper's Short shows the fry too)."""
    try:
        r = con.execute("SELECT video_id, vod_offset FROM radar_candidates WHERE clip_id=?", (clip_id,)).fetchone()
        rows = con.execute("SELECT candidate_json, layout, short_vph FROM moment_matches"
                           " WHERE layout IN ('full', 'fit', 'stack') ORDER BY short_vph DESC").fetchall()
    except Exception:  # noqa: BLE001
        return None
    if not r or not r[0] or r[1] is None:
        return None
    for cj, lay, _ in rows:
        c = json.loads(cj)
        if str(c.get("video_id")) == str(r[0]) and c.get("vod_offset") is not None \
                and abs(float(c["vod_offset"]) - float(r[1])) <= window_s:
            return lay
    return None


def for_clip(con, clip_id):
    """The most popping clipper Short this Radar clip matched: {title, dur, vph, layout}, or None."""
    try:
        r = con.execute("SELECT short_title, short_dur, short_vph, layout FROM moment_matches WHERE clip_id = ?"
                        " ORDER BY short_vph DESC LIMIT 1", (clip_id,)).fetchone()
    except Exception:  # noqa: BLE001 - table missing on an old DB
        return None
    return {"title": r[0], "dur": r[1], "vph": r[2], "layout": r[3] if r[3] in ("full", "fit", "stack") else None} \
        if r else None
