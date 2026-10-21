"""Remake engine entry (D58): pick a popping clipper Short, rebuild it frame for frame from the streamer's own VOD,
register it as an edited clip (QC -> visual check -> Telegram -> post, like every clip).

Run (from clipper/):  python -m remake.run [--short ID] [--max N] [--dry-run]
Systemd: clipper-remake.timer (its own lock; a remake takes ~10-15 min, longer than a pipeline pass should).
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from . import align, amap, caps, look, match, render, source, style, title, vmap
from . import common as C

OUR_CHANNEL = "Peakz Recaps"
MAX_AGE_H = 36            # popping now: published in the last 36 h
MAX_DUR_S = 60            # market length (D36)
MIN_DUR_S = 8
MIN_VPH = 1500            # views/hour to count as popping
MAX_ATTEMPTS = 2
PER_DAY = int(os.environ.get("REMAKES_PER_DAY", "5"))
MIN_MAPPED = 0.8          # share of the Short's frames found in the stream, else it is not a stream remake
CAPTIONS_GOOD = 92.0      # caption match (%) that ends the search for a better caption look
MIN_AUDIO = 0.4           # share of 0.8 s audio windows heard in the stream (their music bed hides the rest)
LOCK = "/opt/clipper/remake.lock"


class Unsupported(RuntimeError):
    pass


def _ts(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)


def candidates(market_data, con, now=None, twitch_names=None):
    """Popping clipper Shorts not tried yet, best first: [{id, title, channel, views, vph, dur, published, streamer}]."""
    now = now or datetime.now(timezone.utc)
    # a 'working' row older than 2 h is a run that was killed (stop/timeout): it may be tried again
    tried = {r[0] for r in con.execute("SELECT short_id FROM remakes WHERE status IN ('done','skipped')"
                                       " OR (status='working' AND updated_at >= datetime('now','-2 hours'))"
                                       " OR attempts >= ?", (MAX_ATTEMPTS,))}
    out, seen = [], set()
    for name, d in (market_data or {}).get("streamers", {}).items():
        if twitch_names is not None and name not in twitch_names:
            continue
        for s in d.get("shorts", []):
            sid = s.get("id")
            if not sid or sid in seen or sid in tried or s.get("channel") == OUR_CHANNEL:
                continue
            if not (MIN_DUR_S <= (s.get("dur") or 0) <= MAX_DUR_S) or s.get("en") is False:
                continue
            try:
                age_h = (now - _ts(s["published"])).total_seconds() / 3600
            except (KeyError, ValueError):
                continue
            if age_h > MAX_AGE_H or (s.get("vph") or 0) < MIN_VPH:
                continue
            seen.add(sid)
            out.append({**s, "streamer": name})
    return sorted(out, key=lambda s: -(s.get("vph") or 0))


def twitch_watchlist_names(wl_path=None):
    """Watchlist streamers whose streams we can rebuild from: Twitch archives or YouTube live streams."""
    import yaml
    cfg = yaml.safe_load(Path(wl_path or source.WATCHLIST).read_text()) or {}
    return {str(e["name"]) for e in cfg.get("streamers", [])
            if e.get("platform") in ("twitch", "youtube") and not e.get("disabled")}


def done_today(con, now=None):
    now = now or datetime.now(timezone.utc)
    return con.execute("SELECT COUNT(*) FROM remakes WHERE status='done' AND date(updated_at)=?",
                       (now.strftime("%Y-%m-%d"),)).fetchone()[0]


def _status(con, s, status, **kw):
    cols = {"status": status, **kw}
    con.execute("INSERT OR IGNORE INTO remakes (short_id, streamer, channel, title, views, vph, published)"
                " VALUES (?,?,?,?,?,?,?)", (s["id"], s.get("streamer"), s.get("channel"), s.get("title"),
                                            s.get("views"), s.get("vph"), s.get("published")))
    sets = ", ".join(f"{k}=?" for k in cols) + ", updated_at=datetime('now')"
    if status == "working":
        sets += ", attempts=attempts+1"
    con.execute(f"UPDATE remakes SET {sets} WHERE short_id=?", (*cols.values(), s["id"]))
    con.commit()


def same_moment_done(con, vod_id, a, b, share=0.5):
    """A remake of the same VOD seconds is already done (another clipper's cut of the same moment)."""
    for va, vb in con.execute("SELECT vod_s, vod_e FROM remakes WHERE status='done' AND vod_id=?", (vod_id,)):
        inter = min(b, vb or 0) - max(a, va or 0)
        if inter > share * min(b - a, (vb or 0) - (va or 0)):
            return True
    return False


def register(con, s, found, am, vm, cp, mp4, our_title):
    """Our remake becomes an edited clip (QC, visual check and Telegram take it from there)."""
    login = found["login"]
    yt = source.is_yt(found["vod_id"])
    dur = vm["nfr"] / vm["fps"]
    secs = found["sections"]
    seg0 = am["segments"][0]
    vod_s = secs[seg0["sec"]]["vod_s"] + seg0["off"]
    con.execute("INSERT OR IGNORE INTO creators (name, main_platform, channel_url) VALUES (?, ?, ?)",
                (login, "youtube" if yt else "twitch",
                 f"https://www.youtube.com/{login}" if yt else f"https://twitch.tv/{login}"))
    creator_id = con.execute("SELECT id FROM creators WHERE name=?", (login,)).fetchone()[0]
    url = source.vod_url(found["vod_id"]) + (f"&t={int(vod_s)}s" if yt else f"?t={int(vod_s)}s")
    con.execute("INSERT OR IGNORE INTO sources (creator_id, url, title, source_views) VALUES (?,?,?,?)",
                (creator_id, url, s.get("title"), s.get("views")))
    source_id = con.execute("SELECT id FROM sources WHERE url=?", (url,)).fetchone()[0]
    first = " ".join(w["w"] for w in cp["events"][0]["words"]) if cp["events"] else s.get("title")
    # context_line becomes the public YouTube description: never name the clipper or their title there.
    # Telegram shows the source Short from the remakes table (approvals.same_moment_of).
    cur = con.execute(
        "INSERT INTO clips (source_id, start_s, end_s, picked_by, state, state_changed_at, file_path, title, hook_text,"
        " context_line, music_risk, caption_style, model_score) VALUES (?,?,?, 'ai', 'edited', datetime('now'), ?,?,?,?,0,"
        " 'remake', ?)",
        (source_id, vod_s, vod_s + dur, str(mp4), our_title, first, None,
         min(1.0, (s.get("vph") or 0) / 50000)))
    clip_id = cur.lastrowid
    con.execute("INSERT OR IGNORE INTO radar_candidates (clip_id, creator, title, url, video_id, vod_offset, duration_s,"
                " view_count, clip_created_at, views_per_hour, status, clips_id, source)"
                " VALUES (?,?,?,?,?,?,?,?,?,?, 'edited', ?, 'remake')",
                (f"remake:{s['id']}", login, s.get("title"), f"https://www.youtube.com/shorts/{s['id']}",
                 str(found["vod_id"]).removeprefix("yt:"), int(vod_s), dur, s.get("views") or 0, s.get("published") or "",
                 s.get("vph") or 0, clip_id))
    con.commit()
    return clip_id


def _stage(work, name, fn):
    """Cached stage result (work/<name>.json): a re-run after a fix only redoes what was deleted."""
    f = work / f"{name}.json"
    if f.exists():
        return C.load_json(f)
    out = fn()
    C.save_json(f, out)
    return out


def build_best(short_path, work, vm, am, lk, cp, sp, mark, vision_style=None, vision=caps.anthropic_vision):
    """Render once without captions, then burn caption candidates (their measured look, the next-best fonts, the
    study look) and keep the one that matches their Short best (match.py). {'path', 'match', 'name', 'tried'}."""
    OW, OH, fps, nfr = vm["out_w"], vm["out_h"], vm["fps"], vm["nfr"]
    base = work / "base.mp4"
    if not base.exists():
        render.render({"vmap": vm, "amap": am, "look": lk, "ass": None}, base, work, crf=10)
    # their caption states, frame-exact from the pixels (a new word / caption / no caption), one OCR per state
    y0 = float(np.median([e["y"] for e in cp["events"]])) if cp["events"] else 0.5
    pe = _stage(work, "pixcaps", lambda: {"events": style.pixel_events(short_path, base, fps, nfr, (OW, OH), y0,
                                                                         vision)})
    evs = pe["events"] if len(pe["events"]) >= 0.5 * len(cp["events"]) else cp["events"]
    st = _stage(work, "style", lambda: style.build(short_path, base, evs, fps, OW, OH, vision_style))
    if st.get("colours"):     # word colours read from their pixels beat the OCR's guess
        evs = [{**e, "words": [{**w, "c": c} for w, c in zip(e["words"], cols)]}
               for e, cols in zip(evs, st["colours"])]
    pos = st.get("pos") or []
    sevs = [{**e, "y": (pos[k][1] if k < len(pos) and pos[k] else st.get("y") or e.get("y", 0.5))}
            for k, e in enumerate(evs)]           # caption rows to score: where each of their captions is

    def score(k, name, s_):
        ass = work / f"cap_{k}.ass"
        if s_ is not None:
            caps.write_ass_style(evs, ass, OW, OH, s_, mark=mark, dur=sp["dur"])
        else:
            caps.write_ass(evs, ass, OW, OH, mark=mark, dur=sp["dur"])
        cand = match.burn(base, ass, work / f"cand_{k}.mp4")
        m = match.score(short_path, cand, sevs, fps, nfr, OW, OH, line_h=st.get("line_h"), base=base)
        m.pop("per_frame", None)
        C.log(f"captions '{name}': {match.summary(m)}")
        return {"path": cand, "match": m, "name": name}

    first = [(f"measured: {st['family']}", st)] if st.get("ok") else []
    rest = [(f"next font: {alt['family']}", alt) for alt in (style.with_font(st, i) for i in range(2)) if alt] \
        if st.get("ok") else []
    rest.append(("study look", None))
    tried, best = [], None
    for k, (name, s_) in enumerate(first + rest):
        if best and best["match"]["captions"] >= CAPTIONS_GOOD:
            break
        r = score(k, name, s_)
        tried.append({"name": name, **{x: r["match"][x] for x in ("picture", "captions", "overall")}})
        if best is None or r["match"]["captions"] > best["match"]["captions"]:
            best = r
    best["tried"] = tried
    return best


def remake_one(con, s, out_dir, tw=None, vision=caps.anthropic_vision, ask=title.anthropic_ask, keep=False,
               vision_style=None):
    """Rebuild one clipper Short. Returns our clip id; raises Unsupported / other errors (status recorded)."""
    sid = s["id"]
    work = C.workdir(sid)
    _status(con, s, "working", last_error=None)
    try:
        text = f"{s.get('title', '')} {s.get('desc', '')}"
        logins = source.twitch_logins([s.get("streamer", "")], text)
        handles = source.youtube_handles([s.get("streamer", "")], text)
        plans = [] if (work / "found.json").exists() else \
            source.plans_for({"id": sid, "published": s["published"]}, con, tw, logins, handles)
        if not plans and not (work / "found.json").exists():
            raise source.NotFound(f"no stream VOD of {', '.join(logins + handles) or s.get('streamer')} around it")
        short_path = source.download_short(sid, work)
        found = _stage(work, "found", lambda: source.find({"id": sid, "published": s["published"]}, work, con=con,
                                                            tw=tw, logins=logins, plans=plans, handles=handles))
        am = _stage(work, "amap", lambda: amap.build(short_path, [x["file"] for x in found["sections"]]))
        if am["matched_share"] < MIN_AUDIO:
            raise Unsupported(f"only {am['matched_share']:.0%} of the audio is the stream")
        vm = _stage(work, "vmap", lambda: vmap.build(short_path, found["sections"], am))
        if vm["mapped"] < MIN_MAPPED * vm["nfr"]:
            raise Unsupported(f"only {vm['mapped']}/{vm['nfr']} frames found in the stream")
        if any(sh["layout"] == "other" for sh in vm["shots"]):
            raise Unsupported("layout not supported yet (stack / overlay)")
        vm = _stage(work, "vmap_aligned", lambda: align.refine(short_path, vm))   # their framing, frame by frame
        secs = found["sections"]
        a = min(secs[g["sec"]]["vod_s"] + g["t0"] + g["off"] for g in am["segments"])
        b = max(secs[g["sec"]]["vod_s"] + g["t1"] + g["off"] for g in am["segments"])
        if same_moment_done(con, found["vod_id"], a, b):
            raise Unsupported("same moment already remade from another clipper")
        _status(con, s, "working", vod_id=found["vod_id"], vod_s=a, vod_e=b)
        lk = _stage(work, "look", lambda: look.build(short_path, vm))
        sp = C.probe(short_path)
        mark = os.environ.get("CLIPPER_WATERMARK", "@Peakz.Recaps").strip() or None
        cp = _stage(work, "caps", lambda: caps.build(short_path, sp["dur"], sp["h"] / sp["w"], work / "captions.ass",
                                                     vm["out_w"], vm["out_h"], vision, mark=mark,
                                                     bands=lk.get("overlay", {}).get("bands"), fps=vm["fps"]))
        out = Path(out_dir) / f"remake_{sid}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        best = build_best(short_path, work, vm, am, lk, cp, sp, mark, vision_style, vision)
        shutil.move(str(best["path"]), out)
        try:   # Lucas reviews every remake next to the original (2026-10-21)
            render.side_by_side(short_path, out, out.with_suffix(".sbs.mp4"))
        except Exception as e:  # noqa: BLE001 - the remake itself is fine without it
            C.log(f"side by side failed: {e}")
        out.with_suffix(".json").write_text(json.dumps({"our_captions": True, "mode": "remake", "cut": 0.0,
                                                        "moving": False, "match": best["match"],
                                                        "caption_look": best["name"]}))
        said = " / ".join(" ".join(w["w"] for w in e["words"]) for e in cp["events"])[:400]
        names = sorted(twitch_watchlist_names() | {s.get("streamer", "")})
        ours = title.make(s.get("title", ""), found.get("owner") or found["login"], said, ask, names=names)
        C.save_json(work / "spec.json", {"short": s, "found": {k: v for k, v in found.items() if k != "hits"},
                                         "amap": am, "vmap": {k: v for k, v in vm.items() if k != "frames"},
                                         "look": {k: v for k, v in lk.items() if k != "overlay"},
                                         "overlay_frames": len(lk.get("overlay", {}).get("alpha", {})),
                                         "captions": cp["events"], "title": ours, "match": best["match"],
                                         "caption_look": best["name"], "tried": best["tried"]})
        clip_id = register(con, s, found, am, vm, cp, out, ours)
        _status(con, s, "done", clip_id=clip_id)
        C.log(f"{sid}: done -> clip {clip_id} '{ours}'")
        return clip_id
    except source.BotCheck as e:   # not this Short's fault: back in the queue, attempt not counted
        _status(con, s, "picked", last_error=str(e)[:500])
        con.execute("UPDATE remakes SET attempts=MAX(0, attempts-1) WHERE short_id=?", (sid,))
        con.commit()
        raise
    except source.NotFound as e:
        _status(con, s, "skipped", last_error=f"source: {e}"[:500])
        raise
    except Unsupported as e:
        _status(con, s, "skipped", last_error=str(e)[:500])
        raise
    except Exception as e:
        _status(con, s, "failed", last_error=f"{type(e).__name__}: {e}"[:500])
        raise
    finally:
        if not keep:   # media go, the stage maps stay (a retry re-downloads only what it needs)
            for p in work.iterdir():
                if p.suffix in (".mp4", ".m4a", ".wav", ".webm", ".part", ".ts"):
                    p.unlink(missing_ok=True)
            for name in ("found", "amap", "vmap", "vmap_aligned"):   # they point at the deleted media
                (work / f"{name}.json").unlink(missing_ok=True)


def run(con, out_dir, max_n=1, short=None, tw=None, market_data=None, now=None, dry=False):
    """Remake up to `max_n` popping Shorts (or the one named). Returns {'done': [...], 'skipped': {...}, 'failed': {...}}."""
    res = {"done": [], "skipped": {}, "failed": {}}
    if short:
        picks = [short]
    else:
        if done_today(con, now) >= PER_DAY:
            return res
        if market_data is None:
            from radar import market
            market_data = market.load()
        picks = candidates(market_data, con, now, twitch_watchlist_names())
    if dry:
        for p in picks[:10]:
            print(f"{p['vph']:>8}/h {p['dur']:>3}s {p['streamer']:<14} {p['channel'][:22]:<22} {p['title'][:60]}")
        return res
    if tw is None:
        try:
            from radar.twitch import Twitch
            tw = Twitch()
        except Exception as e:  # no Twitch credentials: only moment-match hints can locate VODs
            C.log(f"twitch client unavailable: {e}")
    for s in picks:
        if len(res["done"]) >= max_n:
            break
        try:
            res["done"].append(remake_one(con, s, out_dir, tw=tw))
        except source.BotCheck as e:   # every download would hit it now: stop, the timer tries again later
            res["failed"][s["id"]] = str(e)
            break
        except (Unsupported, source.NotFound) as e:
            res["skipped"][s["id"]] = str(e)
        except Exception as e:  # one bad Short must not stop the next
            traceback.print_exc()
            res["failed"][s["id"]] = f"{type(e).__name__}: {e}"
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--short", help="YouTube id of a clipper Short to remake (else: the most popping one)")
    ap.add_argument("--streamer", default="", help="watchlist name for --short")
    ap.add_argument("--published", default=None, help="ISO time --short was published (VOD search window)")
    ap.add_argument("--title", default="")
    ap.add_argument("--max", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep", action="store_true", help="keep downloaded media in the work dir")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "editor"))   # llm.py: API cost tracking
    con = sqlite3.connect(os.environ.get("CLIPPER_DB", "/opt/clipper/db/clip.db"), timeout=60)
    con.row_factory = sqlite3.Row
    out_dir = os.environ.get("CLIPPER_CLIPS", "/opt/clipper/clips")
    short = None
    if a.short:
        short = {"id": a.short, "streamer": a.streamer, "title": a.title, "channel": "",
                 "published": a.published or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    import fcntl
    with open(os.environ.get("CLIPPER_REMAKE_LOCK", LOCK), "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("another remake run holds the lock")
            return
        if short and a.keep:
            from radar.twitch import Twitch
            print(remake_one(con, short, out_dir, tw=Twitch(), keep=True))
            return
        print(json.dumps(run(con, out_dir, a.max, short, dry=a.dry_run)))


if __name__ == "__main__":
    main()
