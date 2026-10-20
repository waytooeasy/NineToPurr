"""Trend Scout data: competitor Shorts metadata only (D29). No video is ever downloaded.

Sources, in order: YouTube RSS (title/views/published) -> optional YouTube Data API
`videos.list` (duration + exact stats, needs YOUTUBE_API_KEY) -> yt-dlp `--skip-download -J`
fallback when RSS fails. Every network failure is logged and skipped, never raised.
"""
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

RSS = "https://www.youtube.com/feeds/videos.xml?channel_id="
API = "https://www.googleapis.com/youtube/v3/videos"
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
      "m": "http://search.yahoo.com/mrss/"}


def log(msg):
    print(f"[trend_scout] {msg}", file=sys.stderr)


def _dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _video(channel, **kw):
    return {"channel": channel["name"], "channel_id": channel["channel_id"],
            "default_streamers": list(channel.get("streamers") or []), **kw}


def parse_rss(xml_text, channel):
    """Atom feed -> list of video dicts (duration_s None: RSS has none)."""
    out = []
    for e in ET.fromstring(xml_text).findall("a:entry", NS):
        stats = e.find("m:group/m:community/m:statistics", NS)
        out.append(_video(
            channel, id=e.findtext("yt:videoId", namespaces=NS),
            title=e.findtext("a:title", default="", namespaces=NS),
            published=_dt(e.findtext("a:published", namespaces=NS)),
            views=int(stats.get("views", 0)) if stats is not None else 0,
            likes=None, duration_s=None))
    return out


def parse_iso_duration(s):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return None
    d, h, mi, sec = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + sec


def enrich_api(videos, api_key, session=None, batch=50):
    """Fill duration, exact views/likes, description and tags from videos.list (one quota unit per 50
    videos whatever the parts). Failures leave videos as-is."""
    http = session or requests
    by_id = {v["id"]: v for v in videos}
    ids = list(by_id)
    for i in range(0, len(ids), batch):
        try:
            r = http.get(API, params={"part": "snippet,contentDetails,statistics", "key": api_key,
                                      "id": ",".join(ids[i:i + batch])}, timeout=20)
            r.raise_for_status()
            items = r.json().get("items", [])
        except Exception as ex:  # noqa: BLE001 - best-effort enrichment
            log(f"videos.list failed: {type(ex).__name__}")  # never log the key/URL
            continue
        for it in items:
            v = by_id.get(it["id"])
            if not v:
                continue
            v["duration_s"] = parse_iso_duration(it.get("contentDetails", {}).get("duration"))
            st = it.get("statistics", {})
            if "viewCount" in st:
                v["views"] = int(st["viewCount"])
            if "likeCount" in st:
                v["likes"] = int(st["likeCount"])
            sn = it.get("snippet") or {}
            if sn:
                v["description"] = sn.get("description") or ""
                v["tags"] = list(sn.get("tags") or [])
    return videos


def parse_ytdlp(json_text, channel):
    """yt-dlp -J (flat playlist or full) -> video dicts; entries without a date are dropped."""
    out = []
    for e in json.loads(json_text).get("entries") or []:
        if e.get("timestamp"):
            pub = datetime.fromtimestamp(e["timestamp"], timezone.utc)
        elif e.get("upload_date"):
            pub = datetime.strptime(e["upload_date"], "%Y%m%d").replace(tzinfo=timezone.utc)
        else:
            continue
        out.append(_video(channel, id=e.get("id"), title=e.get("title") or "", published=pub,
                          views=int(e.get("view_count") or 0), likes=e.get("like_count"),
                          duration_s=e.get("duration")))
    return out


def fetch_ytdlp(channel, run=subprocess.run):
    url = f"https://www.youtube.com/channel/{channel['channel_id']}/shorts"
    try:
        p = run(["yt-dlp", "--skip-download", "-J", "--playlist-end", "30", url],
                capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            raise RuntimeError(f"yt-dlp exit {p.returncode}")
        return parse_ytdlp(p.stdout, channel)
    except Exception as ex:  # noqa: BLE001 - often bot-blocked on CI
        log(f"yt-dlp fallback failed for {channel['name']}: {type(ex).__name__}")
        return []


def fetch_channel(channel, session=None, ytdlp=fetch_ytdlp):
    """RSS first; yt-dlp if RSS fails or is empty. Returns [] on total failure."""
    http = session or requests
    try:
        r = http.get(RSS + channel["channel_id"], timeout=20)
        r.raise_for_status()
        vids = parse_rss(r.text, channel)
        if vids:
            return vids
    except Exception as ex:  # noqa: BLE001
        log(f"RSS failed for {channel['name']}: {type(ex).__name__}")
    return ytdlp(channel)


def fetch_all(channels, api_key=None, session=None, ytdlp=fetch_ytdlp):
    videos = []
    for ch in channels:
        if not ch.get("channel_id"):
            log(f"skip '{ch['name']}': no channel_id")
            continue
        videos += fetch_channel(ch, session, ytdlp)
    if api_key and videos:
        enrich_api(videos, api_key, session)
    return videos
