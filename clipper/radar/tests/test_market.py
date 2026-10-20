"""Shorts market scan + demand-driven Heat (D48). Offline: fake YouTube API session, fixed clock."""
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

CLIPPER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(CLIPPER), str(CLIPPER / "editor")]

import run_pipeline  # noqa: E402
from radar import heat, market as M  # noqa: E402
from radar.tests.test_radar import migrate_db  # noqa: E402

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def item(vid, title, views, hours_ago, channel="Clips", desc="", dur="PT25S", tags=()):
    return {"id": vid, "snippet": {"title": title, "description": desc, "channelTitle": channel, "tags": list(tags),
                                   "publishedAt": (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")},
            "statistics": {"viewCount": str(views)}, "contentDetails": {"duration": dur}}


class R:
    def __init__(self, js, status=200):
        self._js, self.status_code = js, status

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code} quotaExceeded")


class Session:
    """search -> ids; videos -> items. Per query: {q: [items]}."""

    def __init__(self, by_q, fail_q=()):
        self.by_q, self.fail_q, self.calls = by_q, set(fail_q), []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url.rsplit("/", 1)[-1], params.get("q")))
        if url.endswith("/search"):
            if params["q"] in self.fail_q:
                return R({}, 403)
            self.last = self.by_q.get(params["q"], [])
            assert params["order"] == "viewCount" and params["videoDuration"] == "short"
            return R({"items": [{"id": {"videoId": i["id"]}} for i in self.last]})
        return R({"items": self.last})


JYNX = [
    item("j1", "Jynxzi Defends Joe Bart After the Streamer of the Year Controversy", 324_000, 12, "iboclips",
         "#jynxzi #r6"),
    item("j2", "Jynxzi Gets a Real Proximity Alarm From Rainbow Six Siege 😭", 228_000, 10, "iboclips", "#jynxzi"),
    item("j3", "Jynxzi reacts to the worst ace #jynxzi #r6", 140_000, 40, "Junko Highlights", dur="PT1M44S"),
    item("j4", "rainbow six siege tips and tricks", 900_000, 5, "R6 Guides"),                  # does not name him
    item("j5", "Jynxzi ist endlich Unreal in Fortnite..🤣", 154_000, 18, "Addi LIVE"),        # not English
]


def test_scan_streamer_measures_demand_from_shorts_that_name_him():
    al = {"jynxzi"}
    r = M.scan_streamer("Jynxzi", al, "K", Session({"Jynxzi": JYNX}), NOW)
    ids = [s["id"] for s in r["shorts"]]
    assert "j4" not in ids and "j5" not in ids and ids[0] == "j1"                    # unrelated / not English
    assert r["demand_vph"] == sum(s["vph"] for s in r["shorts"]) == 27000 + 22800 + 3500
    assert r["dur_median"] == 25 and r["hashtags"] == ["#jynxzi", "#r6"]               # both used by 2 channels


def test_ambiguous_names_need_stream_context():
    al = {"sketch"}
    assert not M.mentions("pencil sketch tutorial for beginners", al)
    assert not M.mentions("Por favor comparte con tus amigos #pov #sketch", al)          # 2026-10-20 scan
    assert M.mentions("Sketch goes crazy on stream", al)
    assert not M.mentions("When Marlon Wayans Almost Got Sued", {"marlon"}, {"kai cenat"})
    assert M.mentions("Joe Bart Calls Ludwig about his IShowSpeed take", {"ludwig"}, {"ishowspeed"})
    assert not M.mentions("a classic fallacy", {"lacy"}) and M.mentions("Kai Cenat cant wait", {"kai cenat"})


def test_scan_writes_and_stops_on_quota(tmp_path):
    wl = tmp_path / "w.yaml"
    wl.write_text("streamers:\n  - {name: Jynxzi, platform: twitch, id: jynxzi}\n"
                  "  - {name: Valkyrae, platform: twitch, id: valkyrae}\n  - {name: CaseOh, platform: twitch, id: caseoh_}\n")
    s = Session({"Jynxzi": JYNX}, fail_q={"Valkyrae"})
    d = M.scan("K", s, NOW, wl)
    assert list(d["streamers"]) == ["Jynxzi"]                                          # 403 -> stop, keep what we have
    assert [q for c, q in s.calls if c == "search"] == ["Jynxzi", "Valkyrae"]
    p = M.write(d, tmp_path / "m.json")
    assert M.load(tmp_path / "m.json", NOW + timedelta(hours=10))["streamers"]["Jynxzi"]["demand_vph"] > 0
    assert M.load(tmp_path / "m.json", NOW + timedelta(hours=80)) is None             # stale
    assert M.due(tmp_path / "m.json", NOW + timedelta(hours=2)) is False
    assert M.due(tmp_path / "m.json", NOW + timedelta(hours=25)) is True
    assert p["window_h"] == 48


def test_popping_titles_maps_login_to_name_and_keeps_english(tmp_path):
    wl = tmp_path / "w.yaml"
    wl.write_text("streamers:\n  - {name: CaseOh, platform: twitch, id: caseoh_}\n")
    m = {"streamers": {"CaseOh": {"shorts": [{"title": "Someone needs to lock CaseOh up 😭🙏", "vph": 6869, "dur": 16, "en": True},
                                              {"title": "CaseOh Cuma Iseng", "vph": 9000, "dur": 20, "en": False}]}}}
    assert M.popping_titles("caseoh_", market=m, wl_path=wl) == ("CaseOh", [{"title": "Someone needs to lock CaseOh up 😭🙏",
                                                                             "vph": 6869, "dur": 16}])
    assert M.name_for("CASEOH_", wl) == "CaseOh" and M.name_for("nobody", wl) is None


