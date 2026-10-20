"""Market hashtags on uploads (publisher/hashtags.py)."""
import json
import sqlite3

import hashtags as H

MARKET = {"title_share": 0.95, "title_tags": 1, "generic": ["#shorts", "#twitch", "#fyp"],
          "streamers": {"IShowSpeed": "#ishowspeed"}, "keywords": ["streamers", "streamer clips"]}
SN = {"title": "Speed can't believe it 😭", "description": "x\n\n#Shorts", "tags": ["#Shorts"], "categoryId": "20"}
SPEED = {"name": "IShowSpeed", "login": "ishowspeed", "platform": "twitch"}
ADIN = {"name": "Adin Ross", "login": "adinross", "platform": "kick"}


def test_streamer_tag_in_title_and_market_tags_in_description():
    sn = H.apply(SN, "Speed met the master of a throw game", SPEED, MARKET)
    assert sn["title"] == "Speed can't believe it 😭 #ishowspeed"
    assert sn["description"] == "Speed met the master of a throw game\n\n#ishowspeed #shorts #twitch #fyp"
    assert sn["tags"][:2] == ["IShowSpeed", "#Shorts"] and "streamer clips" in sn["tags"]
    assert sn["categoryId"] == "20"


def test_no_duplicate_when_writer_already_tagged_and_kick_gets_kick():
    sn = H.apply(dict(SN, title="Adin Ross: she quit before round 2 😭 #adinross"), "ctx", ADIN, MARKET)
    assert sn["title"].count("#adinross") == 1
    assert sn["description"].endswith("#adinross #shorts #fyp #kick")      # #twitch swapped for #kick


def test_title_tag_only_when_the_market_does_it_and_it_fits():
    assert H.apply(SN, "c", SPEED, dict(MARKET, title_share=0.2))["title"] == SN["title"]
    long = dict(SN, title="x" * 95)
    assert H.apply(long, "c", SPEED, MARKET)["title"] == "x" * 95


def test_load_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_HASHTAGS", str(tmp_path / "none.json"))
    assert H.load() == H.DEFAULT
    p = tmp_path / "h.json"
    p.write_text(json.dumps({"generic": ["#kick"], "junk": 1}))
    assert H.load(p)["generic"] == ["#kick"] and "junk" not in H.load(p)


def test_streamer_for_maps_login_to_watchlist_name(tmp_path):
    con = sqlite3.connect(":memory:")
    con.executescript("CREATE TABLE creators (id INTEGER PRIMARY KEY, name TEXT, main_platform TEXT);"
                      "CREATE TABLE sources (id INTEGER PRIMARY KEY, creator_id INT);"
                      "CREATE TABLE clips (id INTEGER PRIMARY KEY, source_id INT);"
                      "INSERT INTO creators VALUES (1, 'adinross', 'kick');"
                      "INSERT INTO sources VALUES (1, 1); INSERT INTO clips VALUES (6, 1);")
    wl = tmp_path / "w.yaml"
    wl.write_text("streamers:\n  - {name: Adin Ross, platform: kick, id: adinross}\n")
    assert H.streamer_for(con, 6, wl) == ADIN
    assert H.streamer_for(con, 99, wl) is None
    assert H.streamer_tag({"name": "Stable Ronaldo", "login": "stableronaldo"}, MARKET) == "#stableronaldo"


def test_streamer_sub_market_tags_and_cap(tmp_path, monkeypatch):
    m = tmp_path / "market.json"
    m.write_text(json.dumps({"streamers": {"Jynxzi": {"hashtags": ["#jynxzi", "#r6", "#rainbowsix"]}}}))
    monkeypatch.setenv("CLIPPER_MARKET", str(m))
    assert H.market_tags("Jynxzi") == ["#jynxzi", "#r6", "#rainbowsix"] and H.market_tags("Nobody") == []
    jyn = {"name": "Jynxzi", "login": "jynxzi", "platform": "twitch"}
    sn = H.apply(dict(SN, title="Jynxzi hears a real alarm 😭"), "ctx", jyn, dict(MARKET, streamer_tags=H.market_tags("Jynxzi")))
    assert sn["title"].endswith("#jynxzi")
    tags = sn["description"].split("\n\n")[1].split()
    assert tags[:3] == ["#jynxzi", "#r6", "#rainbowsix"] and len(tags) <= H.MAX_DESC_TAGS
