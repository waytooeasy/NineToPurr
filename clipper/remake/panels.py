"""Stacked / overlay layouts (#130): their frame shows two or more crops of the same stream frame (facecam on top
of gameplay, a facecam box over gameplay, two cameras). Each crop is a panel: a rectangle of the output frame with
its own camera path, in vmap's convention (stream x = cx + (u - OW/2) * k, y = cy + (v - OH/2) * k, applied inside
the rectangle). What no panel covers (a divider, a solid background) is filled with its measured colour.

1. probe (`find_panels`): on sample frames the crop pass 1 found (or a fresh SIFT) explains one region; SIFT on
   what is left finds the next crop, until the frame is explained.
2. templates (`templates`): sample geometries that agree become one template; every inner edge is moved to where
   the pixels switch from one panel to the other (`refine_edges`), the rest of the frame gets its colour.
3. pass 2 (`map_job`): every frame, every panel: SIFT inside the panel only -> its crop. A frame is stacked when two
   or more panels map to different crops (`classify`).
4. shots (`stack_shots`): stacked runs split where the main panel jumps (or any panel jumps hard) or the footage
   changes; one smoothed path per panel.
"""
import cv2
import numpy as np

from . import common as C
from . import vmap as VM

WIN = 15              # local correlation window (analysis px)
COV_NCC = 0.5         # a pixel is explained by a crop at this local correlation
PANEL_MIN = 0.06      # a panel covers at least this share of the frame
MAX_PANELS = 3
PROBES = 16           # sample frames probed for a stack
TOL = 0.05            # rectangles of two samples agree within this (share of width / height) per edge
SNAP = 0.025          # an edge this close to the frame border is the border
EDGE_S = 0.05         # inner edges are searched this far (share of the frame) around the coarse one
SAME_PX = 3.0         # two crops are the same when they place the frame within this (section analysis px)
HARD_JUMP = 4         # a secondary panel cuts a shot only on a jump this many times vmap.JUMP
ERR_CAP = 60.0        # per-pixel error cap for the edge search (0-255)
MERGE_TOL = 0.015     # two templates whose refined edges agree this closely are one layout
DENSE_N = 8000        # keypoints kept per section frame (a facecam corner keeps enough of its own)

_dense = _masked = None


def dense_feats(img):
    """SIFT of a section frame with a high cap: small regions (a facecam) keep their keypoints."""
    global _dense
    if _dense is None:
        _dense = cv2.SIFT_create(nfeatures=DENSE_N, contrastThreshold=0.03)
    return _dense.detectAndCompute(img, None)


def feats_in(img, mask):
    global _masked
    if _masked is None:
        _masked = cv2.SIFT_create(nfeatures=2000, contrastThreshold=0.03)
    return _masked.detectAndCompute(img, mask.astype(np.uint8) * 255)


_flann = None


def similarity(f1, f2):
    """vmap.similarity with a FLANN matcher (the dense section sets are large)."""
    global _flann
    if _flann is None:
        _flann = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 4}, {"checks": 48})
    return VM.similarity(f1, f2, matcher=_flann)


# ---------------- pixels ----------------
def warp_in(sec, M, size):
    """Section frame warped into their frame (w, h) by M (their -> section), and where it exists."""
    w, h = size
    M = np.asarray(M, np.float64)
    wv = cv2.warpAffine(sec, M, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=0)
    ok = cv2.warpAffine(np.full(sec.shape[:2], 255, np.uint8), M, (w, h),
                        flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP, borderValue=0) > 0
    return wv, ok


def local_ncc(a, b, win=WIN):
    """Per-pixel correlation of a and b over win x win windows, and where both are flat."""
    a, b = a.astype(np.float32), b.astype(np.float32)
    k = (win, win)
    ma, mb = cv2.blur(a, k), cv2.blur(b, k)
    va, vb = cv2.blur(a * a, k) - ma * ma, cv2.blur(b * b, k) - mb * mb
    cab = cv2.blur(a * b, k) - ma * mb
    return cab / np.sqrt(np.maximum(va, 1.0) * np.maximum(vb, 1.0)), (va < 25) & (vb < 25)


