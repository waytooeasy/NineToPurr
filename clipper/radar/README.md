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

## Rules in code
- Score = views / hours since `created_at` (age floored at 15 min).
- Dedupe: same `video_id` + overlapping `[vod_offset, vod_offset+duration]`; no VOD offset → same creator + title similarity ≥ 0.8 + `created_at` within 5 min. Best score kept.
- `picks.json`: `[{"start", "end", "source_url", "creator", "clip_id"}]` (D23). `start`/`end` are seconds **inside the file for `source_url`**, max 60 s apart:
  - Twitch: the source is the clip, so `0 → duration`.
  - YouTube: the source is the whole VOD, so `start`/`end` are **VOD-absolute** (`vod_offset → vod_offset+duration`). Same shape, Editor needs no change. `capture.py` downloads the VOD (≤720p) once as `yt_<videoid>.mp4`, shared by all its picks; `radar_candidates.file_path` points at it.
- YouTube rows: `clip_id = yt:<video_id>:<start>`, `url` = VOD URL, `video_id`/`vod_offset`/`duration_s` as for Twitch, so dedupe (same video + overlapping window) is shared. Score = VOD views/hour × replay heat (a proxy; YouTube has no per-moment views). Re-runs reuse a stored row when a shifted heatmap peak overlaps it.
- Moment window: a heatmap/chapter segment >60 s is centred and cut to 60 s; <10 s or outside the video is dropped.

## Run (from `clipper/`)
```
python -m radar.top_clips              # store + print ranked list
python -m radar.top_clips --picks 5    # also write picks.json
python -m radar.top_clips --youtube --picks 5   # Twitch + YouTube VOD moments in one ranking
python -m radar.youtube_vods --picks 3 # YouTube only (needs yt-dlp on PATH, no keys)
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

**Next:** chat spikes (live chat message-rate peaks → extra candidates).
