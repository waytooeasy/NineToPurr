"""Video map of a clipper Short onto the downloaded VOD sections (D58).

For every frame of the Short: which section frame it shows and where (SIFT + RANSAC similarity, their frame ->
section). From that: cuts (the mapping jumps), a smooth camera path per shot (holds, pans and slow zooms come out
as they were edited) and the layout of each shot: 'full' (the stream fills the frame) or 'fit' (the stream is a
band across the frame over a blurred copy whose zoom, blur and brightness are fitted here).

Output coordinates are for an output frame OW wide with the Short's aspect: stream x = cx + (u - OW/2) * k,
stream y = cy + (v - OH/2) * k (stream = the section file at native size).
"""
import os
from multiprocessing import Pool

import cv2
import numpy as np

from . import common as C

AW = 540              # analysis width of the Short
VA = 960              # analysis width of the sections
MIN_NCC = 0.55        # a frame is mapped at this correlation after warping
MARGIN_S = 0.15       # video cuts can sit off the audio switch (J/L cuts; ~30 ms in the study)
JUMP = 0.012          # per-frame change of zoom or centre (fraction) above this = a cut
MIN_SHOT_F = 3        # shorter runs are mapping noise, not shots
BG_RMSE_MAX = 38.0    # a 'fit' shot whose surround is not a blurred copy is another layout (stack...)
WORKERS = int(os.environ.get("REMAKE_WORKERS", "5"))
SYNC_D = 3            # frames the video may sit off the audio map

_sift = None


def _feats(img):
    global _sift
    if _sift is None:
        _sift = cv2.SIFT_create(nfeatures=2500)
    return _sift.detectAndCompute(img, None)


def similarity(f1, f2):
    """2x3 similarity mapping points of image 1 onto image 2, or None."""
    (kp1, d1), (kp2, d2) = f1, f2
    if d1 is None or d2 is None or len(kp1) < 8 or len(kp2) < 8:
        return None
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1, d2, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
    if len(good) < 8:
        return None
    p1 = np.float32([kp1[m.queryIdx].pt for m in good])
    p2 = np.float32([kp2[m.trainIdx].pt for m in good])
    M, inl = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=2.0,
                                         maxIters=4000, confidence=0.999)
    if M is None or inl is None or int(inl.sum()) < 8:
        return None
    idx = inl.ravel().astype(bool)
    M2, _ = cv2.estimateAffinePartial2D(p1[idx], p2[idx], method=cv2.LMEDS)
    return M2 if M2 is not None else M


def warp_ncc(their, sec, M):
    """Correlation of their frame with the section frame warped into it (where the section exists)."""
    h, w = their.shape[:2]
    wv = cv2.warpAffine(sec, M, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=0)
    ok = cv2.warpAffine(np.full(sec.shape[:2], 255, np.uint8), M, (w, h),
                        flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP, borderValue=0) > 0
    x, y = their[ok].astype(np.float32), wv[ok].astype(np.float32)
    if x.size < 2000:
        return -1.0
    x -= x.mean()
    y -= y.mean()
    return float((x * y).sum() / (np.sqrt((x * x).sum() * (y * y).sum()) + 1e-9))


def _job(args):
    """Map frames n0..n1-1 of the Short against one (section, offset) candidate."""
    seg_i, short_path, fps, asz, sec_path, sfps, vsz, off, n0, n1 = args
    th = C.read_frames(short_path, n0, n1 - n0, fps, asz, gray=True)
    m_of = {n: int(round((n / fps + off) * sfps)) for n in range(n0, n0 + len(th))}
    if not m_of:
        return []
    m_lo, m_hi = min(m_of.values()) - 1 - SYNC_D, max(m_of.values()) + 1 + SYNC_D
    if m_hi < 0:
        return []
    m_lo = max(0, m_lo)
    sec = C.read_frames(sec_path, m_lo, m_hi - m_lo + 1, sfps, vsz, gray=True)
    cache = {}

    def sfeat(m):
        if m not in cache:
            cache[m] = _feats(sec[m - m_lo])
        return cache[m]

    out = []
    for i, n in enumerate(range(n0, n0 + len(th))):
        f1 = _feats(th[i])
        best = None
        for d in (0, -1, 1):
            m = m_of[n] + d
            if not (m_lo <= m < m_lo + len(sec)):
                continue
            M = similarity(f1, sfeat(m))
            if M is None:
                continue
            c = warp_ncc(th[i], sec[m - m_lo], M)
            if best is None or c > best[0]:
                best = (c, m, M)
            if c > 0.9:
                break
        if best is not None:
            out.append((n, seg_i, best[1], best[2].tolist(), best[0]))
    return resync(out, th, n0, sec, m_lo)


