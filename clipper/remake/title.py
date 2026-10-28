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

FRESH = """You write YouTube Shorts titles for a streamer-clips channel.
Whose stream the footage is from: {streamer}. What happens in the clip (captions): {captions}
Write a punchy title for this clip, at most {max_len} characters, English, at most one emoji. Name only {streamer} if you
name anyone. No hashtags, no quotes, nothing the clip does not show. Reply with the title only."""

# last resort when the model keeps echoing theirs: ours, never theirs (2026-10-28, clip 33 went out as "What A Surprise 😭")
FALLBACKS = ("{s} Was Not Ready For This 😭", "{s} Can't Believe What Just Happened", "This Caught {s} Off Guard 😭",
             "{s}'s Reaction Says It All", "Nobody Expected This From {s} 😭")


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


REFUSAL = ("i can't", "i cannot", "i can not", "i'm not able", "i won't", "as framed", "i'd rather not")


def refused(t):
    """The model answered about the request instead of writing a title."""
    low = (t or "").lower()
    return any(r in low for r in REFUSAL)


def make(theirs, streamer, captions="", ask=anthropic_ask, names=()):
    extra = ""
    best = ""
    for _ in range(3):
        t = clean(ask(PROMPT.format(title=theirs, streamer=streamer, captions=captions or "-", max_len=MAX_LEN,
                                    extra=extra)))
        if refused(t):
            t = ""
        bad = wrong_names(t, theirs, streamer, names) if t else []
        if t and not too_close(t, theirs) and not bad:
            return t
        if not bad:
            best = best or t
        extra = (f'Your last try "{t}" named {", ".join(bad)}, who is not in this clip. ' if bad else
                 f'Your last try "{t}" was too close to theirs: change the wording more. ')
    if best and not too_close(best, theirs):
        return best
    # A short title ("What A Surprise 😭") has few words to reword: every try stayed too close. Write one from the
    # clip itself without showing theirs, then a fixed one with the streamer's name. Never their title.
    t = clean(ask(FRESH.format(streamer=streamer, captions=captions or "-", max_len=MAX_LEN)))
    if t and not refused(t) and not too_close(t, theirs) and not wrong_names(t, theirs, streamer, names):
        return t
    for f in FALLBACKS[sum(map(ord, theirs)) % len(FALLBACKS):] + FALLBACKS:
        t = f.format(s=streamer or "Streamer")[:MAX_LEN]
        if not too_close(t, theirs):
            return t
    return f"{streamer or 'Streamer'} Clip"[:MAX_LEN]
