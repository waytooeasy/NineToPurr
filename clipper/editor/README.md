# Editor

**Scope:** candidate → finished Short. Writer step (Claude Haiku: score, 3 hooks, context line, title) → Whisper word captions → face-tracked 9:16 → story captions + context line → ≤60 s → mp4.

**HQ decisions (D7, D8, D15, D18):**
- Every clip gets a context line + setup→payoff captions. No raw re-uploads.
- Hard cap 60 s; flag music segments.
- No speed-up, pitch shift, mirroring or heavy filters.
- Writer = provider-neutral `llm()` defaulting to Claude Haiku 5.5 (`ANTHROPIC_API_KEY` in `/opt/clipper/.env`); Gemini as fallback.

**Status:** `clip.py` works (download → Whisper → 9:16 blurred bg → hook + 3-word captions → CSV log). Tested on synthetic video only. `--auto` calls Anthropic directly; move it behind `llm()` with Haiku as default.

**Run:** `python clip.py <url>` then `python clip.py <url> --picks picks.json`

**Next:** Haiku Writer (`writer.py` + `llm.py`), ≤60 s enforcement, context-line overlay, face-tracked crop (MediaPipe).
