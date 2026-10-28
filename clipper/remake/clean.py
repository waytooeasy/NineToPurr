"""Checks a finished remake must pass that the match score can't see (2026-10-28, clip 33, Asmongold reacting to a
TikTok): the clipper used the clean original video, we rebuilt from his stream, where it played in a browser.
1. judder: a video played inside a stream comes out with uneven frames (34 % of ours repeated the previous one,
   17 % of theirs) and the picture jumps; a remake much less smooth than theirs is skipped.
2. foreign_ui: the stream also showed the player's progress bar and TikTok's watermark, which theirs didn't have;
   a vision check on theirs | ours frames skips a remake that shows another app's logo or a video player's UI."""
import json
import re
import subprocess

import cv2
import numpy as np

from . import common as C

REPEAT_MARGIN = 0.12   # our share of repeated frames may exceed theirs by this much
JUMP_FACTOR = 2.0      # our picture jumps per second may be this many times theirs (+ JUMP_SLACK)
JUMP_SLACK = 1.0
JUMP_PX = 2.0          # a change of frame-to-frame motion above this (at 270 px wide) is a jump
STILL = 0.3            # mean abs difference below this: the frame repeats the previous one
CHUNK = 120


def smoothness(path, fps, nfr, size, reader=None):
    """(share of frames that repeat the previous one, picture jumps per second)."""
    read = reader or C.read_frames
    prev, prev_shift, n, rep, jumps = None, None, 0, 0, 0
    for k in range(0, nfr, CHUNK):
        frames = read(path, k, min(CHUNK, nfr - k), fps, size)
        if len(frames) == 0:
            break
        for f in frames:
            g = (cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) if f.ndim == 3 else f).astype(np.float32)
            if prev is not None:
                n += 1
                if float(np.abs(g - prev).mean()) < STILL:
                    rep += 1
                (dx, dy), _ = cv2.phaseCorrelate(prev, g)
                if prev_shift is not None and abs(dx - prev_shift[0]) + abs(dy - prev_shift[1]) > JUMP_PX:
                    jumps += 1
                prev_shift = (dx, dy)
            prev = g
    return rep / max(n, 1), jumps / max(n / fps, 1e-6)


def judder(theirs, ours, fps, nfr, size, reader=None):
    """Why ours is much less smooth than theirs, or None."""
    t, o = smoothness(theirs, fps, nfr, size, reader), smoothness(ours, fps, nfr, size, reader)
    C.log(f"smoothness: repeated frames {o[0]:.0%} (theirs {t[0]:.0%}), jumps {o[1]:.1f}/s (theirs {t[1]:.1f}/s)")
    if o[0] > t[0] + REPEAT_MARGIN or o[1] > JUMP_FACTOR * t[1] + JUMP_SLACK:
        return (f"judder: {o[0]:.0%} of our frames repeat (theirs {t[0]:.0%}), {o[1]:.1f} jumps/s (theirs "
                f"{t[1]:.1f}/s): the stream showed a video in a player, they used the clean original")
    return None


PROMPT = """Each image shows the same moment of a vertical video twice: LEFT is the original, RIGHT is our copy.
Does RIGHT show something LEFT does not: another app's logo or watermark (TikTok, Instagram, Reels, Snapchat, a
@username tag of that app), a video player's controls (progress bar, a timestamp like 0:02 / 0:31, play, pause,
volume or settings icons), browser or desktop UI (tabs, address bar, a mouse cursor, a taskbar) or a notification?
Ignore captions and their colours, and ignore the "@Peakz.Recaps" handle. Answer JSON only:
{"extra": true or false, "what": "<what RIGHT shows that LEFT doesn't, a few words>"}"""


def pair_jpeg(theirs, ours, t, w=360, h=640):
    return subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(theirs), "-ss", f"{t:.3f}", "-i",
                           str(ours), "-filter_complex", f"[0]scale={w}:{h}[a];[1]scale={w}:{h}[b];[a][b]hstack",
                           "-frames:v", "1", "-f", "image2", "-c:v", "mjpeg", "-q:v", "4", "-"],
                          capture_output=True, check=True).stdout


def foreign_ui(theirs, ours, dur, vision, jpeg=pair_jpeg, at=(0.2, 0.5, 0.8)):
    """Why ours shows another app's watermark or a player's UI that theirs doesn't, or None (also on any error:
    this check never blocks by failing)."""
    try:
        reply = vision([jpeg(theirs, ours, f * dur) for f in at], PROMPT)
        m = re.search(r"\{.*\}", reply or "", re.S)
        d = json.loads(m.group(0)) if m else {}
    except Exception as e:  # noqa: BLE001
        C.log(f"foreign UI check skipped: {e}")
        return None
    if d.get("extra") is True:
        return f"ours shows what theirs doesn't: {str(d.get('what') or 'another app or a player UI')[:80]}"
    return None
