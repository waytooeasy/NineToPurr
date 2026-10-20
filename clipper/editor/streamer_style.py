"""Per-streamer market look (D49, Lucas 2026-10-20: "if the most popping clip right now is using this format
in this context, you use the same stuff").

The global style scout (analyst/style_scout.py) learns one look from the competitor top 20, which is mostly
IShowSpeed (NexxoRecaps). The Shorts that pop about Jynxzi, CaseOh, Lacy, xQc look different: 2026-10-20 they
mostly use a condensed font (Anton/Bebas-like), Lacy/CaseOh/Ice Poseidon a white header box, some no
keyword colour. Daily, for the streamers the market scan ranks highest, this reads the thumbnails (oar2,
public images, never the video) of their most popping English Shorts and asks Claude Haiku (vision) for the
text style of each image; the majority per field (in code, so one odd thumbnail or one odd reply can't
flip the look day to day) -> styles.json; editor/style.py lays it over the global style when rendering that
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
IMAGES = 8
MIN_SEEN = 3
MAX_AGE_H = 24
PROMPT = (
    "These are thumbnails (frames) of today's most popular YouTube Shorts about ONE streamer, made by different "
    "clip channels. Classify EACH image on its own. Answer with a JSON list, one object per image in order: "
    "[{\"captions\": true|false (burned-in caption words of the speech), \"font\": \"condensed\" (tall narrow "
    "heavy, like Anton/Bebas/Impact) | \"geometric\" (wide heavy, like Montserrat Black) | \"rounded\" | "
    "\"other\", \"case\": \"upper\"|\"lower\"|\"title\"|\"as_spoken\", \"fill\": \"#RRGGBB\", "
    "\"highlight\": \"#RRGGBB\" or null (no caption word in another colour), \"words\": <words in the caption "
    "line>, \"position\": \"upper\"|\"middle\"|\"lower\", \"header\": \"white_box\" (a title line in a white box) "
    "| \"text\" (a title line without a box, separate from the captions) | \"none\", \"chat\": \"none\" | "
    "\"stream\" (the streamer's own on-stream chat box is visible) | \"added\" (a chat box the clip channel put "
    "on top), \"actions\": true|false (a caption describing an action in asterisks, like *LOOKS* or *CLOSES DOOR*)}]"
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


def anthropic_vision(images):  # noqa: D103
    import anthropic  # lazy
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": base64.b64encode(b).decode()}} for b in images]
    content.append({"type": "text", "text": PROMPT})
    msg = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=1200, thinking={"type": "disabled"},
                                                messages=[{"role": "user", "content": content}])
    try:
        import llm
        llm.log_usage("anthropic", MODEL, llm._usage_dict(msg.usage))
    except Exception:  # noqa: BLE001
        pass
    return "".join(b.text for b in msg.content if b.type == "text")


def parse(text):
    """Model reply -> list of per-image dicts (a single object is accepted as a one-item list)."""
    m = re.search(r"\[.*\]", text or "", re.S) or re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    d = [d] if isinstance(d, dict) else d
    return [x for x in d if isinstance(x, dict)] if isinstance(d, list) else None


def _majority(values, min_share=0.5):
    """Most common value if it covers more than `min_share` of the votes, else None (no clear market)."""
    vals = [json.dumps(v) for v in values]
    if not vals:
        return None
    best = max(sorted(set(vals)), key=vals.count)
    return json.loads(best) if vals.count(best) / len(vals) > min_share else None


def aggregate(per_image):
    """Majority per field over the images that show captions. Colours: the most common exact value, else
    the field is left out (the global style keeps it). The header needs a majority of ALL images."""
    cap = [x for x in per_image if x.get("captions")]
    out = {"seen": len(cap)}
    for k in ("font", "case", "position"):
        v = _majority([x.get(k) for x in cap])
        if v is not None:
            out[k] = v
    hl = [x.get("highlight") for x in cap]
    if hl and sum(h is None for h in hl) / len(hl) > 0.5:
        out["highlight"] = None                      # most popping clips use no keyword colour
    else:
        v = _majority([h.upper() for h in hl if isinstance(h, str)], 0.0)
        if v:
            out["highlight"] = v
    words = sorted(int(x["words"]) for x in cap if str(x.get("words", "")).isdigit())
    if words:
        out["words"] = words[len(words) // 2]
    chat = _majority([x.get("chat") or "none" for x in per_image], 0.0)
    out["chat"] = chat if chat in ("stream", "added") and [x.get("chat") for x in per_image].count(chat) * 2 \
        > len(per_image) else "none"                 # imitate: only when most popping Shorts show it
    out["actions"] = sum(bool(x.get("actions")) for x in cap) * 2 > len(cap) if cap else False
    head = _majority([x.get("header", "none") for x in per_image], 0.0)
    out["header"] = head if head in ("white_box", "text") and [x.get("header") for x in per_image].count(head) \
        * 2 > len(per_image) else "none"
    return out


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
    try:  # yesterday's looks: a field with no clear majority today keeps yesterday's value (no flip-flop)
        prev = json.loads(Path(out_path or path()).read_text()).get("streamers") or {}
    except (OSError, ValueError, AttributeError):
        prev = {}
    out = {}
    for name, m in ranked:
        ids = [s["id"] for s in m.get("shorts", []) if s.get("en")][:IMAGES + 3]
        try:
            imgs = grab(ids)
            per = parse(vision(imgs)) if len(imgs) >= MIN_SEEN else None
        except Exception as e:  # noqa: BLE001 - one streamer must not stop the rest
            log(f"{name}: {type(e).__name__}")
            continue
        d = aggregate(per or [])
        old = (prev.get(name) or {}).get("caption") or {}
        if d["seen"] < MIN_SEEN:
            if old:
                out[name] = prev[name]                # no clear read today: keep yesterday's look
            continue
        cap = {k: d.get(k) for k in ("font", "case", "fill", "highlight", "outline", "words", "position", "header",
                                     "chat", "actions") if k in d}
        for k, v in old.items():
            cap.setdefault(k, v)
        out[name] = {"logins": sorted(logins.get(name, [])), "caption": cap, "images": len(imgs), "seen": d["seen"]}
    doc = {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "market": market.get("updated", ""), "streamers": out}
    p = Path(out_path or path())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc
