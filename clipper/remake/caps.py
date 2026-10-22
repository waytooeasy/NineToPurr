"""Their captions (D58): read at 10 fps with Haiku vision (text per line, colour per word, height), turned into
caption events with the time each word appears, then written as ASS in their style (Montserrat Black, wide
tracking, colour glow + dark drop shadow, words fading and blurring in where they sit, line laid out in full).
Size and tracking are calibrated on the rendered font (cap height and width measured on the study Short)."""
import base64
import difflib
import json
import re
import subprocess

import numpy as np

from . import common as C

MODEL = "claude-haiku-5-5"
OCR_FPS = 10
BATCH = 15
FONT = "Montserrat Black"
CAP_H = 42 / 1080          # cap height / frame width (study Short)
TRACK = 10.62 / 89.4       # ASS letter spacing / font size (study Short)
FADE_MS = 130
WHITE = "#FFFFFF"

PROMPT = ("These are {n} consecutive frames (0.1 s apart) of a YouTube Short. For each frame read the BIG burned-in "
          "caption only (not the stream's chat overlay, usernames, signs or logos in the scene). Return JSON only: "
          "a list with one object per frame, in order: {{\"lines\": [[[\"WORD\", \"#RRGGBB\"], ...], ...], "
          "\"y\": vertical centre of the caption as a fraction of the frame height}}. 'lines' lists the caption's "
          "lines top to bottom, each line its words left to right with the word's fill colour; keep punctuation and "
          "*asterisks* inside the words. A frame without a caption: {{\"lines\": [], \"y\": null}}.")


def anthropic_vision(images, prompt):
    import anthropic  # lazy
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": base64.b64encode(b).decode()}} for b in images]
    content.append({"type": "text", "text": prompt})
    msg = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=6000, thinking={"type": "disabled"},
                                                messages=[{"role": "user", "content": content}])
    try:
        import llm  # editor/llm.py when editor/ is on sys.path: cost tracking, never raises
        llm.log_usage("anthropic", MODEL, llm._usage_dict(msg.usage))
    except Exception:  # noqa: BLE001
        pass
    return "".join(b.text for b in msg.content if b.type == "text")


def _jpeg(path, t, w, h):
    return subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                           "-vf", f"scale={w}:{h}", "-f", "image2", "-c:v", "mjpeg", "-q:v", "4", "-"],
                          capture_output=True, check=True).stdout


def parse(text, n):
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return None
    try:
        items = json.loads(m.group(0))
    except ValueError:
        return None
    return items if isinstance(items, list) and len(items) == n else None


def ocr(short_path, dur, aspect, vision=anthropic_vision, fps=OCR_FPS):
    """[{'t', 'lines': [[(word, colour)]], 'y'}] every 1/fps s."""
    w = 320
    h = int(round(w * aspect / 2) * 2)
    times = [round(i / fps, 3) for i in range(int(dur * fps))]
    out = []
    for k in range(0, len(times), BATCH):
        batch = times[k:k + BATCH]
        imgs = [_jpeg(short_path, t, w, h) for t in batch]
        items = None
        for _ in range(3):
            items = parse(vision(imgs, PROMPT.format(n=len(batch))), len(batch))
            if items is not None:
                break
        for t, it in zip(batch, items or [{}] * len(batch)):
            lines = []
            for line in (it or {}).get("lines") or []:
                words = [(str(wd[0]).strip(), str(wd[1]) if len(wd) > 1 else WHITE) for wd in line
                         if isinstance(wd, (list, tuple)) and wd and str(wd[0]).strip()]
                if words:
                    lines.append(words)
            out.append({"t": t, "lines": lines, "y": (it or {}).get("y")})
    return out


def _key(w):
    return re.sub(r"[^A-Z0-9']", "", w.upper())


def _same(a, b):
    """Same caption word: equal, one still being revealed (prefix), or a small misread."""
    a, b = _key(a), _key(b)
    if a == b or (a and b and (a.startswith(b) or b.startswith(a))):
        return True
    return len(a) > 2 and len(b) > 2 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.6


def _spelling(variants):
    """The full word: each reading also votes for the longer readings it is a prefix of."""
    forms = set(variants)
    score = {f: sum(1 for v in variants if _key(f).startswith(_key(v))) for f in forms}
    return max(forms, key=lambda f: (score[f], len(_key(f)), variants.count(f)))


def _compatible(cur, words):
    """Does `words` continue caption `cur` (same words so far, maybe more)?"""
    n = min(len(cur), len(words))
    return n > 0 and sum(_same(a, b) for a, b in zip(cur[:n], words[:n])) >= max(1, n - (1 if n >= 3 else 0))


def _hex(c):
    c = str(c).strip()
    return c.upper() if re.fullmatch(r"#[0-9A-Fa-f]{6}", c) else WHITE


def _mean_colour(cs):
    rgb = np.array([[int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)] for c in map(_hex, cs)], float)
    if (rgb.min(1) > 215).mean() >= 0.5:      # mostly read as white: white
        return WHITE
    rgb = rgb[rgb.min(1) <= 215] if (rgb.min(1) <= 215).any() else rgb
    r, g, b = np.median(rgb, 0).astype(int)
    return f"#{r:02X}{g:02X}{b:02X}"


def events(rows, step=1 / OCR_FPS):
    """Caption events: [{'start', 'end', 'y', 'lines': [n_words per line], 'words': [{'w', 'c', 't'}]}]."""
    evs, cur = [], None

    def close(t_end):
        if cur:
            words = []
            for i, var in enumerate(cur["seen"]):
                spelling = _spelling([v for v, _ in var])
                words.append({"w": spelling, "c": _mean_colour([c for _, c in var]),
                              "t": round(max(cur["start"], cur["first"][i] - step / 2), 3)})
            evs.append({"start": round(cur["start"], 3), "end": round(t_end, 3),
                        "y": float(np.median(cur["ys"])) if cur["ys"] else 0.5,
                        "lines": cur["lines"], "words": words})

    for r in rows:
        flat = [w for line in r["lines"] for w in line]
        if not flat:
            close(r["t"] - step / 2)
            cur = None
            continue
        words = [w for w, _ in flat]
        if cur is None or not _compatible([v[0][0] for v in cur["seen"]], words):
            close(r["t"] - step / 2)
            cur = {"start": max(0.0, r["t"] - step / 2), "seen": [], "first": [], "ys": [], "lines": []}
        for i, (w, c) in enumerate(flat):
            if i >= len(cur["seen"]):
                cur["seen"].append([])
                cur["first"].append(r["t"])
            cur["seen"][i].append((w, c))
        if len(flat) > cur.get("nmax", 0):
            cur["nmax"], cur["shapes"] = len(flat), []
        if len(flat) == cur.get("nmax"):   # line breaks: the shape read most often once all words are up
            cur["shapes"].append(tuple(len(line) for line in r["lines"]))
            cur["lines"] = list(max(set(cur["shapes"]), key=cur["shapes"].count))
        if isinstance(r.get("y"), (int, float)):
            cur["ys"].append(float(r["y"]))
    if rows:
        close(rows[-1]["t"] + step / 2)
    return [e for e in evs if e["end"] - e["start"] >= 0.15]


def merge_continuations(evs, gap=0.2):
    """'I GOT YOU' then 'I GOT YOU YOUR FLOWERS' (or a misread last word) right after: one caption still revealing."""
    out = []
    for e in evs:
        p = out[-1] if out else None
        if p and e["start"] - p["end"] <= gap:
            k = 0
            while k < min(len(p["words"]), len(e["words"])) and _same(p["words"][k]["w"], e["words"][k]["w"]):
                k += 1
            if k >= 2 and k >= len(p["words"]) - 1:
                words = p["words"][:k] + [dict(w, t=max(w["t"], e["start"])) for w in e["words"][k:]]
                out[-1] = {**p, "end": e["end"], "words": words, "lines": e["lines"] if len(e["words"]) >= len(p["words"]) else p["lines"]}
                continue
        out.append(e)
    return out


def one_position(evs):
    """Clippers keep one caption position per Short; OCR heights are noisy: use their median for every event."""
    ys = [e["y"] for e in evs if isinstance(e.get("y"), (int, float))]
    if ys:
        y = float(np.clip(np.median(ys), 0.12, 0.88))
        for e in evs:
            e["y"] = y
    return evs


