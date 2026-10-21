"""Our title for a remake (D58): the same moment and hook as the clipper's title, in our own words (never theirs)."""
import difflib
import re

MODEL = "claude-haiku-5-5"
MAX_LEN = 70
TOO_CLOSE = 0.8

PROMPT = """You write YouTube Shorts titles for a streamer-clips channel.
A clipper's Short of this moment is popping right now. Their title: "{title}"
Whose stream the footage is from: {streamer}. What happens (their captions): {captions}

Write OUR title for the same clip: the same moment and the same hook, with the people named exactly as their title
names them (nicknames included; never add a name their title does not use), at most {max_len} characters, English, same tone. If they use emojis, use at most two. Do NOT copy their
wording: reorder, swap words, say it your own way. No hashtags, no quotes, nothing the clip does not show.
{extra}Reply with the title only."""


def anthropic_ask(prompt):
    import anthropic  # lazy
    msg = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=120, thinking={"type": "disabled"},
                                                messages=[{"role": "user", "content": prompt}])
    try:
        import llm
        llm.log_usage("anthropic", MODEL, llm._usage_dict(msg.usage))
    except Exception:  # noqa: BLE001
        pass
    return "".join(b.text for b in msg.content if b.type == "text")


def _norm(t):
    return re.sub(r"[^a-z0-9 ]", "", (t or "").lower()).strip()


def too_close(ours, theirs):
    return difflib.SequenceMatcher(None, _norm(ours), _norm(theirs)).ratio() >= TOO_CLOSE


def clean(t):
    t = (t or "").strip().splitlines()[0] if (t or "").strip() else ""
    t = t.strip().strip('"').strip("'").strip()
    t = re.sub(r"\s#\w+", "", t).strip()
    return t[:MAX_LEN].rstrip()


def wrong_names(t, theirs, streamer, names=()):
    """Streamer names in our title that are neither in their title nor the stream's owner (a Kai Cenat title on
    an Agent00 clip, 2026-10-21)."""
    low, th = t.lower(), theirs.lower()
    return [n for n in names if n and re.search(r"\b" + re.escape(n.lower()) + r"\b", low)
            and not re.search(r"\b" + re.escape(n.lower()) + r"\b", th) and n.lower() != (streamer or "").lower()]


def make(theirs, streamer, captions="", ask=anthropic_ask, names=()):
    extra = ""
    best = ""
    for _ in range(3):
        t = clean(ask(PROMPT.format(title=theirs, streamer=streamer, captions=captions or "-", max_len=MAX_LEN,
                                    extra=extra)))
        bad = wrong_names(t, theirs, streamer, names) if t else []
        if t and not too_close(t, theirs) and not bad:
            return t
        if not bad:
            best = best or t
        extra = (f'Your last try "{t}" named {", ".join(bad)}, who is not in this clip. ' if bad else
                 f'Your last try "{t}" was too close to theirs: change the wording more. ')
    return best if best and not too_close(best, theirs) else theirs[:MAX_LEN]
