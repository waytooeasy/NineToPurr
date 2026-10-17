# Radar

**Scope:** find moments worth clipping and hand them to the Editor as `picks.json`. Radar does not write hooks/titles (Editor's Writer does).

**HQ decisions (D13, D14):** Twitch Get Clips first (chat spikes later); creators from config; rank by views/hour; dedupe by VOD + overlapping offset; widen to 7 days when thin; table `radar_candidates` via `../db/migrations/002_radar.sql`.

**Status:** v1 built; YouTube live-VOD source added (issue #19, D29). `pytest clipper/radar` passes offline (saved responses in `tests/fixtures/`).

## Files
- `config/creators.yaml` — per creator: a plain Twitch login, or `{twitch: kaicenat, youtube_channel: "@KaiCenat"}` to also pull that channel's livestream VODs.
- `youtube_vods.py` — yt-dlp metadata only (no API key): `<channel>/streams` → per-video JSON → moments from the `heatmap` ("most replayed", segments with value ≥ 0.5, top 3 per VOD), else `chapters` (weak score), else nothing → `radar_candidates` rows with `source='youtube'` (migration `007_radar_source.sql`). Skips `/shorts/` URLs, videos not from the configured channel, and non-live uploads / still-live streams. VODs from the last 7 days.
- `twitch.py` — app token (client credentials, cached in `/opt/clipper/twitch_token.json`), login → broadcaster id, paginated Get Clips.
- `top_clips.py` — last 24 h per creator (7 days if < N candidates after dedupe) → score → dedupe → `radar_candidates` → ranked list → `--picks N` writes `picks.json`.
- `capture.py` — yt-dlp download of picked clips into `$CLIPPER_WORK`; marks rows `captured` and the linked `clips` row `captured` + `file_path`.
- `top_clips.register_clips` — with `--picks N`, the chosen candidates become `clips` rows with `state='found'`, linked via `radar_candidates.clips_id` (D22). Idempotent.

## Heat Index (issue #33, D33)
Decides *which streamers* get today's Shorts slots; Radar then ranks moments only inside them.
- `config/watchlist.yaml` — ~30 English streamers, each entry `{name, platform, id}` (`twitch` | `youtube` | `kick`; Kick is `disabled: true`, no source yet). Also `daily_cap` (5), `max_per_streamer` (2), `explore_days` (3), `explore_top_n` (15). Add/remove a line, no code. Twitch logins are best guesses.
- `heat.py` — per streamer (entries with the same name are summed): **D** = views on clips created in the last 24 h (Twitch Get Clips; YouTube: views of own live VODs from the last 24 h), **W** = same over 7 d, **B** = W/7, **momentum** = (D+1)/(B+1), `live_now` (Twitch Get Streams / YouTube `/live`), **saturation** = competitor Shorts about the streamer in 24 h (Trend Scout), else 0.
  - `heat = ln(1+D) * (1 + 0.5*log2(momentum)) + 0.3*ln(1+B) + 1.0*live_now` (natural log; momentum factor floored at 0.1 so a collapsing streamer is never negative)
  - `opportunity = heat / (1 + 0.1*saturation)`
  - Slots (`allocate`, seedable rng): 1 exploration slot to a random top-15 streamer not posted in 3 days (from `posts` -> `clips` -> `sources` -> `creators`; never-posted counts), the remaining slots proportional to opportunity (D'Hondt), max 2 per streamer, total = cap. No eligible explorer -> that slot goes proportional.
  - Writes `streamer_heat` (migration `008_streamer_heat.sql`), one row per streamer per run.
- `top_clips.py` hook: `collect(..., allowed=[...])` / `filter_allowed`, `apply_allocation(cands, slots, ids)`; CLI `--allocation allocation.json` ranks only allocated streamers and keeps at most `slots` moments per streamer. Without the flag nothing changes.
- Saturation input: `CLIPPER_SATURATION` = JSON `{"Kai Cenat": 7}` (competitor Shorts in 24 h). Missing -> 0.

## Pipeline wiring (issue #47, `run_pipeline.py` radar step)
Every 20-min pass (D22): `radar_step` = **Heat slots → moments → picks**.
- `heat_allocation` re-measures the Heat Index at most every 30 min (`HEAT_REFRESH_MIN`); in between it re-allocates from the latest `streamer_heat` snapshot. Exploration slot is seeded per day, so it stays stable. Slots already used today (clips started, not killed) are subtracted per streamer.
- Per allocated creator: Twitch top clips (`top_clips.collect(allowed=...)`) **and** YouTube VOD most-replayed windows (`youtube_vods.collect`, creators with `youtube_channel`), merged and ranked by score; `apply_allocation` keeps the best `slots` per streamer, then the 5/day cap (`qc.DAILY_CAP`) trims the total. Already-registered moments are skipped before slots are applied.
- Heat unavailable (error) → logged, falls back to ranking all creators; the cap still holds. A yt-dlp failure keeps the Twitch picks.
- `_picks` reads `clips.start_s/end_s` (set by `pick_window`, D23): Twitch `0 → duration`, YouTube VOD-absolute. `capture_step` gets those as is; `editor_step` gets YouTube picks shifted into the downloaded window file (`start - capture.section(pick)[0]`), same as `python -m radar.capture` does for `picks.json`. Previously every pick was `0 → duration`, wrong for VOD moments.
- Tests: `radar/tests/test_pipeline_radar.py` (fake Twitch, fake yt-dlp, fake Heat fetchers).
- Needs `creators.yaml` logins to match the watchlist (`ids` map in the allocation); a creator not in the watchlist gets no slot while Heat is on.

## Rules in code
- Score = views / hours since `created_at` (age floored at 15 min).
- Dedupe: same `video_id` + overlapping `[vod_offset, vod_offset+duration]`; no VOD offset → same creator + title similarity ≥ 0.8 + `created_at` within 5 min. Best score kept.
- `picks.json`: `[{"start", "end", "source_url", "creator", "clip_id"}]` (D23). `start`/`end` are seconds **inside the file for `source_url`**, max 60 s apart:
  - Twitch: the source is the clip, so `0 → duration`.
  - YouTube: the source is the whole VOD, so `start`/`end` are **VOD-absolute** (`vod_offset → vod_offset+duration`). `clips.start_s/end_s` and `picks.json` from `youtube_vods` stay VOD-absolute. `capture.py` downloads only each pick's window (`--download-sections "*start-end"`, ±3 s padding, ≤720p, 150 MB cap) as `yt_<videoid>_<s>_<e>.mp4` via a temp file that is removed on failure; `radar_candidates.file_path` points at it. The file starts at the padded start, so `python -m radar.capture` rewrites `picks.json` `start`/`end` file-relative for the Editor. A YouTube URL with no video id raises `ValueError`.
  - **Needs HQ:** `editor/rerender.py` cuts `source_file` using the absolute `clips.start_s/end_s`, which is wrong for YouTube window files (offset = `start - padded start`). Contract change, not made here.
- YouTube rows: `clip_id = yt:<video_id>:<start>`, `url` = VOD URL, `video_id`/`vod_offset`/`duration_s` as for Twitch, so dedupe (same video + overlapping window) is shared. Score = VOD views/hour × replay heat (a proxy; YouTube has no per-moment views). Re-runs reuse a stored row when a shifted heatmap peak overlaps it.
- Moment window: a heatmap/chapter segment >60 s is centred and cut to 60 s; <10 s or outside the video is dropped.

## Run (from `clipper/`)
```
python -m radar.top_clips              # store + print ranked list
python -m radar.top_clips --picks 5    # also write picks.json
python -m radar.top_clips --youtube --picks 5   # Twitch + YouTube VOD moments in one ranking
python -m radar.youtube_vods --picks 3 # YouTube only (needs yt-dlp on PATH, no keys)
python -m radar.heat --allocation allocation.json   # Heat Index + today's slots (every 30 min)
python -m radar.top_clips --allocation allocation.json --picks 5   # moments only for allocated streamers
python -m radar.capture picks.json     # download picks
pytest radar
```
| Env | Meaning |
|---|---|
| `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` | from `/opt/clipper/.env` (never in git) |
| `CLIPPER_DB` | default `/opt/clipper/db/clip.db` |
| `CLIPPER_WORK` | default `/opt/clipper/work` |

The DB is built by `python db/migrate.py` (needs 002 + 004 + 007).

**Needs:** Twitch app (dev.twitch.tv/console, 2FA, redirect `http://localhost`).

**Infra:** proposed `infra/systemd/clipper-radar.{service,timer}` (every 20 min). Assumes repo at `/opt/clipper/repo`; adjust `WorkingDirectory` if different.

**Editor** now reads `source_url` per pick (D23) and moves the `clips` row on (see `../db/README.md`). Open: `creators.name` is the Twitch login, which may duplicate a hand-made display-name row.

**Open:** YouTube picks make the Editor work from a multi-hour VOD file (large download, seeks by VOD-absolute time); a section download (`--download-sections`) would be lighter but changes the start/end contract. Heatmap segments are ~1% of the VOD, so the 60 s window is centred on the segment, not on the exact peak.

**Needs HQ (issue #33):**
- Trend Scout does not persist per-streamer Shorts counts (`leaderboard_24h` is only in its in-memory summary). `heat.py` reads `CLIPPER_SATURATION` JSON; the analyst should write `{streamer: shorts_24h}` next to `creators_ranking.json`, or HQ confirms another hand-off. Until then saturation = 0.
- No systemd unit for `radar.heat` yet (`.github/` and infra timer every 30 min not added; `top_clips` should read the latest `allocation.json`).
- Heat constants (live bonus 1.0, momentum floor 0.1) are my choice; D33 gives only the shape.
- Watchlist Twitch logins are unverified guesses; `creators.yaml` (what `top_clips` actually pulls) is not yet derived from the watchlist.

**Needs HQ (issue #47):** `editor/rerender.py` still cuts YouTube window files with the absolute `clips.start_s/end_s` (see the earlier note); `run_pipeline` now feeds the Editor file-relative times but the DB keeps absolute ones. Contract change, not made here.

**Next:** saturation hand-off (the pipeline now runs the Heat allocation itself); chat spikes (live chat message-rate peaks → extra candidates).
