"""Same moments as the top clippers (D54): popping Shorts -> the streamer's own clip of that moment ->
posted first, our title paraphrases theirs, cut to their length. Offline: the model and the clip APIs are fakes."""
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

CLIPPER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(CLIPPER), str(CLIPPER / "editor")]

import run_pipeline  # noqa: E402
from radar import market as M, match, top_clips  # noqa: E402
from radar.tests.test_radar import migrate_db  # noqa: E402

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
ISO = "%Y-%m-%dT%H:%M:%SZ"


def iso(h):
    return (NOW - timedelta(hours=h)).strftime(ISO)


def clip(cid, title, views, h, creator="jynxzi", dur=30.0, source=None, video=None, offset=None):
    c = {"clip_id": cid, "creator": creator, "broadcaster_id": None, "title": title,
         "url": f"https://clips.twitch.tv/{cid}", "video_id": video, "vod_offset": offset, "duration_s": dur,
         "view_count": views, "created_at": iso(h)}
    if source:
        c["source"] = source
    c["views_per_hour"] = top_clips.score(c, NOW)
    return c


SHORTS = [
    {"id": "s0", "title": "Jynxzi's Mom Walks In On Stream 😭", "vph": 9000, "dur": 22, "published": iso(5),
     "en": True, "desc": "#jynxzi"},
    {"id": "s1", "title": "Jynxzi Rages At Teammate", "vph": 4000, "dur": 35, "published": iso(3), "en": True},
    {"id": "s2", "title": "Jynxzi Hits A Crazy Ace", "vph": 2000, "dur": 18, "published": iso(30), "en": True},
    {"id": "s3", "title": "Jynxzi ist endlich da", "vph": 50000, "dur": 20, "published": iso(2), "en": False},
]
CLIPS = [clip("c-mom", "mom walked in LMAO", 20_000, 8), clip("c-ace", "ACE", 9_000, 6),
         clip("c-merch", "RANKED | !merch", 3_000, 10)]
MARKET = {"updated": iso(1), "window_h": 48, "streamers": {"Jynxzi": {"demand_vph": 15000, "shorts": SHORTS}}}


@pytest.fixture
def con():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    migrate_db(db)
    yield db
    db.close()


def reply(*pairs):
    return lambda prompt: "Here:\n" + json.dumps([{"short": s, "clip": c, "confidence": p} for s, c, p in pairs])


def test_match_streamer_keeps_confident_matches_made_before_the_short():
    seen = []
    ask = reply(("S0", "C0", 0.93), ("S1", "C2", 0.4), ("S2", "C1", 0.9), ("S9", "C0", 0.99), ("S1", None, 0))
    out = match.match_streamer("Jynxzi", SHORTS[:3], CLIPS, lambda p: seen.append(p) or ask(p))
    # s1 -> merch clip: low confidence; s2 (posted 30 h ago) <- ace clip made 6 h ago: impossible; S9: no such
    assert [(s["id"], c["clip_id"]) for s, c, _ in out] == [("s0", "c-mom")]
    assert "mom walked in LMAO" in seen[0] and "Jynxzi's Mom Walks In" in seen[0] and "desc: #jynxzi" in seen[0]
    assert match.match_streamer("Jynxzi", SHORTS, CLIPS, lambda p: "sorry, no JSON") == []
    assert match.match_streamer("Jynxzi", [], CLIPS, lambda p: 1 / 0) == []          # nothing to ask


def test_run_stores_matches_and_candidates_rank_by_the_shorts_views(con):
    ask = reply(("S0", "C0", 0.9), ("S1", "C1", 0.8))
    r = match.run(con, MARKET, ["Jynxzi", "Nobody"], lambda n: CLIPS, NOW, ask)
    assert r == {"streamers": 1, "matches": 2}
    cands = match.candidates(con, NOW)
    assert [(c["clip_id"], c["match"]["title"]) for c in cands] == [
        ("c-mom", "Jynxzi's Mom Walks In On Stream 😭"), ("c-ace", "Jynxzi Rages At Teammate")]
    assert match.for_clip(con, "c-mom") == {"title": "Jynxzi's Mom Walks In On Stream 😭", "dur": 22, "vph": 9000,
                                            "layout": None}
    assert match.for_clip(con, "c-merch") is None
    assert match.candidates(con, NOW + timedelta(hours=match.KEEP_H + 1)) == []      # old matches expire


