import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from radar import heat, top_clips
from radar.tests.test_radar import migrate_db

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def opp(D, W, live=False, sat=0):
    return heat.compute_heat(D, W, live, sat)["opportunity"]


def test_popping_today_not_weekly_beats_steady():
    pop = heat.compute_heat(D=50_000, W=55_000)      # baseline ~7.9k/day, today 50k
    steady = heat.compute_heat(D=8_000, W=56_000)    # same weekly volume, flat
    assert pop["momentum"] > 5 and steady["momentum"] == pytest.approx(1, abs=0.01)
    assert pop["heat"] > steady["heat"]


def test_weekly_strong_but_quiet_today_ranks_below_popping():
    quiet = heat.compute_heat(D=100, W=700_000)      # huge week, dead today
    pop = heat.compute_heat(D=40_000, W=60_000)
    assert quiet["momentum"] < 0.01
    assert quiet["heat"] >= 0                        # floor: never negative
    assert pop["heat"] > quiet["heat"]


def test_formula_values_and_live_bonus():
    r = heat.compute_heat(D=0, W=0)
    assert r["heat"] == 0 and r["momentum"] == 1
    r = heat.compute_heat(D=99, W=0)  # B=0, momentum=100
    import math
    assert r["heat"] == pytest.approx(math.log(100) * (1 + 0.5 * math.log2(100)))
    assert opp(1000, 7000, live=True) == pytest.approx(opp(1000, 7000) + heat.LIVE_BONUS)


def test_saturation_penalty():
    base = heat.compute_heat(5000, 14000)
    sat = heat.compute_heat(5000, 14000, saturation=10)
    assert sat["heat"] == base["heat"]
    assert sat["opportunity"] == pytest.approx(base["heat"] / 2)


def test_cap_and_max_two_per_streamer():
    o = {"A": 100.0, "B": 1.0, "C": 1.0, "D": 1.0, "E": 1.0, "F": 1.0}
    for seed in range(20):
        s = heat.allocate(o, cap=5, now=NOW, rng=random.Random(seed))
        assert sum(s.values()) == 5
        assert max(s.values()) <= 2
    assert sum(heat.allocate(o, cap=3, now=NOW, rng=random.Random(1)).values()) == 3
    # fewer streamers than needed: cap can't be filled past max_per
    assert sum(heat.allocate({"A": 1, "B": 1}, cap=9, now=NOW).values()) == 4


def test_slots_proportional_to_opportunity():
    # all recently posted -> no exploration slot, pure proportional
    lp = {n: NOW for n in "ABC"}
    s = heat.allocate({"A": 6.0, "B": 3.0, "C": 1.0}, cap=4, last_posted=lp, now=NOW, rng=random.Random(0))
    assert s == {"A": 2, "B": 1, "C": 1} or s == {"A": 2, "B": 2}
    assert s["A"] == 2


def test_exploration_slot_picks_unposted_top15_only():
    o = {f"S{i:02d}": 100.0 - i for i in range(20)}
    lp = {n: NOW - timedelta(hours=5) for n in o}                 # everyone posted recently...
    lp["S07"] = NOW - timedelta(days=4)                           # ...except S07 (top 15)
    lp["S18"] = NOW - timedelta(days=9)                           # stale but outside top 15
    for seed in range(10):
        s = heat.allocate(o, cap=5, last_posted=lp, now=NOW, rng=random.Random(seed))
        assert s["S07"] >= 1 and "S18" not in s
    del lp["S07"]
    del lp["S03"]  # never posted counts as eligible
    s = heat.allocate(o, cap=5, last_posted=lp, now=NOW, rng=random.Random(3))
    assert s.get("S03", 0) >= 1 or s.get("S07", 0) >= 1


def test_no_exploration_candidate_uses_slot_proportionally():
    lp = {"A": NOW, "B": NOW}
    s = heat.allocate({"A": 5.0, "B": 5.0}, cap=3, last_posted=lp, now=NOW, rng=random.Random(0))
    assert sum(s.values()) == 3


def test_load_watchlist_real_config():
    cfg = heat.load_watchlist()
    assert cfg["cap"] == 6 and 28 <= len(cfg["streamers"]) <= 40
    assert cfg["streamers"]["Adin Ross"] == [{"platform": "kick", "id": "adinross"}]   # Kick on (D45)
    assert {e["platform"] for e in cfg["streamers"]["xQc"]} == {"twitch", "kick"}
    assert {e["platform"] for e in cfg["streamers"]["IShowSpeed"]} == {"twitch", "youtube"}


