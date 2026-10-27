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
# weights of variable fonts, cut to static files at fetch time (libass would only use the default weight):
# (family we give the static file, bold, italic, file, variable font source, axes)
VAR_FONTS = [
    ("Oswald Medium", 0, 0, "Oswald-Medium.ttf", f"{G}/ofl/oswald/Oswald%5Bwght%5D.ttf", {"wght": 500}),
    ("Oswald SemiBold", 0, 0, "Oswald-SemiBold.ttf", f"{G}/ofl/oswald/Oswald%5Bwght%5D.ttf", {"wght": 600}),
    ("Oswald Bold", 0, 0, "Oswald-Bold.ttf", f"{G}/ofl/oswald/Oswald%5Bwght%5D.ttf", {"wght": 700}),
    ("Antonio SemiBold", 0, 0, "Antonio-SemiBold.ttf", f"{G}/ofl/antonio/Antonio%5Bwght%5D.ttf", {"wght": 600}),
    ("Antonio Bold", 0, 0, "Antonio-Bold.ttf", f"{G}/ofl/antonio/Antonio%5Bwght%5D.ttf", {"wght": 700}),
    ("Roboto Condensed Bold", 0, 0, "RobotoCondensed-Bold.ttf",
     f"{G}/ofl/robotocondensed/RobotoCondensed%5Bwght%5D.ttf", {"wght": 700}),
    ("Roboto Condensed Black", 0, 0, "RobotoCondensed-Black.ttf",
     f"{G}/ofl/robotocondensed/RobotoCondensed%5Bwght%5D.ttf", {"wght": 900}),
    ("Roboto Black", 0, 0, "Roboto-Black.ttf", f"{G}/ofl/roboto/Roboto%5Bwdth,wght%5D.ttf", {"wght": 900, "wdth": 100}),
    ("Roboto Bold", 0, 0, "Roboto-Bold.ttf", f"{G}/ofl/roboto/Roboto%5Bwdth,wght%5D.ttf", {"wght": 700, "wdth": 100}),
    ("Inter Black", 0, 0, "Inter-Black.ttf", f"{G}/ofl/inter/Inter%5Bopsz,wght%5D.ttf", {"wght": 900, "opsz": 32}),
    ("Inter ExtraBold", 0, 0, "Inter-ExtraBold.ttf", f"{G}/ofl/inter/Inter%5Bopsz,wght%5D.ttf", {"wght": 800, "opsz": 32}),
    ("Open Sans ExtraBold", 0, 0, "OpenSans-ExtraBold.ttf", f"{G}/ofl/opensans/OpenSans%5Bwdth,wght%5D.ttf",
     {"wght": 800, "wdth": 100}),
    ("Teko SemiBold", 0, 0, "Teko-SemiBold.ttf", f"{G}/ofl/teko/Teko%5Bwght%5D.ttf", {"wght": 600}),
    ("League Gothic", 0, 0, "LeagueGothic-Regular.ttf", f"{G}/ofl/leaguegothic/LeagueGothic%5Bwdth%5D.ttf",
     {"wdth": 100}),
    ("Nunito Black", 0, 0, "Nunito-Black.ttf", f"{G}/ofl/nunito/Nunito%5Bwght%5D.ttf", {"wght": 900}),
    ("Rubik Bold", 0, 0, "Rubik-Bold.ttf", f"{G}/ofl/rubik/Rubik%5Bwght%5D.ttf", {"wght": 700}),
    ("Rubik Black", 0, 0, "Rubik-Black.ttf", f"{G}/ofl/rubik/Rubik%5Bwght%5D.ttf", {"wght": 900}),
    ("Big Shoulders Display Black", 0, 0, "BigShouldersDisplay-Black.ttf",
     f"{G}/ofl/bigshouldersdisplay/BigShouldersDisplay%5Bwght%5D.ttf", {"wght": 900}),
    ("Sofia Sans Condensed Black", 0, 0, "SofiaSansCondensed-Black.ttf",
     f"{G}/ofl/sofiasanscondensed/SofiaSansCondensed%5Bwght%5D.ttf", {"wght": 900}),
    ("Sofia Sans Condensed Bold", 0, 0, "SofiaSansCondensed-Bold.ttf",
     f"{G}/ofl/sofiasanscondensed/SofiaSansCondensed%5Bwght%5D.ttf", {"wght": 700}),
    ("Archivo Narrow Bold", 0, 0, "ArchivoNarrow-Bold.ttf", f"{G}/ofl/archivonarrow/ArchivoNarrow%5Bwght%5D.ttf",
     {"wght": 700}),
    ("Outfit Black", 0, 0, "Outfit-Black.ttf", f"{G}/ofl/outfit/Outfit%5Bwght%5D.ttf", {"wght": 900}),
    ("League Spartan Black", 0, 0, "LeagueSpartan-Black.ttf", f"{G}/ofl/leaguespartan/LeagueSpartan%5Bwght%5D.ttf",
     {"wght": 900}),
    ("Barlow Condensed Bold", 0, 0, "BarlowCondensed-Bold.ttf", None, None),
    ("Barlow Condensed SemiBold", 0, 0, "BarlowCondensed-SemiBold.ttf", None, None),
    ("Barlow Semi Condensed Bold", 0, 0, "BarlowSemiCondensed-Bold.ttf", None, None),
    ("Saira Semi Condensed Bold", 0, 0, "SairaSemiCondensed-Bold.ttf", None, None),
    ("Pathway Gothic One", 0, 0, "PathwayGothicOne-Regular.ttf", None, None),
]
_STATIC = {"BarlowCondensed-Bold.ttf": f"{G}/ofl/barlowcondensed/BarlowCondensed-Bold.ttf",
           "BarlowCondensed-SemiBold.ttf": f"{G}/ofl/barlowcondensed/BarlowCondensed-SemiBold.ttf",
           "BarlowSemiCondensed-Bold.ttf": f"{G}/ofl/barlowsemicondensed/BarlowSemiCondensed-Bold.ttf",
           "SairaSemiCondensed-Bold.ttf": f"{G}/ofl/sairasemicondensed/SairaSemiCondensed-Bold.ttf",
           "PathwayGothicOne-Regular.ttf": f"{G}/ofl/pathwaygothicone/PathwayGothicOne-Regular.ttf"}
