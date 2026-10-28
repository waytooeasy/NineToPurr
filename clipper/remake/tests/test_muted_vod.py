"""Twitch sections come from the segments that cover them; a muted stream is skipped, never crashes (2026-10-28)."""
from pathlib import Path

import pytest

from remake import source

URL = "https://cdn.example/abc_plaqueboymax/1080p60/index-muted-XYZ.m3u8"


def playlist(n=400, seg=10.0, muted=()):
    lines = ["#EXTM3U", "#EXT-X-VERSION:6", "#EXT-X-TARGETDURATION:13", '#EXT-X-MAP:URI="init-0.mp4"']
    for i in range(n):
        lines += [f"#EXTINF:{seg:.3f},", f"{i}-muted.mp4" if i in muted else f"{i}.mp4"]
    return "\n".join(lines + ["#EXT-X-ENDLIST"])


def test_window_keeps_only_the_segments_around_the_moment_with_the_init_segment():
    text, off, muted = source.hls_window(playlist(muted=range(0, 22)), URL, 2907.0, 2988.0)
    segs = [l for l in text.splitlines() if l.endswith(".mp4") and not l.startswith("#")]
    assert segs[0] == "https://cdn.example/abc_plaqueboymax/1080p60/290.mp4"     # absolute, from the moment on
    assert segs[-1].endswith("/298.mp4") and len(segs) == 9
    assert '#EXT-X-MAP:URI="https://cdn.example/abc_plaqueboymax/1080p60/init-0.mp4"' in text
    assert abs(off - 7.0) < 1e-6 and muted == 0.0                                 # its muted start is not read
    assert text.rstrip().endswith("#EXT-X-ENDLIST")


def test_muted_share_and_nothing_outside_the_vod():
    _, _, muted = source.hls_window(playlist(muted=range(290, 296)), URL, 2907.0, 2988.0)
    assert abs(muted - 6 / 9) < 1e-6
    assert source.hls_window(playlist(n=10), URL, 2907.0, 2988.0) is None


class Runner:
    def __init__(self, url=URL, ffmpeg_ok=True):
        self.url, self.ffmpeg_ok, self.calls = url, ffmpeg_ok, []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)

        class R:
            returncode, stdout, stderr = 0, "", ""
        r = R()
        if "-g" in cmd:
            r.stdout = self.url + "\n"
        elif cmd[0] == "ffmpeg":
            if not self.ffmpeg_ok:
                raise source.subprocess.CalledProcessError(1, cmd)
            Path(cmd[-1]).write_bytes(b"mp4")
        else:                                   # yt-dlp's own sections (the fallback)
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"mp4")
        return r


def test_section_is_cut_from_its_own_segments(tmp_path):
    run = Runner()
    out = source.download_video("2911870173", 2907.0, 2988.0, tmp_path / "sec0.mp4", runner=run,
                                fetch=lambda u: playlist(muted=range(0, 22)), audio_check=lambda p: True)
    ff = next(c for c in run.calls if c[0] == "ffmpeg")
    assert ff[ff.index("-ss") + 1] == "7.000" and ff[ff.index("-t") + 1] == "81.000"
    assert out.exists() and not any("--download-sections" in c for c in run.calls)
    assert not (tmp_path / "sec0.m3u8").exists()


def test_a_muted_moment_is_skipped_before_downloading(tmp_path):
    run = Runner()
    with pytest.raises(source.NotFound, match="muted"):
        source.download_video("2911870173", 2907.0, 2988.0, tmp_path / "sec0.mp4", runner=run,
                              fetch=lambda u: playlist(muted=range(285, 300)), audio_check=lambda p: True)
    assert not any(c[0] == "ffmpeg" for c in run.calls)


def test_falls_back_to_yt_dlp_sections_and_a_soundless_section_is_a_skip_not_a_crash(tmp_path):
    run = Runner(ffmpeg_ok=False)
    with pytest.raises(source.Muted, match="without its sound track"):
        source.download_video("2911870173", 2907.0, 2988.0, tmp_path / "sec0.mp4", runner=run,
                              fetch=lambda u: playlist(), audio_check=lambda p: False)
    assert any("--download-sections" in c for c in run.calls)                    # tried the old way too
    assert not (tmp_path / "sec0.mp4").exists()                                   # no soundless file left behind
