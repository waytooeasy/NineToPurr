"""Audio map of a clipper Short onto the downloaded VOD sections (D58).

Every 0.2 s of the Short is located in a section by normalised cross-correlation (8 kHz), runs of the same
offset become segments, offsets are refined to the sample (48 kHz), the gain of each segment is measured and
the switch point between segments is found by minimum residual. Sound that is not the stream (bass booms,
a music bed) is reported: booms are re-made with our own synthesised boom, their music is left out.
"""
import numpy as np

from . import common as C

SR, WIN, HOP = 8000, 0.8, 0.2
FINE_SR = 48000
MIN_NC = 0.6


def _prep(a, L):
    n = 1 << int(np.ceil(np.log2(len(a) + L)))
    cs = np.concatenate([[0.0], np.cumsum(a.astype(np.float64) ** 2)])
    loc = cs[L:] - cs[:-L]
    return {"F": np.fft.rfft(a, n), "n": n, "loc": np.maximum(loc, 0.02 * float(np.median(loc)) + 1e-9), "len": len(a)}


def dense(short, sections, sr=SR):
    """[(t, sec, off, nc)] for windows of the Short; off = section time - Short time."""
    L, H = int(WIN * sr), int(HOP * sr)
    pre = [_prep(a, L) for a in sections]
    rows = []
    for i in range(0, max(1, len(short) - L + 1), H):
        seg = short[i:i + L]
        if len(seg) < L or np.sqrt(np.mean(seg ** 2)) < 0.003:
            rows.append((i / sr, None, None, 0.0))
            continue
        best = (-1.0, None, None)
        for k, p in enumerate(pre):
            if p["len"] < L:
                continue
            c = np.fft.irfft(p["F"] * np.conj(np.fft.rfft(seg, p["n"])), p["n"])[:p["len"] - L + 1]
            nc = c / (np.sqrt(p["loc"]) * (np.linalg.norm(seg) + 1e-9))
            j = int(np.argmax(nc))
            if nc[j] > best[0]:
                best = (float(nc[j]), k, j / sr - i / sr)
        rows.append((i / sr, best[1], best[2], best[0]))
    return rows


def segments(rows, dur, tol=0.03):
    """Runs of windows with one (section, offset); unmatched windows join their neighbours."""
    segs = []
    for t, k, o, nc in rows:
        if k is None or nc < MIN_NC:
            continue
        c = t + WIN / 2
        if segs and segs[-1]["sec"] == k and abs(np.median(segs[-1]["offs"]) - o) <= tol:
            segs[-1]["c1"] = c
            segs[-1]["offs"].append(o)
        else:
            segs.append({"sec": k, "offs": [o], "c0": c, "c1": c})
    # a lone window inside a longer run of another mapping is noise
    segs = [s for i, s in enumerate(segs) if len(s["offs"]) > 1 or len(segs) == 1
            or not (0 < i < len(segs) - 1 and segs[i - 1]["sec"] == segs[i + 1]["sec"]
                    and abs(np.median(segs[i - 1]["offs"]) - np.median(segs[i + 1]["offs"])) <= tol)]
    # fewer than 3 windows (< 0.4 s of agreeing audio) is a stray match: in a remake it would be an audio glitch
    if len(segs) > 1:
        segs = [s for s in segs if len(s["offs"]) >= 3] or segs
    merged = []
    for s in segs:
        if merged and merged[-1]["sec"] == s["sec"] and abs(np.median(merged[-1]["offs"]) - np.median(s["offs"])) <= tol:
            merged[-1]["c1"] = s["c1"]
            merged[-1]["offs"] += s["offs"]
        else:
            merged.append(s)
    out = []
    for i, s in enumerate(merged):
        t0 = 0.0 if i == 0 else (merged[i - 1]["c1"] + s["c0"]) / 2
        t1 = dur if i == len(merged) - 1 else (s["c1"] + merged[i + 1]["c0"]) / 2
        out.append({"sec": s["sec"], "off": float(np.median(s["offs"])), "t0": t0, "t1": t1, "n_win": len(s["offs"])})
    return out


def _at(audio, off, t0, n, sr):
    k = int(round((t0 + off) * sr))
    if k < 0:
        return np.concatenate([np.zeros(-k, np.float32), audio[:max(0, n + k)]])[:n]
    x = audio[k:k + n]
    return np.pad(x, (0, n - len(x))) if len(x) < n else x


def refine(short48, secs48, segs, sr=FINE_SR):
    """Sample-exact offset and gain per segment (in place)."""
    for s in segs:
        a, b = s["t0"] + 0.05, s["t1"] - 0.05
        if b - a < 0.3:
            s["gain"] = 1.0
            continue
        y = short48[int(a * sr):int(b * sr)]
        n = len(y)
        best = (-2.0, s["off"])
        for d in range(-int(0.004 * sr), int(0.004 * sr) + 1):
            x = _at(secs48[s["sec"]], s["off"] + d / sr, a, n, sr)
            nc = float(np.dot(y, x) / (np.linalg.norm(y) * np.linalg.norm(x) + 1e-9))
            if nc > best[0]:
                best = (nc, s["off"] + d / sr)
        s["off"], s["nc"] = best[1], best[0]
        x = _at(secs48[s["sec"]], s["off"], a, n, sr)
        s["gain"] = robust_gain(y, x, sr)
    return segs


