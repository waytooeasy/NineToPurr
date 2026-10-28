"""Checks a finished remake must pass that the match score can't see (2026-10-28, clip 33, Asmongold reacting to a
TikTok): the clipper used the clean original video, we rebuilt from his stream, where it played in a browser.
1. judder: our crop of each stacked panel wobbled (noisy per-frame estimates on a dark, low-texture video) where
   theirs held still; a remake that shakes much more than theirs is skipped.
2. foreign_ui: the stream also showed the player's progress bar and TikTok's watermark, which theirs didn't have;
   a vision check on theirs | ours frames skips a remake that shows another app's logo or a video player's UI."""
import json
import re
import subprocess

import cv2
import numpy as np

from . import common as C

FLIP_MARGIN = 8        # back-and-forth jitters ours may have more than theirs, per half of the frame
ACCEL_FACTOR = 3.0     # our frame-to-frame motion change (p90) may be this many times theirs (+ ACCEL_SLACK)
ACCEL_SLACK = 0.25
FLIP_PX = 0.4          # a frame-to-frame shift this big (at 270 px wide) that reverses the last one: a jitter
HALVES = ((0.05, 0.5), (0.55, 0.95))   # top and bottom: a stack's panels move on their own
CHUNK = 150


def shake(path, fps, nfr, size, reader=None):
    """Per half of the frame: (back-and-forth jitters, p90 of frame-to-frame motion change in px)."""
    read = reader or C.read_frames
    prev, shifts = [None] * len(HALVES), [[] for _ in HALVES]
    for k in range(0, nfr, CHUNK):
        frames = read(path, k, min(CHUNK, nfr - k), fps, size)
        if len(frames) == 0:
            break
        for f in frames:
            g = (cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) if f.ndim == 3 else f).astype(np.float32)
            for j, (a, b) in enumerate(HALVES):
                part = g[int(a * g.shape[0]):int(b * g.shape[0])]
                if prev[j] is not None:
                    (dx, dy), _ = cv2.phaseCorrelate(prev[j], part)
                    shifts[j].append((dx, dy))
                prev[j] = part
    out = []
    for sh in shifts:
        s = np.array(sh) if sh else np.zeros((2, 2))
        flips = int(((np.sign(s[1:, 0]) * np.sign(s[:-1, 0]) < 0) & (np.abs(s[1:, 0]) > FLIP_PX)
                     & (np.abs(s[:-1, 0]) > FLIP_PX)).sum()
                    + ((np.sign(s[1:, 1]) * np.sign(s[:-1, 1]) < 0) & (np.abs(s[1:, 1]) > FLIP_PX)
                       & (np.abs(s[:-1, 1]) > FLIP_PX)).sum())
        acc = np.hypot(*np.diff(s, axis=0).T) if len(s) > 2 else np.zeros(1)
        out.append((flips, float(np.percentile(acc, 90))))
    return out


def judder(theirs, ours, fps, nfr, size, reader=None):
    """Why our picture wobbles where theirs holds still, or None. Clip 33: our crop of each stack panel jittered
    (top: 20 back-and-forth shakes in 25 s, theirs 0; bottom: 10x their motion changes); clip 32 matched theirs."""
    t, o = shake(theirs, fps, nfr, size, reader), shake(ours, fps, nfr, size, reader)
    C.log("shake (ours vs theirs): " + ", ".join(f"{n} {oo[0]} vs {tt[0]} jitters, {oo[1]:.2f} vs {tt[1]:.2f} px"
                                                  for n, oo, tt in zip(("top", "bottom"), o, t)))
    for name, (of, oa), (tf, ta) in zip(("top", "bottom"), o, t):
        if of >= tf + FLIP_MARGIN or oa > ACCEL_FACTOR * ta + ACCEL_SLACK:
            return (f"judder: the {name} of ours shakes ({of} jitters, motion change {oa:.2f} px) where theirs holds "
                    f"({tf}, {ta:.2f} px)")
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