def coverage(th, sec, M):
    """Pixels of their frame this crop explains (flat areas count: they agree with any crop)."""
    wv, ok = warp_in(sec, M, th.shape[::-1])
    ncc, flat = local_ncc(th, wv)
    ok = cv2.erode(ok.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    return ok & ((ncc >= COV_NCC) | flat)


def masked_ncc(th, sec, M, mask):
    """Correlation of their frame with the warped section frame inside `mask` (where the section exists)."""
    wv, ok = warp_in(sec, M, th.shape[::-1])
    sel = ok & mask
    if sel.sum() < 1500:
        return -1.0
    x, y = th[sel].astype(np.float32), wv[sel].astype(np.float32)
    x -= x.mean()
    y -= y.mean()
    return float((x * y).sum() / (np.sqrt((x * x).sum() * (y * y).sum()) + 1e-9))


def same_crop(M1, M2, size, px=SAME_PX):
    """True when two maps place their frame (size w, h) at the same spot of the section."""
    w, h = size
    pts = np.float64([[w / 2, h / 2, 1], [0, 0, 1], [w, 0, 1], [0, h, 1], [w, h, 1]])
    a, b = pts @ np.asarray(M1, np.float64).T, pts @ np.asarray(M2, np.float64).T
    return float(np.abs(a - b).max()) < px


def _runs(flags, gap):
    """[(start, end)] of True runs, joining runs separated by fewer than `gap` False."""
    out = []
    for i, f in enumerate(flags):
        if not f:
            continue
        if out and i - out[-1][1] <= gap:
            out[-1][1] = i + 1
        else:
            out.append([i, i + 1])
    return out


def rect_of(cov, min_area):
    """[y0, y1, x0, x1] of the largest explained region, read as a rectangle (captions and small holes inside it
    are bridged), and the cleaned region itself. (None, None) when it is too small."""
    H, W = cov.shape
    m = cv2.morphologyEx(cov.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=4)
    if n < 2:
        return None, None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[i, cv2.CC_STAT_AREA] < min_area:
        return None, None
    c = lab == i
    x, y, w, h = (int(v) for v in stats[i, :4])
    rows = _runs(c[y:y + h, x:x + w].mean(1) >= 0.35, int(0.12 * H))
    y0, y1 = max(rows, key=lambda r: r[1] - r[0])
    y0, y1 = y0 + y, y1 + y
    cols = _runs(c[y0:y1, x:x + w].mean(0) >= 0.35, int(0.12 * W))
    x0, x1 = max(cols, key=lambda r: r[1] - r[0])
    x0, x1 = x0 + x, x1 + x
    if (y1 - y0) * (x1 - x0) < min_area:
        return None, None
    return [y0, y1, x0, x1], c


def find_panels(th, sec, secf=None, M0=None, max_panels=MAX_PANELS):
    """[(rect px [y0, y1, x0, x1], M)] in their analysis frame `th` (gray), canonical order. M0: pass 1's crop."""
    H, W = th.shape
    min_area = PANEL_MIN * H * W
    free = np.ones((H, W), bool)
    out = []
    pending = [np.asarray(M0, np.float64)] if M0 is not None else []
    for _ in range(max_panels + 3):
        if len(out) >= max_panels or free.sum() < min_area:
            break
        from_m0 = bool(pending)
        if from_m0:
            M = pending.pop()
        else:
            mask = cv2.erode(free.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
            if mask.sum() < min_area:
                break
            if secf is None:
                secf = dense_feats(sec)
            M = similarity(feats_in(th, mask), secf)
            if M is None:
                break
        cov = coverage(th, sec, M)
        if any(same_crop(M, p[1], (W, H)) for p in out):
            free &= ~cov                  # leftovers of a panel already found (flat spots, holes): look elsewhere
            continue
        rect, region = rect_of(cov & free, min_area)
        if rect is None:
            if from_m0:
                continue                  # pass 1's crop explains too little here: look with SIFT instead
            break
        out.append((rect, M))
        free &= ~region
    order = canon([r for r, _ in out])
    return [out[i] for i in order]


def _inside(a, b, share=0.8):
    """Rectangle a lies (mostly) inside rectangle b."""
    h = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    w = max(0.0, min(a[3], b[3]) - max(a[2], b[2]))
    area = max(1e-9, (a[1] - a[0]) * (a[3] - a[2]))
    return h * w >= share * area and (b[1] - b[0]) * (b[3] - b[2]) > area


def canon(rects):
    """Indices in draw order: panels other panels sit on first (a box inside another panel after it), then top to
    bottom, left to right. Also the order samples are compared in."""
    depth = [sum(_inside(r, o) for j, o in enumerate(rects) if j != i) for i, r in enumerate(rects)]
    return sorted(range(len(rects)), key=lambda i: (depth[i], rects[i][0], rects[i][2]))


def probe_job(args):
    """One sample frame -> {'n', 'seg', 'm', 'panels': [(rect px, M)]} (None if a frame can't be read)."""
    short_path, fps, asz, sec_path, sfps, vsz, n, seg, m, M0 = args
    col = C.read_frames(short_path, n, 1, fps, asz)
    sec = C.read_frames(sec_path, max(0, m), 1, sfps, vsz, gray=True)
    if not len(col) or not len(sec):
        return None
    panels = find_panels(cv2.cvtColor(col[0], cv2.COLOR_BGR2GRAY), sec[0], M0=M0)
    return {"n": int(n), "seg": seg, "m": int(m), "col": col[0], "sec": sec[0],
            "panels": [([int(v) for v in r], np.asarray(M).tolist()) for r, M in panels]}


# ---------------- templates ----------------
def _frac(rect, H, W):
    y0, y1, x0, x1 = rect
    return [y0 / H, y1 / H, x0 / W, x1 / W]


def _agree(a, b, tol=TOL):
    return len(a) == len(b) and all(max(abs(p - q) for p, q in zip(r, s)) <= tol for r, s in zip(a, b))


def cluster(geoms, min_members=2):
    """geoms: [(sample, [rect fractions, largest first])] with >= 2 panels -> [[sample, ...] per template],
    biggest group first; groups with fewer than `min_members` samples are dropped (one odd frame is no layout)."""
    groups = []
    for s, g in geoms:
        for grp in groups:
            if _agree(g, grp["rects"]):
                grp["members"].append((s, g))
                break
        else:
            groups.append({"rects": g, "members": [(s, g)]})
    groups = [g for g in groups if len(g["members"]) >= min_members]
    return sorted(groups, key=lambda g: -len(g["members"]))


def median_rects(members):
    rs = np.array([g for _, g in members], np.float64)       # (samples, panels, 4)
    return np.median(rs, 0).tolist()


def error_map(th, sec, M, rect):
    """|their - (g * crop + o)| per pixel (low-passed, capped), g/o fitted inside the panel's rectangle."""
    a = cv2.GaussianBlur(th.astype(np.float32), (0, 0), 1.5)
    wv, ok = warp_in(cv2.GaussianBlur(sec.astype(np.float32), (0, 0), 1.5), M, th.shape[::-1])
    y0, y1, x0, x1 = (int(v) for v in rect)
    sel = np.zeros(ok.shape, bool)
    sel[y0:y1, x0:x1] = True
    sel &= ok
    g, o = 1.0, 0.0
    if sel.sum() > 500:
        A = np.stack([wv[sel], np.ones(int(sel.sum()), np.float32)], 1)
        (g, o), *_ = np.linalg.lstsq(A, a[sel], rcond=None)
    e = np.minimum(np.abs(a - (g * wv + o)), ERR_CAP)
    e[~ok] = ERR_CAP
    return e


def _owner(R, i, y, x, H, W):
    """The panel (other than i) drawn on top at pixel (y, x), -1 for the fill, None outside the frame."""
    if not (0 <= y < H and 0 <= x < W):
        return None
    for j in reversed(range(len(R))):
        if j != i and R[j][0] <= y < R[j][1] and R[j][2] <= x < R[j][3]:
            return j
    return -1


def refine_edges(rects, errs, fill_err, H, W):
    """Inner edges moved to where the pixels switch from this panel to what lies outside it (the adjacent panel,
    the panel it sits on, or the fill); edges near the border snap to it. rects: px, draw order. errs: summed
    error map per panel; fill_err: the fill's, or None."""
    R = [[int(round(v)) for v in r] for r in rects]
    for i in range(len(R)):
        for side in ("top", "bottom", "left", "right"):
            y0, y1, x0, x1 = R[i]
            horiz = side in ("top", "bottom")
            dim = H if horiz else W
            pos = {"top": y0, "bottom": y1, "left": x0, "right": x1}[side]
            border = 0 if side in ("top", "left") else dim
            if abs(pos - border) <= SNAP * dim:
                R[i][("top", "bottom", "left", "right").index(side)] = border
                continue
            s = max(2, int(EDGE_S * dim))
            look = s + 2
            if horiz:
                j = _owner(R, i, pos - look if side == "top" else pos + look, (x0 + x1) // 2, H, W)
            else:
                j = _owner(R, i, (y0 + y1) // 2, pos - look if side == "left" else pos + look, H, W)
            out_err = errs[j] if (j is not None and j >= 0) else (fill_err if j == -1 else None)
            if out_err is None:
                continue
            lo, hi = max(0, pos - s), min(dim, pos + s)
            if hi - lo < 3:
                continue
            if horiz:
                pin, pout = errs[i][lo:hi, x0:x1].sum(1), out_err[lo:hi, x0:x1].sum(1)
            else:
                pin, pout = errs[i][y0:y1, lo:hi].sum(0), out_err[y0:y1, lo:hi].sum(0)
            cin, cout = np.concatenate([[0], np.cumsum(pin)]), np.concatenate([[0], np.cumsum(pout)])
            if side in ("top", "left"):          # outside before p, inside from p on
                cost = cout + (cin[-1] - cin)
            else:                                # inside before p, outside from p on
                cost = cin + (cout[-1] - cout)
            R[i][("top", "bottom", "left", "right").index(side)] = lo + int(np.argmin(cost))
    return R


def templates(probes, asz):
    """probes: [{'n', 'seg', 'm', 'col': their analysis frame (BGR), 'sec': section analysis frame (gray),
    'panels': [(rect px, M)]}] -> [{'rects': [[top, bot, left, right] fractions], 'fill': [b, g, r] | None,
    'members': k}]."""
    AW, AH = asz
    geoms = [(p, [_frac(r, AH, AW) for r, _ in p["panels"]]) for p in probes if len(p["panels"]) >= 2]
    out = []
    for grp in cluster(geoms)[:2]:
        rects = median_rects(grp["members"])
        order = canon(rects)
        rects = [rects[i] for i in order]
        px = [[r[0] * AH, r[1] * AH, r[2] * AW, r[3] * AW] for r in rects]
        errs = [np.zeros((AH, AW), np.float32) for _ in rects]
        cover = np.zeros((AH, AW), bool)
        for r in px:
            cover[int(r[0]):int(r[1]), int(r[2]):int(r[3])] = True
        fills, ths = [], []
        for p, _ in grp["members"]:
            th = cv2.cvtColor(p["col"], cv2.COLOR_BGR2GRAY)
            Ms = [p["panels"][order[i]][1] for i in range(len(rects))]
            for i, M in enumerate(Ms):
                errs[i] += error_map(th, p["sec"], M, px[i])
            if (~cover).sum() > 0.01 * AH * AW:
                fills.append(np.median(p["col"][~cover], 0))
            ths.append(th)
        fill = np.median(fills, 0).tolist() if fills else None
        fill_err = None
        if fill is not None:
            g = float(np.dot(fill, [0.114, 0.587, 0.299]))
            fill_err = sum(np.minimum(np.abs(cv2.GaussianBlur(t.astype(np.float32), (0, 0), 1.5) - g), ERR_CAP)
                           for t in ths)
        R = refine_edges(px, errs, fill_err, AH, AW)
        cover[:] = False
        for r in R:
            cover[r[0]:r[1], r[2]:r[3]] = True
        if (~cover).sum() <= 0.002 * AH * AW:
            fill = None
        elif fill is None:                       # refined edges opened a gap: measure its colour
            fill = np.median(np.concatenate([p["col"][~cover] for p, _ in grp["members"]]), 0).tolist()
        t = {"rects": [_frac(r, AH, AW) for r in R], "fill": fill, "members": len(grp["members"])}
        if not any(_agree(t["rects"], o["rects"], MERGE_TOL) for o in out):   # refined to the same layout: one
            out.append(t)
    return out


# ---------------- pass 2: every frame, every panel ----------------
def masks_for(rects, asz, shrink=4):
    """Per panel: its pixels in their analysis frame minus the panels drawn over it, eroded a little."""
    AW, AH = asz
    px = [[int(round(r[0] * AH)), int(round(r[1] * AH)), int(round(r[2] * AW)), int(round(r[3] * AW))] for r in rects]
    out = []
    for i, (y0, y1, x0, x1) in enumerate(px):
        m = np.zeros((AH, AW), bool)
        m[y0:y1, x0:x1] = True
        for (a0, a1, b0, b1) in px[i + 1:]:
            m[a0:a1, b0:b1] = False
        out.append(cv2.erode(m.astype(np.uint8), np.ones((2 * shrink + 1, 2 * shrink + 1), np.uint8)) > 0)
    return out


def map_frame(th, sec_at, m0, masks, sync=(0, -1, 1)):
    """One frame against one template: (m, [M | None per panel], [ncc per panel]). The section frame is chosen on
    the main panel (index 0) around m0; sec_at(m) -> (gray frame, features) or None."""
    P = len(masks)
    Ms, cs = [None] * P, [-1.0] * P
    feats = [feats_in(th, mk) for mk in masks]
    m_best = None
    for p in range(P):
        cands = []
        for d in (sync if m_best is None else (0,)):
            m = (m0 if m_best is None else m_best) + d
            s = sec_at(m)
            if s is None:
                continue
            M = similarity(feats[p], s[1])
            if M is None:
                continue
            cands.append((masked_ncc(th, s[0], M, masks[p]), m, M))
            if cands[-1][0] > 0.9:
                break
        if not cands:
            continue
        c, m, M = max(cands, key=lambda x: x[0])
        if m_best is None:
            m_best = m
        Ms[p], cs[p] = M, c
    return (m_best if m_best is not None else m0), Ms, cs


def map_job(args):
    """Frames n0..n1-1 of the Short against the templates: [(n, seg_i, m, tpl, [M | None], [ncc])]."""
    seg_i, short_path, fps, asz, sec_path, sfps, vsz, off, n0, n1, tmasks, hints = args
    th = C.read_frames(short_path, n0, n1 - n0, fps, asz, gray=True)
    m_of = {n: int(hints.get(n, round((n / fps + off) * sfps))) for n in range(n0, n0 + len(th))}
    if not m_of:
        return []
    m_lo = max(0, min(m_of.values()) - 1 - VM.SYNC_D)
    m_hi = max(m_of.values()) + 1 + VM.SYNC_D
    if m_hi < 0:
        return []
    sec = C.read_frames(sec_path, m_lo, m_hi - m_lo + 1, sfps, vsz, gray=True)
    cache = {}

    def sec_at(m):
        if not (m_lo <= m < m_lo + len(sec)):
            return None
        if m not in cache:
            cache[m] = (sec[m - m_lo], dense_feats(sec[m - m_lo]))
        return cache[m]

    out = []
    for i, n in enumerate(range(n0, n0 + len(th))):
        best = None
        for t, masks in enumerate(tmasks):
            m, Ms, cs = map_frame(th[i], sec_at, m_of[n], masks)
            area = [float(mk.sum()) for mk in masks]
            score = sum(a * max(c, 0) for a, c in zip(area, cs) if c >= VM.MIN_NCC) / max(1.0, sum(area))
            if best is None or score > best[0]:
                best = (score, (n, seg_i, m, t, [M.tolist() if M is not None and c >= VM.MIN_NCC else None
                                                 for M, c in zip(Ms, cs)], [float(c) for c in cs]))
        if best is not None and best[0] > 0:
            out.append(best[1])
    return out


def is_stacked(rec, asz):
    """Two or more panels mapped, to different crops."""
    Ms = [np.asarray(M) for M in rec[4] if M is not None]
    if len(Ms) < 2:
        return False
    return any(not same_crop(a, b, asz) for i, a in enumerate(Ms) for b in Ms[i + 1:])


def classify(nfr, recs, single, asz, reach=30):
    """Per frame: ('stack', rec) or ('single', None) or None (unmapped). A frame with one panel mapped is stacked
    when the nearest decided frames on both sides (within `reach`) are stacked with the same template."""
    kind = [None] * nfr
    for n in single:
        kind[n] = ("single", None)
    part = {}
    for r in recs:
        if is_stacked(r, asz):
            kind[r[0]] = ("stack", r)
        elif sum(M is not None for M in r[4]) == 1:
            part[r[0]] = r
    for n, r in part.items():
        if kind[n] is not None and kind[n][0] == "stack":
            continue
        prv = next((kind[j] for j in range(n - 1, max(-1, n - reach - 1), -1)
                    if kind[j] is not None and j not in part), None)
        nxt = next((kind[j] for j in range(n + 1, min(nfr, n + reach + 1))
                    if kind[j] is not None and j not in part), None)
        if prv and nxt and prv[0] == nxt[0] == "stack" and prv[1][3] == nxt[1][3] == r[3]:
            kind[n] = ("stack", r)
    return kind


# ---------------- stacked shots ----------------
def _params(M, short_wh, sec_wh, out_w):
    k, cx, cy, _ = VM.to_out(M, short_wh, sec_wh, out_w)
    return k, cx, cy


def _jump(a, b, sec_wh, f):
    SW, SH = sec_wh
    return (abs(np.log(a[0] / b[0])) > f * VM.JUMP or abs(a[1] - b[1]) / SW > f * VM.JUMP
            or abs(a[2] - b[2]) / SH > f * VM.JUMP)


def split_stack(frames, sec_wh):
    """frames: sorted [{'n', 'seg', 'tpl', 'p': [(k, cx, cy) | None per panel]}] -> runs split at cuts: another
    template or footage, every panel jumping at once, or one panel jumping hard. Runs < MIN_SHOT_F dropped."""
    shots = []
    for f in frames:
        if shots:
            q = shots[-1][-1]
            cut = f["seg"] != q["seg"] or f["tpl"] != q["tpl"] or f["n"] - q["n"] > 6
            if not cut:   # a cut moves every panel; one panel alone moving that much is a punch-in on it
                both = [(a, b) for a, b in zip(f["p"], q["p"]) if a is not None and b is not None]
                cut = bool(both) and (all(_jump(a, b, sec_wh, 1) for a, b in both)
                                      or any(_jump(a, b, sec_wh, HARD_JUMP) for a, b in both))
            if not cut:
                shots[-1].append(f)
                continue
        shots.append([f])
    return [s for s in shots if len(s) >= VM.MIN_SHOT_F]


def stack_shots(kind, tpls, amap, secp, short_wh, out_w):
    """Shots of the stacked frames: {'layout': 'stack', 'panels': [{'rect', 'path'}], 'fill', 'path' (main
    panel's), ...} plus {n: [seg, m]} for the frames they show."""
    frames = []
    for n, kd in enumerate(kind):
        if kd is None or kd[0] != "stack":
            continue
        _, seg_i, m, t, Ms, cs = kd[1]
        sec_i = amap["segments"][seg_i]["sec"]
        sec_wh = (secp[sec_i]["w"], secp[sec_i]["h"])
        frames.append({"n": n, "seg": seg_i, "sec": sec_i, "m": m, "tpl": t,
                       "ncc": float(np.mean([c for c, M in zip(cs, Ms) if M is not None])),
                       "p": [None if M is None else _params(M, short_wh, sec_wh, out_w) for M in Ms]})
    shots, fmap = [], {}
    if not frames:
        return shots, fmap
    for run in split_stack(frames, (secp[frames[0]["sec"]]["w"], secp[frames[0]["sec"]]["h"])):
        tpl = tpls[run[0]["tpl"]]
        panels = []
        for i, rect in enumerate(tpl["rects"]):
            have = [f for f in run if f["p"][i] is not None]
            if not have:
                panels.append({"rect": rect, "path": None})
                continue
            sm = VM.smooth([[np.log(f["p"][i][0]), f["p"][i][1], f["p"][i][2]] for f in have])
            panels.append({"rect": rect, "path": {str(f["n"]): [float(np.exp(a)), float(b), float(c)]
                                                  for f, (a, b, c) in zip(have, sm)}})
        seg_i = run[0]["seg"]
        shots.append({"n0": run[0]["n"], "n1": run[-1]["n"] + 1, "seg": seg_i, "sec": run[0]["sec"],
                      "off": amap["segments"][seg_i]["off"], "layout": "stack", "band": [0.0, 1.0, 0.0, 1.0],
                      "rot": 0.0, "tpl": run[0]["tpl"], "panels": panels, "fill": tpl.get("fill"),
                      "ncc": float(np.median([f["ncc"] for f in run]))})
        for f in run:
            fmap[f["n"]] = [f["seg"], f["m"]]
    _borrow_paths(shots)
    for s in shots:
        s["panels"] = [p for p in s["panels"] if p["path"]]
        s["path"] = s["panels"][0]["path"]
    return shots, fmap


def _borrow_paths(shots):
    """A panel never mapped inside one shot holds its crop from the nearest shot of the same layout."""
    for i, s in enumerate(shots):
        for j, p in enumerate(s["panels"]):
            if p["path"]:
                continue
            near = [o for k, o in enumerate(shots)
                    if k != i and o["tpl"] == s["tpl"] and o["panels"][j]["path"]]
            if near:
                src = min(near, key=lambda o: abs(o["n0"] - s["n0"]))["panels"][j]["path"]
                key = min(src, key=lambda x: abs(int(x) - s["n0"]))
                p["path"] = {str(s["n0"]): src[key]}
