#!/usr/bin/env python3
"""Radar YouTube source (D29): moments from a creator's OWN livestream VODs, via yt-dlp metadata only.

Per creator with `youtube_channel` in config/creators.yaml:
  <channel>/streams (flat list) -> per-video JSON -> moments from the `heatmap` ("most replayed"),
  else `chapters` -> radar_candidates rows with source='youtube'.
Only the configured channel's livestream VODs are used: /shorts URLs, other channels' videos and
non-live uploads are skipped. No API key, no download here (capture.py downloads picked VODs).

Usage (from clipper/):
  python -m radar.youtube_vods                # store + print ranked moments
  python -m radar.youtube_vods --picks 3      # also write picks.json (VOD-absolute start/end)
"""
import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import top_clips

MAX_MOMENT_S = 60
MIN_MOMENT_S = 10
MIN_HEAT = 0.5            # heatmap value (0..1) a segment needs to count as "most replayed"
CHAPTER_HEAT = 0.3        # chapters carry no replay signal: weak constant
PER_VOD = 3               # max moments kept per VOD
LIST_N = 10               # newest N entries of /streams


def run_ytdlp(args, runner=subprocess.run):
    """Run yt-dlp, return stdout. `runner` is injectable so tests never hit the network."""
    r = runner(["yt-dlp", *args], capture_output=True, text=True, check=True)
    return r.stdout


def channel_streams_url(channel):
    ch = channel.strip()
    if ch.startswith("http"):
        base = ch.rstrip("/")
    elif ch.startswith("UC"):
        base = f"https://www.youtube.com/channel/{ch}"
    else:
        base = f"https://www.youtube.com/{ch if ch.startswith('@') else '@' + ch}"
    return base if base.endswith("/streams") else base + "/streams"


def list_stream_urls(channel, runner=subprocess.run, limit=LIST_N):
    """Watch URLs from the channel's /streams tab. Shorts URLs are dropped."""
    out = run_ytdlp(["--flat-playlist", "--dump-json", "--playlist-end", str(limit),
                     channel_streams_url(channel)], runner)
    urls = []
    for line in out.splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        url = e.get("url") or e.get("webpage_url") or ""
        if "/shorts/" in url or not e.get("id"):
            continue
        urls.append(f"https://www.youtube.com/watch?v={e['id']}")
    return urls


def video_info(url, runner=subprocess.run):
    return json.loads(run_ytdlp(["--dump-json", "--skip-download", "--no-playlist", url], runner))


def own_vod_infos(channel, runner=subprocess.run, limit=LIST_N):
    """video_info for each /streams entry, skipping entries yt-dlp can't read (members-only, premieres,
    YouTube's "confirm you're not a bot"). Raises only if the list had entries and every one failed,
    so the caller logs it instead of silently treating the channel as 0 views."""
    urls = list_stream_urls(channel, runner, limit)
    infos, failed = [], 0
    for url in urls:
        try:
            infos.append(video_info(url, runner))
        except (subprocess.CalledProcessError, ValueError):
            failed += 1
    if urls and failed == len(urls):
        raise RuntimeError(f"yt-dlp could not read any of {len(urls)} VODs on {channel}")
    return infos


def _same_channel(info, channel):
    ch = channel.strip().rstrip("/").split("/")[-1].lower()
    ids = {str(info.get(k) or "").lower() for k in
           ("channel_id", "uploader_id", "channel_handle")}
    ids |= {str(info.get("channel_url") or "").rstrip("/").split("/")[-1].lower()}
    return ch in ids


def is_own_live_vod(info, channel):
    """Own channel + finished livestream (was_live) + not a Short."""
    if "/shorts/" in (info.get("webpage_url") or ""):
        return False
    if not _same_channel(info, channel):
        return False
    return info.get("live_status") == "was_live" or (info.get("was_live") is True and not info.get("is_live"))


def _window(start, end, duration):
    """<=60 s window; a longer segment is centred on its middle. None if too short / outside."""
    if end - start > MAX_MOMENT_S:
        mid = (start + end) / 2
        start, end = mid - MAX_MOMENT_S / 2, mid + MAX_MOMENT_S / 2
    start = max(0.0, start)
    end = min(end, float(duration))
    if end - start < MIN_MOMENT_S:
        return None
    return int(start), min(end - int(start), MAX_MOMENT_S)


