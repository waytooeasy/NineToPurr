"""Their caption look, measured on their own frames (D58, Lucas 2026-10-21: "they should be IDENTICAL").

Our caption-free remake (`base`) shows the same stream pixels as their Short frame for frame, so |their - base| is
their caption alone. From that difference:
- fill: bright caption pixels -> lines -> words: each word's real colour, the caption's centre and size,
- font: their glyph shapes against every font in FONTS (rendered with PIL, tight crop, IoU + width/height ratio),
  with letter spacing searched too,
- size: the libass font size that gives their line width with that font and spacing,
- outline: dark caption pixels hugging the fill (thickness from a distance transform),
- animation: the first frames of each caption (pop = height grows / overshoots, fade = brightness ramps, none),
- shadow, glow, box, italic: one Sonnet vision call on crops of their captions (MODEL), pixel numbers as hints.
The result (`style.json`) drives caps.write_ass_style. Anything not measurable falls back to caps' study style.
"""
import base64
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

from . import common as C

MODEL = os.environ.get("REMAKE_STYLE_MODEL", "claude-sonnet-5-5")
RAW = "https://raw.githubusercontent.com"
G = f"{RAW}/google/fonts/main"
MS = f"{RAW}/JulietaUla/Montserrat/master/fonts/ttf"

