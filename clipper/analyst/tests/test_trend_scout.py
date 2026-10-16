import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

import scout_data as data
import scout_stats as stats
import trend_scout

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)  # a Friday
MONDAY = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
CH = {"name": "KaiClips", "channel_id": "UC1", "streamers": ["Kai Cenat"]}
ALIASES = {"Kai Cenat": ["kai"], "IShowSpeed": ["speed"], "Druski": []}


class Resp:
    def __init__(self, text="", js=None, status=200):
        self.text, self._js, self.status_code = text, js, status

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class Session:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if self.fail:
            raise RuntimeError("blocked")
        if "feeds/videos.xml" in url:
            return Resp(text=(FIX / "feed.xml").read_text())
        return Resp(js=json.loads((FIX / "videos_list.json").read_text()))


def videos():
    return data.parse_rss((FIX / "feed.xml").read_text(), CH)


def test_parse_rss():
    v = videos()
    assert [x["id"] for x in v] == ["v1", "v2", "v3", "v4"]
    assert v[0]["views"] == 120000 and v[0]["published"].hour == 8


def test_api_enrich_sets_duration_and_exact_views():
    v = data.enrich_api(videos(), "KEY", Session())
    assert v[0]["duration_s"] == 34 and v[0]["views"] == 130000 and v[0]["likes"] == 9000
    assert v[1]["duration_s"] == 65
    assert v[3]["duration_s"] is None


def test_api_failure_leaves_rss_data():
    v = data.enrich_api(videos(), "KEY", Session(fail=True))
    assert v[0]["views"] == 120000 and v[0]["duration_s"] is None


def test_iso_duration():
    assert data.parse_iso_duration("PT1H2M3S") == 3723
    assert data.parse_iso_duration("bad") is None


def test_ytdlp_fallback_when_rss_blocked_and_graceful_when_both_fail():
    def fake_run(cmd, **kw):
        assert "--skip-download" in cmd and "-J" in cmd
        return subprocess.CompletedProcess(cmd, 0, (FIX / "ytdlp.json").read_text(), "")
    got = data.fetch_channel(CH, Session(fail=True), ytdlp=lambda ch: data.fetch_ytdlp(ch, fake_run))
    assert [v["id"] for v in got] == ["y1"]  # undated entry dropped

    def boom(cmd, **kw):
        raise OSError("no yt-dlp")
    assert data.fetch_channel(CH, Session(fail=True), ytdlp=lambda ch: data.fetch_ytdlp(ch, boom)) == []


def test_fetch_all_skips_blank_channel_id():
    s = Session()
    got = data.fetch_all([CH, {"name": "x", "channel_id": ""}], None, s)
    assert len(got) == 4 and len(s.calls) == 1


def test_top_videos_last_7_days_by_vph():
    top = stats.top_videos(videos(), NOW)
    assert [v["id"] for v in top] == ["v1", "v2", "v3"]  # v4 older than 7 d
    assert stats.vph(top[0], NOW) == pytest.approx(120000 / 4)


def test_top_excludes_long_videos():
    v = data.enrich_api(videos(), "K", Session())
    v[0]["duration_s"] = 600
    assert "v1" not in [x["id"] for x in stats.top_videos(v, NOW)]


def test_patterns_hours_buckets_templates():
    m = stats.build_matchers(ALIASES)
    top = stats.top_videos(data.enrich_api(videos(), "K", Session()), NOW)
    top = [v for v in top if v["id"] != "v2"] + [dict(videos()[1], duration_s=65)]
    p = stats.patterns(top, m, NOW)
    assert {r["key"] for r in p["upload_hour_utc"]} == {8, 2, 20}
    assert {r["key"]: r["videos"] for r in p["upload_hour_asuncion"]}[5] == 1  # 08 UTC = 05 ASU
    assert {r["key"] for r in p["length_buckets"]} == {"31-45s", ">60s", "<=15s"}
    assert any(t["template"].startswith("{S} can't believe {S}") for t in p["title_templates"])
    assert dict(p["streamers"])["Kai Cenat"] == 2


def test_leaderboard_crowding_and_test_slot():
    vs = videos()
    other = dict(vs[0], id="z", channel="Other")
    m = stats.build_matchers(ALIASES)
    lb = {r["streamer"]: r for r in stats.leaderboard(vs + [other], m, NOW, 24 * 7, tracked=["druski"])}
    assert lb["Kai Cenat"]["clippers"] == 2 and lb["Kai Cenat"]["shorts"] == 3
    assert lb["IShowSpeed"]["shorts"] == 2
    assert lb["Druski"]["tracked"] is True and lb["Druski"]["test_slot"] is False
    assert all(r["streamer"] != "Druski" for r in stats.leaderboard(vs, m, NOW, 24))


def test_default_streamer_fallback_and_rising_candidates():
    m = stats.build_matchers(ALIASES)
    v = {"title": "wild moment", "default_streamers": ["Kai Cenat"]}
    assert stats.streamers_in(v, m) == ["Kai Cenat"]
    assert stats.rising_candidates(videos(), m) == [{"tag": "newguy", "videos": 2, "channels": 1}]


def test_ranking_score_trend_and_new_flag():
    lb24 = [{"streamer": "Kai Cenat", "total_vph": 100.0, "clippers": 4},
            {"streamer": "Druski", "total_vph": 100.0, "clippers": 1}]
    prev = [{"streamer": "Kai Cenat", "score": 50000.0}]
    r = {x["streamer"]: x for x in stats.build_ranking({"Kai Cenat": 200.0, "Druski": 200.0}, lb24, prev)}
    assert r["Kai Cenat"]["score"] == 5000.0 and r["Kai Cenat"]["trend"] == "down"
    assert r["Druski"]["score"] == 20000.0 and r["Druski"]["trend"] == "new"
    assert r["Druski"]["weight"] == 1.0 and r["Kai Cenat"]["weight"] == 0.25
    assert set(r["Druski"]) == {"streamer", "platform", "score", "weight", "trend"}


def test_clip_velocity_and_weights():
    clips = [{"view_count": 480, "created_at": "2026-10-16T00:00:00Z"}]
    assert stats.clip_velocity(clips, NOW) == 40.0
    lb7 = [{"streamer": "A", "views": 1000, "total_vph": 10.0, "clippers": 1},
           {"streamer": "B", "views": 1000, "total_vph": 10.0, "clippers": 4}]
    w = stats.build_weights([{"streamer": "A", "total_vph": 10.0}, {"streamer": "B", "total_vph": 10.0}], lb7)
    assert w == {"A": 1.0, "B": 0.25}
    rec = stats.weekly_recommendations(lb7, w, ["B", "Gone"])
    assert rec == {"add": ["A"], "drop": ["Gone"]}


class FakeTwitch:
    def _get(self, path, params):
        return {"data": [{"user_id": "1", "user_name": "KaiCenat"}]}

    def broadcaster_id(self, login):
        return {"kaicenat": "1", "druski": "2"}[login]

    def get_clips(self, bid, a, b, max_clips=100):
        return [{"view_count": 480, "created_at": "2026-10-16T00:00:00Z"}]


def cfg(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump({"channels": [CH], "aliases": {"Kai Cenat": ["kai cenat", "kaicenat"]}}))
    return p


def fake_llm(system, user):
    assert "STATS:" in user and "never suggest downloading" in system
    return json.dumps({"report": "\n".join(f"line {i}" for i in range(60)), "library": "# Library v2"})


def test_end_to_end_offline(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    lib = tmp_path / "formats" / "library.md"
    lib.parent.mkdir()
    lib.write_text("# Library v1")
    rep = tmp_path / "report.md"
    trend_scout.scout(cfg(tmp_path), lib, rep, now=MONDAY, session=Session(), twitch=FakeTwitch(),
                      llm=fake_llm, api_key="K", creators=["kaicenat", "druski"])
    assert lib.read_text() == "# Library v2\n"
    text = rep.read_text()
    assert "line 39" in text and "line 40" not in text  # LLM part capped at 40 lines
    assert "Weekly: 7-day leaderboard" in text and "Streamer leaderboard: last 24 h" in text
    ranking = json.loads((lib.parent / "creators_ranking.json").read_text())
    assert {"streamer", "platform", "score", "weight", "trend"} == set(ranking[0])
    assert "Kai Cenat" in [r["streamer"] for r in ranking]  # twitch name canonicalised to alias
    weights = json.loads((lib.parent / "creator_weights.json").read_text())
    assert all(0 <= w <= 1 for w in weights.values())
    # second run reads the previous ranking for the trend column
    trend_scout.scout(cfg(tmp_path), lib, rep, now=NOW, session=Session(), twitch=FakeTwitch(),
                      llm=fake_llm, creators=["kaicenat"])
    assert "Weekly" not in rep.read_text()  # Friday: no weekly section


def test_no_keys_no_network_degrades(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    lib = tmp_path / "library.md"
    lib.write_text("keep me")
    rep = tmp_path / "report.md"
    trend_scout.scout(cfg(tmp_path), lib, rep, now=NOW, session=Session(fail=True),
                      ytdlp=lambda ch: [], creators=[])
    assert lib.read_text() == "keep me"
    assert "no competitor data fetched" in rep.read_text()
    assert json.loads((tmp_path / "creators_ranking.json").read_text()) == []


def test_bad_llm_reply_keeps_library(tmp_path):
    lib = tmp_path / "library.md"
    lib.write_text("keep me")
    trend_scout.scout(cfg(tmp_path), lib, tmp_path / "r.md", now=NOW, session=Session(),
                      llm=lambda s, u: "not json", creators=[])
    assert lib.read_text() == "keep me"
    assert "LLM step skipped" in (tmp_path / "r.md").read_text()
