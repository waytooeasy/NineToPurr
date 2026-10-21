"""Caption style the renderer follows, refreshed daily from what the top clip channels do.

The Trend Scout's style step (analyst/style_scout.py) looks at the thumbnails of the day's top
competitor Shorts and writes clipper/formats/style.json on the `trends` branch; run_pipeline copies
it to $CLIPPER_STYLE. Anything missing or invalid falls back to DEFAULT (the 2026-10-19 frame-by-frame
research on NexxoRecaps/StreamBellz). `version()` stamps each render so the Telegram bot can send a
clip back for a re-render when the market style changed after it was made (Lucas, 2026-10-19).

Per streamer (D49, Lucas 2026-10-20: "same as the popping clips in this context"): editor/streamer_style.py
reads the thumbnails of today's popping Shorts about each streamer we may post (market scan) and writes
styles.json ($CLIPPER_STYLES). `load(creator=...)` lays that streamer's style over the global one: font
family (condensed like Anton vs geometric like Montserrat), header (white box / text / none), colours,
words per line, position. 2026-10-20: Jynxzi/Lacy/Stable Ronaldo/Ice Poseidon/xQc clippers use a
condensed font; Lacy/CaseOh/Ice Poseidon a white header box; Speed's (Nexxo) look matches our default.
"""
import hashlib
import json
import os
import re
from pathlib import Path

STYLE_FILE = "/opt/clipper/formats/style.json"
STYLES_FILE = "/opt/clipper/formats/styles.json"      # per streamer (D49)
DEFAULT = {"case": "upper", "fill": "#FFFFFF", "highlight": "#FFE500", "outline": "#000000",
           "words": 2, "position": "middle", "font": "geometric", "header": "none", "highlight_on": True}
CASES = {"upper", "title", "lower", "as_spoken"}
# family -> (ASS font name, caption size). Condensed faces are narrow, so the market sets them bigger.
FONTS = {"geometric": ("Montserrat Black", 100), "condensed": ("Anton", 124),
         "rounded": ("Montserrat Black", 100), "other": ("Montserrat Black", 100)}
HEADERS = {"none", "white_box", "text"}
POSITIONS = {"upper": 760, "middle": 1080, "lower": 1300}   # crop layout; stack uses the seam
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def path():
    return Path(os.environ.get("CLIPPER_STYLE", STYLE_FILE))


def normalize(raw, base=None):
    """Validated caption style: unknown keys dropped, bad values replaced by `base` (default DEFAULT)."""
    cap = (raw or {}).get("caption", raw or {})
    out = dict(base or DEFAULT)
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
    if cap.get("font") in FONTS:
        out["font"] = cap["font"]
    if cap.get("header") in HEADERS:
        out["header"] = cap["header"]
    if "highlight" in cap:                       # the market can say "no keyword colour" (highlight: null)
        out["highlight_on"] = cap["highlight"] is not None
    if out["highlight"] == out["fill"]:          # a highlight nobody can see is no highlight
        out["highlight"] = DEFAULT["highlight"] if out["fill"] != DEFAULT["highlight"] else "#FFFFFF"
    pal = [c.upper() for c in (cap.get("highlights") or []) if isinstance(c, str) and HEX.match(c)]
    pal = [c for i, c in enumerate(pal) if c != out["fill"] and c not in pal[:i]][:4]
    if pal:
        out["highlights"] = pal
    return out


def highlight_for(st, seed):
    """Top channels vary the emphasis colour per clip: pick one from today's palette, stable per clip.
    No keyword colour in this market (highlight_on False) -> the fill colour."""
    if not st.get("highlight_on", True):
        return st["fill"]
    pal = st.get("highlights") or [st["highlight"]]
    return pal[int(hashlib.sha1(str(seed).encode()).hexdigest(), 16) % len(pal)]


def styles_path():
    return Path(os.environ.get("CLIPPER_STYLES", STYLES_FILE))


def _flat(s):
    return re.sub(r"[\W_]+", "", str(s or "").lower())


def streamer_raw(creator, sp=None):
    """The per-streamer style entry (styles.json) for a Radar creator login/slug or streamer name."""
    if not creator:
        return None
    try:
        d = json.loads(Path(sp or styles_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    key = _flat(creator)
    for name, e in (d.get("streamers") or {}).items():
        if key == _flat(name) or key in {_flat(x) for x in e.get("logins") or []}:
            return e
    return None


def market_layout(creator, sp=None):
    """How the top clippers frame this streamer right now (styles.json "layout": full / fit / stack), or None."""
    return (streamer_raw(creator, sp) or {}).get("layout")


def load(p=None, creator=None, sp=None):
    """Global market style (style.json), with this creator's streamer style (styles.json) laid over it."""
    try:
        st = normalize(json.loads(Path(p or path()).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        st = dict(DEFAULT)
    own = streamer_raw(creator, sp)
    if own:
        st = normalize(own, base=st)
        if "highlights" in st and own.get("caption", own).get("highlight") is not None:
            st.pop("highlights", None)           # their own keyword colour, not the global palette
    return st


def version(p=None, creator=None, sp=None):
    """12-char stamp of the style in force for this creator ('default' without any style file)."""
    if not Path(p or path()).exists() and streamer_raw(creator, sp) is None:
        return "default"
    return hashlib.sha1(json.dumps(load(p, creator, sp), sort_keys=True).encode()).hexdigest()[:12]


def font_for(st):
    """(ASS font name, caption size) for the style's font family."""
    return FONTS.get(st.get("font"), FONTS["geometric"])


def ass_color(hex_rgb):
    """#RRGGBB -> ASS &H00BBGGRR&."""
    h = hex_rgb.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def apply_case(text, case):
    return {"upper": text.upper(), "title": text.title(), "lower": text.lower()}.get(case, text)


_INVISIBLE = {0x200D, 0x20E3} | set(range(0xFE00, 0xFE10)) | set(range(0xE0020, 0xE0080))


def onscreen(text):
    """Text that is burned into the video: emoji and other pictographs removed (the caption font has
    no emoji glyphs, they render as boxes; Lucas 2026-10-19: "no emojis in the video texts"). Titles
    keep their emoji; only on-screen text goes through here."""
    import unicodedata
    out = "".join(ch for ch in str(text or "")
                  if ord(ch) not in _INVISIBLE and unicodedata.category(ch) not in ("So", "Sk", "Cs", "Co"))
    return re.sub(r"\s+", " ", out).strip()
