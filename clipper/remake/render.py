"""Render a remake (D58) from its spec: the streamer's VOD sections re-framed exactly like the clipper's Short
(vmap), their look (grade + sharpening + flashes, look.py), their captions (caps.py, ASS/libass) and the stream
audio cut at their switch points with short crossfades (amap). Their music is never added; their bass hits are
re-made with our own synthesised boom. Their pixels are never used (D57)."""
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np

from . import common as C
from . import vmap as VM

XFADE_S = 0.024     # crossfade at every audio switch (measured on the study Short)


def shot_at(vm, n):
    for s in vm["shots"]:
        if s["n0"] <= n < s["n1"]:
            return s
    return vm["shots"][-1]


def src_frame(vm, n):
    """Map frame rendered at output frame n. frame_shift (match.frame_shift on a render) is in THEIR frames: our
    n + s showed their n, so output frame n is rendered as map frame n + s in everything: shot (cut), crop and
    section frame. Adding s to the section index instead breaks on 30 fps streams stored at 60 fps (every other
    section frame a duplicate): one section frame is 0 or 2 of their frames there, never 1 (#121)."""
    return min(max(n + int(vm.get("frame_shift", 0)), 0), vm["nfr"] - 1)


def sec_frame_index(vm, shot, n):
    """Section frame shown at output frame n (the map's own choice when it has one)."""
    f = vm.get("frames", {}).get(str(n))
    if f is not None and f[0] == shot["seg"]:
        return int(f[1])
    sec = vm["sections"][shot["sec"]]
    return int(round((n / vm["fps"] + shot["off"]) * sec["fps"]))


def compose(sec_img, vm, shot, n, size=None, shifted=None):
    """Our frame n (ungraded): the section frame framed like theirs. `size` (w, h) renders smaller; `sec_img` may
    be a downscaled section frame (its width says by how much). shifted: {panel index: its own section frame}
    for stack panels on other seconds (panel_frames, same scale as sec_img)."""
    OW, OH = vm["out_w"], vm["out_h"]
    w, h = size or (OW, OH)
    r = w / OW
    sec = vm["sections"][shot["sec"]]
    q = sec_img.shape[1] / sec["w"]
    flags = cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP
    if shot["layout"] == "stack":
        return compose_stack(sec_img, vm, shot, n, (w, h), q, r, flags, shifted or {})
    k, cx, cy = VM.params_at(shot, n)
    M = np.array([[q * k / r, 0, q * (cx - k * OW / 2)], [0, q * k / r, q * (cy - k * OH / 2)]])
    if shot["layout"] == "full":
        return cv2.warpAffine(sec_img, M, (w, h), flags=flags, borderMode=cv2.BORDER_REPLICATE)
    bg = shot.get("bg") or {"rel": 0.97, "sigma": 20.0 * OW / 1080, "gain": 1.0}
    if bg.get("color") is not None:          # a solid surround (black bars...), not a blurred copy
        out = np.empty((h, w, 3), np.uint8)
        out[:] = np.clip(np.round(bg["color"]), 0, 255).astype(np.uint8)
        panel = cv2.warpAffine(sec_img, M, (w, h), flags=flags, borderMode=cv2.BORDER_CONSTANT)
        ok = cv2.warpAffine(np.full(sec_img.shape[:2], 255, np.uint8), M, (w, h),
                            flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP, borderValue=0) > 127
        out[ok] = panel[ok]
        return out
    kb = sec["h"] / OH * bg["rel"]
    sw, sh = max(8, w // 4), max(8, h // 4)
    # small px -> full output px: u = u_s * w / (sw * r); section x = SW/2 + (u - OW/2) * kb (blurred copy, centred)
    Mb = np.array([[q * kb * w / (sw * r), 0, q * (sec["w"] / 2 - kb * OW / 2)],
                   [0, q * kb * h / (sh * r), q * (sec["h"] / 2 - kb * OH / 2)]])
    small = cv2.warpAffine(sec_img, Mb, (sw, sh), flags=cv2.INTER_AREA | cv2.WARP_INVERSE_MAP,
                           borderMode=cv2.BORDER_REFLECT)
    small = cv2.GaussianBlur(small, (0, 0), max(0.5, bg["sigma"] * r * sw / w))
    out = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC).astype(np.float32) * bg.get("gain", 1.0)
    out = np.clip(out, 0, 255).astype(np.uint8)
    panel = cv2.warpAffine(sec_img, M, (w, h), flags=flags, borderMode=cv2.BORDER_CONSTANT)
    ok = cv2.warpAffine(np.full(sec_img.shape[:2], 255, np.uint8), M, (w, h),
                        flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP, borderValue=0) > 127
    out[ok] = panel[ok]
    return out


def panel_px(rect, w, h):
    """[top, bottom, left, right] fractions -> (v0, v1, u0, u1) px of a w x h frame."""
    t, b, lft, rgt = rect
    return int(round(t * h)), int(round(b * h)), int(round(lft * w)), int(round(rgt * w))