FONTS += [(f, b, i, fn, _STATIC[fn]) if axes is None else (f, b, i, fn, url, axes)
          for f, b, i, fn, url, axes in VAR_FONTS]
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
                if len(e) > 5:      # a weight of a variable font
                    var = d / "_var" / re.sub(r"[^A-Za-z0-9.,\[\]-]", "_", e[4].rsplit("/", 1)[-1])
                    if not var.exists():
                        var.parent.mkdir(parents=True, exist_ok=True)
                        var.write_bytes(_fetch(e[4], get))
                    static_instance(var, e[5], e[0], p)
                else:
                    p.write_bytes(_fetch(e[4], get))
            except Exception as ex:  # noqa: BLE001
                C.log(f"font {e[0]} unavailable: {ex}")
                continue
        ok.append(e)
    return ok


def _fetch(url, get=None):
    if get is not None:
        return get(url)
    import requests
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def static_instance(var_path, axes, family, out):
    """One weight of a variable font as a static font named `family` (so libass can ask for it by name)."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    f = TTFont(str(var_path))
    axes = {a: v for a, v in axes.items() if a in {x.axisTag for x in f["fvar"].axes}}
    inst = instancer.instantiateVariableFont(f, axes)
    name = inst["name"]
    for rec in list(name.names):
        if rec.nameID in (16, 17, 21, 22, 25):
            name.removeNames(nameID=rec.nameID)
    ps = re.sub(r"[^A-Za-z0-9]", "", family) + "-Regular"
    for nid, val in ((1, family), (2, "Regular"), (3, ps), (4, family), (6, ps)):
        name.setName(val, nid, 3, 1, 0x409)
        name.setName(val, nid, 1, 0, 0)
    if "OS/2" in inst:
        inst["OS/2"].fsSelection = (inst["OS/2"].fsSelection & ~0b1100001) | 0b1000000   # REGULAR, not bold/italic
        inst["head"].macStyle = 0
    inst.save(str(out))
    return out


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
    k = max(2, int(round(th.shape[1] / 360)))        # letter strokes survive, 1-2 px picture edges don't
    fill = cv2.morphologyEx(fill.astype(np.uint8), cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fill, connectivity=8)
    if n > 1:              # specks (sharpness / grain differences in the picture) are not letters
        big = np.percentile(stats[1:, cv2.CC_STAT_HEIGHT], 90)
        keep = np.zeros(n, bool)
        keep[1:] = (stats[1:, cv2.CC_STAT_AREA] >= 25) & (stats[1:, cv2.CC_STAT_HEIGHT] >= 0.35 * big)
        fill = keep[lab]
    else:
        fill = fill > 0
    return d, fill, dark


def lines_of(fill, min_rows=6, near=None, k=None):
    """Row ranges of text lines in the fill mask (horizontal projection), biggest blocks only; with `near` (row),
    only the k consecutive lines closest to it (picture differences elsewhere are not captions)."""
    runs = _line_runs(fill, min_rows)
    if near is None or not runs:
        return runs
    k = max(1, min(k or 1, len(runs)))
    best = min(range(len(runs) - k + 1),
               key=lambda i: abs((runs[i][0] + runs[i + k - 1][1]) / 2 - near))
    return runs[best:best + k]


def _line_runs(fill, min_rows=6):
    prof = fill.sum(1)
    on = prof > max(2, 0.12 * prof.max()) if prof.max() else prof > 0
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


def main_block(line_mask, gap=1.5):
    """The line's text: the biggest run of columns with ink, gaps under gap * line height bridged."""
    h = line_mask.shape[0]
    cols = line_mask.sum(0) >= max(2, 0.06 * h)
    xs = np.where(cols)[0]
    if not len(xs):
        return line_mask
    runs, s, last = [], xs[0], xs[0]
    for x in xs[1:]:
        if x - last > gap * h:
            runs.append((s, last + 1))
            s = x
        last = x
    runs.append((s, last + 1))
    a, b = max(runs, key=lambda r: line_mask[:, r[0]:r[1]].sum())
    out = np.zeros_like(line_mask)
    out[:, a:b] = line_mask[:, a:b]
    return out


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
    shape = ev.get("lines") or [len(ev["words"])]
    lines = lines_of(fill, near=ev.get("y", 0.5) * th.shape[0], k=len(shape))
    if not lines:
        return None
    rows = np.zeros(th.shape[0], bool)
    rows[max(0, lines[0][0] - 4):lines[-1][1] + 4] = True
    fill, dark = fill & rows[:, None], dark & rows[:, None]
    words = ev["words"]
    out = {"lines": [], "colours": [None] * len(words), "heights": [None] * len(words)}
    if len(lines) == 1 and len(shape) > 1:      # their caption sits on one line where the OCR saw a break
        shape = [len(words)]
    if len(lines) == len(shape):
        i = 0
        for (r0, r1), n in zip(lines, shape):
            lm = main_block(fill[r0:r1])
            cols = words_of(lm, n)
            text = " ".join(w["w"] for w in words[i:i + n])
            xs = np.where(lm.any(0))[0]
            out["lines"].append({"r0": int(r0), "r1": int(r1), "x0": int(xs.min()), "x1": int(xs.max() + 1),
                                 "text": text, "mask": tight(lm), "w0": i, "w1": i + n})
            if len(cols) == n:
                for k, (c0, c1) in enumerate(cols):      # each word's letter height (#124: sizes per word)
                    ys = np.where(lm[:, c0:c1].any(1))[0]
                    if len(ys) >= 3:
                        out["heights"][i + k] = int(ys.max() - ys.min() + 1)
                hug = _hugging(lm, dark[r0:r1], th[r0:r1])
                for k, (c0, c1) in enumerate(cols):
                    sel = lm[:, c0:c1] & hug[:, c0:c1]
                    if sel.sum() < 0.3 * max(1, lm[:, c0:c1].sum()):
                        sel = lm[:, c0:c1] if not dark[r0:r1].any() else None   # no box/outline to trust
                    if sel is None:
                        continue
                    px = th[r0:r1, c0:c1][sel]
                    if len(px) > 20:
                        out["colours"][i + k] = hex_of(np.median(px.reshape(-1, 3), 0))
            i += n
    if out["lines"]:
        y0, y1 = min(ln["r0"] for ln in out["lines"]), max(ln["r1"] for ln in out["lines"])
        x0, x1 = min(ln["x0"] for ln in out["lines"]), max(ln["x1"] for ln in out["lines"])
    else:
        y0, y1 = lines[0][0], lines[-1][1]
        xs = np.where(main_block(fill[y0:y1]).any(0))[0]
        x0, x1 = xs.min(), xs.max() + 1
    out["cy"] = float((y0 + y1) / 2 / th.shape[0])
    out["cx"] = float((x0 + x1) / 2 / th.shape[1])
    out["box_pad"] = box_pad(th, (x0, x1, y0, y1), base)
    cap = [ln["r1"] - ln["r0"] for ln in out["lines"]] or [lines[0][1] - lines[0][0]]
    out["line_h"] = float(np.median(cap))
    out["outline"] = outline_px(fill, dark, out["line_h"])
    return out


