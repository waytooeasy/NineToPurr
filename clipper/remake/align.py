"""Frame-exact framing (D61): after the video map, every frame of a 'full' shot is aligned on their pixels.

The map's camera path is smoothed per shot (holds and pans stay clean), so where their crop moves by small steps
(handheld IRL, nudges, quick punch-ins) ours sits a few pixels off. Here our composed frame is aligned to theirs
with ECC (scale + shift, their caption rows left out) and the correction is folded back into the path:
their pixel x = our pixel a*x + t  ->  k' = a*k, centre' = centre + (a*O/2 + t - O/2)*k.
A correction is kept only when it makes the frame match better.
"""
import copy

import cv2
import numpy as np

from . import common as C
from . import render as R

W = 270
CAP_BAND = (0.36, 0.66)
MIN_GAIN = 0.01          # correlation gain needed to keep a correction
MAX_SCALE = 0.08         # |a - 1| larger than this is not a nudge: leave it to the map


def _gray(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return cv2.GaussianBlur(g, (0, 0), 1.0)


def _blank(g, h):
    """Their caption rows are left out of the alignment: kept as they are, masked in ECC and in the score."""
    return g


def _mask(h, w):
    m = np.full((h, w), 255, np.uint8)
    m[int(CAP_BAND[0] * h):int(CAP_BAND[1] * h)] = 0
    return m


def _ncc(a, b):
    m = _mask(*a.shape) > 0
    a, b = a[m], b[m]
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))


def ecc(theirs, ours):
    """(a, tx, ty) with their(x) ~ our(a*x + t) at analysis size, or None."""
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        _, warp = cv2.findTransformECC(theirs, ours, warp, cv2.MOTION_AFFINE,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5),
                                       _mask(*theirs.shape), 3)
    except cv2.error:
        return None
    a = float((warp[0, 0] + warp[1, 1]) / 2)          # ECC: their(x) ~ our(warp x); one scale a, kept exact
    if abs(a - 1) > MAX_SCALE or abs(warp[0, 1]) > 0.03 or abs(warp[1, 0]) > 0.03:
        return None
    h, w = theirs.shape
    c = np.array([w / 2, h / 2])
    wc = warp[:, :2] @ c + warp[:, 2]                  # where their centre lands in ours
    t = wc - a * c
    return a, float(t[0]), float(t[1])


def update(k, cx, cy, a, tx, ty, OW, OH, r):
    """Path params after their(x) = our(a*x + t) (t at analysis size, r = output px per analysis px)."""
    return a * k, cx + (a * OW / 2 + tx * r - OW / 2) * k, cy + (a * OH / 2 + ty * r - OH / 2) * k


def align_frame(A, sec_img, vm, shot, n, h, passes=3):
    """Our framing of frame n moved onto their pixels A: ((k, cx, cy), our frame there) or (None, None)."""
    OW, OH = vm["out_w"], vm["out_h"]
    k, cx, cy = R.VM.params_at(shot, n)
    B, moved = None, False
    for _ in range(passes):
        trial = {**shot, "path": {**shot["path"], str(n): [k, cx, cy]}}
        B = _blank(_gray(R.compose(sec_img, vm, trial, n, (W, h))), h)
        e = ecc(A, B)
        if e is None:
            break
        a, tx, ty = e
        if abs(a - 1) < 1e-3 and abs(tx) < 0.05 and abs(ty) < 0.05:
            break
        k, cx, cy = update(k, cx, cy, a, tx, ty, OW, OH, OW / W)
        moved = True
    if not moved:
        return None, None
    trial = {**shot, "path": {**shot["path"], str(n): [k, cx, cy]}}
    return (k, cx, cy), _blank(_gray(R.compose(sec_img, vm, trial, n, (W, h))), h)


def refine(short_path, vm):
    """A copy of the video map whose 'full' shot paths follow their framing frame by frame."""
    vm = copy.deepcopy(vm)
    OW, OH, fps = vm["out_w"], vm["out_h"], vm["fps"]
    h = int(round(W * OH / OW / 2) * 2)
    r = OW / W
    fixed = tried = 0
    for shot in vm["shots"]:
        if shot["layout"] != "full":
            continue
        n0, n1 = shot["n0"], shot["n1"]
        th = C.read_frames(short_path, n0, n1 - n0, fps, (W, h))
        sec = vm["sections"][shot["sec"]]
        m0 = R.sec_frame_index(vm, shot, n0)
        m1 = R.sec_frame_index(vm, shot, max(n0, n1 - 1))
        sf = C.read_frames(sec["file"], m0, m1 - m0 + 2, sec["fps"], (sec["w"] // 4, sec["h"] // 4))
        new = {}
        for i, n in enumerate(range(n0, n0 + len(th))):
            j = R.sec_frame_index(vm, shot, n) - m0
            if not (0 <= j < len(sf)):
                continue
            tried += 1
            A = _blank(_gray(th[i]), h)
            B = _blank(_gray(R.compose(sf[j], vm, shot, n, (W, h))), h)
            p2, B2 = align_frame(A, sf[j], vm, shot, n, h)
            if p2 is not None and _ncc(A, B2) - _ncc(A, B) >= MIN_GAIN:
                new[str(n)] = [float(x) for x in p2]
        shot["path"].update(new)
        fixed += len(new)
    C.log(f"align: {fixed}/{tried} frames re-framed on their pixels")
    vm["aligned"] = fixed
    return vm