# (family as libass/fontconfig knows it, bold flag, italic flag, file, OFL/Apache source)
FONTS = [
    ("Montserrat Black", 0, 0, "Montserrat-Black.ttf", f"{MS}/Montserrat-Black.ttf"),
    ("Montserrat Black", 0, 1, "Montserrat-BlackItalic.ttf", f"{MS}/Montserrat-BlackItalic.ttf"),
    ("Montserrat ExtraBold", 0, 0, "Montserrat-ExtraBold.ttf", f"{MS}/Montserrat-ExtraBold.ttf"),
    ("Montserrat ExtraBold", 0, 1, "Montserrat-ExtraBoldItalic.ttf", f"{MS}/Montserrat-ExtraBoldItalic.ttf"),
    ("Montserrat", 1, 0, "Montserrat-Bold.ttf", f"{MS}/Montserrat-Bold.ttf"),
    ("Anton", 0, 0, "Anton-Regular.ttf", f"{G}/ofl/anton/Anton-Regular.ttf"),
    ("Bebas Neue", 0, 0, "BebasNeue-Regular.ttf", f"{G}/ofl/bebasneue/BebasNeue-Regular.ttf"),
    ("Poppins Black", 0, 0, "Poppins-Black.ttf", f"{G}/ofl/poppins/Poppins-Black.ttf"),
    ("Poppins Black", 0, 1, "Poppins-BlackItalic.ttf", f"{G}/ofl/poppins/Poppins-BlackItalic.ttf"),
    ("Poppins ExtraBold", 0, 0, "Poppins-ExtraBold.ttf", f"{G}/ofl/poppins/Poppins-ExtraBold.ttf"),
    ("Poppins", 1, 0, "Poppins-Bold.ttf", f"{G}/ofl/poppins/Poppins-Bold.ttf"),
    ("Bangers", 0, 0, "Bangers-Regular.ttf", f"{G}/ofl/bangers/Bangers-Regular.ttf"),
    ("Luckiest Guy", 0, 0, "LuckiestGuy-Regular.ttf", f"{G}/apache/luckiestguy/LuckiestGuy-Regular.ttf"),
    ("Archivo Black", 0, 0, "ArchivoBlack-Regular.ttf", f"{G}/ofl/archivoblack/ArchivoBlack-Regular.ttf"),
    ("Lilita One", 0, 0, "LilitaOne-Regular.ttf", f"{G}/ofl/lilitaone/LilitaOne-Regular.ttf"),
    ("Titan One", 0, 0, "TitanOne-Regular.ttf", f"{G}/ofl/titanone/TitanOne-Regular.ttf"),
    ("Russo One", 0, 0, "RussoOne-Regular.ttf", f"{G}/ofl/russoone/RussoOne-Regular.ttf"),
    ("Passion One", 0, 0, "PassionOne-Regular.ttf", f"{G}/ofl/passionone/PassionOne-Regular.ttf"),
    ("Barlow Black", 0, 0, "Barlow-Black.ttf", f"{G}/ofl/barlow/Barlow-Black.ttf"),
    ("Barlow ExtraBold", 0, 0, "Barlow-ExtraBold.ttf", f"{G}/ofl/barlow/Barlow-ExtraBold.ttf"),
    ("Barlow Condensed Black", 0, 0, "BarlowCondensed-Black.ttf", f"{G}/ofl/barlowcondensed/BarlowCondensed-Black.ttf"),
    ("Barlow Condensed ExtraBold", 0, 0, "BarlowCondensed-ExtraBold.ttf",
     f"{G}/ofl/barlowcondensed/BarlowCondensed-ExtraBold.ttf"),
    ("Saira Condensed Black", 0, 0, "SairaCondensed-Black.ttf", f"{G}/ofl/sairacondensed/SairaCondensed-Black.ttf"),
    ("Saira Condensed ExtraBold", 0, 0, "SairaCondensed-ExtraBold.ttf",
     f"{G}/ofl/sairacondensed/SairaCondensed-ExtraBold.ttf"),
    ("Fjalla One", 0, 0, "FjallaOne-Regular.ttf", f"{G}/ofl/fjallaone/FjallaOne-Regular.ttf"),
    ("Kanit Black", 0, 0, "Kanit-Black.ttf", f"{G}/ofl/kanit/Kanit-Black.ttf"),
    ("Kanit ExtraBold", 0, 0, "Kanit-ExtraBold.ttf", f"{G}/ofl/kanit/Kanit-ExtraBold.ttf"),
    ("Kanit", 1, 0, "Kanit-Bold.ttf", f"{G}/ofl/kanit/Kanit-Bold.ttf"),
    ("Lato Black", 0, 0, "Lato-Black.ttf", f"{G}/ofl/lato/Lato-Black.ttf"),
    ("Black Ops One", 0, 0, "BlackOpsOne-Regular.ttf", f"{G}/ofl/blackopsone/BlackOpsOne-Regular.ttf"),
    ("Bowlby One", 0, 0, "BowlbyOne-Regular.ttf", f"{G}/ofl/bowlbyone/BowlbyOne-Regular.ttf"),
    ("Alfa Slab One", 0, 0, "AlfaSlabOne-Regular.ttf", f"{G}/ofl/alfaslabone/AlfaSlabOne-Regular.ttf"),
    ("Chango", 0, 0, "Chango-Regular.ttf", f"{G}/ofl/chango/Chango-Regular.ttf"),
    ("Sigmar", 0, 0, "Sigmar-Regular.ttf", f"{G}/ofl/sigmar/Sigmar-Regular.ttf"),
    ("Bungee", 0, 0, "Bungee-Regular.ttf", f"{G}/ofl/bungee/Bungee-Regular.ttf"),
    ("Staatliches", 0, 0, "Staatliches-Regular.ttf", f"{G}/ofl/staatliches/Staatliches-Regular.ttf"),
    ("Righteous", 0, 0, "Righteous-Regular.ttf", f"{G}/ofl/righteous/Righteous-Regular.ttf"),
    ("Changa One", 0, 0, "ChangaOne-Regular.ttf", f"{G}/ofl/changaone/ChangaOne-Regular.ttf"),
    ("Dela Gothic One", 0, 0, "DelaGothicOne-Regular.ttf", f"{G}/ofl/delagothicone/DelaGothicOne-Regular.ttf"),
]
TRACKS = (-0.04, 0.0, 0.04, 0.08, 0.12, 0.16)   # letter spacing / font size tried for every font
DIFF_MIN = 48           # |their - base| (max channel) above this is caption
FILL_V = 150            # caption fill: brightest channel at least this (white, yellow, green, red ... fills)
DARK_V = 90             # outline / shadow: brightest channel below this
SAMPLES = 8             # caption events measured
DEFAULT_WHITE = "#FFFFFF"


# ---------------- fonts ----------------
def font_path(entry, d=None):
    return Path(d or C.fonts_dir()) / entry[3]


def ensure_fonts(d=None, get=None):
    """Download the catalogue fonts that are missing (best effort). Returns the entries available."""
    d = Path(d or C.fonts_dir())
    d.mkdir(parents=True, exist_ok=True)
    ok = []
    for e in FONTS:
        p = d / e[3]
        if not p.exists():
            try:
                if get is None:
                    import requests
                    r = requests.get(e[4], timeout=30)
                    r.raise_for_status()
                    data = r.content
                else:
                    data = get(e[4])
                p.write_bytes(data)
            except Exception as ex:  # noqa: BLE001
                C.log(f"font {e[0]} unavailable: {ex}")
                continue
        ok.append(e)
    return ok


def text_mask(path, text, size=120, track=0.0):
    """Tight binary mask of `text` in the font at `path`, letters drawn one by one with `track` * size spacing."""
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(str(path), size)
    adv = [f.getlength(ch) for ch in text]
    w = int(sum(adv) + max(0.0, track) * size * len(text) + size * 2)
    h = int(size * 2.2)
    im = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(im)
    x = size * 0.5
    for ch, a in zip(text, adv):
        dr.text((x, size * 0.4), ch, font=f, fill=255)
        x += a + track * size
    m = np.array(im) > 127
    return tight(m)


def tight(m):
    ys, xs = np.where(m)
    if not len(ys):
        return m[:0, :0]
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def shape_score(theirs, ours):
    """1 = same glyph shapes: IoU at their size, minus how far the width/height ratios differ."""
    if theirs.size == 0 or ours.size == 0:
        return 0.0
    h, w = theirs.shape
    o = cv2.resize(ours.astype(np.uint8) * 255, (w, h), interpolation=cv2.INTER_AREA) > 127
    t = theirs
    k = max(1, int(round(h * 0.06)))       # a few px of slack (anti-aliasing, outline eating the fill edge)
    tk = cv2.dilate(t.astype(np.uint8), np.ones((k, k), np.uint8)) > 0
    ok = cv2.dilate(o.astype(np.uint8), np.ones((k, k), np.uint8)) > 0
    inter = (t & ok).sum() + (o & tk).sum()
    iou = inter / max(1, t.sum() + o.sum())
    ar_t, ar_o = w / h, ours.shape[1] / max(1, ours.shape[0])
    return float(iou * np.exp(-2.5 * abs(np.log(ar_t / ar_o))))


def rank_fonts(samples, fonts, d=None):
    """[(score, entry, track)] best first; samples: [(their tight line mask, line text)]."""
    out = []
    for e in fonts:
        p = font_path(e, d)
        if not p.exists():
            continue
        best = (0.0, 0.0)
        for tr in TRACKS:
            sc = [shape_score(m, text_mask(p, txt, track=tr)) for m, txt in samples]
            s = float(np.mean(sc)) if sc else 0.0
            best = max(best, (s, tr))
        out.append((best[0], e, best[1]))
    return sorted(out, key=lambda x: -x[0])


# ---------------- their caption pixels ----------------
def frame(path, n, fps, size):
    a = C.read_frames(path, n, 1, fps, size)
    return a[0] if len(a) else None


def caption_masks(th, base, y, band=0.2):
    """(caption, fill, dark) masks near caption height y (fraction), from their frame and our caption-free one."""
    H = th.shape[0]
    d = np.abs(th.astype(np.int16) - base.astype(np.int16)).max(2) > DIFF_MIN
    rows = np.zeros(H, bool)
    rows[max(0, int((y - band) * H)):min(H, int((y + band) * H))] = True
    d &= rows[:, None]
    v = th.max(2)
    fill = d & (v >= FILL_V)
    dark = d & (v < DARK_V)
    fill = cv2.morphologyEx(fill.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) > 0
    return d, fill, dark


def lines_of(fill, min_rows=6):
    """Row ranges of text lines in the fill mask (horizontal projection), biggest blocks only."""
    prof = fill.sum(1)
    on = prof > max(2, 0.02 * prof.max()) if prof.max() else prof > 0
    runs, s = [], None
    for i, o in enumerate(list(on) + [False]):
        if o and s is None:
            s = i
        elif not o and s is not None:
            if i - s >= min_rows:
                runs.append((s, i))
            s = None
    if not runs:
        return []
    big = max(b - a for a, b in runs)
    return [r for r in runs if r[1] - r[0] >= 0.5 * big]


def words_of(line_mask, n_words):
    """Column ranges of the words of one line: the n_words - 1 widest gaps split them."""
    cols = line_mask.any(0)
    xs = np.where(cols)[0]
    if not len(xs):
        return []
    x0, x1 = xs.min(), xs.max() + 1
    gaps, s = [], None
    for x in range(x0, x1):
        if not cols[x] and s is None:
            s = x
        elif cols[x] and s is not None:
            gaps.append((x - s, s, x))
            s = None
    if n_words <= 1:
        return [(x0, x1)]
    gaps = sorted(sorted(gaps, reverse=True)[:n_words - 1], key=lambda g: g[1])
    if len(gaps) < n_words - 1:
        return []
    out, a = [], x0
    for _, gs, ge in gaps:
        out.append((a, gs))
        a = ge
    out.append((a, x1))
    return out


def hex_of(bgr):
    b, g, r = [int(np.clip(x, 0, 255)) for x in bgr]
    if min(r, g, b) >= 205:
        return DEFAULT_WHITE
    return f"#{r:02X}{g:02X}{b:02X}"


def measure_event(th, base, ev):
    """Their caption of one event at a fully revealed frame: lines, words with real colours, box, outline."""
    _, fill, dark = caption_masks(th, base, ev.get("y", 0.5))
    lines = lines_of(fill)
    if not lines:
        return None
    shape = ev.get("lines") or [len(ev["words"])]
    words = ev["words"]
    out = {"lines": [], "colours": [None] * len(words)}
    if len(lines) == len(shape):
        i = 0
        for (r0, r1), n in zip(lines, shape):
            lm = fill[r0:r1]
            cols = words_of(lm, n)
            text = " ".join(w["w"] for w in words[i:i + n])
            xs = np.where(lm.any(0))[0]
            out["lines"].append({"r0": int(r0), "r1": int(r1), "x0": int(xs.min()), "x1": int(xs.max() + 1),
                                 "text": text, "mask": tight(lm)})
            if len(cols) == n:
                for k, (c0, c1) in enumerate(cols):
                    px = th[r0:r1, c0:c1][lm[:, c0:c1]]
                    if len(px) > 20:
                        out["colours"][i + k] = hex_of(np.median(px.reshape(-1, 3), 0))
            i += n
    fy = np.where(fill.any(1))[0]
    fx = np.where(fill.any(0))[0]
    out["cy"] = float((fy.min() + fy.max() + 1) / 2 / th.shape[0])
    out["cx"] = float((fx.min() + fx.max() + 1) / 2 / th.shape[1])
    cap = [ln["r1"] - ln["r0"] for ln in out["lines"]] or [lines[0][1] - lines[0][0]]
    out["line_h"] = float(np.median(cap))
    out["outline"] = outline_px(fill, dark, out["line_h"])
    return out


