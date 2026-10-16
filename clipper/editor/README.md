# Editor

**Scope:** candidate → finished Short. Writer step (Gemini: score, 3 hooks, context line, title) → Whisper word captions → face-tracked 9:16 → story captions + context line → ≤60 s → mp4.

**HQ decisions (D5, D7, D8, D15):**
- Every clip gets a context line + setup→payoff captions. No raw re-uploads.
- Hard cap 60 s; flag music segments.
- No speed-up, pitch shift, mirroring or heavy filters.
- Replace `--auto` (Anthropic SDK) with a provider-neutral `llm()` using Gemini 3.1 Flash-Lite (`GEMINI_API_KEY` in `/opt/clipper/.env`).

**Status:** `clip.py` works (download → Whisper → 9:16 blurred bg → hook + 3-word captions → CSV log). Tested on synthetic video only. `--auto` still points at Anthropic (to fix).

**Run:** `python clip.py <url>` then `python clip.py <url> --picks picks.json`

**Next:** Gemini Writer, ≤60 s enforcement, context-line overlay, face-tracked crop (MediaPipe).
