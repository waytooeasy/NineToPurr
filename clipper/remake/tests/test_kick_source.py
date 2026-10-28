"""Kick streamers' Shorts are rebuilt from their Kick streams (Adin Ross, N3on, Clavicular, Ice Poseidon, xQc)."""
from datetime import datetime, timezone
from pathlib import Path

from remake import source
from remake.tests.test_muted_vod import playlist

SRC = "https://stream.kick.com/x/ivs/v1/1/ABo/2026/10/27/9/38/KofK/media/hls/master.m3u8"
MASTER = "\n".join([
    "#EXTM3U",
    '#EXT-X-STREAM-INF:BANDWIDTH=6848883,CODECS="avc1.64002A,mp4a.40.2",RESOLUTION=1920x1080,FRAME-RATE=60.000',
    "1080p60/playlist.m3u8",
    '#EXT-X-STREAM-INF:BANDWIDTH=3480869,RESOLUTION=1280x720',
    "720p60/playlist.m3u8",
    '#EXT-X-STREAM-INF:BANDWIDTH=230000,RESOLUTION=284x160',
    "160p30/playlist.m3u8"])


class Kc:
    def get_videos(self, slug):
        return [
            {"start_time": "2026-10-28 09:55:34", "duration": 0, "is_live": True, "source": SRC.replace("KofK", "Live"),
             "video": {"uuid": "live-uuid"}},
            {"start_time": "2026-10-27 09:38:50", "duration": 7280000, "is_live": False, "source": SRC,
             "video": {"uuid": "4fd9f002"}},
            {"start_time": "2026-10-20 09:00:00", "duration": 3600000, "is_live": False, "source": SRC,
             "video": {"uuid": "old"}}]


def test_kick_streams_before_the_short_become_plans_with_their_playlists():
    pub = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    got = source.kick_vods(Kc(), "adinross", pub, now=datetime(2026, 10, 28, 11, 0, tzinfo=timezone.utc))
    assert [v["id"] for v in got] == ["kick:4fd9f002"]                  # live one is after it, old one too old
    assert source._KICK_SRC["kick:4fd9f002"] == SRC
    plans = source.plans_for({"id": "s", "published": "2026-10-27T12:00:00Z"}, kicks=["adinross"], kc=Kc())
    assert plans == [("kick:4fd9f002", "adinross", None, None, (0.0, 7280.0))]   # it ended before the Short


def test_a_short_from_the_stream_live_now_searches_up_to_its_publish_time():
    pub = datetime(2026, 10, 28, 10, 30, tzinfo=timezone.utc)
    got = source.kick_vods(Kc(), "adinross", pub, now=datetime(2026, 10, 28, 11, 0, tzinfo=timezone.utc))
    assert got[0]["id"] == "kick:live-uuid" and abs(got[0]["dur"] - 3866) < 1
    assert source.before_publish(got[0]["start"], got[0]["dur"], pub) == (0.0, 2066.0)


def test_best_1080p_for_video_smallest_for_the_audio_search():
    source._KICK_SRC["kick:v"] = SRC
    base = SRC.rsplit("/", 1)[0] + "/"
    assert source.kick_variant("kick:v", video=True, fetch=lambda u: MASTER) == base + "1080p60/playlist.m3u8"
    assert source.kick_variant("kick:v", video=False, fetch=lambda u: MASTER) == base + "160p30/playlist.m3u8"
    assert source.vod_url("kick:v") == "https://kick.com/video/v" and source.platform_of("kick:v") == "kick"


class Runner:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        Path(cmd[-1] if cmd[0] == "ffmpeg" else cmd[cmd.index("-o") + 1]).write_bytes(b"x")

        class R:
            returncode, stdout, stderr = 0, "", ""
        return R()


def fetch(u):
    return MASTER if u.endswith("master.m3u8") else playlist(n=600, seg=12.5)


def test_kick_section_and_audio_come_from_the_playlists_without_yt_dlp_sections(tmp_path):
    source._KICK_SRC["kick:4fd9f002"] = SRC
    run = Runner()
    out = source.download_video("kick:4fd9f002", 3000.0, 3060.0, tmp_path / "sec0.mp4", runner=run, fetch=fetch,
                                audio_check=lambda p: True)
    assert out.exists()
    ff = run.calls[-1]
    assert ff[0] == "ffmpeg" and ff[ff.index("-ss") + 1] == "12.500"           # from the segment before (1 s pad)
    assert not any("--download-sections" in c for c in run.calls)
    run = Runner()
    source._kick_audio("kick:4fd9f002", tmp_path / "vod.m4a", runner=run, fetch=fetch)
    assert run.calls[0][0] != "ffmpeg" and run.calls[0][-1].endswith("160p30/playlist.m3u8")   # whole: parallel HLS
    assert run.calls[-1][run.calls[-1].index("-vn") + 1:] == ["-c:a", "copy", str(tmp_path / "vod.m4a")]


def test_kick_slugs_come_from_the_watchlist(tmp_path):
    wl = tmp_path / "w.yaml"
    wl.write_text("streamers:\n  - {name: Adin Ross, platform: kick, id: adinross}\n"
                  "  - {name: Jynxzi, platform: twitch, id: jynxzi}\n")
    assert source.kick_slugs(["Adin Ross"], "", wl) == ["adinross"]
    assert source.kick_slugs(["Jynxzi"], "adin ross and jynxzi", wl) == ["adinross"]
