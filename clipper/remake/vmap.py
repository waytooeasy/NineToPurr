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


def similarity(f1, f2, matcher=None):
    """2x3 similarity mapping points of image 1 onto image 2, or None."""
    (kp1, d1), (kp2, d2) = f1, f2
    if d1 is None or d2 is None or len(kp1) < 8 or len(kp2) < 8:
        return None
    pairs = (matcher or cv2.BFMatcher(cv2.NORM_L2)).knnMatch(d1, d2, k=2)
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


FILL_S = 0.5          # unmapped frames: search this far around the predicted section frame (#121)
FILL_STEP = 3         # coarse step of that search, then every frame around the best
FILL_BLUR = 1.2       # analysis px: motion-blurred frames correlate better once both sides are softened


def gap_plan(nfr, best, fps, sec_fps):
    """For every frame the matcher missed: candidates (seg, predicted section frame, M) taken from the nearest
    mapped frame before and after it (same crop, continuous footage). At a fast cut the frames before the next
    shot's first match get that shot's crop as well as the previous one's; the openings get the first shot's.
    best: {n: (seg, m, M, ncc)}; sec_fps: {seg: fps of its section}. -> {n: [(seg, m_pred, M), ...]}"""
    mapped = sorted(best)
    if not mapped:
        return {}
    plan = {}
    j = 0
    for n in range(nfr):
        if n in best:
            continue
        while j < len(mapped) and mapped[j] < n:
            j += 1
        cands = []
        for nb in ([mapped[j - 1]] if j > 0 else []) + ([mapped[j]] if j < len(mapped) else []):
            seg, m, M, _ = best[nb]
            mp = int(round(m + (n - nb) * sec_fps[seg] / fps))
            if not any(c[0] == seg and abs(c[1] - mp) <= 1 and np.allclose(c[2], M) for c in cands):
                cands.append((seg, mp, M))
        plan[n] = cands
    return plan


def _soft(img):
    return cv2.GaussianBlur(img, (0, 0), FILL_BLUR)


def best_in_window(their, sec, m_lo, center, M, win):
    """(ncc, m): the section frame around `center` (±win) that their frame matches best under the crop M.
    sec: softened gray section frames starting at index m_lo."""
    M = np.asarray(M, np.float64)
    lo, hi = max(m_lo, center - win), min(m_lo + len(sec) - 1, center + win)
    if lo > hi:
        return -1.0, None
    seen = {}

    def score(m):
        if m not in seen:
            seen[m] = warp_ncc(their, sec[m - m_lo], M)
        return seen[m]

    coarse = list(range(lo, hi + 1, FILL_STEP)) + ([center] if lo <= center <= hi else [])
    mb = max(coarse, key=score)
    for m in range(max(lo, mb - FILL_STEP + 1), min(hi, mb + FILL_STEP - 1) + 1):
        score(m)
    m = max(seen, key=seen.get)
    return seen[m], m


def _fill_job(args):
    """One run of consecutive unmapped frames: [(n, seg, m, M, ncc)] for those that match above MIN_NCC."""
    short_path, fps, asz, n0, n1, plan, secs = args
    th = C.read_frames(short_path, n0, n1 - n0, fps, asz, gray=True)
    win = {seg: int(round(FILL_S * secs[seg][1])) for seg in secs}
    need = {}
    for n in range(n0, n0 + len(th)):
        for seg, mp, _ in plan[n]:
            a, b = need.get(seg, (mp, mp))
            need[seg] = (min(a, mp - win[seg]), max(b, mp + win[seg]))
    frames = {}
    for seg, (a, b) in need.items():
        path, sfps, vsz = secs[seg]
        a = max(0, a)
        frames[seg] = (a, [_soft(f) for f in C.read_frames(path, a, b - a + 1, sfps, vsz, gray=True)])
    out = []
    for i, n in enumerate(range(n0, n0 + len(th))):
        their = _soft(th[i])
        best = None
        for seg, mp, M in plan[n]:
            m_lo, sec = frames[seg]
            c, m = best_in_window(their, sec, m_lo, mp, M, win[seg])
            if m is not None and (best is None or c > best[4]):
                best = (n, seg, m, M, c)
        if best is not None and best[4] >= MIN_NCC:
            out.append(best)
    return out