def outline_px(fill, dark, line_h):
    """Their outline thickness in px (0 = none): how far dark pixels reach out from the fill, if they hug it."""
    if fill.sum() < 50:
        return 0.0
    edge = fill & ~(cv2.erode(fill.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    near_dark = cv2.dilate(dark.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    hug = (edge & near_dark).sum() / max(1, edge.sum())
    if hug < 0.5:
        return 0.0
    dt = cv2.distanceTransform((~fill).astype(np.uint8), cv2.DIST_L2, 3)
    ring = dark & (dt < 0.3 * line_h)
    return float(np.percentile(dt[ring], 90)) if ring.sum() > 30 else 0.0


# ---------------- animation ----------------
def animation(short_path, base_path, evs, fps, size, n_events=6, look_frames=14):
    """How a caption appears: {'kind': 'pop'|'fade'|'none', 'from': scale, 'peak': scale, 't_peak_ms', 'ms'}."""
    votes = []
    for ev in evs[:n_events]:
        n0 = int(ev["start"] * fps) - 1
        th = C.read_frames(short_path, max(0, n0), look_frames, fps, size)
        ba = C.read_frames(base_path, max(0, n0), look_frames, fps, size)
        hs, vs = [], []
        for a, b in zip(th, ba):
            _, fill, _ = caption_masks(a, b, ev.get("y", 0.5))
            ys = np.where(fill.any(1))[0]
            if fill.sum() < 30 or not len(ys):
                hs.append(0.0)
                vs.append(0.0)
                continue
            ls = lines_of(fill)
            hs.append(float(max((r1 - r0) for r0, r1 in ls)) if ls else float(ys.max() - ys.min()))
            vs.append(float(a.max(2)[fill].mean()))
        if len(hs) < 4 or max(hs) == 0:
            continue
        hf, vf = np.median(hs[-4:]), np.median(vs[-4:])
        if hf <= 0:
            continue
        k0 = next((i for i, h in enumerate(hs) if h > 0.3 * hf), None)
        if k0 is None:
            continue
        rel = np.array(hs[k0:]) / hf
        settle = next((i for i in range(len(rel)) if all(abs(r - 1) < 0.05 for r in rel[i:])), len(rel))
        if rel[0] < 0.88 or rel.max() > 1.08:
            ip = int(np.argmax(rel))
            votes.append({"kind": "pop", "from": float(rel[0]), "peak": float(max(1.0, rel.max())),
                          "t_peak_ms": int(ip * 1000 / fps), "ms": int(max(1, settle) * 1000 / fps)})
        elif vs[k0] < 0.8 * vf:
            up = next((i for i in range(k0, len(vs)) if vs[i] >= 0.95 * vf), len(vs))
            votes.append({"kind": "fade", "ms": int(max(1, up - k0 + 1) * 1000 / fps)})
        else:
            votes.append({"kind": "none", "ms": 0})
    if not votes:
        return {"kind": "none", "ms": 0}
    kinds = [v["kind"] for v in votes]
    kind = max(set(kinds), key=kinds.count)
    vv = [v for v in votes if v["kind"] == kind]
    out = {"kind": kind, "ms": int(np.median([v["ms"] for v in vv]))}
    if kind == "pop":
        out.update({"from": float(np.median([v["from"] for v in vv])), "peak": float(np.median([v["peak"] for v in vv])),
                    "t_peak_ms": int(np.median([v["t_peak_ms"] for v in vv]))})
    return out


# ---------------- libass size ----------------
def libass_width(entry, text, fs, spacing, fonts_dir=None):
    """Width in px of `text` as libass renders it with this font, size and spacing."""
    W, H = 4000, int(fs * 3)
    with tempfile.TemporaryDirectory() as d:
        ass = Path(d) / "w.ass"
        ass.write_text(
            f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: S,{entry[0]},{fs:.1f},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,{-1 if entry[1] else 0},"
            f"{-1 if entry[2] else 0},0,0,100,100,{spacing:.2f},0,1,0,0,5,0,0,0,1\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            f"Dialogue: 0,0:00:00.00,0:00:01.00,S,,0,0,0,,{{\\pos({W // 2},{H // 2})}}{text}\n")
        raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=black:s={W}x{H}:d=0.1",
                              "-vf", f"ass={ass}:fontsdir={fonts_dir or C.fonts_dir()}", "-frames:v", "1",
                              "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(H, W) > 128
    xs = np.where(a.any(0))[0]
    return float(xs.max() - xs.min() + 1) if len(xs) else 0.0


# ---------------- Sonnet: what pixels can't say easily ----------------
PROMPT = ("These are crops of the burned-in captions of one YouTube Short. Describe how the caption TEXT is drawn "
          "(not the video behind it). Measured from the pixels: letter height ~{h:.0f}px, outline ~{o:.1f}px. "
          "Return JSON only: {{\"outline\": {{\"present\": bool, \"colour\": \"#RRGGBB\"}}, "
          "\"shadow\": {{\"present\": bool, \"dx\": x offset / letter height, \"dy\": y offset / letter height, "
          "\"blur\": 0 (hard) to 1 (very soft), \"colour\": \"#RRGGBB\", \"opacity\": 0-1}}, "
          "\"glow\": {{\"present\": bool, \"colour\": \"#RRGGBB\" or \"text\" if it takes each word's colour, "
          "\"size\": glow radius / letter height, \"opacity\": 0-1}}, "
          "\"box\": {{\"present\": bool, \"colour\": \"#RRGGBB\", \"opacity\": 0-1}}, \"italic\": bool, "
          "\"case\": \"upper\" | \"as_is\"}}")


def ask_style(crops, line_h, outline, vision=None):
    imgs = [cv2.imencode(".jpg", c, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes() for c in crops]
    vision = vision or anthropic_vision
    for _ in range(2):
        txt = vision(imgs, PROMPT.format(h=line_h, o=outline))
        m = re.search(r"\{.*\}", txt or "", re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
    return {}


def anthropic_vision(images, prompt):
    import anthropic  # lazy
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": base64.b64encode(b).decode()}} for b in images]
    content.append({"type": "text", "text": prompt})
    msg = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=1500,
                                                messages=[{"role": "user", "content": content}])
    try:
        import llm
        llm.log_usage("anthropic", MODEL, llm._usage_dict(msg.usage))
    except Exception:  # noqa: BLE001
        pass
    return "".join(b.text for b in msg.content if b.type == "text")


# ---------------- all together ----------------
def pick_samples(evs, n=SAMPLES):
    """Events worth measuring: on screen long enough, most words first."""
    ok = [e for e in evs if e["end"] - e["start"] >= 0.3 and e["words"]]
    ok.sort(key=lambda e: (-len(" ".join(w["w"] for w in e["words"])), e["start"]))
    return sorted(ok[:n], key=lambda e: e["start"])


def measure_all(short_path, base_path, evs, fps, size):
    """Per event: their measured caption at a fully revealed frame (most of the way through the event)."""
    out = []
    for ev in evs:
        t = ev["start"] + 0.75 * (ev["end"] - ev["start"])
        t = max(t, max(w["t"] for w in ev["words"]) + 0.15) if ev["words"] else t
        n = int(min(t, ev["end"] - 0.05) * fps)
        th, ba = frame(short_path, n, fps, size), frame(base_path, n, fps, size)
        if th is None or ba is None:
            out.append(None)
            continue
        m = measure_event(th, ba, ev)
        if m:
            m["frame"] = th
        out.append(m)
    return out


def build(short_path, base_path, evs, fps, out_w, out_h, vision=None, fonts_dir=None):
    """style.json: font, size, spacing, colours per word, position, outline, shadow, glow, box, animation."""
    size = (out_w, out_h)
    fonts = ensure_fonts(fonts_dir)
    ms = measure_all(short_path, base_path, evs, fps, size)
    # real word colours (pixels beat OCR's guess)
    colours = []
    for ev, m in zip(evs, ms):
        colours.append([(m["colours"][i] if m and m["colours"][i] else w["c"]) for i, w in enumerate(ev["words"])])
    sample_idx = [i for i, e in enumerate(evs) if e in pick_samples(evs)]
    lines = [(ln["mask"], ln["text"]) for i in sample_idx if ms[i] for ln in ms[i]["lines"]
             if ln["mask"].size and len(ln["text"]) >= 3]
    if not lines:
        C.log("style: their captions not measurable, study style kept")
        return {"ok": False, "colours": colours}
    ranked = rank_fonts(lines[:10], fonts, fonts_dir)
    if not ranked:
        return {"ok": False, "colours": colours}
    score, entry, track = ranked[0]
    # size: libass width of the same line text -> their width
    fss = []
    for i in sample_idx:
        m = ms[i]
        if not m:
            continue
        for ln in m["lines"]:
            if len(ln["text"]) < 3:
                continue
            w100 = libass_width(entry, ln["text"], 100, track * 100, fonts_dir)
            if w100 > 0:
                fss.append(100 * (ln["x1"] - ln["x0"]) / w100)
    fs = float(np.median(fss)) if fss else None
    good = [m for m in ms if m]
    line_h = float(np.median([m["line_h"] for m in good]))
    outline = float(np.median([m["outline"] for m in good]))
    cy = float(np.median([m["cy"] for m in good]))
    cx = float(np.median([m["cx"] for m in good]))
    anim = animation(short_path, base_path, [evs[i] for i in sample_idx], fps, size)
    crops = []
    for i in sample_idx[:4]:
        m = ms[i]
        if m:
            r0 = max(0, int(min(ln["r0"] for ln in m["lines"]) - line_h))
            r1 = min(out_h, int(max(ln["r1"] for ln in m["lines"]) + line_h))
            crops.append(m["frame"][r0:r1])
    looks = ask_style(crops, line_h, outline, vision) if crops else {}
    st = {"ok": fs is not None, "family": entry[0], "bold": entry[1], "italic": entry[2], "file": entry[3],
          "font_score": round(score, 3), "track": track, "fs": fs, "spacing": None if fs is None else track * fs,
          "outline": outline, "line_h": line_h, "x": cx, "y": cy, "anim": anim, "colours": colours,
          "llm": looks, "alternatives": [(round(s, 3), e[0], e[2], t) for s, e, t in ranked[1:4]]}
    C.log(f"style: {entry[0]}{' italic' if entry[2] else ''} (shape {score:.2f}, next "
          f"{', '.join(f'{e[0]} {s:.2f}' for s, e, _ in ranked[1:3])}), size {fs and round(fs)}, track {track}, "
          f"outline {outline:.1f}px, anim {anim['kind']}")
    return st


def with_font(st, alt_index, fonts_dir=None):
    """The same style with the n-th next-best font (a rebuild candidate)."""
    if not st.get("alternatives") or alt_index >= len(st["alternatives"]):
        return None
    _, fam, ital, tr = st["alternatives"][alt_index]
    entry = next((e for e in FONTS if e[0] == fam and e[2] == ital), None)
    if entry is None:
        return None
    scale = None
    if st.get("fs"):
        a = libass_width((st["family"], st["bold"], st["italic"]), "HELLO WORLD", 100, st["track"] * 100, fonts_dir)
        b = libass_width(entry, "HELLO WORLD", 100, tr * 100, fonts_dir)
        scale = a / b if b else None
    fs = st["fs"] * scale if (st.get("fs") and scale) else st.get("fs")
    return {**st, "family": entry[0], "bold": entry[1], "italic": entry[2], "file": entry[3], "track": tr, "fs": fs,
            "spacing": None if fs is None else tr * fs}