def resync(out, th, n0, sec, m_lo, samples=16):
    """The audio puts the video a frame or so off (AAC encoder delay, their own J/L cuts): over this run of frames,
    the section frame offset (-SYNC_D..SYNC_D) whose pixels match theirs best, applied to every frame."""
    if len(out) < 4:
        return out
    pick = out[::max(1, len(out) // samples)][:samples]
    score = {}
    for d in range(-SYNC_D, SYNC_D + 1):
        s = []
        for n, _, m, M, _ in pick:
            j = m + d - m_lo
            if 0 <= j < len(sec):
                s.append(warp_ncc(th[n - n0], sec[j], np.asarray(M, np.float64)))
        if len(s) == len(pick):
            score[d] = float(np.mean(s))
    if not score:
        return out
    d = max(score, key=score.get)
    if d == 0 or score[d] - score.get(0, -1) < 0.002:
        return out
    return [(n, seg, m + d, M, c) for n, seg, m, M, c in out]


def _roll(x, w, fn):
    h = w // 2
    return np.array([fn(x[max(0, i - h):i + h + 1]) for i in range(len(x))])


def smooth(path):
    """Median (5) then mean (7) per parameter: holds stay still, linear pans/zooms stay linear."""
    p = np.asarray(path, np.float64)
    if len(p) < 5:
        return p
    p = np.stack([_roll(p[:, j], 5, np.median) for j in range(p.shape[1])], 1)
    return np.stack([_roll(p[:, j], 7, np.mean) for j in range(p.shape[1])], 1)


def to_out(M, short_wh, sec_wh, out_w):
    """(k, cx, cy, rot_deg) for the output frame from an analysis-space similarity."""
    (W, H), (SW, SH) = short_wh, sec_wh
    aw, ah = AW, int(round(AW * H / W / 2) * 2)
    M = np.asarray(M, np.float64)
    f = SW / VA
    s = float(np.hypot(M[0, 0], M[1, 0]))
    k = f * s * aw / out_w
    cx = f * (M[0, 0] * aw / 2 + M[0, 1] * ah / 2 + M[0, 2])
    cy = f * (M[1, 0] * aw / 2 + M[1, 1] * ah / 2 + M[1, 2])
    return k, cx, cy, float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))


def split_shots(frames, sec_wh):
    """frames: sorted [{'n','seg','k','cx','cy'}] -> [[frame, ...], ...] split where the mapping jumps."""
    SW, SH = sec_wh
    shots = []
    for f in frames:
        if shots:
            p = shots[-1][-1]
            jump = (f["seg"] != p["seg"] or f["n"] - p["n"] > 6
                    or abs(np.log(f["k"] / p["k"])) > JUMP
                    or abs(f["cx"] - p["cx"]) / SW > JUMP or abs(f["cy"] - p["cy"]) / SH > JUMP)
            if not jump:
                shots[-1].append(f)
                continue
        shots.append([f])
    # runs shorter than MIN_SHOT_F frames are bad matches: drop them (their frames follow the neighbours)
    keep = [s for s in shots if len(s) >= MIN_SHOT_F]
    merged = []
    for s in keep:
        p = merged[-1] if merged else None
        if p and p[-1]["seg"] == s[0]["seg"] and abs(np.log(s[0]["k"] / p[-1]["k"])) <= JUMP \
                and abs(s[0]["cx"] - p[-1]["cx"]) / SW <= JUMP and abs(s[0]["cy"] - p[-1]["cy"]) / SH <= JUMP:
            p.extend(s)
        else:
            merged.append(s)
    return merged