def _hugging(fill, dark, th, frac=0.18):
    """Letter pixels: fill pixels close to their box / outline (dark) — a bright picture blob that leaked into the
    caption mask has no dark edge around it."""
    h = max(3, fill.shape[0])
    k = max(3, int(frac * h) | 1)
    near = cv2.dilate((th.max(2) < DARK_V).astype(np.uint8), np.ones((k, k), np.uint8)) > 0
    return fill & near


def box_pad(th, text_box, base=None, dark_v=60, share=0.6, differ=25):
    """(pad_x, pad_y) in px of a solid dark box behind the text, or None: from the text's edges, how far rows /
    columns stay dark AND (when our caption-free frame `base` is given) differ from the picture there (dark hair
    or a dark room next to their box is not box)."""
    x0, x1, y0, y1 = [int(v) for v in text_box]
    H, W = th.shape[:2]
    h = max(1, y1 - y0)
    box = th.max(2) < dark_v
    if base is not None:
        box &= np.abs(th.astype(np.int16) - base.astype(np.int16)).max(2) > differ
    def run(lines):
        n = 0
        for ln in lines:
            if ln.size == 0 or ln.mean() < share:
                break
            n += 1
        return n
    left = run([box[y0:y1, x] for x in range(x0 - 2, max(-1, x0 - 2 * h), -1)])
    right = run([box[y0:y1, x] for x in range(x1 + 1, min(W, x1 + 2 * h))])
    top = run([box[y, x0:x1] for y in range(y0 - 2, max(-1, y0 - 2 * h), -1)])
    bot = run([box[y, x0:x1] for y in range(y1 + 1, min(H, y1 + 2 * h))])
    if min(left, right, top, bot) < 0.08 * h:
        return None
    return (float((left + right) / 2 + 2), float((top + bot) / 2 + 2))


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
def event_heights(short_path, base_path, ev, fps, size, look_frames=14):
    """Their caption's letter height and brightness over the first frames of one event: ([h], [v])."""
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
        ls = lines_of(fill, near=ev.get("y", 0.5) * a.shape[0])
        hs.append(float(max((r1 - r0) for r0, r1 in ls)) if ls else float(ys.max() - ys.min()))
        vs.append(float(a.max(2)[fill].mean()))
    return hs, vs


