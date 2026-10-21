"""Fit the measured caption look on their pixels (D61): size, letter spacing, position, box padding and font are
nudged one at a time and kept when our captions match theirs better.

A sample video is built once: one frame per caption moment (our caption-free `base` frame), 1 fps. Each
candidate look is written as ASS for those moments (caption state as shown at that frame, animation settled),
burned onto the sample in one ffmpeg call and scored against their frames: the share of their caption pixels we
get wrong (1 px tolerance, as in match.py). Coordinate descent, two rounds.
"""
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

from . import caps
from . import common as C
from . import match
from . import style as S

SW = 540
SAMPLES = 14
STRONG = 40


def moments(evs, fps, n=SAMPLES):
    """[(event index, frame, words shown)] spread over the captions: 70 % into each, after its last reveal."""
    out = []
    for k, e in enumerate(evs):
        if e["end"] - e["start"] < 0.15 or not e["words"]:
            continue
        t = e["start"] + 0.7 * (e["end"] - e["start"])
        shown = [w for w in e["words"] if w["t"] <= t]
        if shown:
            out.append((k, int(t * fps), len(shown)))
    if len(out) > n:
        out = [out[i] for i in np.linspace(0, len(out) - 1, n).astype(int)]
    return out


def sample_events(evs, ms, st):
    """Caption events and a style for the sample video: moment i shows on [i, i + 1) s, fully revealed."""
    sev, pos, cols = [], [], []
    for i, (k, _, nw) in enumerate(ms):
        e = evs[k]
        t0 = i + 0.5             # sample frame i + 1 sits mid-caption (frame 0 is a spacer)
        words = [{**w, "t": t0} for w in e["words"][:nw]]
        shape, left = [], nw
        for n in e.get("lines") or [len(e["words"])]:
            if left <= 0:
                break
            shape.append(min(n, left))
            left -= n
        sev.append({**e, "start": t0, "end": t0 + 1.0, "words": words, "lines": shape})
        p = (st.get("pos") or [])
        pos.append(p[k] if k < len(p) else None)
        c = (st.get("colours") or [])
        cols.append((c[k] if k < len(c) else [w["c"] for w in e["words"]])[:nw])
    return sev, {**st, "pos": pos, "colours": cols, "anim": {"kind": "none"}}


def build_sample(base_path, ms, fps, size, path):
    W, H = size
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-r", "1", "-i", "-", "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv444p", str(path)],
                         stdin=subprocess.PIPE)
    p.stdin.write(np.zeros((H, W, 3), np.uint8).tobytes())          # spacer frame 0
    for _, n, _ in ms:
        f = S.frame(base_path, n, fps, size)
        p.stdin.write((f if f is not None else np.zeros((H, W, 3), np.uint8)).tobytes())
    p.stdin.close()
    p.wait()
    return path


def burn_frames(sample, ass, count, size, fonts_dir=None):
    W, H = size
    h = int(round(SW * H / W / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(sample), "-vf",
                          f"ass={ass}:fontsdir={fonts_dir or C.fonts_dir()},scale={SW}:{h}:flags=area",
                          "-frames:v", str(count + 1), "-pix_fmt", "bgr24", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, SW, 3)[1:]


class Scorer:
    def __init__(self, short_path, base_path, evs, st, fps, size, mark=None, work=None):
        self.evs, self.size, self.mark = evs, size, mark
        self.ms = moments(evs, fps)
        W, H = size
        self.h = int(round(SW * H / W / 2) * 2)
        self.dir = Path(work or tempfile.mkdtemp())
        self.sample = build_sample(base_path, self.ms, fps, size, self.dir / "tune_sample.mp4")
        blur = lambda x: cv2.GaussianBlur(x, (0, 0), 1.0).astype(np.int16)  # noqa: E731
        self.theirs = [blur(S.frame(short_path, n, fps, (SW, self.h))) for _, n, _ in self.ms]
        base = [blur(S.frame(base_path, n, fps, (SW, self.h))) for _, n, _ in self.ms]
        self.rows, self.their_px = [], []
        for i, (k, _, _) in enumerate(self.ms):
            p = (st.get("pos") or [None] * len(evs))
            y = (p[k][1] if k < len(p) and p[k] else st.get("y", 0.5))
            lh = (st.get("line_h") or 60) / H
            nl = len(evs[k].get("lines") or [1])
            r = np.zeros(self.h, bool)
            half = (1.6 * nl * lh + 0.03) * self.h
            r[max(0, int(y * self.h - half)):min(self.h, int(y * self.h + half))] = True
            self.rows.append(r)
            self.their_px.append(max(1, int((np.abs(self.theirs[i] - base[i]).max(2)[r] > STRONG).sum())))
        self.n = 0

    def __call__(self, st):
        """Mean share of their caption pixels we get wrong (lower is better)."""
        sev, sst = sample_events(self.evs, self.ms, st)
        self.n += 1
        ass = self.dir / f"tune_{self.n}.ass"
        try:
            caps.write_ass_style(sev, ass, *self.size, sst)
            ours = burn_frames(self.sample, ass, len(self.ms), self.size)
        except Exception as e:  # noqa: BLE001 - a broken candidate just loses
            C.log(f"tune: candidate failed: {e}")
            return 9.0
        errs = []
        for i in range(min(len(ours), len(self.theirs))):
            B = cv2.GaussianBlur(ours[i], (0, 0), 1.0).astype(np.int16)
            d = match.shifted_min(self.theirs[i], B, self.rows[i])
            errs.append(min(2.0, (d > STRONG).sum() / self.their_px[i]))
        return float(np.mean(errs)) if errs else 9.0


def tune(st, score, fonts_dir=None, rounds=2):
    """Coordinate descent over the caption look. Returns (best style, its error)."""
    best, err = dict(st), score(st)
    C.log(f"tune: start {err:.3f}")
    has_box = bool((st.get("llm") or {}).get("box", {}).get("present"))

    def at_font(s, entry):
        alt = {**s, "alternatives": [(0, entry[0], entry[2], s.get("track", 0))]}
        out = S.with_font(alt, 0, fonts_dir)
        return {**out, "alternatives": s.get("alternatives")} if out else None

    for _ in range(rounds):
        steps = [
            ("fs", lambda s, v: {**s, "fs": s["fs"] * v, "spacing": (s.get("track") or 0) * s["fs"] * v,
                                 "dy": s.get("dy", 0) * v}, (0.94, 0.97, 1.03, 1.06)),
            ("track", lambda s, v: {**s, "track": (s.get("track") or 0) + v,
                                    "spacing": ((s.get("track") or 0) + v) * s["fs"]}, (-0.03, -0.015, 0.015, 0.03)),
            ("dy", lambda s, v: {**s, "dy": s.get("dy", 0) + v}, (-8, -4, 4, 8)),
            ("x", lambda s, v: {**s, "x": s.get("x", 0.5) + v}, (-0.008, -0.004, 0.004, 0.008)),
        ]
        if has_box:
            pad0 = best.get("box_pad") or [0.25 * best.get("line_h", 60), 0.2 * best.get("line_h", 60)]
            steps += [
                ("box_x", lambda s, v: {**s, "box_pad": [max(2, (s.get("box_pad") or pad0)[0] + v),
                                                         (s.get("box_pad") or pad0)[1]]}, (-12, -6, 6, 12)),
                ("box_y", lambda s, v: {**s, "box_pad": [(s.get("box_pad") or pad0)[0],
                                                         max(2, (s.get("box_pad") or pad0)[1] + v)]}, (-12, -6, 6, 12)),
            ]
            if not best.get("box_pad"):
                cand = {**best, "box_pad": pad0}
                e = score(cand)
                if e < err:
                    best, err = cand, e
        for name, fn, vals in steps:
            for v in vals:
                cand = fn(best, v)
                e = score(cand)
                if e < err - 1e-3:
                    best, err = cand, e
                    C.log(f"tune: {name} {v:+g} -> {err:.3f}")
        for alt in (best.get("alternatives") or [])[:3]:
            entry = next((f for f in S.FONTS if f[0] == alt[1] and f[2] == alt[2]), None)
            if entry and entry[0] != best.get("family"):
                cand = at_font(best, entry)
                if cand:
                    e = score(cand)
                    if e < err - 1e-3:
                        best, err = cand, e
                        C.log(f"tune: font {entry[0]} -> {err:.3f}")
    return best, err
