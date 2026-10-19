"""Caption style the renderer follows, refreshed daily from what the top clip channels do.

The Trend Scout's style step (analyst/style_scout.py) looks at the thumbnails of the day's top
competitor Shorts and writes clipper/formats/style.json on the `trends` branch; run_pipeline copies
it to $CLIPPER_STYLE. Anything missing or invalid falls back to DEFAULT (the 2026-10-19 frame-by-frame
research on NexxoRecaps/StreamBellz). `version()` stamps each render so the Telegram bot can send a
clip back for a re-render when the market style changed after it was made (Lucas, 2026-10-19).
"""
import hashlib
import json
import os
import re
from pathlib import Path

STYLE_FILE = "/opt/clipper/formats/style.json"
DEFAULT = {"case": "upper", "fill": "#FFFFFF", "highlight": "#FFE500", "outline": "#000000",
           "words": 2, "position": "middle"}
CASES = {"upper", "title", "lower", "as_spoken"}
POSITIONS = {"upper": 760, "middle": 1080, "lower": 1300}   # crop layout; stack uses the seam
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def path():
    return Path(os.environ.get("CLIPPER_STYLE", STYLE_FILE))


def normalize(raw):
    """Validated caption style: unknown keys dropped, bad values replaced by DEFAULT."""
    cap = (raw or {}).get("caption", raw or {})
    out = dict(DEFAULT)
    if cap.get("case") in CASES:
        out["case"] = cap["case"]
    for k in ("fill", "highlight", "outline"):
        if isinstance(cap.get(k), str) and HEX.match(cap[k]):
            out[k] = cap[k].upper()
    try:
        out["words"] = min(3, max(1, int(cap.get("words", out["words"]))))
    except (TypeError, ValueError):
        pass
    if cap.get("position") in POSITIONS:
        out["position"] = cap["position"]
    if out["highlight"] == out["fill"]:          # a highlight nobody can see is no highlight
        out["highlight"] = DEFAULT["highlight"] if out["fill"] != DEFAULT["highlight"] else "#FFFFFF"
    pal = [c.upper() for c in (cap.get("highlights") or []) if isinstance(c, str) and HEX.match(c)]
    pal = [c for i, c in enumerate(pal) if c != out["fill"] and c not in pal[:i]][:4]
    if pal:
        out["highlights"] = pal
    return out


def highlight_for(st, seed):
    """Top channels vary the emphasis colour per clip: pick one from today's palette, stable per clip."""
    pal = st.get("highlights") or [st["highlight"]]
    return pal[int(hashlib.sha1(str(seed).encode()).hexdigest(), 16) % len(pal)]


def load(p=None):
    try:
        return normalize(json.loads(Path(p or path()).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return dict(DEFAULT)


def version(p=None):
    """12-char stamp of the style in force ('default' without a style file)."""
    return hashlib.sha1(json.dumps(load(p), sort_keys=True).encode()).hexdigest()[:12] \
        if Path(p or path()).exists() else "default"


def ass_color(hex_rgb):
    """#RRGGBB -> ASS &H00BBGGRR&."""
    h = hex_rgb.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def apply_case(text, case):
    return {"upper": text.upper(), "title": text.title(), "lower": text.lower()}.get(case, text)