def reveal_of(hs, vs, fps):
    """How one caption came in, from its letter height / brightness per frame: {'kind': 'pop', 'from', 'peak',
    't_peak_ms', 'ms'} | {'kind': 'fade', 'ms'} | {'kind': 'none', 'ms': 0}; None if it can't be read."""
    if len(hs) < 4 or max(hs) == 0:
        return None
    hf, vf = np.median(hs[-4:]), np.median(vs[-4:])
    if hf <= 0:
        return None
    k0 = next((i for i, h in enumerate(hs) if h > 0.3 * hf), None)
    if k0 is None:
        return None
    rel = np.array(hs[k0:]) / hf
    if rel[0] > POP_MAX or rel.max() > POP_MAX:   # bigger than the caption itself: the one before / a flash, not a pop
        return None
    settle = next((i for i in range(len(rel)) if all(abs(r - 1) < 0.05 for r in rel[i:])), len(rel))
    if rel[0] < 0.88 or rel.max() > 1.08:
        ip = int(np.argmax(rel))
        return {"kind": "pop", "from": float(rel[0]), "peak": float(max(1.0, rel.max())),
                "t_peak_ms": int(ip * 1000 / fps), "ms": int(max(1, settle) * 1000 / fps)}
    if vs[k0] < 0.8 * vf:
        up = next((i for i in range(k0, len(vs)) if vs[i] >= 0.95 * vf), len(vs))
        return {"kind": "fade", "ms": int(max(1, up - k0 + 1) * 1000 / fps)}
    return {"kind": "none", "ms": 0}


POP_MAX = 1.6          # a caption measured taller than this x its settled height is something else on screen


def same_reveal(a, b, tol=0.15):
    """Two reveals look alike (kind, and for pops their start / peak scale within tol)."""
    if a is None or b is None or a["kind"] != b["kind"]:
        return a is b
    if a["kind"] != "pop":
        return True
    return abs(a["from"] - b["from"]) <= tol and abs(a["peak"] - b["peak"]) <= tol


def animation(short_path, base_path, evs, fps, size, n_events=6, look_frames=14):
    """How a caption appears: {'kind': 'pop'|'fade'|'none', 'from': scale, 'peak': scale, 't_peak_ms', 'ms'}."""
    votes = []
    for ev in evs[:n_events]:
        v = reveal_of(*event_heights(short_path, base_path, ev, fps, size, look_frames), fps)
        if v is not None:
            votes.append(v)
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
    b = libass_bbox(entry, text, fs, spacing, fonts_dir)
    return float(b[1] - b[0]) if b else 0.0


def libass_bbox(entry, text, fs, spacing, fonts_dir=None):
    """(x0, x1, y0, y1) of the ink of `text` drawn with \\an5 at the canvas centre (W/2, H/2), or None."""
    W, H = 4000, int(fs * 3) // 2 * 2
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
    xs, ys = np.where(a.any(0))[0], np.where(a.any(1))[0]
    if not len(xs):
        return None
    return (float(xs.min() - W / 2), float(xs.max() + 1 - W / 2), float(ys.min() - H / 2), float(ys.max() + 1 - H / 2))


# ---------------- Sonnet: what pixels can't say easily ----------------
PROMPT = ("These are crops of the burned-in captions of one YouTube Short. Describe how the caption TEXT is drawn "
          "(not the video behind it). Measured from the pixels: letter height ~{h:.0f}px, outline ~{o:.1f}px. "
          "Return JSON only: {{\"outline\": {{\"present\": bool, \"colour\": \"#RRGGBB\"}}, "
          "\"shadow\": {{\"present\": bool, \"dx\": x offset / letter height, \"dy\": y offset / letter height, "
          "\"blur\": 0 (hard) to 1 (very soft), \"colour\": \"#RRGGBB\", \"opacity\": 0-1}}, "
          "\"glow\": {{\"present\": bool, \"colour\": \"#RRGGBB\" or \"text\" if it takes each word's colour, "
          "\"size\": glow radius / letter height, \"opacity\": 0-1}}, "
          "\"box\": {{\"present\": bool, \"colour\": \"#RRGGBB\", \"opacity\": 0-1, \"soft_edges\": 0 (sharp) to 1 (very feathered), \"rounded\": 0 (square) to 1 (pill)}}, \"italic\": bool, "
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


def measure_all(short_path, base_path, evs, fps, size, at=(0.4, 0.6, 0.85)):
    """Per event: their measured caption once fully revealed; word colours voted over a few frames (one frame can
    carry a picture difference that looks like a coloured word)."""
    out = []
    for ev in evs:
        t0 = max(w["t"] for w in ev["words"]) + 0.1 if ev["words"] else ev["start"]
        span = max(0.0, ev["end"] - 0.03 - t0)
        found = []
        for f in at:
            n = int((t0 + f * span) * fps)
            th, ba = frame(short_path, n, fps, size), frame(base_path, n, fps, size)
            if th is None or ba is None:
                continue
            m = measure_event(th, ba, ev)
            if m:
                m["frame"] = th
                found.append(m)
        if not found:
            out.append(None)
            continue
        m = found[-1]
        m["colours"] = [vote_colour([x["colours"][i] for x in found]) for i in range(len(ev["words"]))]
        m["heights"] = [steady([x["heights"][i] for x in found if x.get("heights")]) for i in range(len(ev["words"]))]
        out.append(m)
    return out


def merge_colour(pixel, ocr):
    """A word's colour: the pixels' when they found a colour; the OCR's when the pixels say white (or nothing) but
    the OCR saw a highlight colour (a highlight read as white is the usual pixel miss); else white."""
    ocr = ocr if ocr and re.fullmatch(r"#[0-9A-Fa-f]{6}", str(ocr)) else DEFAULT_WHITE
    if pixel and pixel != DEFAULT_WHITE:
        return pixel
    if ocr.upper() != DEFAULT_WHITE and min(int(ocr[i:i + 2], 16) for i in (1, 3, 5)) < 200:
        return ocr.upper()
    return pixel or DEFAULT_WHITE


def vote_colour(cs):
    """White if any reading says white or the readings disagree; else their median colour."""
    cs = [c for c in cs if c]
    if not cs:
        return None
    if DEFAULT_WHITE in cs:
        return DEFAULT_WHITE if cs.count(DEFAULT_WHITE) * 2 >= len(cs) or len(cs) < 2 else _median_hex(
            [c for c in cs if c != DEFAULT_WHITE])
    rgb = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in cs], float)
    if len(cs) >= 2 and np.abs(rgb - np.median(rgb, 0)).max() > 80:
        return DEFAULT_WHITE
    return _median_hex(cs)


