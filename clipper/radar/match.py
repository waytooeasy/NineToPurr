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
import re
import sys
from datetime import datetime, timedelta, timezone

MODEL = "claude-haiku-5-5"
TOP_STREAMERS = 8
MAX_CLIPS = 40
MAX_SHORTS = 10
MIN_CONF = 0.7
KEEP_H = 72
DB_TS = "%Y-%m-%d %H:%M:%S"
PROMPT = """You match YouTube Shorts made by clip channels to {streamer}'s own stream clips of the SAME moment.

SHORTS (popping right now; other channels cut them from {streamer}'s stream):
{shorts}

STREAM CLIPS ({streamer}'s own Twitch/Kick clips of the last 7 days, most viewed first):
{clips}

For each Short, name the stream clip that shows the same moment, or null when none clearly does. Same moment =
the same event (same people, same action, same quote or reaction), told by both titles; the clip must be made
before the Short was posted. A clip whose title says nothing about what happens in it (the stream title,
"lol", emotes) is not a match. Don't guess: null is better than a wrong clip.
Answer with JSON only: [{{"short": "S0", "clip": "C3" or null, "confidence": 0.0-1.0}}]"""


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
            conf = float(x.get("confidence") or 0)
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


def due(con, since):
    """True when no match run happened since `since` (aware datetime of the newest market data)."""
    last = con.execute("SELECT MAX(ran_at) FROM match_runs").fetchone()[0]
    return not last or _ts(last) < since


def store(con, name, matches, now):
    with con:
        for s, c, conf in matches:
            con.execute("INSERT OR REPLACE INTO moment_matches (short_id, streamer, clip_id, confidence, short_title,"
                        " short_vph, short_dur, candidate_json, matched_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (s["id"], name, c["clip_id"], conf, s.get("title"), s.get("vph"), s.get("dur"),
                         json.dumps(c, ensure_ascii=False), now.strftime(DB_TS)))


def run(con, market, streamers, clips_for, now=None, ask=anthropic_ask):
    """Match the popping English Shorts of `streamers` ([name]) to their own clips (`clips_for(name)` ->
    Radar candidates). One failing streamer is logged and skipped."""
    now = now or datetime.now(timezone.utc)
    found = tried = 0
    for name in streamers:
        shorts = [s for s in ((market or {}).get("streamers", {}).get(name) or {}).get("shorts", []) if s.get("en")]
        if not shorts:
            continue
        try:
            clips = sorted(clips_for(name), key=lambda c: -int(c.get("view_count") or 0))
            ms = match_streamer(name, shorts, clips, ask)
        except Exception as e:  # noqa: BLE001 - one streamer must not stop the rest
            log(f"{name}: {type(e).__name__}: {e}")
            continue
        tried += 1
        store(con, name, ms, now)
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
    rows = con.execute("SELECT short_id, short_title, short_vph, short_dur, candidate_json FROM moment_matches"
                       " WHERE matched_at >= ? ORDER BY short_vph DESC",
                       ((now - timedelta(hours=keep_h)).strftime(DB_TS),)).fetchall()
    out = {}
    for sid, title, vph, dur, cj in rows:
        c = json.loads(cj)
        if c["clip_id"] not in out:
            c["match"] = {"short_id": sid, "title": title, "dur": dur, "vph": float(vph or 0)}
            out[c["clip_id"]] = c
    return list(out.values())


def for_clip(con, clip_id):
    """The most popping clipper Short this Radar clip matched: {title, dur, vph}, or None."""
    try:
        r = con.execute("SELECT short_title, short_dur, short_vph FROM moment_matches WHERE clip_id = ?"
                        " ORDER BY short_vph DESC LIMIT 1", (clip_id,)).fetchone()
    except Exception:  # noqa: BLE001 - table missing on an old DB
        return None
    return {"title": r[0], "dur": r[1], "vph": r[2]} if r else None
