"""Trending Shorts (D65) are remade like the market's: whoever is in them, searched in their own streams."""
from remake import run, source
from remake.tests.test_remake import MARKET, NOW, db

TRENDING = {"shorts": [
    {"id": "VAN", "title": "#vanillamace #twitch", "channel": "vanillas vault", "views": 7e5, "vph": 70000, "dur": 30,
     "published": "2026-10-21T08:00:00Z", "en": True, "streamer": "Vanillamace", "logins": ["vanillamace"],
     "kicks": [], "how": "hashtag/channel"},
    {"id": "A", "title": "dup of the market's", "channel": "SpecificMinds", "views": 3e4, "vph": 9000, "dur": 29,
     "published": "2026-10-21T05:00:00Z", "en": True, "streamer": "Stable Ronaldo", "logins": [], "kicks": [],
     "how": "watchlist"},
    {"id": "NOONE", "title": "x", "channel": "c", "views": 1e6, "vph": 90000, "dur": 30,
     "published": "2026-10-21T08:00:00Z", "en": True, "streamer": "", "logins": [], "kicks": []}]}


def test_trending_shorts_join_the_market_ones_once():
    got = run.candidates(MARKET, db(), NOW, twitch_names={"Stable Ronaldo", "Jynxzi"}, trending=TRENDING)
    ids = [s["id"] for s in got]
    assert ids[0] == "VAN" and ids.count("A") == 1 and "NOONE" not in ids
    assert got[0]["logins"] == ["vanillamace"]


def test_a_trending_streamers_own_logins_lead_the_search():
    s = TRENDING["shorts"][0]
    assert run.own_ids(s["streamer"], s)[0] == "vanillamace"
    assert source.twitch_logins(["Vanillamace"]) == []             # not on the watchlist: only the scan knows him