# --- Heat Index follows the market ---------------------------------------------------------------

def test_market_opportunity_needs_demand_and_fresh_footage():
    assert heat.market_opportunity(108_000, 2524) == pytest.approx(108_000 ** 0.5)
    assert heat.market_opportunity(392, 4391) < heat.market_opportunity(108_000, 2524) / 15  # Valkyrae vs Jynxzi
    assert heat.market_opportunity(351_000, 104) < heat.market_opportunity(108_000, 2524)    # Speed: no fresh Twitch
    assert heat.market_opportunity(50_000, 0) == 0                                           # nothing to clip


def test_slots_follow_shorts_demand_not_twitch_clip_views(tmp_path):
    # 2026-10-20 numbers: the old formula gave Valkyrae/Pokimane slots; the market wants Jynxzi/CaseOh.
    db = sqlite3.connect(":memory:")
    migrate_db(db)
    cfg = {"cap": 5, "max_per": 2, "explore_days": 3, "explore_top_n": 15, "streamers": {
        n: [{"platform": "twitch", "id": n.lower()}] for n in ["Jynxzi", "CaseOh", "xQc", "Valkyrae", "Pokimane"]}}
    twitch_d = {"jynxzi": 2524, "caseoh": 3323, "xqc": 15480, "valkyrae": 4391, "pokimane": 1412}
    demand = {"Jynxzi": 108_023, "CaseOh": 46_143, "xQc": 23_387, "Valkyrae": 392, "Pokimane": 2_736}
    m = {"streamers": {n: {"demand_vph": v} for n, v in demand.items()}}
    import random
    rows, slots = heat.run(db, cfg, lambda e, now: (twitch_d[e["id"]], twitch_d[e["id"]] * 5), lambda e: False, {}, NOW,
                           random.Random(1), market=m)
    assert rows["Jynxzi"]["demand"] == 108_023
    ranked = sorted(rows, key=lambda n: -rows[n]["opportunity"])
    assert ranked[:3] == ["Jynxzi", "CaseOh", "xQc"] and ranked[-1] == "Valkyrae"
    assert slots.get("Jynxzi") == 2 and slots.get("Valkyrae", 0) <= 1                  # exploration slot at most
    stored = dict(db.execute("SELECT streamer, demand FROM streamer_heat").fetchall())
    assert stored["CaseOh"] == 46_143
    # no / partial market -> the old formula, demand NULL
    rows, _ = heat.run(db, cfg, lambda e, now: (twitch_d[e["id"]], 1), lambda e: False, {}, NOW + timedelta(hours=1),
                       market={"streamers": {"Jynxzi": {"demand_vph": 1}}})
    assert all(r["demand"] is None for r in rows.values()) and rows["xQc"]["opportunity"] > rows["Jynxzi"]["opportunity"]


# --- pipeline: pacing + daily scan ----------------------------------------------------------------

def test_paced_cap_spreads_the_day():
    at = lambda h, m=0: run_pipeline.paced_cap(5, NOW.replace(hour=h, minute=m))  # noqa: E731
    assert [at(0, 9), at(4, 47), at(4, 49), at(9, 40), at(14, 30), at(19, 13), at(23, 59)] == [1, 1, 2, 3, 4, 5, 5]


def test_market_step_runs_once_a_day(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_MARKET", str(tmp_path / "m.json"))
    assert run_pipeline.market_step(NOW, key="") .startswith("skipped")
    calls = []
    monkeypatch.setattr(M, "scan", lambda key, now=None: calls.append(key) or
                        {"updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "window_h": 48, "streamers": {"X": {"demand_vph": 1}}})
    assert run_pipeline.market_step(NOW, key="K") == "scanned 1 streamers"
    assert run_pipeline.market_step(NOW + timedelta(hours=3), key="K") == "fresh" and calls == ["K"]
    assert json.loads((tmp_path / "m.json").read_text())["streamers"]["X"]["demand_vph"] == 1


def test_target_length_is_what_the_top_clippers_post(tmp_path):
    wl = tmp_path / "w.yaml"
    wl.write_text("streamers:\n  - {name: Kai Cenat, platform: twitch, id: kaicenat}\n"
                  "  - {name: Lacy, platform: twitch, id: lacy}\n")
    sh = lambda *d: [{"dur": x, "en": True} for x in d]  # noqa: E731
    m = {"streamers": {"Kai Cenat": {"shorts": sh(15, 20, 20, 36, 126) + [{"dur": 90, "en": False}]},
                       "Lacy": {"shorts": sh(21)}}}
    assert M.target_length("kaicenat", m, wl) == 20                            # Kai's own market
    assert M.target_length("lacy", m, wl) == 21                                # too few -> market-wide median
    assert M.target_length("kaicenat", {"streamers": {"Kai Cenat": {"shorts": sh(3, 4, 5)}}}, wl) == 8   # floor
    assert M.target_length("kaicenat", {"streamers": {}}, wl) is None        # no data at all
