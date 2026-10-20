"""Per-streamer market look (D49, Lucas 2026-10-20: "if the most popping clip right now is using this format
in this context, you use the same stuff").

The global style scout (analyst/style_scout.py) learns one look from the competitor top 20, which is mostly
IShowSpeed (NexxoRecaps). The Shorts that pop about Jynxzi, CaseOh, Lacy, xQc look different: 2026-10-20 they
mostly use a condensed font (Anton/Bebas-like), Lacy/CaseOh/Ice Poseidon a white header box, some no
keyword colour. Daily, for the streamers the market scan ranks highest, this reads the thumbnails (oar2,
public images, never the video) of their most popping English Shorts and asks Claude Haiku (vision) for the
dominant text style -> styles.json; editor/style.py lays it over the global style when rendering that
streamer's clips. Needs >= MIN_SEEN captioned images, else that streamer keeps the global look.
"""
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

MODEL = "claude-haiku-5-5"
TOP_STREAMERS = 10
IMAGES = 5
MIN_SEEN = 3
MAX_AGE_H = 24
PROMPT = (
    "These are thumbnails (frames) of today's most popular YouTube Shorts about ONE streamer, made by different "
    "clip channels. Describe the dominant burned-in text style as JSON only: {\"seen\": <number of images with "
    "burned-in captions>, \"font\": \"condensed\" (tall narrow heavy, like Anton/Bebas/Impact) | \"geometric\" "
    "(wide heavy, like Montserrat Black) | \"rounded\" | \"other\", \"case\": \"upper\"|\"lower\"|\"title\"|"
    "\"as_spoken\", \"fill\": \"#RRGGBB\", \"highlight\": \"#RRGGBB\" or null (no word in another colour), "
    "\"outline\": \"#RRGGBB\" or null, \"words\": <typical words per caption line>, \"position\": \"upper\"|"
    "\"middle\"|\"lower\", \"header\": \"white_box\" (a title line in a white box that stays on screen) | \"text\" "
    "(a title line without a box that stays on screen) | \"none\"}"
)


def log(msg):
    print(f"[styles] {msg}", file=sys.stderr)


def path():
    return Path(os.environ.get("CLIPPER_STYLES", "/opt/clipper/formats/styles.json"))


def thumbnails(ids, session=None, limit=IMAGES):
    import requests
    http = session or requests
    out = []
    for vid in ids:
        r = http.get(f"https://i.ytimg.com/vi/{vid}/oar2.jpg", timeout=15)
        if getattr(r, "ok", False) and len(r.content) > 3000:
            out.append(r.content)
        if len(out) == limit:
            break
    return out


def anthropic_vision(images):
    import anthropic  # lazy
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": base64.b64encode(b).decode()}} for b in images]
    content.append({"type": "text", "text": PROMPT})
    msg = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=400, thinking={"type": "disabled"},
                                                messages=[{"role": "user", "content": content}])
    try:
        import llm
        llm.log_usage("anthropic", MODEL, llm._usage_dict(msg.usage))
    except Exception:  # noqa: BLE001
        pass
    return "".join(b.text for b in msg.content if b.type == "text")


def parse(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def due(p=None, market_updated=None, now=None):
    """Re-run once a day, or when a newer market scan exists."""
    try:
        d = json.loads(Path(p or path()).read_text())
        t = datetime.fromisoformat(d["updated"].replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError, TypeError):
        return True
    now = now or datetime.now(timezone.utc)
    if market_updated and market_updated > d.get("market", ""):
        return True
    return (now - t).total_seconds() > MAX_AGE_H * 3600


def run(market, logins, out_path=None, vision=None, grab=thumbnails, now=None, top=TOP_STREAMERS):
    """styles.json for the `top` streamers by Shorts demand. `logins`: {streamer: [radar logins/slugs]}."""
    now = now or datetime.now(timezone.utc)
    vision = vision or anthropic_vision
    ranked = sorted(market["streamers"].items(), key=lambda kv: -kv[1].get("demand_vph", 0))[:top]
    out = {}
    for name, m in ranked:
        ids = [s["id"] for s in m.get("shorts", []) if s.get("en")][:IMAGES + 3]
        try:
            imgs = grab(ids)
            d = parse(vision(imgs)) if len(imgs) >= MIN_SEEN else None
        except Exception as e:  # noqa: BLE001 - one streamer must not stop the rest
            log(f"{name}: {type(e).__name__}")
            continue
        if not d or int(d.get("seen") or 0) < MIN_SEEN:
            continue
        cap = {k: d.get(k) for k in ("font", "case", "fill", "highlight", "outline", "words", "position", "header")
               if k in d}
        out[name] = {"logins": sorted(logins.get(name, [])), "caption": cap, "images": len(imgs)}
    doc = {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "market": market.get("updated", ""), "streamers": out}
    p = Path(out_path or path())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc
