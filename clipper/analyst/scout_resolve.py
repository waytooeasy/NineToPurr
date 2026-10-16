"""Trend Scout channel resolution: `handle: "@Name"` -> UC... channel_id, plus discovery slots.

Order per handle: cache -> YouTube Data API `channels.list?forHandle=` (needs YOUTUBE_API_KEY)
-> `yt-dlp --skip-download -J --playlist-items 0`. Discovery (`discover:` in the config) needs the
API key: `search.list` type=channel, then the top results by subscribers. Failures are logged and
returned as 'Fix me' handles, never raised. Only resolved ids are cached.
"""
import json
import subprocess
from pathlib import Path

import requests

from scout_data import log

API = "https://www.googleapis.com/youtube/v3/"


def norm_handle(h):
    h = (h or "").strip()
    return h if h.startswith("@") else "@" + h


def load_cache(path):
    try:
        d = json.loads(Path(path).read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(path, cache):
    try:
        Path(path).write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    except OSError as ex:
        log(f"channel cache not written: {type(ex).__name__}")


def _api(path, params, api_key, session):
    r = (session or requests).get(API + path, params={**params, "key": api_key}, timeout=20)
    r.raise_for_status()
    return r.json()


def resolve_api(handle, api_key, session=None):
    try:
        items = _api("channels", {"part": "id", "forHandle": handle}, api_key, session).get("items") or []
        return items[0]["id"] if items else None
    except Exception as ex:  # noqa: BLE001
        log(f"channels.list failed for {handle}: {type(ex).__name__}")  # never log the key/URL
        return None


def resolve_ytdlp(handle, run=subprocess.run):
    try:
        p = run(["yt-dlp", "--skip-download", "-J", "--playlist-items", "0",
                 f"https://www.youtube.com/{handle}"], capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            raise RuntimeError(f"yt-dlp exit {p.returncode}")
        cid = json.loads(p.stdout).get("channel_id")
        return cid if isinstance(cid, str) and cid.startswith("UC") else None
    except Exception as ex:  # noqa: BLE001
        log(f"yt-dlp resolve failed for {handle}: {type(ex).__name__}")
        return None


def resolve_handle(handle, api_key=None, session=None, run=subprocess.run):
    handle = norm_handle(handle)
    cid = resolve_api(handle, api_key, session) if api_key else None
    return cid or resolve_ytdlp(handle, run)


def discover(streamer, count, api_key, session=None):
    """Top `count` channels for `"<streamer> clips" shorts`, ranked by subscribers.
    Returns [{name, channel_id}]; [] on failure."""
    try:
        found = _api("search", {"part": "snippet", "type": "channel", "maxResults": 10,
                                "q": f'"{streamer} clips" shorts'}, api_key, session).get("items") or []
        ids = [i["id"]["channelId"] for i in found]
        if not ids:
            return []
        chans = _api("channels", {"part": "snippet,statistics", "id": ",".join(ids)},
                     api_key, session).get("items") or []
    except Exception as ex:  # noqa: BLE001
        log(f"discovery failed for {streamer}: {type(ex).__name__}")
        return []
    chans.sort(key=lambda c: int(c.get("statistics", {}).get("subscriberCount") or 0), reverse=True)
    return [{"name": c["snippet"]["title"], "channel_id": c["id"]} for c in chans[:count]]


def resolve_channels(channels, discover_cfg, cache_path, api_key=None, session=None,
                     run=subprocess.run):
    """-> (channels with channel_id set, fixme [handles/names], notes)."""
    cache = load_cache(cache_path)
    before = json.dumps(cache, sort_keys=True)
    out, fixme, notes = [], [], []
    for ch in channels or []:
        ch = dict(ch)
        if not ch.get("channel_id"):
            if not ch.get("handle"):
                fixme.append(ch.get("name") or "(unnamed entry)")
                continue
            h = norm_handle(ch["handle"])
            ch["channel_id"] = cache.get(h) or resolve_handle(h, api_key, session, run)
            if not ch["channel_id"]:
                fixme.append(h)
                continue
            cache[h] = ch["channel_id"]
            ch.setdefault("name", h)
        out.append(ch)
    for slot in discover_cfg or []:
        who, n = slot["streamer"], int(slot.get("count", 1))
        key = f"search:{who}:{n}"
        if isinstance(cache.get(key), list):
            found = cache[key]
        elif not api_key:
            notes.append(f"discovery for {who} skipped: YOUTUBE_API_KEY missing")
            continue
        else:
            found = discover(who, n, api_key, session)
            if found:
                cache[key] = found
            else:
                notes.append(f"discovery found nothing for {who}")
        have = {c["channel_id"] for c in out}
        out += [{"name": f["name"], "channel_id": f["channel_id"], "streamers": [who]}
                for f in found if f["channel_id"] not in have]
    if json.dumps(cache, sort_keys=True) != before:
        save_cache(cache_path, cache)
    return out, fixme, notes