def fill_gaps(short_path, fps, asz, nfr, best, secs, workers=WORKERS):
    """Frames SIFT missed (fast cuts, the first frames, motion blur): found by correlation around the predicted
    section frame with a neighbour's crop (#121). secs: {seg: (section file, fps, analysis size)}.
    Adds them to `best` in place; returns how many were filled."""
    plan = gap_plan(nfr, best, fps, {s: v[1] for s, v in secs.items()})
    runs, cur = [], []
    for n in sorted(plan):
        if cur and (n != cur[-1] + 1 or len(cur) >= 60):
            runs.append(cur)
            cur = []
        cur.append(n)
    if cur:
        runs.append(cur)
    jobs = [(str(short_path), fps, asz, r[0], r[-1] + 1, {n: plan[n] for n in r}, secs) for r in runs]
    if not jobs:
        return 0
    with Pool(max(1, workers)) as pool:
        res = [x for part in pool.map(_fill_job, jobs) for x in part]
    for n, seg, m, M, c in res:
        best[n] = (seg, m, M, c)
    return len(res)


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
    sift_n = len(best)
    segs = amap["segments"]
    secs = {i: (sections[g["sec"]]["file"], secp[g["sec"]]["fps"],
                (VA, int(round(VA * secp[g["sec"]]["h"] / secp[g["sec"]]["w"] / 2) * 2))) for i, g in enumerate(segs)}
    filled = fill_gaps(short_path, fps, asz, nfr, best, secs, workers) if best else 0
    frames = []
    for n in sorted(best):
        seg_i, m, M, c = best[n]
        sec_i = amap["segments"][seg_i]["sec"]
        k, cx, cy, rot = to_out(M, (W, H), (secp[sec_i]["w"], secp[sec_i]["h"]), out_w)
        frames.append({"n": n, "seg": seg_i, "sec": sec_i, "m": m, "k": k, "cx": cx, "cy": cy, "rot": rot, "ncc": c})
    shots = single_shots(frames, short_path, fps, sections, secp, amap, out_wh)
    stacked = 0
    tpls = probe_stack(short_path, fps, asz, nfr, best, amap, sections, secp, shots, workers)
    if tpls:      # stacked / overlay layout (#130): every frame mapped per panel, stacked frames become 'stack' shots
        from . import panels as PN
        kind, recs = map_panels(short_path, fps, asz, nfr, best, amap, sections, secp, tpls, workers)
        st_shots, st_frames = PN.stack_shots(kind, tpls, amap, secp, (W, H), out_w)
        if st_shots:
            singles = [f for f in frames if kind[f["n"]] is not None and kind[f["n"]][0] == "single"]
            frames = singles + [{"n": n, "seg": v[0], "m": v[1]} for n, v in st_frames.items()]
            frames.sort(key=lambda f: f["n"])
            shots = st_shots
            for run in _single_runs(singles, set(st_frames)):
                shots += single_shots(run, short_path, fps, sections, secp, amap, out_wh)
            stacked = len(st_frames)
            hits = [sum(1 for r in recs if len(r[4]) > i and r[4][i] is not None) for i in range(3)]
            C.log(f"stack: panels mapped on {hits[:max(len(t['rects']) for t in tpls)]} of {len(recs)} frames tried")
            C.log(f"stack: {len(tpls)} layout(s) " + "; ".join(
                " | ".join("[" + ", ".join(f"{v:.3f}" for v in r) + "]" for r in t["rects"]) for t in tpls)
                + f", {stacked} frames stacked")
    if not shots:
        raise RuntimeError("video map: no frame of the Short matches the sections")
    # cut frames: a shot runs until the next one starts (frames the matcher missed follow the shot before)
    shots.sort(key=lambda s: s["n0"])
    shots[0]["n0"] = 0
    for a, b in zip(shots, shots[1:]):
        a["n1"] = b["n0"]
    shots[-1]["n1"] = nfr
    C.log(f"video map: {len(frames)}/{nfr} frames mapped ({filled} filled after SIFT's {sift_n}, {stacked} stacked), "
          f"{len(shots)} shots "
          + ", ".join(f"{s['n0']}:{s['layout']}" for s in shots))
    return {"fps": fps, "w": W, "h": H, "out_w": out_wh[0], "out_h": out_wh[1], "nfr": nfr, "shots": shots,
            "frames": {str(f["n"]): [f["seg"], f["m"]] for f in frames}, "mapped": len(frames), "filled": filled,
            "stacked": stacked,
            "sections": [{"file": s["file"], "fps": p["fps"], "w": p["w"], "h": p["h"]} for s, p in zip(sections, secp)]}


def single_shots(frames, short_path, fps, sections, secp, amap, out_wh):
    """Shots of single-crop frames: split at jumps, smoothed path, layout 'full' / 'fit' (+ its surround) /
    'other' (the surround is neither a blurred copy nor one colour)."""
    if not frames:
        return []
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
                col = flat_bg(short_path, fps, samples, out_wh, sec_wh)
                if col is not None:              # a solid background (black bars...) instead of a blurred copy
                    shot["bg"]["color"] = col
                else:
                    shot["layout"] = "other"
        shots.append(shot)
    return shots


def _single_runs(frames, stacked):
    """Single-crop frames grouped into runs that no stacked frame interrupts."""
    runs, cur = [], []
    st = sorted(stacked)
    j = 0
    for f in frames:
        if cur:
            while j < len(st) and st[j] <= cur[-1]["n"]:
                j += 1
            if j < len(st) and st[j] < f["n"]:
                runs.append(cur)
                cur = []
        cur.append(f)
    if cur:
        runs.append(cur)
    return runs