def test_one_failing_streamer_does_not_stop_the_rest(con):
    m = {"streamers": {"A": {"shorts": SHORTS[:1]}, "B": {"shorts": SHORTS[:1]}}}

    def clips_for(name):
        if name == "A":
            raise RuntimeError("twitch down")
        return CLIPS
    assert match.run(con, m, ["A", "B"], clips_for, NOW, reply(("S0", "C0", 0.9))) == {"streamers": 1, "matches": 1}


def test_due_once_per_market_data(con):
    assert match.due(con, M.fresh_at(MARKET))
    match.run(con, MARKET, [], lambda n: [], NOW, reply())
    assert not match.due(con, M.fresh_at(MARKET))
    assert match.due(con, M.fresh_at({**MARKET, "refreshed": (NOW + timedelta(hours=6)).strftime(ISO)}))


def test_match_step_matches_the_streamers_radar_posts(con, tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_MARKET", str(tmp_path / "m.json"))
    assert run_pipeline.match_step(con, NOW, ask=reply()) == "skipped: no market scan"
    M.write({**MARKET, "streamers": {**MARKET["streamers"], "Valkyrae": {"demand_vph": 99, "shorts": SHORTS[:1]}}})
    for name, opp in (("Jynxzi", 9), ("Valkyrae", 1), ("Nobody", 50)):   # Nobody: not in the scan
        con.execute("INSERT INTO streamer_heat (streamer, ts, D, W, B, momentum, heat, opportunity)"
                    " VALUES (?, ?, 0, 0, 0, 1, 0, ?)", (name, iso(0), opp))
    asked = []
    out = run_pipeline.match_step(con, NOW, ask=reply(("S0", "C0", 0.9)),
                                  clips_for=lambda n: asked.append(n) or CLIPS)
    assert out == "matched 2 moments (2 streamers)" and asked == ["Jynxzi", "Valkyrae"]   # Heat order
    assert run_pipeline.match_step(con, NOW + timedelta(minutes=20), ask=reply()) == "fresh"


def test_own_clips_reads_twitch_and_kick_and_survives_a_dead_channel():
    class Tw:
        def broadcaster_id(self, login):
            return "b-" + login

        def get_clips(self, bid, start, end, max_clips=500):
            assert (end - start).days == match.CLIP_DAYS and max_clips == 100
            return [{"id": "t1", "url": "u", "title": "x", "view_count": 5, "duration": 30, "created_at": iso(3)}]

    class Kc:
        def get_clips(self, slug, window="week", max_pages=1):
            raise RuntimeError("blocked")
    out = run_pipeline.own_clips([{"platform": "twitch", "id": "xQc"}, {"platform": "kick", "id": "xqc"}], NOW,
                                 {"twitch": Tw(), "kick": Kc()})
    assert [(c["clip_id"], c["creator"]) for c in out] == [("t1", "xqc")]


def test_matched_moments_go_first_and_join_when_radar_did_not_pull_them(con):
    match.run(con, MARKET, ["Jynxzi"], lambda n: CLIPS, NOW, reply(("S0", "C0", 0.9), ("S1", "C1", 0.8)))
    pulled = [clip("c-hot", "huge moment", 90_000, 1), clip("c-ace", "ACE", 9_100, 6)]   # c-mom not pulled
    out = run_pipeline.same_moments_first(con, pulled, NOW)
    assert [c["clip_id"] for c in out] == ["c-mom", "c-ace", "c-hot"]
    assert out[1]["view_count"] == 9_100                                  # Radar's fresher copy keeps its stats
    other = run_pipeline.same_moments_first(con, pulled, NOW, allowed=["Somebody"])
    assert [c["clip_id"] for c in other] == ["c-hot", "c-ace"]            # no slot: matched moments not added


def test_a_matched_second_clip_of_one_moment_marks_the_first():
    a = clip("k1", "mom", 50, 8, creator="jynxzi", source="kick")
    b = clip("t1", "mom walked in", 9, 8.002, creator="jynxzi")
    assert run_pipeline.same_footage(a, b) and not run_pipeline.same_footage(a, clip("t2", "x", 9, 7))
    v1, v2 = clip("v1", "a", 1, 8, video="9", offset=100), clip("v2", "b", 1, 8, video="9", offset=200)
    assert not run_pipeline.same_footage(v1, v2)                          # Twitch VOD offsets decide
    assert not run_pipeline.same_footage(a, {**b, "source": "youtube"})


class Tw:
    """Twitch fake: the given raw clips for every login."""

    def __init__(self, raw):
        self.raw = raw

    def broadcaster_id(self, login):
        return login

    def get_clips(self, bid, start, end, max_clips=500):
        return list(self.raw)


def raw(cid, title, views, h, dur=30):
    return {"id": cid, "url": f"https://clips.twitch.tv/{cid}", "title": title, "view_count": views,
            "duration": dur, "created_at": iso(h)}


def test_radar_posts_the_matched_moment_first_and_never_twice(con):
    match.run(con, MARKET, ["Jynxzi"], lambda n: CLIPS, NOW, reply(("S0", "C0", 0.9)))
    alloc = {"slots": {"Jynxzi": 1}, "ids": {"jynxzi": "Jynxzi"}}
    kick = []

    def step(tw):
        return run_pipeline.radar_step(con, tw, ["jynxzi"], allocate=lambda c, n: alloc, youtube=lambda *a: [],
                                       now=NOW, kick=lambda *a: list(kick), kick_from=["jynxzi"])
    assert len(step(Tw([raw("c-hot", "huge moment", 90_000, 1)]))) == 1
    rows = con.execute("SELECT r.clip_id FROM clips c JOIN radar_candidates r ON r.clips_id=c.id").fetchall()
    assert [r[0] for r in rows] == ["c-mom"]                 # the clippers' moment beat a bigger Twitch clip
    # Later the Kick copy of that same moment shows up (or gets matched): never posted twice
    con.execute("DELETE FROM moment_matches")
    con.execute("UPDATE clips SET state='killed'")           # frees the slot; the moment still counts as done
    con.commit()
    kick[:] = [clip("k-mom", "mom walked in", 900_000, 8.001, source="kick")]
    assert step(Tw([])) == []
    assert len(step(Tw([raw("c-new", "new moment", 500, 2)]))) == 1


def test_pool_shows_yesterdays_rising_clip_next_to_the_weeks_big_ones():
    big = [clip(f"old{i}", f"old {i}", 50_000 - i, 90) for i in range(30)]      # 90 h old, many views
    fresh = clip("new", "jynxzi hits unreal", 3_000, 5)                         # 5 h old, rising fast
    out = match.pool(big + [fresh])
    assert len(out) == 31 and "new" in [c["clip_id"] for c in out]               # 25 by views + the other 6
    assert [c["view_count"] for c in out] == sorted((c["view_count"] for c in out), reverse=True)
    assert "new" not in [c["clip_id"] for c in match.pool(big + [fresh], n_views=25, n_fresh=0)]


def test_verdict_same_passes_related_does_not():
    ask = lambda p: json.dumps([{"short": "S0", "clip": "C0", "match": "same"},        # noqa: E731
                                {"short": "S1", "clip": "C1", "match": "related"}])
    out = match.match_streamer("Jynxzi", SHORTS[:2], CLIPS, ask)
    assert [(s["id"], c["clip_id"], conf) for s, c, conf in out] == [("s0", "c-mom", 0.9)]


def test_market_refresh_follows_the_streamers_radar_posts(con, tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_MARKET", str(tmp_path / "m.json"))
    M.write({**MARKET, "updated": iso(7)})                                       # full scan 7 h ago
    con.execute("INSERT INTO streamer_heat (streamer, ts, D, W, B, momentum, heat, opportunity)"
                " VALUES ('Jynxzi', ?, 0, 0, 0, 1, 0, 9)", (iso(0),))
    seen = {}
    monkeypatch.setattr(M, "refresh", lambda d, key, now=None, names=None:
                        seen.update(names=names) or {**d, "refreshed": now.strftime(ISO)})
    assert run_pipeline.market_step(NOW, key="K", con=con) == "refreshed Jynxzi" and seen["names"] == ["Jynxzi"]


def test_neighbouring_clips_are_not_one_moment_and_the_matched_clip_is_posted(con):
    # 2026-10-21: "Jason asks Ron out" (VOD 2872-2932 s) was matched; Radar pulled the fry clip next to it
    # (2840-2890 s, 18 s shared), posted that as the matched moment, then blocked the real one as "posted".
    ask = clip("ask", "Jason asks Ron out to the pumpkin patch", 169, 37, creator="stableronaldo", dur=60,
               video="2904593598", offset=2872)
    fry = clip("fry", ".", 5, 0.5, creator="stableronaldo", dur=50, video="2904593598", offset=2840)
    assert not run_pipeline.same_footage(ask, fry)
    assert run_pipeline.same_footage(ask, {**fry, "vod_offset": 2860})          # 30 of 50 s shared: one moment
    m = {"streamers": {"Stable Ronaldo": {"shorts": [{"id": "r0", "title": "Jason And Ron Goes On A Date", "vph": 2500,
                                                      "dur": 30, "en": True}]}}}
    match.run(con, m, ["Stable Ronaldo"], lambda n: [ask], NOW, reply(("S0", "C0", 0.9)))
    out = run_pipeline.same_moments_first(con, [fry], NOW)
    assert [c["clip_id"] for c in out] == ["ask", "fry"] and "match" not in out[1]
    twin = {**fry, "clip_id": "twin", "vod_offset": 2875}                      # a near copy of the matched clip
    assert [c["clip_id"] for c in run_pipeline.same_moments_first(con, [twin, fry], NOW)] == ["ask", "fry"]


def test_the_matched_clippers_layout_is_read_from_the_thumbnail_and_kept(con):
    looks = {"s0": '{"layout": "fit"}', "s1": "no idea"}
    assert match.thumb_layout("s0", look=lambda b: looks["s0"], fetch=lambda sid: b"jpg") == "fit"
    assert match.thumb_layout("s1", look=lambda b: looks["s1"], fetch=lambda sid: b"jpg") is None
    assert match.thumb_layout("s0", look=lambda b: 1 / 0, fetch=lambda sid: b"jpg") is None
    match.run(con, MARKET, ["Jynxzi"], lambda n: CLIPS, NOW, reply(("S0", "C0", 0.9)),
              layout_of=lambda sid: "fit" if sid == "s0" else None)
    assert match.for_clip(con, "c-mom")["layout"] == "fit"
    assert match.candidates(con, NOW)[0]["match"]["layout"] == "fit"


def test_layouts_are_filled_later_and_shared_with_clips_of_the_same_scene(con):
    ask = clip("ask", "Jason asks Ron out", 169, 37, creator="stableronaldo", dur=60, video="2904593598", offset=2872)
    m = {"streamers": {"Stable Ronaldo": {"shorts": [{"id": "r0", "title": "Jason And Ron Goes On A Date",
                                                      "vph": 2500, "dur": 30, "en": True}]}}}
    match.run(con, m, ["Stable Ronaldo"], lambda n: [ask], NOW, reply(("S0", "C0", 0.9)), layout_of=lambda sid: None)
    assert match.for_clip(con, "ask")["layout"] is None
    looks = iter([None, "fit"])
    assert match.fill_layouts(con, layout_of=lambda sid: next(looks)) == 0          # first look failed: retry later
    assert match.fill_layouts(con, layout_of=lambda sid: next(looks)) == 1
    fry = clip("fry", ".", 5, 0.5, creator="stableronaldo", dur=50, video="2904593598", offset=2840)
    other = clip("other", "x", 5, 0.5, creator="stableronaldo", dur=50, video="2904593598", offset=9000)
    top_clips.store(con, [fry, other])
    assert match.nearby_layout(con, "fry") == "fit" and match.nearby_layout(con, "other") is None
    assert match.fill_layouts(con, layout_of=lambda sid: "full") == 0                # nothing left to fill