def moments(info):
    """[(start_s, length_s, heat 0..1, label)] from heatmap, else chapters, else []."""
    duration = info.get("duration") or 0
    out = []
    heat = info.get("heatmap") or []
    if heat:
        for seg in sorted(heat, key=lambda s: s.get("value", 0), reverse=True):
            if seg.get("value", 0) < MIN_HEAT:
                break
            w = _window(seg["start_time"], seg["end_time"], duration)
            if w:
                out.append((w[0], w[1], float(seg["value"]), "most replayed"))
        return out
    for ch in info.get("chapters") or []:
        w = _window(ch["start_time"], ch.get("end_time", ch["start_time"] + MAX_MOMENT_S), duration)
        if w:
            out.append((w[0], w[1], CHAPTER_HEAT, ch.get("title") or "chapter"))
    return out


def _vod_time(info):
    ts = info.get("release_timestamp") or info.get("timestamp")
    if ts:
        return datetime.fromtimestamp(ts, timezone.utc)
    d = info.get("upload_date")  # YYYYMMDD
    return datetime.strptime(d, "%Y%m%d").replace(tzinfo=timezone.utc) if d else None


def candidates_for_vod(info, creator, now):
    """Scored, deduped (overlap within the VOD) candidate dicts for one VOD."""
    vid = info["id"]
    when = _vod_time(info) or now
    hours = max((now - when).total_seconds() / 3600, top_clips.MIN_AGE_H)
    vod_views = int(info.get("view_count") or 0)
    url = info.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
    cands = []
    for start, length, heat, label in moments(info):
        cands.append({
            "clip_id": f"yt:{vid}:{start}", "creator": creator, "broadcaster_id": None,
            "title": f"{info.get('title') or ''} [{label}]".strip(), "url": url, "video_id": vid,
            "vod_offset": start, "duration_s": float(length),
            # no per-moment views on YouTube: VOD views/hour weighted by replay heat
            "view_count": vod_views, "views_per_hour": max(vod_views, 1) * heat / hours,
            "created_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "youtube",
        })
    return top_clips.dedupe(cands)[:PER_VOD]


def _reuse_existing(db, c):
    """Idempotent re-runs: heatmaps shift, so a moment overlapping a stored one adopts its id/window."""
    for cid, off, dur in db.execute(
            "SELECT clip_id, vod_offset, duration_s FROM radar_candidates "
            "WHERE source='youtube' AND video_id=?", (c["video_id"],)).fetchall():
        if off is not None and c["vod_offset"] < off + dur and off < c["vod_offset"] + c["duration_s"]:
            return dict(c, clip_id=cid, vod_offset=off, duration_s=dur)
    return c


def collect(creator_cfgs, db=None, now=None, runner=subprocess.run, days=7):
    """Moments from each configured creator's recent own livestream VODs, best first."""
    now = now or datetime.now(timezone.utc)
    allc = []
    for cfg in creator_cfgs:
        channel = cfg.get("youtube_channel")
        if not channel:
            continue
        found = []
        for info in own_vod_infos(channel, runner):
            if not is_own_live_vod(info, channel):
                continue
            when = _vod_time(info)
            if when and when < now - timedelta(days=days):
                continue
            found.extend(candidates_for_vod(info, cfg["twitch"], now))
        if db is not None:
            found = [_reuse_existing(db, c) for c in found]
        allc.extend(top_clips.dedupe(found))
    return sorted(allc, key=lambda x: x["views_per_hour"], reverse=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--picks", type=int, metavar="N", help="write picks.json with top N")
    ap.add_argument("--out", default="picks.json")
    ap.add_argument("--config", help="creators.yaml path")
    a = ap.parse_args(argv)
    db = top_clips.connect()
    cands = collect(top_clips.load_creator_configs(a.config), db)
    top_clips.store(db, cands)
    for i, c in enumerate(cands, 1):
        print(f"{i:>3}. {c['views_per_hour']:>9.1f} score  {c['creator']}  {c['title'][:50]!r}  "
              f"{c['url']}  @{c['vod_offset']}s +{c['duration_s']:.0f}s")
    if a.picks:
        top_clips.register_clips(db, cands[:a.picks])
        Path(a.out).write_text(json.dumps(top_clips.to_picks(cands, a.picks), indent=2))
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
