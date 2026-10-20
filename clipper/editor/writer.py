"""Writer: transcript window + creator + Radar metadata -> clip plan (via llm()).

Output keys: score (0-1), in, out (s, out-in <= 60), hooks (3, <=7 words),
context_line (<=12 words), title (<=70 chars, names the streamer, never a copy of a popping title), music_risk.
Prompt lives in prompts/writer.md so the Analyst can tune it.
"""
import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

from llm import llm

PROMPT_FILE = Path(__file__).parent / "prompts" / "writer.md"
MAX_CLIP_S = 60.0
INPUT_MARKER = "=== INPUT ==="
FORMATS_FILE = "/opt/clipper/formats/library.md"  # Trend Scout's library, refreshed by run_pipeline
MARKET_MAX_CHARS = 6000
RUBRIC = {"hook": .30, "coherence": .25, "emotion": .20, "value": .15, "payoff": .10}

SCHEMA = {
    "type": "object",
    "required": ["score", "in", "out", "hooks", "context_line", "title", "music_risk"],
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "in": {"type": "number", "minimum": 0},
        "out": {"type": "number", "minimum": 0},
        "hooks": {"type": "array", "minItems": 3, "maxItems": 3,
                  "items": {"type": "string", "maxLength": 80}},
        "context_line": {"type": "string", "maxLength": 100},
        "title": {"type": "string", "maxLength": 70},
        "music_risk": {"type": "boolean"},
    },
}


def _words(s):
    return len(s.split())


def _flat(s):
    return re.sub(r"[\W_]+", "", str(s or "").lower())


def check(plan, creator="", popping=(), target=None):
    """Semantic limits the schema cannot express. Raises ValueError. `popping`: today's most popping
    titles for this streamer (radar/market.py): ours may follow their style but never copy one."""
    errs = []
    if plan["out"] <= plan["in"]:
        errs.append("out must be after in")
    if plan["out"] - plan["in"] > MAX_CLIP_S:
        errs.append(f"clip longer than {MAX_CLIP_S:.0f}s")
    for h in plan["hooks"]:
        if not h.strip() or _words(h) > 7:
            errs.append(f"hook not 1-7 words: {h!r}")
    if not plan["context_line"].strip() or _words(plan["context_line"]) > 12:
        errs.append("context_line not 1-12 words")
    if creator and _flat(creator) not in _flat(plan["title"]):
        errs.append("title must name the streamer")
    if target and not 0.6 * target <= plan["out"] - plan["in"] <= 1.4 * target:
        errs.append(f"clip should be about {target:.0f}s long, like the top clippers post (now "
                    f"{plan['out'] - plan['in']:.0f}s): pick the best part of that length")
    for p in popping or ():
        if SequenceMatcher(None, _flat(plan["title"]), _flat(p)).ratio() >= 0.9:
            errs.append(f"title copies the popping title {p!r}: paraphrase it with synonyms")
    if errs:
        raise ValueError("; ".join(errs))
    return plan


def format_window(words_or_lines):
    """Accept ready-made '[s-e] text' lines or a list of whisper segments."""
    return words_or_lines if isinstance(words_or_lines, str) else "\n".join(words_or_lines)


def market_section(path=None):
    """Today's format library from the Trend Scout (titles, hook templates, what to avoid), or "".
    Goes into the cached system part: it changes at most daily, so the cache still pays off."""
    p = Path(path or os.environ.get("CLIPPER_FORMATS", FORMATS_FILE))
    try:
        text = p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not text:
        return ""
    return ("=== TODAY'S MARKET (Trend Scout format library: copy what is working) ===\n"
            + text[:MARKET_MAX_CHARS])


def load_prompt(formats=None):
    """Split prompts/writer.md at the INPUT_MARKER line: (static system part, per-clip user
    template). The static part (role, rubric, rules + today's market) is what gets prompt-cached (D31)."""
    text = PROMPT_FILE.read_text(encoding="utf-8")
    system, sep, user = text.partition(INPUT_MARKER)
    if not sep:
        raise ValueError(f"{PROMPT_FILE.name} is missing the {INPUT_MARKER} line")
    market = market_section(formats)
    system = system.strip() + ("\n\n" + market if market else "")
    return system, user.strip()


def write_clip(transcript, creator, meta=None, clip_id=None):
    """One LLM call -> validated plan. Retries once if the plan breaks the
    semantic limits; the second failure raises ValueError."""
    system, user = load_prompt()
    prompt = user.format(creator=creator, meta=json.dumps(meta or {}, ensure_ascii=False),
                         transcript=format_window(transcript))
    popping = [p["title"] if isinstance(p, dict) else str(p) for p in (meta or {}).get("popping_now") or []]
    target = (meta or {}).get("target_len_s")
    plan = llm(prompt, SCHEMA, system=system, clip_id=clip_id)
    try:
        return check(plan, creator, popping, target)
    except ValueError as e:
        plan = llm(prompt + f"\n\nYour previous answer broke the rules: {e}. Fix them.", SCHEMA,
                   system=system, clip_id=clip_id)
        try:
            return check(plan, creator, popping, target)
        except ValueError:
            if not target:
                raise
            return check(plan, creator, popping)   # length is enforced by clip.length_window anyway