def refine_times(evs, bands, fps, nfr, back_s=1.0, fwd_s=0.5):
    """Start/end of each caption from the pixels: the caption band differs from our caption-free frame while a
    caption is on screen (OCR at 10 fps misses or delays some)."""
    if not evs or not bands:
        return evs
    y = evs[0]["y"]
    j = int(np.clip(y * 16, 1, 14))
    E = np.array([np.mean(bands.get(str(n), [0] * 16)[j - 1:j + 2]) if str(n) in bands else np.nan
                  for n in range(nfr)])
    if np.all(np.isnan(E)):
        return evs
    on = [E[int(e["start"] * fps):int(e["end"] * fps)] for e in evs]
    on_lvl = np.nanmedian(np.concatenate(on)) if on else np.nan
    off_lvl = np.nanpercentile(E, 10)
    if not on_lvl > off_lvl * 1.3:
        return evs
    th = off_lvl + 0.4 * (on_lvl - off_lvl)
    lit = np.nan_to_num(E, nan=0) > th
    for i, e in enumerate(evs):
        lo = int((evs[i - 1]["end"] if i else 0) * fps)
        hi = int((evs[i + 1]["start"] if i + 1 < len(evs) else nfr / fps) * fps)
        a, b = int(e["start"] * fps), max(int(e["start"] * fps) + 1, int(e["end"] * fps))
        while a - 1 >= max(lo, int((e["start"] - back_s) * fps)) and lit[a - 1]:
            a -= 1
        while b < min(hi, int((e["end"] + fwd_s) * fps), nfr) and lit[b]:
            b += 1
        new_start = a / fps
        if new_start < e["start"]:
            first = e["words"][0]["t"]
            for w in e["words"]:
                w["t"] = round(new_start + (w["t"] - first) if w["t"] <= first + 1e-9 else max(w["t"], new_start), 3)
        e["start"], e["end"] = round(min(new_start, e["start"]), 3), round(max(b / fps, e["end"]), 3)
        for w in e["words"]:
            w["t"] = max(w["t"], e["start"])
    return evs


def ass_colour(hex_rgb):
    h = _hex(hex_rgb)
    return f"&H{h[5:7]}{h[3:5]}{h[1:3]}&"