FLAT_MAD = 6.0        # a surround this even (mean |pixel - median|, 0-255) is a solid colour


def flat_bg(short_path, fps, samples, out_wh, sec_wh, cap_band=(0.36, 0.64)):
    """[b, g, r] when the surround of a 'fit' band is one colour on every sample, else None."""
    (OW, OH), (SW, SH) = out_wh, sec_wh
    rw, rh = OW // 4, OH // 4
    px = []
    for n, m, k, cx, cy in samples:
        th = C.read_frames(short_path, n, 1, fps, (rw, rh))
        if not len(th):
            continue
        top, bot = OH / 2 - cy / k, OH / 2 + (SH - cy) / k
        mask = np.zeros((rh, rw), bool)
        mask[2:max(2, int(top / 4) - 2)] = True
        mask[min(rh - 2, int(bot / 4) + 2):rh - 2] = True
        mask[int(cap_band[0] * rh):int(cap_band[1] * rh)] = False
        if mask.sum() >= 200:
            px.append(th[0][mask].astype(np.float32))
    if not px:
        return None
    px = np.concatenate(px)
    col = np.median(px, 0)
    if float(np.abs(px - col).max(1).mean()) > FLAT_MAD:
        return None
    return [float(v) for v in col]


def probe_stack(short_path, fps, asz, nfr, best, amap, sections, secp, shots, workers=WORKERS):
    """Stack templates (panels.templates) found on sample frames outside 'fit' shots, [] for single-crop Shorts."""
    from . import panels as PN
    fit = [(s["n0"], s["n1"]) for s in shots if s["layout"] == "fit"]
    picks, seen = [], set()
    for t in np.linspace(0, nfr - 1, PN.PROBES).astype(int):
        if any(a <= t < b for a, b in fit):
            continue
        near = [n for n in range(t - 15, t + 16) if n in best]
        if near:
            n = min(near, key=lambda x: abs(x - t))
            seg, m, M, _ = best[n]
        else:
            seg = next((i for i, g in enumerate(amap["segments"]) if g["t0"] <= t / fps < g["t1"]), None)
            if seg is None:
                continue
            g = amap["segments"][seg]
            n, M = int(t), None
            m = int(round((t / fps + g["off"]) * secp[g["sec"]]["fps"]))
        if n in seen:
            continue
        seen.add(n)
        p = secp[amap["segments"][seg]["sec"]]
        vsz = (VA, int(round(VA * p["h"] / p["w"] / 2) * 2))
        picks.append((str(short_path), fps, asz, sections[amap["segments"][seg]["sec"]]["file"], p["fps"], vsz,
                      n, seg, m, None if M is None else np.asarray(M).tolist()))
    if not picks:
        return []
    with Pool(max(1, min(workers, len(picks)))) as pool:
        probes = [p for p in pool.map(PN.probe_job, picks) if p is not None]
    return PN.templates(probes, asz)


def map_panels(short_path, fps, asz, nfr, best, amap, sections, secp, tpls, workers=WORKERS):
    """Pass 2 (#130): every frame of the Short against the stack templates. -> (panels.classify kinds, records)."""
    from . import panels as PN
    tmasks = [PN.masks_for(t["rects"], asz) for t in tpls]
    jobs = []
    for i, seg in enumerate(amap["segments"]):
        p = secp[seg["sec"]]
        vsz = (VA, int(round(VA * p["h"] / p["w"] / 2) * 2))
        a = max(0, int((seg["t0"] - MARGIN_S) * fps))
        b = min(nfr, int(np.ceil((seg["t1"] + MARGIN_S) * fps)))
        for n0 in range(a, b, 90):
            n1 = min(b, n0 + 90)
            hints = {n: best[n][1] for n in range(n0, n1) if n in best and best[n][0] == i}
            jobs.append((i, str(short_path), fps, asz, sections[seg["sec"]]["file"], p["fps"], vsz, seg["off"],
                         n0, n1, tmasks, hints))
    with Pool(max(1, workers)) as pool:
        res = [r for part in pool.map(PN.map_job, jobs) for r in part]
    recs = {}
    for r in res:              # a frame near a segment switch is tried in both: keep the better one
        sc = sum(max(c, 0) for c, M in zip(r[5], r[4]) if M is not None)
        if r[0] not in recs or sc > recs[r[0]][0]:
            recs[r[0]] = (sc, r)
    recs = [v[1] for _, v in sorted(recs.items())]
    single = {n for n in best}
    return PN.classify(nfr, recs, single, asz), recs


def params_at(shot, n):
    """(k, cx, cy) for frame n of a shot (or of a stack panel): its own path, else the nearest mapped frame."""
    p = shot["path"].get(str(n))
    if p is not None:
        return p
    keys = sorted(int(x) for x in shot["path"])
    j = min(keys, key=lambda x: abs(x - n))
    return shot["path"][str(j)]
