"""Their look (D58), measured against our exact re-framing of the same stream frames:
- grade: cubic colour polynomial fitted on low-passed frame pairs (detail and captions do not bias it),
- sharpening: how much more fine detail their frames carry (they sharpen / 'enhance' hard),
- overlays: full-frame colour washes (red flash on the punch line...) with their per-frame strength.
"""
import cv2
import numpy as np

from . import common as C
from . import render as R

CAP_BAND = (0.33, 0.67)    # rows where captions usually sit: not used to fit the grade
OVERLAY_MIN = 0.04         # per-frame washes weaker than this are not stored
CORE_MIN = 0.15            # a wash's core frames are at least this strong
PEAK_MIN = 0.2             # a flash peaks at least this strong
SAT_MIN = 100              # ... in a saturated colour (max - min channel of its colour)


def _pairs(short_path, vm, ns, width):
    """(their, ours) frame pairs at `width` (ours ungraded), skipping frames the map missed."""
    OW, OH = vm["out_w"], vm["out_h"]
    w, h = width, int(round(width * OH / OW / 2) * 2)
    out = []
    for n in ns:
        shot = R.shot_at(vm, n)
        sec = vm["sections"][shot["sec"]]
        m = R.sec_frame_index(vm, shot, n)
        th = C.read_frames(short_path, n, 1, vm["fps"], (w, h))
        sf = C.read_frames(sec["file"], m, 1, sec["fps"], (sec["w"] // 2, sec["h"] // 2))
        if len(th) and len(sf):
            out.append((n, shot, th[0], R.compose(sf[0], vm, shot, n, (w, h))))
    return out


def _valid(vm, shot, n, w, h):
    """Rows/cols of our frame that show the stream itself (the panel of a 'fit' shot)."""
    m = np.ones((h, w), bool)
    if shot["layout"] == "fit":
        k, cx, cy = R.VM.params_at(shot, n)
        OW, OH = vm["out_w"], vm["out_h"]
        sec = vm["sections"][shot["sec"]]
        top, bot = (OH / 2 - cy / k) / OH, (OH / 2 + (sec["h"] - cy) / k) / OH
        m[:max(0, int(top * h) + 3)] = False
        m[min(h, int(bot * h) - 3):] = False
    m[int(CAP_BAND[0] * h):int(CAP_BAND[1] * h)] = False
    m[:3] = m[-3:] = False
    m[:, :3] = m[:, -3:] = False
    return m


def mapped_samples(vm, count, away=3):
    ns = sorted(int(n) for n in vm["frames"])
    cuts = {s["n0"] for s in vm["shots"]}
    ns = [n for n in ns if all(abs(n - c) > away for c in cuts)]
    if not ns:
        return []
    step = max(1, len(ns) // count)
    return ns[::step][:count]


def fit_grade(pairs, vm):
    P, Q = [], []
    for n, shot, th, ours in pairs:
        h, w = th.shape[:2]
        m = _valid(vm, shot, n, w, h)
        a = cv2.GaussianBlur(th.astype(np.float32), (0, 0), 3)
        b = cv2.GaussianBlur(ours.astype(np.float32), (0, 0), 3)
        idx = np.where(m.ravel())[0][::5]
        P.append(b.reshape(-1, 3)[idx] / 255.0)
        Q.append(a.reshape(-1, 3)[idx] / 255.0)
    if not P:
        return None, None
    P, Q = np.concatenate(P), np.concatenate(Q)
    F = R.poly_feats(P)
    W, *_ = np.linalg.lstsq(F, Q, rcond=None)
    err = np.abs(F @ W - Q).mean(1)
    keep = err <= np.quantile(err, 0.9)          # captions / overlays outside the band: drop the worst 10 %
    W, *_ = np.linalg.lstsq(F[keep], Q[keep], rcond=None)
    return W, float(np.abs(F[keep] @ W - Q[keep]).mean() * 255)


def detail_ratio(pairs, W):
    """Fine-detail energy (DoG 1-2.5 px at 1080 wide) of their frames over our graded frames."""
    lut = R.lut128(W) if W is not None else None
    num = den = 0.0
    for n, shot, th, ours in pairs:
        g = R.apply_look(ours, lut)
        a = cv2.cvtColor(th, cv2.COLOR_BGR2GRAY).astype(np.float32)
        b = cv2.cvtColor(g, cv2.COLOR_BGR2GRAY).astype(np.float32)
        da = cv2.GaussianBlur(a, (0, 0), 1) - cv2.GaussianBlur(a, (0, 0), 2.5)
        db = cv2.GaussianBlur(b, (0, 0), 1) - cv2.GaussianBlur(b, (0, 0), 2.5)
        h = a.shape[0]
        sl = slice(0, int(CAP_BAND[0] * h))       # above the captions
        num += float((da[sl] ** 2).sum())
        den += float((db[sl] ** 2).sum())
    return float(np.sqrt(num / den)) if den > 0 else 1.0


def overlays(short_path, vm, W, width=270):
    """Per-frame colour wash: their = (1 - a) * ours + a * colour (low-passed, captions band excluded)."""
    lut = R.lut128(W) if W is not None else None
    OW, OH = vm["out_w"], vm["out_h"]
    w, h = width, int(round(width * OH / OW / 2) * 2)
    alpha, colour, cols = {}, {}, []
    bands = {}                       # n -> mean |their - ours| in 16 horizontal bands (captions show up here)
    for shot in vm["shots"]:
        n0, n1 = shot["n0"], shot["n1"]
        th = C.read_frames(short_path, n0, n1 - n0, vm["fps"], (w, h))
        sec = vm["sections"][shot["sec"]]
        m0 = R.sec_frame_index(vm, shot, n0)
        m1 = R.sec_frame_index(vm, shot, max(n0, n1 - 1))
        sf = C.read_frames(sec["file"], m0, m1 - m0 + 2, sec["fps"], (sec["w"] // 4, sec["h"] // 4))
        for i, n in enumerate(range(n0, n0 + len(th))):
            j = R.sec_frame_index(vm, shot, n) - m0
            if not (0 <= j < len(sf)):
                continue
            ours = R.apply_look(R.compose(sf[j], vm, shot, n, (w, h)), lut).astype(np.float32)
            a = cv2.GaussianBlur(th[i].astype(np.float32), (0, 0), 2)
            b = cv2.GaussianBlur(ours, (0, 0), 2)
            diff = np.abs(a - b).mean(axis=2)
            bands[n] = [round(float(diff[int(j * h / 16):int((j + 1) * h / 16)].mean()), 2) for j in range(16)]
            m = np.ones((h, w), bool)
            m[int(CAP_BAND[0] * h):int(CAP_BAND[1] * h)] = False
            d, o = (a - b)[m].reshape(-1, 3), b[m].reshape(-1, 3)
            A = np.zeros((d.size, 4))
            A[0::3, 0] = 1
            A[1::3, 1] = 1
            A[2::3, 2] = 1
            A[:, 3] = -o.ravel()
            sol, *_ = np.linalg.lstsq(A, d.ravel(), rcond=None)
            al = float(sol[3])
            if al >= OVERLAY_MIN:
                c = sol[:3] / al
                alpha[n] = round(min(al, 0.9), 3)
                colour[n] = c
                cols.append(c)
    if not cols:
        return {"alpha": {}, "color": [0, 0, 255], "bands": {str(n): v for n, v in bands.items()}}
    # a wash is a short, strong, saturated colour event (red flash on the punch line); grade mismatch on a shot is
    # weak, long and grey-ish. Cores: >= CORE_MIN; grown while the same colour fades out (or in).
    bd = {str(n): v for n, v in bands.items()}
    keep, keep_cols = {}, []
    core = sorted(n for n, a in alpha.items() if a >= CORE_MIN)
    runs, cur = [], []
    for n in core:
        if cur and n != cur[-1] + 1:
            runs.append(cur)
            cur = []
        cur.append(n)
    if cur:
        runs.append(cur)
    for r in runs:
        c = np.median(np.array([colour[n] for n in r]), 0)
        if max(alpha[n] for n in r) < PEAK_MIN or float(c.max() - c.min()) < SAT_MIN:
            continue
        lo, hi = r[0], r[-1]
        while (lo - 1) in alpha and np.linalg.norm(colour[lo - 1] - c) < 90:
            lo -= 1
        while (hi + 1) in alpha and np.linalg.norm(colour[hi + 1] - c) < 90:
            hi += 1
        if hi - lo + 1 > 3 * vm["fps"]:
            continue
        keep.update({n: alpha[n] for n in range(lo, hi + 1) if n in alpha})
        keep_cols.append(c)
    if not keep:
        return {"alpha": {}, "color": [0, 0, 255], "bands": bd}
    col = np.median(np.array(keep_cols), 0)
    return {"alpha": {str(n): a for n, a in keep.items()}, "color": [float(np.clip(x, 0, 255)) for x in col],
            "bands": bd}


def build(short_path, vm, samples=36):
    pairs = _pairs(short_path, vm, mapped_samples(vm, samples), 540)
    W, mae = fit_grade(pairs, vm)
    big = _pairs(short_path, vm, mapped_samples(vm, 6), vm["out_w"])
    ratio = detail_ratio(big, W)
    amount = float(np.clip((ratio - 1.0) * 1.25, 0.0, 1.5))
    ov = overlays(short_path, vm, W)
    C.log(f"look: grade mae {mae if mae is None else round(mae, 1)}, detail x{ratio:.2f} -> sharpen {amount:.2f}, "
          f"overlay frames {len(ov['alpha'])}")
    return {"poly": None if W is None else W.tolist(), "grade_mae": mae,
            "sharpen": {"sigma": 1.5 * vm["out_w"] / 1080, "amount": amount, "ratio": ratio}, "overlay": ov}
