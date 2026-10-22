"""How identical is our remake to their Short? (D58, Lucas 2026-10-21: "they should be IDENTICAL")

Both videos are read frame by frame at 270 px wide, low-passed (encoding noise out), and compared:
- picture: every frame outside the caption rows (framing, cuts, zooms, grade, flashes),
- captions: in the caption rows while a caption is on screen, the pixels where ours differs from theirs, counted
  against their caption's own pixels (their frame vs our caption-free `base`): 0 = same text, font, size, colour,
  timing and place; 1 = as wrong as no caption at all.
A frame matches when picture diff < PICTURE_OK (0-255) and caption error < CAPTION_OK. The score is the share of
matching frames; `bad` lists the worst stretches (seconds) so a rebuild or Lucas knows where to look.
"""
import subprocess
from pathlib import Path

import cv2
import numpy as np

from . import common as C

W = 270
PICTURE_OK = 18.0     # mean of the max-channel difference
CAPTION_OK = 0.45   # share of their caption pixels we may get wrong (anti-aliasing, 1 px) per frame
STRONG = 40          # a pixel differs (0-255, max channel) above this
CHUNK = 90


def _rows(evs, n, fps, h, line_h_frac=0.06, pad=1.6):
    """Caption rows (bool per row) at frame n, or None when no caption is on screen."""
    t = n / fps
    on = [e for e in evs if e["start"] <= t < e["end"]]
    if not on:
        return None
    r = np.zeros(h, bool)
    for e in on:
        k = max(1, len(e.get("lines") or [1]))
        half = pad * line_h_frac * k * h
        y = e.get("y", 0.5) * h
        r[max(0, int(y - half)):min(h, int(y + half))] = True
    return r


def score(theirs, ours, evs, fps, nfr, out_w, out_h, y=None, line_h=None, base=None):
    """{'picture': %, 'captions': %, 'overall': %, 'per_frame': [(pic, cap|None)], 'bad': [[t0, t1, what]]}"""
    h = int(round(W * out_h / out_w / 2) * 2)
    lh = (line_h / out_h) if line_h else 0.06
    if y is not None:
        evs = [{**e, "y": y} for e in evs]
    pf = []
    blur = lambda x: cv2.GaussianBlur(x, (0, 0), 1.2).astype(np.int16)  # noqa: E731
    for k in range(0, nfr, CHUNK):
        cnt = min(CHUNK, nfr - k)
        a = C.read_frames(theirs, k, cnt, fps, (W, h))
        b = C.read_frames(ours, k, cnt, fps, (W, h))
        z = C.read_frames(base, k, cnt, fps, (W, h)) if base else None
        for i in range(min(len(a), len(b))):
            n = k + i
            A, B = blur(a[i]), blur(b[i])
            d = np.abs(A - B).max(2)
            rows = _rows(evs, n, fps, h, lh)
            if rows is None:
                pf.append((float(d.mean()), None))
                continue
            pic = float(d[~rows].mean()) if (~rows).any() else 0.0
            err = (shifted_min(A, B, rows) > STRONG).sum()      # 1 px off (= 4 px at 1080) is not an error
            if z is not None and i < len(z):
                theirs_px = (np.abs(A - blur(z[i])).max(2)[rows] > STRONG).sum()
            else:
                theirs_px = 0.08 * rows.sum() * W
            pf.append((pic, float(err / max(theirs_px, 0.02 * rows.sum() * W))))
    if not pf:
        return {"picture": 0.0, "captions": 0.0, "overall": 0.0, "per_frame": [], "bad": []}
    pic_ok = [p < PICTURE_OK for p, _ in pf]
    caps = [(c < CAPTION_OK) for _, c in pf if c is not None]
    picture = 100.0 * np.mean(pic_ok)
    captions = 100.0 * np.mean(caps) if caps else 100.0
    bad = _stretches([not ok for ok in pic_ok], fps, "picture") + \
        _stretches([c is not None and c >= CAPTION_OK for _, c in pf], fps, "captions")
    return {"picture": round(float(picture), 1), "captions": round(float(captions), 1),
            "overall": round(float(min(picture, captions)), 1),
            "per_frame": [(round(p, 1), None if c is None else round(c, 3)) for p, c in pf],
            "bad": sorted(bad, key=lambda b: b[0])[:12]}


def shifted_min(A, B, rows, r=1):
    """Per pixel of the caption rows: the smallest |A - B| over B shifted by up to r px each way (max channel)."""
    ys = np.where(rows)[0]
    y0, y1 = max(0, ys.min() - r), min(A.shape[0], ys.max() + 1 + r)
    a, b = A[y0:y1], B[y0:y1]
    best = None
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = np.abs(a - np.roll(np.roll(b, dy, 0), dx, 1)).max(2)
            best = d if best is None else np.minimum(best, d)
    return best[rows[y0:y1]]


def frame_shift(theirs, ours, max_s=4, step=10):
    """Frames our render runs late (+) or early (-) against theirs, read in sequence (both at their frame rate):
    the shift that matches best on most frames, 0 if none is clearly better."""
    def frames(p):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vf", "scale=135:240:flags=area", "-pix_fmt",
                              "gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        return np.frombuffer(raw, np.uint8).reshape(-1, 240, 135).astype(np.float32)
    a, b = frames(theirs), frames(ours)
    votes, gain = [], []
    for n in range(max_s, min(len(a), len(b)) - max_s, step):
        d = [float(np.abs(a[n] - b[n + s]).mean()) for s in range(-max_s, max_s + 1)]
        votes.append(int(np.argmin(d)) - max_s)
        gain.append(d[max_s] - min(d))
    if not votes:
        return 0
    s = max(set(votes), key=votes.count)
    return s if s != 0 and votes.count(s) >= 0.6 * len(votes) and np.mean(gain) > 0.5 else 0


def _stretches(flags, fps, what, min_frames=4):
    out, s = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and s is None:
            s = i
        elif not f and s is not None:
            if i - s >= min_frames:
                out.append([round(s / fps, 2), round(i / fps, 2), what])
            s = None
    return out


def burn(base, ass, out, fonts_dir=None):
    """Captions onto the caption-free remake (audio copied)."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(base), "-vf",
                    f"ass={ass}:fontsdir={fonts_dir or C.fonts_dir()}", "-c:v", "libx264", "-preset", "medium",
                    "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(out)],
                   check=True)
    return Path(out)


def summary(m):
    return f"picture {m['picture']:.0f}% · captions {m['captions']:.0f}%"