def robust_gain(y, x, sr, chunk=0.25, min_nc=0.8):
    """Median gain over 0.25 s chunks that really are this mapping (segment edges are only approximate here)."""
    L = int(chunk * sr)
    gains = []
    for i in range(0, len(y) - L + 1, L):
        a, b = y[i:i + L], x[i:i + L]
        den = float(np.dot(b, b))
        if den <= 1e-9:
            continue
        nc = float(np.dot(a, b) / (np.linalg.norm(a) * np.sqrt(den) + 1e-9))
        if nc >= min_nc:
            gains.append(float(np.dot(a, b) / den))
    if not gains:
        gains = [float(np.dot(y, x) / (np.dot(x, x) + 1e-9))]
    return float(np.clip(np.median(gains), 0.2, 4.0))


def switches(short48, secs48, segs, sr=FINE_SR, span=0.3):
    """Exact time the audio switches between consecutive segments (minimum residual), in place."""
    for a, b in zip(segs, segs[1:]):
        m = a["t1"]
        t0 = max(0.0, m - span)
        n = int(2 * span * sr)
        y = short48[int(t0 * sr):int(t0 * sr) + n]
        if len(y) < n:
            continue
        ra = (y - a.get("gain", 1) * _at(secs48[a["sec"]], a["off"], t0, n, sr)) ** 2
        rb = (y - b.get("gain", 1) * _at(secs48[b["sec"]], b["off"], t0, n, sr)) ** 2
        err = np.concatenate([[0.0], np.cumsum(ra)]) + (rb.sum() - np.concatenate([[0.0], np.cumsum(rb)]))
        k = int(np.argmin(err[::int(0.002 * sr)]) * int(0.002 * sr))
        a["t1"] = b["t0"] = t0 + k / sr
    return segs


BOOM_DBFS = -24.0      # sub-150 Hz residual level (dBFS rms) of a bass hit: the study's booms sat at -10..-15
BOOM_MIN_S = 0.4


def _lowpass(x, sr, fc=150.0):
    X = np.fft.rfft(x)
    X[np.fft.rfftfreq(len(x), 1 / sr) > fc] = 0
    return np.fft.irfft(X, len(x)).astype(np.float32)


def extras(short48, secs48, segs, sr=FINE_SR, frame=0.05):
    """Sound that is not the stream: bass hits (re-made with our own boom) and a music bed (left out)."""
    res = np.zeros_like(short48)
    for s in segs:
        i0, i1 = int(s["t0"] * sr), min(int(s["t1"] * sr), len(short48))
        if i1 > i0:
            res[i0:i1] = short48[i0:i1] - s.get("gain", 1) * _at(secs48[s["sec"]], s["off"], s["t0"], i1 - i0, sr)
    F = int(frame * sr)
    rlo, ylo = _lowpass(res, sr), _lowpass(short48, sr)
    booms, run = [], None
    for i in range(0, len(res) - F, F):
        e_r = float(np.mean(rlo[i:i + F] ** 2))
        db = 10 * np.log10(e_r + 1e-12)
        if db > BOOM_DBFS and e_r > 0.5 * float(np.mean(ylo[i:i + F] ** 2)):
            run = run or {"t": i / sr, "dur": 0.0, "db": db}
            run["dur"] += frame
            run["db"] = max(run["db"], db)
        else:
            if run and run["dur"] >= BOOM_MIN_S:
                booms.append(run)
            run = None
    if run and run["dur"] >= BOOM_MIN_S:
        booms.append(run)
    # music bed: share of frames where non-stream sound carries much of the 150 Hz - 4 kHz band
    hi_r = res - rlo
    hi_y = short48 - ylo
    n = m = 0
    for i in range(0, len(res) - F, F):
        n += 1
        er, ey = float(np.mean(hi_r[i:i + F] ** 2)), float(np.mean(hi_y[i:i + F] ** 2))
        if er > 0.3 * ey and 10 * np.log10(er + 1e-12) > -45:
            m += 1
    return {"booms": booms, "music_share": m / max(n, 1)}


def build(short_path, section_files):
    """Full audio map: {'segments': [...], 'booms': [...], 'music_share': x}."""
    short8 = C.read_audio(short_path, SR, highpass=120)
    secs8 = [C.read_audio(f, SR, highpass=120) for f in section_files]
    rows = dense(short8, secs8)
    dur = len(C.read_audio(short_path, 1000)) / 1000
    segs = segments(rows, dur)
    if not segs:
        raise RuntimeError("audio map: no part of the Short matches the downloaded sections")
    short48 = C.read_audio(short_path, FINE_SR)
    secs48 = [C.read_audio(f, FINE_SR) for f in section_files]
    refine(short48, secs48, segs)
    switches(short48, secs48, segs)
    ex = extras(short48, secs48, segs)
    covered = sum(1 for t, k, o, nc in rows if k is not None and nc >= MIN_NC) / max(1, sum(1 for r in rows if r[1] is not None))
    return {"segments": segs, "dur": dur, "matched_share": covered, **ex}
