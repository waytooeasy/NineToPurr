# Editor

**Scope:** candidate → finished Short. Writer step (Claude Haiku: score, 3 hooks, context line, title) → Whisper word captions → 9:16 → story captions + context line → ≤60 s → mp4.

**HQ decisions (D7, D8, D15, D18):**
- Every clip gets a context line + setup→payoff captions. No raw re-uploads.
- Hard cap 60 s; flag music segments.
- **Market style:** the Writer's cached system prompt includes the Trend Scout format library (`$CLIPPER_FORMATS`, default `/opt/clipper/formats/library.md`; `run_pipeline.refresh_formats()` copies it from the `trends` branch every ≤6 h). Titles and hooks follow what is working that day.
- **Market window:** a Radar pick keeps the length viewers chose (popular Twitch clip / most-replayed YouTube part). The Writer may only trim dead air, max 2 s per end (`market_window()`, `MAX_TRIM_S`). No fixed minimum length.
- No speed-up, pitch shift, mirroring or heavy filters.
- Writer = provider-neutral `llm()` defaulting to Claude Haiku 5.5 (`ANTHROPIC_API_KEY` in `/opt/clipper/.env`); Gemini as fallback.

## Files
| File | What |
|---|---|
| `llm.py` | `llm(prompt, schema) -> dict`. Anthropic `claude-haiku-5-5` by default (`CLAUDE_MODEL` overrides); `LLM_PROVIDER=gemini` uses Gemini (`GEMINI_API_KEY`, `GEMINI_MODEL`). Output is validated against the schema; one retry on invalid JSON. SDK/HTTP imported lazily. **D31:** `llm(prompt, schema, system=None, clip_id=None)` sends `system` as a `cache_control: ephemeral` block (prompt cache); `llm_batch(items, schema, system=None)` runs `[{id, prompt}]` through the Message Batches API (50% cheaper, Anthropic only), polls, returns `{id: dict or None}` (no retry; resubmit the `None` ids). Every call/batch item inserts a row into `llm_usage` (migration 006: input/output/cache-creation/cache-read tokens, `kind` call/batch) when `$CLIPPER_DB` exists; logging never raises. |
| `writer.py` | `write_clip(transcript_window, creator, meta) -> dict`: `score` (0–1), `in`/`out` (≤60 s), 3 `hooks` (≤7 words), `context_line` (≤12 words), `title` (≤70 chars, names the streamer), `music_risk`. Retries once if limits are broken, then raises. |
| `prompts/writer.md` | Writer prompt + score rubric. Everything above the `=== INPUT ===` line is the cached system prompt; per-clip data goes below it only. (hook .30, coherence .25, emotion .20, value .15, payoff .10). Edit here, no code change. |
| `qc.py` | QC v1 (D27): `edited → qc_passed` if the file is ≤60 s (ffprobe), its sha256 is not already in the library (`clips.file_hash`), and fewer than 5 clips passed today (UTC). Otherwise sets `last_error` and leaves the state. `music_risk` passes and stays on the row for the Telegram flag. |
| `rerender.py` | `needs_rerender → qc_passed`: re-cuts the captured source with the new `hook_text` (same start/end + context line; YouTube VOD windows shifted by `capture.section` offset, same as `run_pipeline._picks(file_relative=True)`), replaces the Short in place, refreshes `file_hash`, clears `approval_sent_at`. |
| `clip.py` | Download → Whisper → (`--auto`: Writer on 120 s transcript windows, best N non-overlapping) → render → CSV log. |

## Status
- `--auto` now uses `writer.py` (no direct Anthropic call). Needs `--creator "Kai Cenat"`; `--meta '<json>'` passes Radar metadata.
- `cap_pick()` enforces ≤60 s on every pick (also `--picks` files) and `render()` cuts with `-t`.
- Context line drawn under the hook (first 8 s); word captions unchanged.
- Radar picks (D23): `python clip.py --picks picks.json --auto` reads `source_url` per pick (uses the captured file when the DB has one), runs the Writer on the transcript inside `start`/`end`, renders. `src` is optional in this mode.
- DB (D24, D22): if `$CLIPPER_DB` (default `/opt/clipper/db/clip.db`) exists and has a `clips` row for the pick, the Writer output (`model_score`, `context_line`, `hooks_json`, `hook_text`, `title`, `music_risk`) is written and the state goes `captured → drafted`; after render `edited` + `file_path`. No DB file → DB writes skipped. A failing pick sets `clips.last_error` and the run continues.
- `clips_log.csv` is now a debug log only; it gains `hook_variant`, `context_line`, `title`, `score`, `music_risk` (old logs are migrated in place).
- Tested on synthetic video only. `--lang es` no longer auto-translates (the old pick prompt did); Spanish captions need `es_words` in a picks file.
- `music_risk` is stored on the row; QC passes it. The Telegram message should show it (publisher change, not done here).
- QC + re-render (D27) are driven by `clipper/run_pipeline.py` (radar → capture → editor → qc → rerender, flock-locked, safe every 20 min). A failed capture/editor/re-render step sets `last_error` and is retried after 2 h.
- Duplicate check = exact file hash. Perceptual hash is not built yet (re-renders with a different hook hash differently).
- Work dirs now live under `$CLIPPER_WORK/<clip_id>/` (default `work/` when unset).

- D31: Writer prompt split into cached system part + per-clip input; `write_clip(..., clip_id=)` tags `llm_usage` rows. Models only cache prompts above a minimum length and the current Writer prompt is short, so `cache_read_tokens` may stay 0 until the rubric/examples grow; `llm_usage` will show it.
- `draft_pick(..., clip_id=)` passes `clips.id` to the Writer, so Radar picks get `llm_usage.clip_id`. Window scoring in `writer_picks` (no `clips` row yet) stays NULL.
- `log_usage` warns (logger `llm`) instead of staying silent if `llm_usage` is missing. **Deploy: run `db/migrate.py` first** (migration 006). It connects with `timeout=30`, like `run_pipeline.py`.
- `llm_batch` is not called by any pipeline step yet (the re-scoring job is a follow-up). Usage rows are `kind='batch'`; the Analyst applies the 50% rate.

## Run
```
python clip.py <url>                                   # download + transcribe
python clip.py <url> --picks picks.json                # render chosen picks
python clip.py <url> --auto -n 5 --creator "Kai Cenat" # Writer picks + renders
```
Tests (offline, LLM mocked, no key needed; render test needs ffmpeg and takes ~2 min): `pytest clipper/editor`

## Next
Face-tracked crop (MediaPipe), hook A/B selection (`hook_variant`), perceptual-hash duplicate check.