def ts(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def calibrate(out_w, out_h, fonts_dir=None):
    """(font size, tracking) giving cap height CAP_H * out_w with the font as libass renders it."""
    import tempfile
    from pathlib import Path

    def cap_height(fs):
        with tempfile.TemporaryDirectory() as d:
            ass = Path(d) / "c.ass"
            ass.write_text(header(out_w, out_h, fs, 0) + f"Dialogue: 0,0:00:00.00,0:00:01.00,C,,0,0,0,,"
                           f"{{\\pos({out_w // 2},{out_h // 2})}}HELLO\n")
            raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=black:s={out_w}x{out_h}:d=0.1",
                                  "-vf", f"ass={ass}:fontsdir={fonts_dir or C.fonts_dir()}", "-frames:v", "1",
                                  "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        a = np.frombuffer(raw, np.uint8).reshape(out_h, out_w) > 128
        ys = np.where(a.any(1))[0]
        return (ys.max() - ys.min() + 1) if len(ys) else 0
    h = cap_height(100)
    fs = 100 * CAP_H * out_w / h if h else 0.083 * out_w
    return fs, fs * TRACK


def header(out_w, out_h, fs, fsp):
    return (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {out_w}\nPlayResY: {out_h}\nWrapStyle: 0\n"
            "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding\n"
            f"Style: C,{FONT},{fs:.1f},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,{fsp:.2f},0,1,0,0,"
            f"5,{round(0.08 * out_w)},{round(0.08 * out_w)},0,1\n"
            f"Style: Mark,{FONT},{42 * out_w / 1080:.0f},&H66FFFFFF,&H00FFFFFF,&H99000000,&HFF000000,1,0,0,0,100,100,1,0,1,2,0,"
            "5,80,80,0,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")


def _layer(ev, kind, scale):
    parts, i = [], 0
    for li, n in enumerate(ev["lines"] or [len(ev["words"])]):
        for j in range(n):
            if i >= len(ev["words"]):
                break
            w = ev["words"][i]
            i += 1
            t1 = int(round((w["t"] - ev["start"]) * 1000))
            t2 = t1 + FADE_MS
            c = ass_colour(w["c"])
            white = _hex(w["c"]) == WHITE
            if kind == "fill":
                tag = f"{{\\c{c}\\alpha&HFF&\\blur{6 * scale:.1f}\\t({t1},{t2},\\alpha&H00&\\blur{0.6 * scale:.1f})}}"
            elif kind == "glow":
                tag = (f"{{\\c{c}\\3c{c}\\bord{6 * scale:.1f}\\alpha&HFF&\\blur{14 * scale:.1f}"
                       f"\\t({t1},{t2},\\alpha{'&HC8&' if white else '&H38&'})}}")
            else:
                tag = (f"{{\\c&H000000&\\3c&H000000&\\bord{3 * scale:.1f}\\alpha&HFF&\\blur{9 * scale:.1f}"
                       f"\\t({t1},{t2},\\alpha&H60&)}}")
            sep = "\\N" if (j == 0 and li > 0) else ("" if not parts else " ")
            parts.append(sep + tag + w["w"].replace("{", "(").replace("}", ")"))
    return "".join(parts)


def write_ass(evs, path, out_w, out_h, fs=None, fsp=None, mark=None, dur=None):
    """ASS of the caption events (+ our channel handle low-centre for the whole Short, like every clip we post)."""
    if fs is None:
        fs, fsp = calibrate(out_w, out_h)
    scale = out_w / 1080
    lines = []
    if mark and dur:
        lines.append(f"Dialogue: 3,{ts(0)},{ts(dur)},Mark,,0,0,0,,{{\\an5\\pos({out_w / 2:.0f},{0.849 * out_h:.0f})}}{mark}")
    for ev in evs:
        x, y = out_w / 2, ev.get("y", 0.5) * out_h
        s0, s1 = ts(ev["start"]), ts(ev["end"])
        dx, dy = 6 * scale, 7 * scale
        lines.append(f"Dialogue: 0,{s0},{s1},C,,0,0,0,,{{\\an5\\pos({x + dx:.0f},{y + dy:.0f})}}" + _layer(ev, "shadow", scale))
        lines.append(f"Dialogue: 1,{s0},{s1},C,,0,0,0,,{{\\an5\\pos({x:.0f},{y:.0f})}}" + _layer(ev, "glow", scale))
        lines.append(f"Dialogue: 2,{s0},{s1},C,,0,0,0,,{{\\an5\\pos({x:.0f},{y:.0f})}}" + _layer(ev, "fill", scale))
    from pathlib import Path
    Path(path).write_text(header(out_w, out_h, fs, fsp) + "\n".join(lines) + "\n")
    return path


def build(short_path, dur, aspect, path, out_w, out_h, vision=anthropic_vision, mark=None, bands=None, fps=None):
    rows = ocr(short_path, dur, aspect, vision)
    evs = one_position(merge_continuations(events(rows)))
    if bands and fps:
        evs = refine_times(evs, bands, fps, int(round(dur * fps)))
    write_ass(evs, path, out_w, out_h, mark=mark, dur=dur)
    C.log(f"captions: {len(evs)} events, {sum(len(e['words']) for e in evs)} words")
    return {"rows": rows, "events": evs, "ass": str(path)}


# ---------------- their style, measured (style.py) ----------------
def _rgb_hex(c, fallback=WHITE):
    c = str(c or "").strip()
    return c.upper() if re.fullmatch(r"#[0-9A-Fa-f]{6}", c) else fallback


def _ass_alpha(opacity):
    return f"&H{int(round((1 - float(np.clip(opacity, 0, 1))) * 255)):02X}&"


def _reveal(t1, anim, target_alpha="&H00&"):
    """ASS tags that keep a word hidden until t1 (ms from the line start), then bring it in like theirs."""
    kind = anim.get("kind", "none")
    ms = max(1, int(anim.get("ms") or 1))
    if kind == "fade":
        tag = f"\\alpha&HFF&\\t({t1},{t1 + ms},\\alpha{target_alpha})"
    else:
        tag = f"\\alpha&HFF&\\t({t1},{t1 + 1},\\alpha{target_alpha})"
    if kind == "pop":
        s0 = int(round(100 * float(anim.get("from", 0.8))))
        pk = int(round(100 * float(anim.get("peak", 1.0))))
        tp = max(1, int(anim.get("t_peak_ms") or ms))
        if pk > 101 and tp < ms:
            tag += (f"\\fscx{s0}\\fscy{s0}\\t({t1},{t1 + tp},\\fscx{pk}\\fscy{pk})"
                    f"\\t({t1 + tp},{t1 + ms},\\fscx100\\fscy100)")
        else:
            tag += f"\\fscx{s0}\\fscy{s0}\\t({t1},{t1 + ms},\\fscx100\\fscy100)"
    return tag


def _styled_text(ev, colours, anim, layer, st):
    """One caption line set: per word colour + reveal; layer = 'main' | 'shadow' | 'glow'."""
    llm = st.get("llm") or {}
    parts, i = [], 0
    for li, n in enumerate(ev.get("lines") or [len(ev["words"])]):
        for j in range(n):
            if i >= len(ev["words"]):
                break
            w = ev["words"][i]
            c = _rgb_hex(colours[i] if i < len(colours) else w["c"])
            i += 1
            t1 = max(0, int(round((w["t"] - ev["start"]) * 1000)))
            if layer == "main":
                tag = f"\\c{ass_colour(c)}" + _reveal(t1, anim)
            elif layer == "glow":
                g = llm.get("glow") or {}
                gc = c if str(g.get("colour", "text")).lower() == "text" else _rgb_hex(g.get("colour"), c)
                tag = f"\\c{ass_colour(gc)}\\3c{ass_colour(gc)}" + _reveal(t1, anim, _ass_alpha(g.get("opacity", 0.6)))
            else:
                s = llm.get("shadow") or {}
                sc = _rgb_hex(s.get("colour"), "#000000")
                tag = f"\\c{ass_colour(sc)}\\3c{ass_colour(sc)}" + _reveal(t1, anim, _ass_alpha(s.get("opacity", 0.8)))
            sep = "\\N" if (j == 0 and li > 0) else ("" if not parts else " ")
            text = w["w"].upper() if llm.get("case") == "upper" else w["w"]
            parts.append(sep + "{" + tag + "}" + text.replace("{", "(").replace("}", ")"))
    return "".join(parts)


def style_header(out_w, out_h, st):
    llm = st.get("llm") or {}
    ol = llm.get("outline") or {}
    box = llm.get("box") or {}
    outline = float(st.get("outline") or 0) if ol.get("present", True) else 0.0
    oc = ass_colour(_rgb_hex(ol.get("colour"), "#000000"))
    border_style, back = 1, "&H00000000"
    if box.get("present") and not st.get("box_pad"):    # measured boxes are drawn exactly (write_ass_style)
        border_style = 3
        back = f"&H{int(round((1 - float(box.get('opacity', 1))) * 255)):02X}{ass_colour(_rgb_hex(box.get('colour'), '#000000'))[2:-1]}"
        oc = f"&H{int(round((1 - float(box.get('opacity', 1))) * 255)):02X}{ass_colour(_rgb_hex(box.get('colour'), '#000000'))[2:-1]}"
        outline = max(outline, 0.12 * float(st.get("line_h") or 40))
    return (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {out_w}\nPlayResY: {out_h}\nWrapStyle: 2\n"
            "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding\n"
            f"Style: C,{st['family']},{st['fs']:.1f},&H00FFFFFF,&H00FFFFFF,{oc},{back},{-1 if st.get('bold') else 0},"
            f"{-1 if st.get('italic') else 0},0,0,100,100,{st.get('spacing') or 0:.2f},0,{border_style},{outline:.2f},0,"
            f"5,0,0,0,1\n"
            f"Style: Mark,{FONT},{42 * out_w / 1080:.0f},&H66FFFFFF,&H00FFFFFF,&H99000000,&HFF000000,1,0,0,0,100,100,1,0,1,2,0,"
            "5,80,80,0,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")


def _libass_width(st):
    """text -> libass width at the style's font, size and spacing (cached; style.libass_width)."""
    from . import style as S
    entry = (st["family"], st.get("bold", 0), st.get("italic", 0))
    cache = {}

    def w(text):
        if text not in cache:
            cache[text] = S.libass_width(entry, text, st["fs"], st.get("spacing") or 0)
        return cache[text]
    return w


def _box_lines(ev, x, cy, pad, lh, box, width, upper):
    """Their solid box, drawn per reveal state around the words shown so far (measured padding)."""
    col = ass_colour(_rgb_hex(box.get("colour"), "#000000"))
    alpha = _ass_alpha(box.get("opacity", 0.85))
    soft = float(box.get("soft_edges") or 0) * 0.25 * lh
    words = [(w["w"].upper() if upper else w["w"]) for w in ev["words"]]
    times = [max(ev["start"], w["t"]) for w in ev["words"]] + [ev["end"]]
    shape = ev.get("lines") or [len(words)]
    out = []
    for i in range(len(words)):
        t0, t1 = times[i], times[i + 1] if i + 1 < len(words) else ev["end"]
        if t1 - t0 <= 0.001:
            continue
        shown, k, rows = words[:i + 1], 0, []
        for n in shape:
            if k >= len(shown):
                break
            rows.append(" ".join(shown[k:k + n]))
            k += n
        bw = max(width(r) for r in rows) + 2 * pad[0]
        bh = len(rows) * lh + (len(rows) - 1) * 0.3 * lh + 2 * pad[1]
        x0, y0 = x - bw / 2, cy - bh / 2
        out.append(f"Dialogue: 0,{ts(t0)},{ts(t1)},C,,0,0,0,,{{\\an7\\pos(0,0)\\bord0\\shad0\\blur{soft:.1f}\\c{col}\\alpha{alpha}\\p1}}"
                   f"m {x0:.0f} {y0:.0f} l {x0 + bw:.0f} {y0:.0f} {x0 + bw:.0f} {y0 + bh:.0f} {x0:.0f} {y0 + bh:.0f}{{\\p0}}")
    return out


def write_ass_style(evs, path, out_w, out_h, st, mark=None, dur=None, width=None):
    """ASS of the caption events in THEIR measured style (style.build): font, size, spacing, colours per word,
    position, outline, shadow, glow, box and how words appear."""
    from pathlib import Path
    llm = st.get("llm") or {}
    anim = st.get("anim") or {"kind": "none"}
    lh = float(st.get("line_h") or 40)
    x, y = (st.get("x") or 0.5) * out_w, None
    lines = []
    if mark and dur:
        lines.append(f"Dialogue: 4,{ts(0)},{ts(dur)},Mark,,0,0,0,,{{\\an5\\pos({out_w / 2:.0f},{0.849 * out_h:.0f})}}{mark}")
    sh, gl = llm.get("shadow") or {}, llm.get("glow") or {}
    box = llm.get("box") or {}
    pad = st.get("box_pad") if box.get("present") else None
    if pad:
        gl = {}            # a glow around a solid box is the box's own edge
    width = width or _libass_width(st)
    outline = float(st.get("outline") or 0)
    pos = st.get("pos") or []
    moves = any(pos)          # style.build keeps per-caption places only when their captions follow the speaker
    for k, ev in enumerate(evs):
        cols = (st.get("colours") or [])[k] if k < len(st.get("colours") or []) else [w["c"] for w in ev["words"]]
        cy = (st.get("y") or ev.get("y", 0.5)) * out_h
        x = (st.get("x") or 0.5) * out_w
        if moves:
            p = next((pos[j] for j in range(min(k, len(pos) - 1), -1, -1) if pos[j]), None)
            if p:
                x, cy = p[0] * out_w, p[1] * out_h
        y = cy - float(st.get("dy") or 0)
        s0, s1 = ts(ev["start"]), ts(ev["end"])
        if pad:
            lines += _box_lines(ev, x, cy, pad, lh, box, width, llm.get("case") == "upper")
        if gl.get("present"):
            gb = max(1.0, float(gl.get("size", 0.25)) * lh)
            lines.append(f"Dialogue: 0,{s0},{s1},C,,0,0,0,,{{\\an5\\pos({x:.0f},{y:.0f})\\bord{outline + gb:.1f}"
                         f"\\blur{gb * 0.7:.1f}\\shad0}}" + _styled_text(ev, cols, anim, "glow", st))
        if sh.get("present"):
            dx, dy = float(sh.get("dx", 0.06)) * lh, float(sh.get("dy", 0.08)) * lh
            bl = float(sh.get("blur", 0.3)) * 0.25 * lh
            lines.append(f"Dialogue: 1,{s0},{s1},C,,0,0,0,,{{\\an5\\pos({x + dx:.0f},{y + dy:.0f})\\bord{outline:.1f}"
                         f"\\blur{bl:.1f}\\shad0}}" + _styled_text(ev, cols, anim, "shadow", st))
        lines.append(f"Dialogue: 2,{s0},{s1},C,,0,0,0,,{{\\an5\\pos({x:.0f},{y:.0f})\\shad0}}"
                     + _styled_text(ev, cols, anim, "main", st))
    Path(path).write_text(style_header(out_w, out_h, st) + "\n".join(lines) + "\n")
    return path