def layout_of(k, cx, cy, out_wh, sec_wh, tol=0.01):
    """'full' if the stream covers the output frame, else 'fit' (+ the band it covers, as fractions)."""
    (OW, OH), (SW, SH) = out_wh, sec_wh
    top, bot = OH / 2 - cy / k, OH / 2 + (SH - cy) / k
    left, right = OW / 2 - cx / k, OW / 2 + (SW - cx) / k
    band = [max(0.0, top / OH), min(1.0, bot / OH), max(0.0, left / OW), min(1.0, right / OW)]
    full = band[0] <= tol and band[1] >= 1 - tol and band[2] <= tol and band[3] >= 1 - tol
    return ("full" if full else "fit"), band


def fit_bg(short_path, fps, sec_path, sfps, samples, out_wh, sec_wh, cap_band=(0.36, 0.64)):
    """Blurred surround of a 'fit' shot: zoom relative to cover-fill, blur sigma (output px), gain, rmse."""
    (OW, OH), (SW, SH) = out_wh, sec_wh
    rw, rh = OW // 4, OH // 4
    cover = SH / OH                              # stream px per output px when its height fills the frame
    acc = {}
    for n, m, k, cx, cy in samples:
        th = C.read_frames(short_path, n, 1, fps, (rw, rh))[0].astype(np.float32)
        sec = C.read_frames(sec_path, m, 1, sfps, (SW // 4, SH // 4))[0].astype(np.float32)
        top, bot = OH / 2 - cy / k, OH / 2 + (SH - cy) / k
        mask = np.zeros((rh, rw), bool)
        mask[2:max(2, int(top / 4) - 2)] = True
        mask[min(rh - 2, int(bot / 4) + 2):rh - 2] = True
        mask[int(cap_band[0] * rh):int(cap_band[1] * rh)] = False
        if mask.sum() < 200:
            continue
        for rel in (0.55, 0.65, 0.75, 0.85, 0.93, 1.0):
            kb = cover * rel                     # quarter-section px per quarter-output px
            Mb = np.array([[kb, 0, SW / 8 - kb * rw / 2], [0, kb, SH / 8 - kb * rh / 2]])
            w = cv2.warpAffine(sec, Mb, (rw, rh), flags=cv2.INTER_AREA | cv2.WARP_INVERSE_MAP,
                               borderMode=cv2.BORDER_REFLECT)
            for sig in (8, 12, 16, 20, 25, 32, 40):
                b = cv2.GaussianBlur(w, (0, 0), sig / 4)
                A, T = b[mask], th[mask]
                g = float((A * T).sum() / ((A * A).sum() + 1e-9))
                acc.setdefault((rel, sig), []).append((float(np.mean((T - g * A) ** 2)), g))
    if not acc:
        return {"rel": 0.97, "sigma": 20.0 * OW / 1080, "gain": 1.0, "rmse": 0.0}
    agg = {key: (float(np.mean([e for e, _ in v])), float(np.mean([g for _, g in v]))) for key, v in acc.items()}
    (rel, sig), (e, g) = min(agg.items(), key=lambda kv: kv[1][0])
    return {"rel": float(rel), "sigma": float(sig) * OW / 1080, "gain": g, "rmse": float(np.sqrt(e))}


def build(short_path, sections, amap, out_w=1080, workers=WORKERS):
    """Video map: {'fps', 'w', 'h', 'out_w', 'out_h', 'shots': [...], 'frames': {n: [seg, m]}, 'unmapped'}.
    sections: [{'file', ...}]; amap: amap.build() output (segments carry 'sec' and 'off')."""
    sp = C.probe(short_path)
    fps, W, H = sp["fps"], sp["w"], sp["h"]
    nfr = int(round(sp["dur"] * fps))
    asz = (AW, int(round(AW * H / W / 2) * 2))
    secp = [C.probe(s["file"]) for s in sections]
    out_wh = (out_w, int(round(out_w * H / W / 2) * 2))
    jobs = []
    for i, seg in enumerate(amap["segments"]):
        p = secp[seg["sec"]]
        vsz = (VA, int(round(VA * p["h"] / p["w"] / 2) * 2))
        a = max(0, int((seg["t0"] - MARGIN_S) * fps))
        b = min(nfr, int(np.ceil((seg["t1"] + MARGIN_S) * fps)))
        for n0 in range(a, b, 90):
            jobs.append((i, str(short_path), fps, asz, sections[seg["sec"]]["file"], p["fps"], vsz, seg["off"],
                         n0, min(b, n0 + 90)))
    with Pool(max(1, workers)) as pool:
        res = [r for part in pool.map(_job, jobs) for r in part]
    best = {}
    for n, seg_i, m, M, c in res:
        if c >= MIN_NCC and (n not in best or c > best[n][3]):
            best[n] = (seg_i, m, M, c)
    frames = []
    for n in sorted(best):
        seg_i, m, M, c = best[n]
        sec_i = amap["segments"][seg_i]["sec"]
        k, cx, cy, rot = to_out(M, (W, H), (secp[sec_i]["w"], secp[sec_i]["h"]), out_w)
        frames.append({"n": n, "seg": seg_i, "sec": sec_i, "m": m, "k": k, "cx": cx, "cy": cy, "rot": rot, "ncc": c})
    if not frames:
        raise RuntimeError("video map: no frame of the Short matches the sections")
    sec_wh0 = (secp[0]["w"], secp[0]["h"])
    shots = []
    for run in split_shots(frames, sec_wh0):
        sm = smooth([[np.log(f["k"]), f["cx"], f["cy"]] for f in run])
        sec_i = run[0]["sec"]
        sec_wh = (secp[sec_i]["w"], secp[sec_i]["h"])
        path = [[float(np.exp(a)), float(b), float(c)] for a, b, c in sm]
        mid = len(run) // 2
        lay, band = layout_of(*path[mid], out_wh, sec_wh)
        shot = {"n0": run[0]["n"], "n1": run[-1]["n"] + 1, "seg": run[0]["seg"], "sec": sec_i,
                "off": amap["segments"][run[0]["seg"]]["off"], "layout": lay, "band": band,
                "rot": float(np.median([f["rot"] for f in run])),
                "path": {str(f["n"]): p for f, p in zip(run, path)},
                "ncc": float(np.median([f["ncc"] for f in run]))}
        if lay == "fit":
            idx = [run[len(run) // 4], run[len(run) // 2], run[3 * len(run) // 4]]
            samples = [(f["n"], f["m"], *shot["path"][str(f["n"])]) for f in idx]
            shot["bg"] = fit_bg(short_path, fps, sections[sec_i]["file"], secp[sec_i]["fps"], samples, out_wh, sec_wh)
            if shot["bg"]["rmse"] > BG_RMSE_MAX:
                shot["layout"] = "other"
        shots.append(shot)
    # cut frames: a shot runs until the next one starts (frames the matcher missed follow the shot before)
    shots.sort(key=lambda s: s["n0"])
    shots[0]["n0"] = 0
    for a, b in zip(shots, shots[1:]):
        a["n1"] = b["n0"]
    shots[-1]["n1"] = nfr
    C.log(f"video map: {len(frames)}/{nfr} frames mapped, {len(shots)} shots "
          + ", ".join(f"{s['n0']}:{s['layout']}" for s in shots))
    return {"fps": fps, "w": W, "h": H, "out_w": out_wh[0], "out_h": out_wh[1], "nfr": nfr, "shots": shots,
            "frames": {str(f["n"]): [f["seg"], f["m"]] for f in frames}, "mapped": len(frames),
            "sections": [{"file": s["file"], "fps": p["fps"], "w": p["w"], "h": p["h"]} for s, p in zip(sections, secp)]}


def params_at(shot, n):
    """(k, cx, cy) for frame n of a shot: its own path, else the nearest mapped frame (held)."""
    p = shot["path"].get(str(n))
    if p is not None:
        return p
    keys = sorted(int(x) for x in shot["path"])
    j = min(keys, key=lambda x: abs(x - n))
    return shot["path"][str(j)]