def test_clip_views_splits_24h_and_7d():
    clips = [{"view_count": 100, "created_at": "2026-10-16T06:00:00Z"},
             {"view_count": 50, "created_at": "2026-10-12T06:00:00Z"}]
    assert heat.clip_views(clips, NOW) == (100, 150)


def test_run_writes_table_and_allocates(tmp_path):
    db = sqlite3.connect(":memory:")
    migrate_db(db)
    cfg = {"cap": 3, "max_per": 2, "explore_days": 3, "explore_top_n": 15, "streamers": {
        "Hot": [{"platform": "twitch", "id": "hot"}],
        "Flat": [{"platform": "twitch", "id": "flat"}, {"platform": "youtube", "id": "@flat"}],
        "Crowded": [{"platform": "twitch", "id": "crowded"}]}}
    data = {"hot": (40_000, 50_000), "flat": (3_000, 21_000), "@flat": (1_000, 7_000),
            "crowded": (40_000, 50_000)}

    def views(e, now):
        if e["id"] == "boom":
            raise RuntimeError
        return data[e["id"]]

    rows, slots = heat.run(db, cfg, views, lambda e: e["id"] == "hot", {"crowded": 20.0}, NOW,
                           rng=random.Random(0))
    assert rows["Flat"]["D"] == 4_000 and rows["Flat"]["W"] == 28_000   # platforms summed
    assert rows["Hot"]["live_now"] == 1
    assert rows["Crowded"]["opportunity"] < rows["Hot"]["opportunity"]
    assert db.execute("SELECT count(*) FROM streamer_heat").fetchone()[0] == 3
    assert sum(slots.values()) == 3 and max(slots.values()) <= 2
    heat.run(db, cfg, views, lambda e: False, {}, NOW + timedelta(minutes=30))
    assert db.execute("SELECT count(*) FROM streamer_heat").fetchone()[0] == 6


def test_measure_survives_failing_entry():
    def views(e, now):
        raise RuntimeError("x")
    rows = heat.measure({"A": [{"platform": "twitch", "id": "a"}]}, views, lambda e: False, {}, NOW)
    assert rows["A"]["D"] == 0


def test_last_posted_from_posts_table():
    db = sqlite3.connect(":memory:")
    migrate_db(db)
    db.execute("INSERT INTO creators (name) VALUES ('kaicenat')")
    db.execute("INSERT INTO sources (creator_id, url) VALUES (1, 'u')")
    db.execute("INSERT INTO clips (source_id, start_s, end_s) VALUES (1, 0, 10)")
    db.execute("INSERT INTO accounts (platform, handle) VALUES ('youtube', 'x')")
    db.execute("INSERT INTO posts (clip_id, account_id, posted_at) VALUES (1, 1, '2026-10-15 09:00:00')")
    st = {"Kai Cenat": [{"platform": "twitch", "id": "kaicenat"}], "Other": [{"platform": "twitch", "id": "o"}]}
    lp = heat.last_posted(db, st)
    assert lp == {"Kai Cenat": datetime(2026, 10, 15, 9, tzinfo=timezone.utc)}


def test_saturation_loader(tmp_path):
    p = tmp_path / "s.json"
    p.write_text('{"Kai Cenat": 7}')
    assert heat.load_saturation(str(p)) == {"kai cenat": 7.0}
    assert heat.load_saturation(str(tmp_path / "missing.json")) == {}
    assert heat.load_saturation(None) == {}


def test_top_clips_hooks():
    assert top_clips.filter_allowed(["a", "B", "c"], None) == ["a", "B", "c"]
    assert top_clips.filter_allowed(["a", "B", "c"], ["b"]) == ["B"]
    cands = [{"creator": "kaicenat", "clip_id": i} for i in range(3)] + [{"creator": "x", "clip_id": 9}]
    out = top_clips.apply_allocation(cands, {"Kai Cenat": 2}, {"kaicenat": "Kai Cenat"})
    assert [c["clip_id"] for c in out] == [0, 1]
    doc = heat.allocation_doc({"streamers": {"Kai Cenat": [{"platform": "youtube", "id": "@KaiCenat"},
                                                         {"platform": "twitch", "id": "kaicenat"}]}},
                              {"Kai Cenat": 1})
    assert doc["ids"]["kaicenat"] == "Kai Cenat"
