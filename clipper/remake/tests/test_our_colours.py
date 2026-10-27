"""D62: our own caption word colours (multicolour, never theirs), everything else copied; the caption gate then
scores where the text is, not its colour. Offline: synthetic frames, ffmpeg for the short videos."""
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

CLIPPER = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(CLIPPER)]
from remake import caps, match  # noqa: E402


def ev(words, colour="#2BFF5A"):
    return {"start": 0, "end": 1, "y": 0.5, "lines": [1], "words": [{"w": w, "c": colour, "t": 0} for w in words]}


def test_all_green_caption_becomes_multicolour_and_never_their_green():
    evs = [ev(["HELLO", "HOW", "ARE", "YOU"]), ev(["NO", "WAY", "BRO"])]
    cols = caps.our_colours(evs, "abc123")
    assert [len(c) for c in cols] == [4, 3]
    assert len(set(cols[0])) >= 2                                       # multicolour, not one colour
    assert "#2BFF5A" not in cols[0] + cols[1]                           # never their colour
    flat = cols[0] + cols[1]
    groups = [c for i, c in enumerate(flat) if i == 0 or c != flat[i - 1]]
    assert all(a != b for a, b in zip(groups, groups[1:]))              # neighbouring groups differ
    assert caps.our_colours(evs, "abc123") == cols                      # same Short, same colours
    assert any(caps.our_colours(evs, s) != cols for s in ("x", "y", "z"))   # other Shorts, other colours
    assert all(c in caps.OUR_PALETTE for c in flat)


def test_their_measured_colours_win_over_the_ocr_guess():
    evs = [ev(["ONE", "TWO", "THREE"], colour="#FFFFFF")]
    theirs = [["#FF3B3B", "#FF3B3B", "#FF3B3B"]]                         # style.build read them red
    cols = caps.our_colours(evs, "s", theirs)
    assert "#FF3B3B" not in cols[0]
    out = caps.with_colours(evs, cols)
    assert [w["c"] for w in out[0]["words"]] == cols[0] and out[0]["words"][0]["w"] == "ONE"


def _video(path, frames, fps=30):
    h, w = frames[0].shape[:2]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(path)],
                         stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(f.tobytes())
    p.stdin.close()
    p.wait()
    return path


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg")
def test_colour_blind_gate_passes_our_colours_and_still_sees_wrong_text(tmp_path):
    rng = np.random.default_rng(5)
    bg = cv2.resize(rng.integers(0, 120, (12, 7, 3), dtype=np.uint8), (270, 480), interpolation=cv2.INTER_NEAREST)
    theirs, recoloured, wrong = [], [], []
    for _ in range(20):
        a, b, c = bg.copy(), bg.copy(), bg.copy()
        for img, col in ((a, (90, 255, 40)), (b, (60, 60, 255))):          # their green, our red: same text
            cv2.putText(img, "YES", (80, 250), cv2.FONT_HERSHEY_DUPLEX, 1.5, (0, 0, 0), 9)
            cv2.putText(img, "YES", (80, 250), cv2.FONT_HERSHEY_DUPLEX, 1.5, col, 4)
        cv2.putText(c, "NO WAY", (40, 250), cv2.FONT_HERSHEY_DUPLEX, 0.8, (60, 60, 255), 2)
        theirs.append(a), recoloured.append(b), wrong.append(c)
    T, Z = _video(tmp_path / "t.mp4", theirs), _video(tmp_path / "z.mp4", [bg] * 20)
    evs = [{"start": 0, "end": 1, "y": 0.5, "lines": [1], "words": [{"w": "YES", "c": "#28FF5A", "t": 0}]}]
    ours = _video(tmp_path / "o.mp4", recoloured)
    blind = match.score(T, ours, evs, 30, 20, 270, 480, base=Z, colour_blind=True)
    seeing = match.score(T, ours, evs, 30, 20, 270, 480, base=Z)
    bad = match.score(T, _video(tmp_path / "w.mp4", wrong), evs, 30, 20, 270, 480, base=Z, colour_blind=True)
    assert blind["captions"] == 100 and seeing["captions"] < 20       # colour no longer counts ...
    assert bad["captions"] < 20                                        # ... the text, font and place still do