def panel_frames(vm, shot, n):
    """{panel index: section frame} for the stack panels on their own seconds ('dt', #130): the clipper showed
    that crop at another moment than the shot (a re-synced facecam reaction)."""
    if shot["layout"] != "stack":
        return {}
    sec = vm["sections"][shot["sec"]]
    base = int(round((n / vm["fps"] + shot["off"]) * sec["fps"]))
    return {i: max(0, base + int(p["dt"])) for i, p in enumerate(shot["panels"]) if p.get("dt") is not None}


def compose_stack(sec_img, vm, shot, n, size, q, r, flags, shifted):
    """Stacked / overlay layout (#130): each panel's own crop of the section frame (or of its own frame, panel
    'dt') inside its rectangle, in draw order; the rest of the frame in the measured fill colour."""
    OW, OH = vm["out_w"], vm["out_h"]
    w, h = size
    out = np.empty((h, w, 3), np.uint8)
    out[:] = np.clip(np.round(shot.get("fill") or (0, 0, 0)), 0, 255).astype(np.uint8)
    for i, p in enumerate(shot["panels"]):
        v0, v1, u0, u1 = panel_px(p["rect"], w, h)
        if v1 <= v0 or u1 <= u0:
            continue
        k, cx, cy = VM.params_at(p, n)
        img = shifted.get(i, sec_img)
        a = q * k / r
        M = np.array([[a, 0, q * (cx - k * OW / 2) + a * u0], [0, a, q * (cy - k * OH / 2) + a * v0]])
        out[v0:v1, u0:u1] = cv2.warpAffine(img, M, (u1 - u0, v1 - v0), flags=flags,
                                           borderMode=cv2.BORDER_REPLICATE)
    return out


# ---------------- look ----------------
def poly_feats(X):
    """Cubic polynomial features of colours X (n, 3) in 0..1."""
    cols = [np.ones(len(X))]
    for p in range(1, 4):
        for i in range(p + 1):
            for j in range(p + 1 - i):
                cols.append(X[:, 0] ** i * X[:, 1] ** j * X[:, 2] ** (p - i - j))
    return np.stack(cols, 1)


def lut128(W):
    """128^3 BGR lookup table of the fitted grade (built in chunks to stay small)."""
    W = np.asarray(W, np.float64)
    g = (np.arange(128) * 2 + 1) / 255.0
    out = np.empty((128, 128, 128, 3), np.uint8)
    for b in range(128):
        G_, R = np.meshgrid(g, g, indexing="ij")
        X = np.stack([np.full(G_.size, g[b]), G_.ravel(), R.ravel()], 1)
        out[b] = (np.clip(poly_feats(X) @ W, 0, 1) * 255 + 0.5).astype(np.uint8).reshape(128, 128, 3)
    return out


def apply_look(img, lut, sharpen=None):
    if sharpen and sharpen.get("amount", 0) > 0:
        f = img.astype(np.float32)
        img = np.clip(f + sharpen["amount"] * (f - cv2.GaussianBlur(f, (0, 0), sharpen["sigma"])), 0, 255).astype(np.uint8)
    if lut is not None:
        q = img >> 1
        img = lut[q[..., 0], q[..., 1], q[..., 2]]
    return img


def apply_mat(img, m):
    """Their per-frame colour effect (look.frame_transform): 3x4 BGR transform."""
    if m is None:
        return img
    return cv2.transform(img.astype(np.float32), np.asarray(m, np.float32).reshape(3, 4)).clip(0, 255).astype(np.uint8)


def apply_overlay(img, alpha, color):
    if alpha <= 0:
        return img
    return np.clip(img.astype(np.float32) * (1 - alpha) + np.asarray(color, np.float32) * alpha, 0, 255).astype(np.uint8)


# ---------------- audio ----------------
def boom(sr, dur=1.1, peak=0.45):
    """Our own sub-bass hit (sine sweep ~90 -> 38 Hz, exponential decay)."""
    t = np.arange(int(dur * sr)) / sr
    f = 38 + 52 * np.exp(-t / 0.12)
    s = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.38) * peak * np.minimum(1, t / 0.004)
    return s.astype(np.float32)


def real_hits(booms, max_n=3, max_dur=1.6):
    """Only isolated bass hits get our boom. Many or long low-end stretches are their music bed (an Agent00 remake
    got 8 'booms' that way, 2026-10-21): then none."""
    if len(booms) > max_n or any(b["dur"] > max_dur for b in booms):
        return []
    return booms


