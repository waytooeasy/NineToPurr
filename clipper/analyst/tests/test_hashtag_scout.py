"""Hashtag scout (Lucas 2026-10-19: "find what hashtags are popping and use em"). Offline: video dicts
shaped like the Trend Scout's, titles/descriptions/tags copied in style from the 2026-10-19 top Shorts."""
from datetime import datetime, timedelta, timezone

import hashtag_scout as H
import scout_data as data

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
NAMES = H.streamer_names({"Kai Cenat": ["kai cenat", "kaicenat", "kai"], "IShowSpeed": ["ishowspeed", "speed"]},
                         ["xQc"])


def v(channel, title, views, description="", tags=(), days=1):
    return {"channel": channel, "title": title, "views": views, "description": description,
            "tags": list(tags), "published": NOW - timedelta(days=days)}


VIDEOS = [
    v("Nexxo Recaps", "Speed with a large forehead is KSI 😭 #ishowspeed", 24_000_000,
      "Speed went to a beach in Miami ... #nexxorecaps"),
    v("Nexxo Recaps", "Bro found the one on camera 😭❤️‍🩹 #ishowspeed", 9_800_000),
    v("Stream Bellz", "IShowSpeed Risked His Hardcore World On One Water Bucket 😂", 1_390_000,
      "IShowSpeed Risked ...\n\nOnly Streamers. Nothing Else.\n\n#twitch #ishowspeed #kaicenat #shorts",
      ["kai cenat", "streamers", "ishowspeed", "twitch", "shorts", "streamer clips"]),
    v("Stream Bellz", "Kai Cenat Gave This Fans Bike The Worst Test Ride Ever 🥹", 25_000,
      "Kai Cenat Gave ...\n\n#twitch #ishowspeed #kaicenat #shorts",
      ["kai cenat", "streamers", "twitch", "shorts", "streamer clips"]),
    v("KaiClips", "kai can't believe it #kaicenat #shorts #twitch", 400_000, tags=["streamers"]),
    v("Old", "old news #ishowspeed #oldtag", 90_000_000, "#oldtag", days=20),        # outside 7 days
]


def test_summary_follows_the_market():
    s = H.summarize(VIDEOS, NAMES, NOW)
    assert s["sample"] == 5 and s["updated"] == "2026-10-19"
    assert s["title_share"] > 0.9                         # the big Shorts carry a tag in the title
    assert s["title_tags"] == 1
    assert s["streamers"] == {"IShowSpeed": "#ishowspeed", "Kai Cenat": "#kaicenat"}
    assert s["generic"][:2] == ["#shorts", "#twitch"]       # used by 2+ channels, most-viewed first
    assert "#nexxorecaps" not in s["generic"] and "#oldtag" not in s["generic"]   # brand / stale
    assert "streamers" in s["keywords"] and "shorts" in s["keywords"]
    assert not any("kai" in k or "speed" in k for k in s["keywords"])          # no streamer keywords


def test_enrich_api_keeps_description_and_tags():
    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"items": [{"id": "a", "snippet": {"description": "d #twitch", "tags": ["x"]},
                               "contentDetails": {"duration": "PT30S"}, "statistics": {"viewCount": "5"}}]}

    class S:
        def get(self, url, params=None, timeout=None):
            assert "snippet" in params["part"]
            return R()
    out = data.enrich_api([{"id": "a", "views": 0}], "K", S())
    assert out[0]["description"] == "d #twitch" and out[0]["tags"] == ["x"] and out[0]["duration_s"] == 30


def test_write_roundtrip(tmp_path):
    import json
    p = tmp_path / "hashtags.json"
    H.write(p, H.summarize(VIDEOS, NAMES, NOW))
    assert json.loads(p.read_text())["streamers"]["IShowSpeed"] == "#ishowspeed"
