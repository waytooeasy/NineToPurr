"""Trend scan (D65): popping stream Shorts found without a streamer list, with who is in them."""
import json
from datetime import datetime, timezone

from radar import trend

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def item(vid, title, channel, views, hours_ago=10, dur="PT40S", desc="", tags=None):
    pub = NOW.timestamp() - hours_ago * 3600
    return {"id": vid, "contentDetails": {"duration": dur}, "statistics": {"viewCount": str(views)},
            "snippet": {"title": title, "channelTitle": channel, "description": desc, "tags": tags or [],
                        "publishedAt": datetime.fromtimestamp(pub, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}}


ITEMS = [
    item("VANILLA", "#vanillamace #twitch #funny #shortsviral #trending", "vanillas vault", 700000),
    item("JASON", "Jason Couldn't Believe What Happened On Stream", "JasonTheWeen Fan", 300000,
         desc="All content belongs to Jason. Watch Jason at https://twitch.tv/jasontheween"),
    item("KAI", "Kai Cenat Randomly Meets Streamer CashMeow Off Stream In Japan", "DaPlug", 500000),
    item("FOOTBALL", "CRISTIANO RONALDO CRAZY FREE KICK | PORTUGAL VS BRAZIL", "GOLU VERS", 400000),
    item("RUSSIAN", "twitch: mellstroy | как ощущается ехать на учебу", "Gubkastroy", 400000),
    item("NOBODY", "This Is Hilarious 😭 #bigmoment", "StompnWorld", 400000),
    item("LONG", "#vanillamace is the best on twitch", "vanillas vault", 900000, dur="PT1M30S"),
    item("SLOW", "#vanillamace #twitch", "vanillas vault", 5000),
    item("KICKER", "N3on and his friends at the mall on stream", "Liu Clipper", 200000,
         desc="watch live at kick.com/n3on"),
    item("CHANNEL", "The Big Plan for the stream", "Asmongold Shorts", 300000),
]


class Session:
    def __init__(self):
        self.calls = []

    def get(self, url, timeout, params):
        self.calls.append(url.rsplit("/", 1)[-1])

        class R:
            def __init__(self, body):
                self.body = body

            def raise_for_status(self):
                pass

            def json(self):
                return self.body
        if url.endswith("/search"):
            return R({"items": [{"id": {"videoId": i["id"]}} for i in ITEMS]})
        ids = params["id"].split(",")
        return R({"items": [i for i in ITEMS if i["id"] in ids]})


class Tw:
    USERS = {"vanillamace": "partner", "jasontheween": "partner", "asmongold": "partner", "bigmoment": "",
             "vanillasvault": ""}

    def __init__(self):
        self.calls = 0

    def _get(self, path, params):
        self.calls += 1
        return {"data": [{"login": lg, "display_name": lg.capitalize(), "broadcaster_type": self.USERS[lg]}
                         for lg in params["login"] if lg in self.USERS]}


def test_trending_shorts_beyond_the_watchlist_get_their_streamer(tmp_path):
    wl = tmp_path / "w.yaml"
    wl.write_text("streamers:\n  - {name: Kai Cenat, platform: twitch, id: kaicenat}\n")
    tw = Tw()
    d = trend.scan("k", tw=tw, session=Session(), now=NOW, wl_path=wl, queries=("twitch", "streamer"))
    got = {s["id"]: s for s in d["shorts"]}
    assert set(got) == {"VANILLA", "JASON", "KAI", "KICKER", "CHANNEL"}
    assert got["VANILLA"]["logins"] == ["vanillamace"] and got["VANILLA"]["how"] == "hashtag/channel"
    assert got["JASON"]["logins"] == ["jasontheween"] and got["JASON"]["how"] == "linked"
    assert got["KAI"]["streamer"] == "Kai Cenat" and got["KAI"]["how"] == "watchlist"
    assert got["KICKER"]["kicks"] == ["n3on"] and got["KICKER"]["logins"] == []
    assert got["CHANNEL"]["logins"] == ["asmongold"]                  # "Asmongold Shorts" is Asmongold's
    assert [s["id"] for s in d["shorts"]][0] == "VANILLA"               # most views/hour first
    assert tw.calls == 1                                                # every name checked in one Twitch call


def test_noise_is_dropped():
    assert not trend.english("twitch: mellstroy | как ощущается ехать на учебу")
    assert trend.english("#vanillamace #twitch #funny")
    assert ("guess", "funny") not in trend.leads("#funny #vanillamace", "", [], "x")
    assert ("twitch", "videos") not in trend.leads("t", "https://twitch.tv/videos/123", [], "x")


def test_file_round_trip_and_due(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_TRENDING", str(tmp_path / "t.json"))
    assert trend.due(now=NOW)
    trend.write({"updated": "2026-10-28T09:00:00Z", "window_h": 48, "found": 1, "shorts": []})
    assert not trend.due(now=NOW) and trend.load(now=NOW)["found"] == 1
    assert trend.due(now=datetime(2026, 10, 28, 16, 0, tzinfo=timezone.utc))   # every 6 h
    assert json.loads((tmp_path / "t.json").read_text())["window_h"] == 48