def side_by_side(theirs, ours, out):
    """Study copy for Lucas in Telegram (never uploaded): their Short | our remake, small enough for the bot."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(theirs), "-i", str(ours), "-filter_complex",
                    "[0:v]scale=540:-2,setsar=1[a];[1:v]scale=540:-2,setsar=1[b];[a][b]hstack=shortest=1[v]",
                    "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart",
                    str(out)], check=True)
    return Path(out)


def build_audio(amap, sections, dur, sr=48000):
    """Stereo float32: each audio segment's stream audio with its gain, crossfaded at the switch points."""
    N = int(round(dur * sr))
    out = np.zeros((N, 2), np.float32)
    xf = int(XFADE_S * sr)
    segs = amap["segments"]
    cache = {}
    for i, s in enumerate(segs):
        if s["sec"] not in cache:
            cache[s["sec"]] = C.read_audio(sections[s["sec"]]["file"], sr, stereo=True)
        a = cache[s["sec"]]
        i0 = max(0, int(round(s["t0"] * sr)) - (xf // 2 if i else 0))
        i1 = min(N, int(round(s["t1"] * sr)) + (xf // 2 if i < len(segs) - 1 else 0))
        if i == len(segs) - 1:
            i1 = N
        if i1 <= i0:
            continue
        k0 = int(round((i0 / sr + s["off"]) * sr))
        seg = np.zeros((i1 - i0, 2), np.float32)
        src = a[max(0, k0):max(0, k0 + i1 - i0)]
        seg[max(0, -k0):max(0, -k0) + len(src)] = src[:len(seg) - max(0, -k0)]
        env = np.ones(len(seg), np.float32)
        if i:
            env[:xf] = np.linspace(0, 1, min(xf, len(seg)))[:len(env[:xf])]
        if i < len(segs) - 1:
            env[-xf:] = np.minimum(env[-xf:], np.linspace(1, 0, min(xf, len(seg)))[-len(env[-xf:]):])
        out[i0:i1] += seg * env[:, None] * float(s.get("gain", 1.0))
    for b in real_hits(amap.get("booms", [])):
        s = boom(sr, max(0.5, min(1.4, b["dur"] + 0.4)), peak=float(np.clip(10 ** (b["db"] / 20) * 2.5, 0.2, 0.6)))
        k = int(b["t"] * sr)
        n = min(len(s), N - k)
        if n > 0:
            out[k:k + n] += s[:n, None]
    return np.tanh(out * 1.1) / np.tanh(1.1)


def write_wav(path, audio, sr=48000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


# ---------------- render ----------------
def render(spec, out_path, work, crf=17):
    """spec: {'vmap', 'amap', 'look', 'ass'} -> mp4 at the Short's aspect and fps, OW wide."""
    vm, look = spec["vmap"], spec["look"]
    work = Path(work)
    OW, OH, fps = vm["out_w"], vm["out_h"], vm["fps"]
    wav = work / "remake.wav"
    write_wav(wav, build_audio(spec["amap"], vm["sections"], vm["nfr"] / fps))
    lut = lut128(look["poly"]) if look.get("poly") else None
    alpha = {int(k): v for k, v in look.get("overlay", {}).get("alpha", {}).items()}
    color = look.get("overlay", {}).get("color", [0, 0, 255])
    mats = {int(k): v for k, v in look.get("overlay", {}).get("mats", {}).items()}
    vf = f"ass={spec['ass']}:fontsdir={C.fonts_dir()}" if spec.get("ass") else "null"
    tmp = Path(out_path).with_suffix(".tmp.mp4")
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{OW}x{OH}",
                            "-r", f"{fps:g}", "-i", "-", "-i", str(wav), "-vf", vf, "-c:v", "libx264", "-preset", "medium",
                            "-crf", str(crf), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
                            "-movflags", "+faststart", str(tmp)], stdin=subprocess.PIPE)
    readers = {}
    try:
        for n in range(vm["nfr"]):
            ns = src_frame(vm, n)      # their colour effects below stay on their own frame n
            shot = shot_at(vm, ns)
            sec = vm["sections"][shot["sec"]]
            rd = readers.get(shot["sec"])
            if rd is None:
                rd = readers[shot["sec"]] = C.FrameReader(sec["file"], sec["fps"], (sec["w"], sec["h"]))
            m = sec_frame_index(vm, shot, ns)
            shifted = {}
            for i, mp in panel_frames(vm, shot, ns).items():   # a panel on other seconds: its own reader
                key = (shot["sec"], i, shot["n0"])
                if key not in readers:
                    readers[key] = C.FrameReader(sec["file"], sec["fps"], (sec["w"], sec["h"]))
                shifted[i] = readers[key].get(mp).copy()
            img = compose(rd.get(m), vm, shot, ns, shifted=shifted)
            img = apply_look(img, lut, look.get("sharpen"))
            if n in mats:      # their exact colour effect on this frame (replaces the single-colour wash)
                img = apply_mat(img, mats[n])
            else:
                img = apply_overlay(img, alpha.get(n, 0.0), color)
            enc.stdin.write(img.tobytes())
    finally:
        for rd in readers.values():
            rd.close()
        enc.stdin.close()
        enc.wait()
    if enc.returncode != 0:
        raise RuntimeError(f"ffmpeg encode failed ({enc.returncode})")
    tmp.replace(out_path)
    return Path(out_path)
