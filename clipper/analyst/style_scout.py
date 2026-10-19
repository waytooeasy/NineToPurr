"""Style scout: today's caption style of the top competitor Shorts, from their THUMBNAILS only.

Lucas (2026-10-19): "always do a quick recheck of the trending clips format before sending me the
clips, like colors n stuff". Each Trend Scout run looks at the thumbnails (public images, no video
download, D29) of the day's top Shorts, asks Claude for the dominant burned-in caption style and
writes clipper/formats/style.json. The renderer follows it (editor/style.py) and the Telegram bot
re-renders any clip made in an older style before sending it.

Keeps yesterday's style.json when fewer than MIN_SEEN thumbnails show captions.
"""
import base64
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "editor"))
import style as S  # noqa: E402

MODEL = "claude-haiku-5-5"
THUMBS = ("oar2.jpg", "hq720.jpg", "hqdefault.jpg")   # Shorts portrait thumb first
MAX_IMAGES = 8
MIN_SEEN = 3

PROMPT = (
    "These are thumbnails of today's top streamer-clip YouTube Shorts. Look ONLY at the text burned "
    "into the video (captions/subtitles), not YouTube UI, logos or the video title. Report the "
    "dominant style across the images as JSON only:\n"
    '{"seen": <how many images show burned-in captions>, "caption": {"case": "upper|title|lower|'
    'as_spoken", "fill": "#RRGGBB" (main text colour), "highlight": "#RRGGBB" (colour of emphasised '
    'words; same as fill if none), "outline": "#RRGGBB", "words": <1-3 words shown at once>, '
    '"position": "upper|middle|lower", "highlights": ["#RRGGBB", ...] (every emphasis colour you see, '
    'most common first, max 4)}, "layout": "fullbleed|stack|letterbox", "notes": "<=20 words"}\n'
    'If no image shows captions reply {"seen": 0}.')


def thumbnails(ids, session=None, limit=MAX_IMAGES):
    """[(video_id, jpeg bytes)] for the first `limit` ids that have a thumbnail."""
    import requests
    http = session or requests
    out = []
    for vid in ids:
        for name in THUMBS:
            try:
                r = http.get(f"https://i.ytimg.com/vi/{vid}/{name}", timeout=15)
            except Exception:  # noqa: BLE001 - one bad fetch must not stop the scout
                continue
            if getattr(r, "status_code", 0) == 200 and r.content and len(r.content) > 2000:
                out.append((vid, r.content))
                break
        if len(out) >= limit:
            break
    return out


def anthropic_vision(images):
    import anthropic  # lazy
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": base64.b64encode(b).decode()}} for _, b in images]
    content.append({"type": "text", "text": PROMPT})
    # thinking off: with it on, Haiku 5.5 spent all 800 tokens thinking and returned no text (VM test)
    msg = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=800, thinking={"type": "disabled"},
                                                messages=[{"role": "user", "content": content}])
    return "".join(b.text for b in msg.content if b.type == "text")


def parse(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def run(ids, out_path, session=None, vision=anthropic_vision, now=None):
    """Write style.json from today's top Shorts. -> the written dict, or None (kept the old one)."""
    images = thumbnails(ids, session)
    if not images:
        return None
    raw = parse(vision(images))
    if not raw or int(raw.get("seen") or 0) < MIN_SEEN:
        return None
    now = now or datetime.now(timezone.utc)
    doc = {"updated": f"{now:%Y-%m-%d}", "sample": [vid for vid, _ in images], "seen": int(raw["seen"]),
           "caption": S.normalize(raw.get("caption") or {}),
           "layout": raw.get("layout") if raw.get("layout") in ("fullbleed", "stack", "letterbox") else None,
           "notes": str(raw.get("notes") or "")[:200]}
    Path(out_path).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc
