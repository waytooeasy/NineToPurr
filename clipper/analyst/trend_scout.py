"""Trend Scout (D29, D30, D32, D33): daily competitor-Shorts format research, metadata only.

    python clipper/analyst/trend_scout.py --library clipper/formats/library.md --report report.md

Writes next to --library: creators_ranking.json (daily, Radar reads it), creator_weights.json and
hashtags.json (hashtags the top Shorts use, for the publisher; analyst/hashtag_scout.py).
Never downloads or stores competitor videos. Every source degrades gracefully: no YOUTUBE_API_KEY
-> RSS only; no Twitch keys -> Shorts-only ranking; no ANTHROPIC_API_KEY -> stats-only report and
library.md untouched.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))  # radar.twitch

import scout_data as data  # noqa: E402
import scout_resolve as resolve  # noqa: E402
import scout_stats as stats  # noqa: E402
import hashtag_scout  # noqa: E402
import style_scout  # noqa: E402

MODEL = "claude-sonnet-5-5"
REPORT_MAX_LINES = 40
WATCHLIST_SIZE = 50
CREATORS_YAML = HERE.parent / "radar" / "config" / "creators.yaml"

SYSTEM = (
    "You are the Trend Scout for a multi-streamer YouTube Shorts clip channel. From the stats JSON "
    "write (1) `report`: markdown, at most 40 lines: what's popping, exactly 5 hook templates, best "
    "post times (UTC and America/Asuncion), streamers to add. (2) `library`: the updated format "
    "library markdown the Editor copies from (keep what still works, fold in new findings, short). "
    "Metadata only: never suggest downloading or re-uploading competitor videos. "
    'Reply with JSON only: {"report": "...", "library": "..."}.')


def load_yaml(path):
    return yaml.safe_load(Path(path).read_text()) or {}


def creator_logins(path=CREATORS_YAML):
    out = []
    for c in load_yaml(path).get("creators", []):
        login = c if isinstance(c, str) else c.get("twitch")
        if login:
            out.append(login)
    return out


def twitch_clip_velocity(twitch, logins, now):
    """Watchlist = top EN streams by viewers + creators.yaml. Returns {streamer: clips/hour sum}."""
    names = {}
    try:
        for s in twitch._get("streams", {"first": WATCHLIST_SIZE, "language": "en"}).get("data", []):
            names[s["user_id"]] = s["user_name"]
    except Exception as ex:  # noqa: BLE001
        data.log(f"twitch watchlist failed: {type(ex).__name__}")
    for login in logins:
        try:
            names.setdefault(twitch.broadcaster_id(login), login)
        except Exception as ex:  # noqa: BLE001
            data.log(f"twitch lookup failed for {login}: {type(ex).__name__}")
    vel = {}
    for bid, name in names.items():
        try:
            clips = twitch.get_clips(bid, now - timedelta(hours=24), now, max_clips=100)
        except Exception as ex:  # noqa: BLE001
            data.log(f"twitch clips failed for {name}: {type(ex).__name__}")
            continue
        if clips:
            vel[name] = stats.clip_velocity(clips, now)
    return vel


def canonical(name, matchers):
    low = name.lower()
    return next((n for n, rx in matchers.items() if rx.fullmatch(low)), name)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def anthropic_llm(system, user):
    import anthropic  # lazy: tests and key-less runs never import it
    msg = anthropic.Anthropic().messages.create(
        model=MODEL, max_tokens=4000, system=system, messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in msg.content if b.type == "text")


def run_llm(llm, summary, library_text):
    """-> (report, library) or (None, None) on any failure / unusable reply."""
    try:
        raw = llm(SYSTEM, "STATS:\n" + json.dumps(summary, default=str)
                  + "\n\nCURRENT LIBRARY:\n" + (library_text or "(empty)"))
        m = re.search(r"\{.*\}", raw, re.S)
        d = json.loads(m.group(0))
        if isinstance(d.get("report"), str) and isinstance(d.get("library"), str):
            return d["report"], d["library"]
    except Exception as ex:  # noqa: BLE001
        data.log(f"LLM step failed: {type(ex).__name__}")
    return None, None


def table(rows, cols):
    head = "| " + " | ".join(h for h, _ in cols) + " |\n|" + "---|" * len(cols) + "\n"
    return head + "".join("| " + " | ".join(str(f(r)) for _, f in cols) + " |\n" for r in rows)


LB_COLS = [("Streamer", lambda r: r["streamer"]), ("Shorts", lambda r: r["shorts"]),
           ("Views", lambda r: r["views"]), ("Total v/h", lambda r: r["total_vph"]),
           ("Avg v/h", lambda r: r["avg_vph"]), ("Clippers", lambda r: r["clippers"]),
           ("Test slot", lambda r: "YES" if r["test_slot"] else "")]


def render_report(llm_report, now, lb24, lb7, ranking, rising, weekly, notes, fixme=()):
    parts = []
    if fixme:
        parts.append("## Fix me: unresolved channels (correct in config/competitors.yaml)\n\n"
                     + "\n".join(f"- {h}" for h in fixme))
    if llm_report:
        lines = llm_report.strip().splitlines()[:REPORT_MAX_LINES]
        parts.append("\n".join(lines))
    else:
        parts.append(f"# Trend Scout {now:%Y-%m-%d}\n\n_LLM step skipped; stats only._")
    parts.append("## Streamer leaderboard: last 24 h (movers)\n\n"
                 + (table(lb24[:15], LB_COLS) if lb24 else "_no data_\n"))
    new = [r["streamer"] for r in ranking if r["trend"] == "new"][:5]
    parts.append("## Daily ranking (clip velocity x Shorts velocity / clippers)\n\n"
                 + table(ranking[:10], [("Streamer", lambda r: r["streamer"]),
                                        ("Score", lambda r: r["score"]),
                                        ("Weight", lambda r: r["weight"]),
                                        ("Trend", lambda r: r["trend"])])
                 + ("\n**NEW (start clipping today):** " + ", ".join(new) + "\n" if new else ""))
    if rising:
        parts.append("## Rising, not in creators.yaml\n\n" + "\n".join(
            f"- #{r['tag']}: {r['videos']} Shorts, {r['channels']} channels" for r in rising[:10]))
    if weekly is not None:
        parts.append("## Weekly: 7-day leaderboard\n\n" + (table(lb7[:20], LB_COLS) if lb7 else "_no data_\n")
                     + f"\n**Add:** {', '.join(weekly['add']) or 'none'}\n"
                     + f"**Drop:** {', '.join(weekly['drop']) or 'none'}\n")
    if notes:
        parts.append("_Notes: " + "; ".join(notes) + "_")
    return "\n\n".join(parts).rstrip() + "\n"


def scout(competitors, library, report, now=None, session=None, twitch=None, llm=None,
          api_key=None, creators=None, ytdlp=data.fetch_ytdlp, resolve_run=subprocess.run, vision=None):
    now = now or datetime.now(timezone.utc)
    cfg = load_yaml(competitors)
    logins = creator_logins() if creators is None else creators
    notes = []

    channels, fixme, rnotes = resolve.resolve_channels(
        cfg.get("channels"), cfg.get("discover"), Path(competitors).parent / "channel_cache.json",
        api_key, session, resolve_run)
    notes += rnotes
    videos = data.fetch_all(channels, api_key, session, ytdlp)
    if not videos:
        notes.append("no competitor data fetched")
    clip_vel = twitch_clip_velocity(twitch, logins, now) if twitch else {}
    if not twitch:
        notes.append("Twitch keys missing: Shorts-only ranking")

    matchers = stats.build_matchers(cfg.get("aliases"), logins)
    clip_vel = {canonical(n, matchers): v for n, v in clip_vel.items()}
    for n in clip_vel:
        matchers.update({k: v for k, v in stats.build_matchers({}, [n]).items() if k not in matchers})

    top = stats.top_videos(videos, now)
    lb24 = stats.leaderboard(videos, matchers, now, 24, logins)
    lb7 = stats.leaderboard(videos, matchers, now, 24 * 7, logins)
    out_dir = Path(library).parent
    ranking = stats.build_ranking(clip_vel, lb24, read_json(out_dir / "creators_ranking.json", []))
    weights = stats.build_weights(lb24, lb7)
    rising = stats.rising_candidates(videos, matchers)
    weekly = (stats.weekly_recommendations(lb7, weights, logins) if now.weekday() == 0 else None)

    summary = {"date": f"{now:%Y-%m-%d}", "top20": [
        {"title": v["title"], "channel": v["channel"], "views": v["views"],
         "vph": round(stats.vph(v, now), 1), "duration_s": v.get("duration_s"),
         "published": v["published"].isoformat()} for v in top],
        "patterns": stats.patterns(top, matchers, now), "leaderboard_24h": lb24[:15],
        "leaderboard_7d": lb7[:15], "rising": rising[:10], "ranking": ranking[:10]}

    library = Path(library)
    lib_text = library.read_text() if library.exists() else ""
    llm_report = new_lib = None
    if llm is None and os.environ.get("ANTHROPIC_API_KEY"):
        llm = anthropic_llm
    if llm and videos:
        llm_report, new_lib = run_llm(llm, summary, lib_text)
    elif not llm:
        notes.append("ANTHROPIC_API_KEY missing: LLM step skipped")

    out_dir.mkdir(parents=True, exist_ok=True)
    if vision is None and os.environ.get("ANTHROPIC_API_KEY"):
        vision = style_scout.anthropic_vision
    if vision and top:
        try:  # caption style of today's top Shorts (thumbnails only) -> style.json for the renderer
            if style_scout.run([v["id"] for v in top if v.get("id")], out_dir / "style.json",
                               session, vision, now) is None:
                notes.append("style: too few captioned thumbnails, kept the previous style.json")
        except Exception as e:  # noqa: BLE001 - the report still goes out
            notes.append(f"style scout failed: {type(e).__name__}")
    if videos:
        try:  # hashtags the top Shorts use today -> hashtags.json for the publisher
            hashtag_scout.write(out_dir / "hashtags.json", hashtag_scout.summarize(
                videos, hashtag_scout.streamer_names(cfg.get("aliases"), logins), now))
        except Exception as e:  # noqa: BLE001 - the report still goes out
            notes.append(f"hashtag scout failed: {type(e).__name__}")
    (out_dir / "creators_ranking.json").write_text(json.dumps(ranking, indent=2) + "\n")
    (out_dir / "creator_weights.json").write_text(json.dumps(weights, indent=2) + "\n")
    if new_lib:
        library.write_text(new_lib.rstrip() + "\n")
    Path(report).write_text(render_report(llm_report, now, lb24, lb7, ranking, rising, weekly, notes, fixme))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--library", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--competitors", default=str(HERE / "config" / "competitors.yaml"))
    a = ap.parse_args(argv)
    twitch = None
    if os.environ.get("TWITCH_CLIENT_ID") and os.environ.get("TWITCH_CLIENT_SECRET"):
        from radar.twitch import Twitch
        twitch = Twitch()
    scout(a.competitors, a.library, a.report, twitch=twitch,
          api_key=os.environ.get("YOUTUBE_API_KEY"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