def _median_hex(cs):
    rgb = np.median(np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in cs], float), 0).astype(int)
    return "#%02X%02X%02X" % tuple(rgb)


def build(short_path, base_path, evs, fps, out_w, out_h, vision=None, fonts_dir=None):
    """style.json: font, size, spacing, colours per word, position, outline, shadow, glow, box, animation."""
    size = (out_w, out_h)
    fonts = ensure_fonts(fonts_dir)
    ms = measure_all(short_path, base_path, evs, fps, size)
    # real word colours (pixels beat OCR's guess)
    colours = []
    for ev, m in zip(evs, ms):
        colours.append([merge_colour(m["colours"][i] if m else None, w["c"]) for i, w in enumerate(ev["words"])])
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
    sizes = word_sizes(evs, ms)
    if sizes and any(sizes):        # #124: the font size is the one of their normal words, not of a big one
        fss2 = []
        for i in sample_idx:
            m = ms[i]
            for ln in (m["lines"] if m else []):
                sc = (sizes[i] or [1.0] * len(evs[i]["words"]))[ln["w0"]:ln["w1"]]
                if len(ln["text"]) >= 3 and all(abs(x - 1) <= SIZE_TOL for x in sc):
                    w100 = libass_width(entry, ln["text"], 100, track * 100, fonts_dir)
                    if w100 > 0:
                        fss2.append(100 * (ln["x1"] - ln["x0"]) / w100)
        if fss2:
            fs = float(np.median(fss2))
    lh0 = float(np.median([m["line_h"] for m in good]))
    pads = [m["box_pad"] for m in good if m.get("box_pad")
            and m["box_pad"][0] <= 1.2 * lh0 and m["box_pad"][1] <= 0.8 * lh0]
    box = [float(np.median([p[0] for p in pads])), float(np.median([p[1] for p in pads]))] \
        if len(pads) >= max(2, 0.4 * len(good)) else None
    line_h = float(np.median([m["line_h"] for m in good]))
    outline = float(np.median([m["outline"] for m in good]))
    cy = float(np.median([m["cy"] for m in good]))
    cx = float(np.median([m["cx"] for m in good]))
    anim = animation(short_path, base_path, [evs[i] for i in sample_idx], fps, size)
    anims = event_reveals(short_path, base_path, evs, fps, size, anim)
    crops = []
    for i in sample_idx[:4]:
        m = ms[i]
        if m:
            top = min((ln["r0"] for ln in m["lines"]), default=m["cy"] * out_h - line_h)
            bot = max((ln["r1"] for ln in m["lines"]), default=m["cy"] * out_h + line_h)
            r0, r1 = max(0, int(top - line_h)), min(out_h, int(bot + line_h))
            crops.append(m["frame"][r0:r1])
    looks = ask_style(crops, line_h, outline, vision) if crops else {}
    dy = 0.0
    if fs:   # \\an5 centres the line box; their measured centre is the letters' centre
        bb = libass_bbox(entry, "HELLO", fs, track * fs, fonts_dir)
        dy = (bb[2] + bb[3]) / 2 if bb else 0.0
    if box and looks.get("box") is not None:
        looks["box"]["present"] = True
    def reliable(m):
        return bool(m and m["lines"] and 0.75 * line_h <= m["line_h"] <= 1.33 * line_h)
    if sum(1 for e in evs if "x" in e) >= 0.6 * len(evs):     # their caption's place, per state from the pixels
        pos = [[e["x"], e["y"]] if "x" in e else None for e in evs]
    else:
        pos = [[round(m["cx"], 4), round(m["cy"], 4)] if reliable(m) else None for m in ms]   # where each sits
    rel = [p for p in pos if p]
    if rel:
        mx, my = float(np.median([p[0] for p in rel])), float(np.median([p[1] for p in rel]))
        off = [abs(p[0] - mx) > 0.08 or abs(p[1] - my) > 0.05 for p in rel]
        if np.mean(off) < 0.3:          # their captions stay put: one place for all (noise can't move them)
            pos = [None] * len(pos)
            cx, cy = mx, my
    st = {"ok": fs is not None, "family": entry[0], "bold": entry[1], "italic": entry[2], "file": entry[3],
          "box_pad": box, "dy": dy, "pos": pos,
          "font_score": round(score, 3), "track": track, "fs": fs, "spacing": None if fs is None else track * fs,
          "outline": outline, "line_h": line_h, "x": cx, "y": cy, "anim": anim, "colours": colours,
          "sizes": sizes, "anims": anims,
          "llm": looks, "alternatives": [(round(s, 3), e[0], e[2], t) for s, e, t in ranked[1:4]]}
    C.log(f"style: {entry[0]}{' italic' if entry[2] else ''} (shape {score:.2f}, next "
          f"{', '.join(f'{e[0]} {s:.2f}' for s, e, _ in ranked[1:3])}), size {fs and round(fs)}, track {track}, "
          f"outline {outline:.1f}px, anim {anim['kind']}, {sum(1 for x in sizes if x)} events with word sizes, "
          f"{sum(1 for a in anims if a)} with their own reveal")
    return st


SIZE_TOL = 0.25          # a word this much bigger / smaller than their normal words is sized on its own (#124)
SIZE_RANGE = (0.55, 2.2)  # outside this a "word height" is a mis-split line, not a size
STEADY = 0.12            # a word's height must agree this closely on the frames it was measured on


def steady(hs):
    """A word's letter height when the frames agree on it (a pop still settling or a mis-split word don't)."""
    hs = [h for h in hs if h]
    if not hs:
        return None
    if len(hs) > 1 and max(hs) > (1 + STEADY) * min(hs):
        return None
    return int(np.median(hs))


def word_sizes(evs, ms):
    """Per event: each word's size relative to their normal words (letter height), or None when all are normal.
    Only words in capitals count (lower-case letters have their own heights)."""
    hs = [h for m in ms if m for h in m.get("heights") or [] if h]
    if len(hs) < 3:
        return [None] * len(evs)
    ref = float(np.median(hs))
    out = []
    for ev, m in zip(evs, ms):
        sc = []
        for w, h in zip(ev["words"], (m or {}).get("heights") or [None] * len(ev["words"])):
            caps = re.search(r"[A-Z0-9]", w["w"]) and not re.search(r"[a-z]", w["w"])
            r = h / ref if (h and caps) else 1.0
            sc.append(round(float(r), 3) if (SIZE_RANGE[0] <= r <= SIZE_RANGE[1] and abs(r - 1) > SIZE_TOL) else 1.0)
        out.append(sc if any(x != 1.0 for x in sc) else None)
    return out


