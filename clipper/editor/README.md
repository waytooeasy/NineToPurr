# Editor

**Scope:** candidate → finished Short. Writer step (Claude Haiku: score, 3 hooks, context line, title) → Whisper word captions → 9:16 → story captions + context line → ≤60 s → mp4.

**HQ decisions (D7, D8, D15, D18):**
- Every clip gets a context line + setup→payoff captions. No raw re-uploads.
- Hard cap 60 s; flag music segments.
- No speed-up, pitch shift, mirroring or heavy filters.
- Writer = provider-neutral `llm()` defaulting to Claude Haiku 5.5 (`ANTHROPIC_API_KEY` in `/opt/clipper/.env`); Gemini as fallback.

## Files
| File | What |
|---|---|
| `llm.py` | `llm(prompt, schema) -> dict`. Anthropic `claude-haiku-5-5` by default (`CLAUDE_MODEL` overrides); `LLM_PROVIDER=gemini` uses Gemini (`GEMINI_API_KEY`, `GEMINI_MODEL`). Output is validated against the schema; one retry on invalid JSON. SDK/HTTP imported lazily. |
| `writer.py` | `write_clip(transcript_window, creator, meta) -> dict`: `score` (0–1), `in`/`out` (≤60 s), 3 `hooks` (≤7 words), `context_line` (≤12 words), `title` (≤70 chars, names the streamer), `music_risk`. Retries once if limits are broken, then raises. |
| `prompts/writer.md` | Writer prompt + score rubric (hook .30, coherence .25, emotion .20, value .15, payoff .10). Edit here, no code change. |
| `clip.py` | Download → Whisper → (`--auto`: Writer on 120 s transcript windows, best N non-overlapping) → render → CSV log. |

## Status
- `--auto` now uses `writer.py` (no direct Anthropic call). Needs `--creator "Kai Cenat"`; `--meta '<json>'` passes Radar metadata.
- `cap_pick()` enforces ≤60 s on every pick (also `--picks` files) and `render()` cuts with `-t`.
- Context line drawn under the hook (first 8 s); word captions unchanged.
- Radar picks (D23): `python clip.py --picks picks.json --auto` reads `source_url` per pick (uses the captured file when the DB has one), runs the Writer on the transcript inside `start`/`end`, renders. `src` is optional in this mode.
- DB (D24, D22): if `$CLIPPER_DB` (default `/opt/clipper/db/clip.db`) exists and has a `clips` row for the pick, the Writer output (`model_score`, `context_line`, `hooks_json`, `hook_text`, `title`, `music_risk`) is written and the state goes `captured → drafted`; after render `edited` + `file_path`. No DB file → DB writes skipped. A failing pick sets `clips.last_error` and the run continues.
- `clips_log.csv` is now a debug log only; it gains `hook_variant`, `context_line`, `title`, `score`, `music_risk` (old logs are migrated in place).
- Tested on synthetic video only. `--lang es` no longer auto-translates (the old pick prompt did); Spanish captions need `es_words` in a picks file.
- `music_risk` is logged but not yet acted on (QC step).

## Run
```
python clip.py <url>                                   # download + transcribe
python clip.py <url> --picks picks.json                # render chosen picks
python clip.py <url> --auto -n 5 --creator "Kai Cenat" # Writer picks + renders
```
Tests (offline, LLM mocked, no key needed; render test needs ffmpeg and takes ~2 min): `pytest clipper/editor`

## Next
Face-tracked crop (MediaPipe), hook A/B selection (`hook_variant`), QC rules using `music_risk`.
