import json
import subprocess
from pathlib import Path

import yaml

import scout_resolve as res
import trend_scout
from test_trend_scout import NOW, Resp, Session

FIX = Path(__file__).parent / "fixtures"


def fx(name):
    return json.loads((FIX / name).read_text())


class ApiSession(Session):
    """channels.list?forHandle -> fixture for @NexxoRecaps only; search + stats fixtures."""

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if "feeds/videos.xml" in url:
            return Resp(text=(FIX / "feed.xml").read_text())
        if url.endswith("/search"):
            return Resp(js=fx("search_channels.json"))
        if url.endswith("/channels") and "forHandle" in params:
            return Resp(js=fx("channels_handle.json") if params["forHandle"] == "@NexxoRecaps"
                        else {"items": []})
        if url.endswith("/channels"):
            return Resp(js=fx("channels_stats.json"))
        return Resp(js=fx("videos_list.json"))


def fake_run(stdout=None, code=0):
    def run(cmd, **kw):
        run.cmds.append(cmd)
        out = stdout if stdout is not None else (FIX / "ytdlp_channel.json").read_text()
        return subprocess.CompletedProcess(cmd, code, stdout=out)
    run.cmds = []
    return run


def test_resolve_via_api():
    s = ApiSession()
    run = fake_run()
    assert res.resolve_handle("NexxoRecaps", "KEY", s, run) == "UCnexxo0000000000000001"
    assert s.calls[0][1]["forHandle"] == "@NexxoRecaps" and run.cmds == []


def test_resolve_via_ytdlp_without_key():
    run = fake_run()
    assert res.resolve_handle("@GoofyRecaps", None, ApiSession(), run) == "UCytdlp000000000000000A"
    assert run.cmds[0][-1] == "https://www.youtube.com/@GoofyRecaps"
    assert "--playlist-items" in run.cmds[0] and "--skip-download" in run.cmds[0]


def test_api_miss_falls_back_to_ytdlp_and_total_failure_is_none():
    assert res.resolve_handle("@Other", "KEY", ApiSession(), fake_run()) == "UCytdlp000000000000000A"
    assert res.resolve_handle("@Bad", None, None, fake_run(code=1)) is None
    assert res.resolve_handle("@Bad", None, None, fake_run(stdout="{}")) is None


def test_resolve_channels_cache_and_fixme(tmp_path):
    cache = tmp_path / "channel_cache.json"
    chans = [{"handle": "@NexxoRecaps"}, {"handle": "@Typo"}, {"name": "Manual", "channel_id": "UC9"},
             {"name": "Nothing"}]
    run = fake_run(code=1)
    out, fixme, _ = res.resolve_channels(chans, [], cache, "KEY", ApiSession(), run)
    assert [c["channel_id"] for c in out] == ["UCnexxo0000000000000001", "UC9"]
    assert out[0]["name"] == "@NexxoRecaps"
    assert fixme == ["@Typo", "Nothing"]
    assert json.loads(cache.read_text()) == {"@NexxoRecaps": "UCnexxo0000000000000001"}
    # second run: served from cache, no network/subprocess for the cached handle
    s = ApiSession()
    out, _, _ = res.resolve_channels(chans[:1], [], cache, None, s, run)
    assert out[0]["channel_id"] == "UCnexxo0000000000000001" and s.calls == []


def test_discover_top_by_subscribers(tmp_path):
    out, fixme, notes = res.resolve_channels([], [{"streamer": "CaseOh", "count": 2}],
                                             tmp_path / "c.json", "KEY", ApiSession())
    assert [c["name"] for c in out] == ["Big Clips", "Mid Clips"]
    assert out[0]["streamers"] == ["CaseOh"] and not fixme and not notes


def test_discover_skipped_without_key(tmp_path):
    out, _, notes = res.resolve_channels([], [{"streamer": "CaseOh"}], tmp_path / "c.json")
    assert out == [] and "YOUTUBE_API_KEY missing" in notes[0]


def test_seed_config_shape():
    cfg = yaml.safe_load((Path(trend_scout.__file__).parent / "config" / "competitors.yaml").read_text())
    handles = [c["handle"] for c in cfg["channels"]]
    assert len(handles) >= 5 and len(set(handles)) == len(handles) and all(h.startswith("@") for h in handles)
    assert [d["streamer"] for d in cfg["discover"]] == ["IShowSpeed", "Kai Cenat", "CaseOh"]


def test_report_lists_fixme_first(tmp_path):
    cfg = tmp_path / "competitors.yaml"
    cfg.write_text(yaml.safe_dump({"channels": [{"handle": "@NexxoRecaps"}, {"handle": "@Typo"}]}))
    lib, rep = tmp_path / "library.md", tmp_path / "report.md"
    lib.write_text("# lib\n")
    trend_scout.scout(cfg, lib, rep, now=NOW, session=ApiSession(), twitch=None, llm=None,
                      api_key="KEY", creators=[], resolve_run=fake_run(code=1))
    text = rep.read_text()
    assert text.startswith("## Fix me") and "- @Typo" in text
    assert "@NexxoRecaps" not in text.split("\n\n")[1]
    assert (tmp_path / "channel_cache.json").exists()