def event_reveals(short_path, base_path, evs, fps, size, anim, look_frames=14):
    """Per event: how that caption came in when it differs from the Short's usual reveal (#124), else None.
    Read at half size (heights are relative)."""
    half = (size[0] // 2, int(round(size[1] / 2 / 2) * 2))
    out = []
    for ev in evs:
        v = reveal_of(*event_heights(short_path, base_path, ev, fps, half, look_frames), fps)
        out.append(None if v is None or same_reveal(v, anim) else v)
    return out


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
    dy = st.get("dy", 0.0)
    if fs:
        bb = libass_bbox(entry, "HELLO", fs, tr * fs, fonts_dir)
        dy = (bb[2] + bb[3]) / 2 if bb else dy
    return {**st, "family": entry[0], "bold": entry[1], "italic": entry[2], "file": entry[3], "track": tr, "fs": fs,
            "spacing": None if fs is None else tr * fs, "dy": dy}


# ---------------- caption states from their pixels (exact timing) ----------------
SEG_W = 540
SEG_IOU = 0.6
SEG_WIDTH = 0.12        # the caption's width changing more than this between two frames = new words
EDGED = 0.35            # share of fill pixels hugging a box / outline that makes captions findable anywhere
OCR_PROMPT = ("Each image is a crop of one YouTube Short frame around its big burned-in caption. For each image, in "
              "order, read the caption exactly as shown (keep punctuation, $, *asterisks*, case) and the fill colour "
              "of each word. Return JSON only: a list with one object per image: "
              "{{\"lines\": [[[\"WORD\", \"#RRGGBB\"], ...], ...]}} (lines top to bottom, words left to right; "
              "white is #FFFFFF); an image without a caption: {{\"lines\": []}}. There are {n} images.")


def _near_dark(th, k):
    return cv2.dilate((th.max(2) < DARK_V).astype(np.uint8), np.ones((k, k), np.uint8)) > 0


def text_lines(th, base, y=0.5, edged=True, near=None):
    """(rows, fill) of their caption in this frame: the text-like line(s) anywhere in the frame (fill hugging a box /
    outline) when their captions are `edged`, else the line(s) nearest `near` (fraction). rows = [(r0, r1)]."""
    H = th.shape[0]
    _, fill, _ = caption_masks(th, base, 0.5, 0.42)
    runs = _line_runs(fill, 3)
    if not runs:
        return [], fill
    if edged:
        best, score = None, 0.0
        nd = _near_dark(th, max(3, int(th.shape[1] / 90) | 1))
        for i, (r0, r1) in enumerate(runs):
            f = fill[r0:r1]
            px = int(f.sum())
            if px < 30 or (r1 - r0) > 0.14 * H:
                continue
            hug = float((f & nd[r0:r1]).sum()) / px
            s = hug * np.sqrt(px)
            if hug >= EDGED and s > score:
                best, score = i, s
        if best is None:
            return [], fill
        r0, r1 = runs[best]
        sel = [runs[best]]
        for j in (best - 1, best + 1, best - 2, best + 2):          # the caption's other lines, close above/below
            if 0 <= j < len(runs):
                q0, q1 = runs[j]
                gap = q0 - sel[-1][1] if q0 > r0 else sel[0][0] - q1
                if 0 <= gap < 0.9 * (r1 - r0) and 0.6 <= (q1 - q0) / (r1 - r0) <= 1.6:
                    sel.append(runs[j])
                    sel.sort()
        return sel, fill
    ls = lines_of(fill, min_rows=3, near=(near if near is not None else y) * H, k=3)
    return ls, fill


def captions_edged(short_path, base_path, fps, nfr, size, samples=24):
    """Do their captions sit in a box / outline (findable anywhere in the frame)?"""
    hugs = []
    for n in np.linspace(0, max(0, nfr - 1), samples).astype(int):
        a, b = frame(short_path, n, fps, size), frame(base_path, n, fps, size)
        if a is None or b is None:
            continue
        ls, _ = text_lines(a, b, edged=True)
        hugs.append(1.0 if ls else 0.0)
    return bool(hugs) and float(np.mean(hugs)) >= 0.4


def refine_y(short_path, base_path, fps, nfr, size, y, samples=24):
    """Their caption's centre row (fraction): the text line nearest the OCR's guess, median over sampled frames."""
    ys = []
    for n in np.linspace(0, max(0, nfr - 1), samples).astype(int):
        a, b = frame(short_path, n, fps, size), frame(base_path, n, fps, size)
        if a is None or b is None:
            continue
        _, fill, _ = caption_masks(a, b, y)
        ls = lines_of(fill, near=y * size[1])
        if ls:
            ys.append((ls[0][0] + ls[0][1]) / 2 / size[1])
    return float(np.median(ys)) if len(ys) >= 3 else y


def caption_states(short_path, base_path, fps, nfr, size, y, edged=False, chunk=120):
    """[{'n0', 'n1', 'box': [x0, x1, y0, y1] (fractions), 'iou': [...]}]: frame ranges in which their caption shows
    the same text. A new range starts when the caption's pixels change shape (IoU), its width jumps (a word swapped
    for one of similar shape) or it disappears. Frames whose 'caption' is far taller than their text (a flash or a
    cut the map missed) keep the current state."""
    W0, H0 = size
    w, h = SEG_W, int(round(SEG_W * H0 / W0 / 2) * 2)
    k3 = np.ones((3, 3), np.uint8)
    masks, boxes = [], []
    for k in range(0, nfr, chunk):
        a = C.read_frames(short_path, k, min(chunk, nfr - k), fps, (w, h))
        b = C.read_frames(base_path, k, min(chunk, nfr - k), fps, (w, h))
        for i in range(min(len(a), len(b))):
            ls, fill = text_lines(a[i], b[i], y, edged, near=y)
            if not ls:
                masks.append(None)
                boxes.append(None)
                continue
            keep = np.zeros(h, bool)
            keep[max(0, ls[0][0] - 2):ls[-1][1] + 2] = True
            m = fill & keep[:, None]
            m = main_block(m) if len(ls) == 1 else m
            xs = np.where(m.any(0))[0]
            if m.sum() < 40 or not len(xs):
                masks.append(None)
                boxes.append(None)
                continue
            masks.append(np.packbits(cv2.dilate(m.astype(np.uint8), k3) > 0))
            boxes.append((int(xs.min()), int(xs.max()) + 1, ls[0][0], ls[-1][1], max(r1 - r0 for r0, r1 in ls)))
    hs = [bx[4] for bx in boxes if bx]
    typical = float(np.median(hs)) if hs else 0
    segs, cur, prev, pbox, ious = [], None, None, None, []

    def close(n_end):
        if cur is not None and n_end - cur >= 2:
            bs = [bx for bx in boxes[cur:n_end] if bx]
            box = [float(np.median([bx[j] for bx in bs])) / (w if j < 2 else h) for j in range(4)] if bs else None
            segs.append({"n0": cur, "n1": n_end, "box": box, "iou": ious[:]})
    for n, (pm, bx) in enumerate(zip(masks, boxes)):
        if pm is not None and typical and bx[4] > 1.6 * typical:
            continue                                  # flash / missed cut: not a caption change
        m = None if pm is None else np.unpackbits(pm)[:h * w].reshape(h, w).astype(bool)
        if m is None:
            close(n)
            cur, ious = None, []
        elif cur is None:
            cur, ious = n, [1.0]
        else:
            inter, union = (m & prev).sum(), (m | prev).sum()
            iou = inter / union if union else 1.0
            wd = (bx[1] - bx[0]) / max(1, pbox[1] - pbox[0])
            if iou < SEG_IOU or abs(wd - 1) > SEG_WIDTH:
                close(n)
                cur, ious = n, [1.0]
            else:
                ious.append(float(iou))
        if m is not None:
            prev, pbox = m, bx
    close(len(masks))
    return segs


def _crop(f, box, size):
    """Their caption with room around it (the OCR sees the words, not the whole frame)."""
    W0, H0 = size
    if box is None:
        return f
    x0, x1, y0, y1 = box
    hh = max(0.04, y1 - y0)
    r0, r1 = max(0, int((y0 - 1.2 * hh) * H0)), min(H0, int((y1 + 1.2 * hh) * H0))
    c0, c1 = max(0, int((x0 - 0.15) * W0)), min(W0, int((x1 + 0.15) * W0))
    return f[r0:r1, c0:c1]


def _parse_lines(it):
    """[[(word, colour)]] from the OCR's lines (words as "W" or ["W", "#RRGGBB"])."""
    lines = []
    raw = it.get("lines") if isinstance(it, dict) else it      # the model sometimes answers the lines bare
    if raw and isinstance(raw, list) and raw and not isinstance(raw[0], list):
        raw = [raw]                                             # one line given flat
    for ln in raw or []:
        if not isinstance(ln, list):
            continue
        out = []
        for wd in ln:
            if isinstance(wd, (list, tuple)) and wd:
                w, c = str(wd[0]).strip(), (str(wd[1]) if len(wd) > 1 else DEFAULT_WHITE)
            else:
                w, c = str(wd).strip(), DEFAULT_WHITE
            if w:
                c = c.upper() if re.fullmatch(r"#[0-9A-Fa-f]{6}", c) else DEFAULT_WHITE
                out.append((w, c))
        if out:
            lines.append(out)
    return lines


def ocr_frames(short_path, reqs, fps, size, vision, batch=12):
    """reqs: [(frame, box)] -> [[[(word, colour)]]] one caption per request."""
    imgs = []
    for n, box in reqs:
        f = frame(short_path, n, fps, size)
        crop = _crop(f, box, size) if f is not None else np.zeros((64, 64, 3), np.uint8)
        if crop.size == 0:
            crop = f
        s = 720 / max(1, crop.shape[1])
        crop = cv2.resize(crop, (720, max(16, int(crop.shape[0] * s))))
        imgs.append(cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes())
    out = []
    for k in range(0, len(imgs), batch):
        part = imgs[k:k + batch]
        items = None
        for _ in range(3):
            txt = vision(part, OCR_PROMPT.format(n=len(part)))
            mm = re.search(r"\[.*\]", txt or "", re.S)
            try:
                items = json.loads(mm.group(0)) if mm else None
            except ValueError:
                items = None
            if isinstance(items, list) and len(items) == len(part):
                break
            items = None
        out += [_parse_lines(it) for it in (items or [{}] * len(part))]
    return out


def read_states(short_path, segs, fps, size, y, vision, long_f=8):
    """Text of each caption state; a long state is read near its start and its end, and split where its pixels
    changed most when the two readings differ (two words of the same shape in a row). Returns (segs, texts)."""
    reqs, owner = [], []
    for i, s in enumerate(segs):
        a, b = s["n0"], s["n1"]
        pts = [a + int(0.3 * (b - a)), a + int(0.85 * (b - a))] if b - a >= long_f else [a + int(0.7 * (b - a))]
        for n in pts:
            reqs.append((n, s.get("box")))
            owner.append(i)
    reads = ocr_frames(short_path, reqs, fps, size, vision)
    by = {}
    for i, r in zip(owner, reads):
        by.setdefault(i, []).append(r)
    out_s, out_t = [], []
    for i, s in enumerate(segs):
        rs = by.get(i, [[]])
        k0 = [_key(w) for ln in rs[0] for w, _ in ln]
        k1 = [_key(w) for ln in rs[-1] for w, _ in ln]
        if len(rs) == 2 and k0 != k1 and k0 and k1 and len(s["iou"]) > 3:
            j = 1 + int(np.argmin(s["iou"][1:]))            # the frame whose pixels changed most
            out_s += [{**s, "n1": s["n0"] + j}, {**s, "n0": s["n0"] + j}]
            out_t += [rs[0], rs[1]]
        else:
            out_s.append(s)
            out_t.append(rs[-1])
    return out_s, out_t


def _key(w):
    return re.sub(r"[^A-Z0-9$]", "", str(w).upper())


def state_events(segs, texts, fps, y):
    """Caption events from the states: a state whose words continue the previous state's (right after it) adds
    its new words to that event at its first frame; anything else starts a new event. Each event carries where
    their caption sat (x, y) and each word's colour as read."""
    evs = []
    for s, lines in zip(segs, texts):
        a, b = (s["n0"], s["n1"]) if isinstance(s, dict) else s
        box = s.get("box") if isinstance(s, dict) else None
        lines = [[(w, DEFAULT_WHITE) if isinstance(w, str) else tuple(w) for w in ln] for ln in lines]
        words = [w for ln in lines for w in ln]
        if not words:
            continue
        p = evs[-1] if evs else None
        pk = [_key(w["w"]) for w in p["words"]] if p else []
        nk = [_key(w) for w, _ in words]
        if p and abs(p["end"] - a / fps) < 1.5 / fps and nk[:len(pk)] == pk and len(nk) >= len(pk):
            p["words"] += [{"w": w, "c": c, "t": round(a / fps, 3)} for w, c in words[len(pk):]]
            p["end"], p["lines"] = round(b / fps, 3), [len(ln) for ln in lines]
            continue
        if p and a / fps - p["end"] < 0.4 and nk == pk:      # same caption, lost for a moment (flash, pop)
            p["end"] = round(b / fps, 3)
            continue
        e = {"start": round(a / fps, 3), "end": round(b / fps, 3), "y": y, "lines": [len(ln) for ln in lines],
             "words": [{"w": w, "c": c, "t": round(a / fps, 3)} for w, c in words]}
        if box:
            e["x"], e["y"] = round((box[0] + box[1]) / 2, 4), round((box[2] + box[3]) / 2, 4)
        evs.append(e)
    return evs


def pixel_events(short_path, base_path, fps, nfr, size, y, vision):
    edged = captions_edged(short_path, base_path, fps, nfr, size)
    y = refine_y(short_path, base_path, fps, nfr, size, y)
    segs = caption_states(short_path, base_path, fps, nfr, size, y, edged=edged)
    if not segs:
        return []
    segs, texts = read_states(short_path, segs, fps, size, y, vision)
    evs = state_events(segs, texts, fps, y)
    C.log(f"captions from pixels ({'anywhere: box/outline' if edged else 'at one height'}): {len(segs)} states -> {len(evs)} events, "
          f"{sum(len(e['words']) for e in evs)} words")
    return evs
