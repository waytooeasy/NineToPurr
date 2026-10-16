# Radar

**Scope:** find moments worth clipping and hand them to the Editor as `picks.json`. Radar does not write hooks/titles (Editor's Writer does).

**HQ decisions (D13, D14):** Twitch Get Clips first (chat spikes later); creators from config; rank by views/hour; dedupe by VOD + overlapping offset; widen to 7 days when thin; table `radar_candidates` via `../db/migrations/002_radar.sql`.

**Status:** v1 built. `pytest clipper/radar` passes offline (saved responses in `tests/fixtures/`).

## Files
- `config/creators.yaml` — Twitch logins (`kaicenat`); add a line to add a streamer.
- `twitch.py` — app token (client credentials, cached in `/opt/clipper/twitch_token.json`), login → broadcaster id, paginated Get Clips.
- `top_clips.py` — last 24 h per creator (7 days if < N candidates after dedupe) → score → dedupe → `radar_candidates` → ranked list → `--picks N` writes `picks.json`.
- `capture.py` — yt-dlp download of picked clips into `$CLIPPER_WORK`; marks rows `captured`.

## Rules in code
- Score = views / hours since `created_at` (age floored at 15 min).
- Dedupe: same `video_id` + overlapping `[vod_offset, vod_offset+duration]`; no VOD offset → same creator + title similarity ≥ 0.8 + `created_at` within 5 min. Best score kept.
- `picks.json`: `[{"start", "end", "source_url", "creator", "clip_id"}]`. `start`/`end` are seconds **inside the downloaded Twitch clip** (0 → duration, capped 60 s), since `source_url` is the clip, not the VOD.

## Run (from `clipper/`)
```
python -m radar.top_clips              # store + print ranked list
python -m radar.top_clips --picks 5    # also write picks.json
python -m radar.capture picks.json     # download picks
pytest radar
```
| Env | Meaning |
|---|---|
| `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` | from `/opt/clipper/.env` (never in git) |
| `CLIPPER_DB` | default `/opt/clipper/db/clip.db` |
| `CLIPPER_WORK` | default `/opt/clipper/work` |

The DB needs `002_radar.sql` applied: `sqlite3 /opt/clipper/db/clip.db < db/migrations/002_radar.sql`.

**Needs:** Twitch app (dev.twitch.tv/console, 2FA, redirect `http://localhost`).

**Infra:** proposed `infra/systemd/clipper-radar.{service,timer}` (every 20 min). Assumes repo at `/opt/clipper/repo`; adjust `WorkingDirectory` if different.

**Open note for HQ/Editor:** Editor's `clip.py` currently takes a VOD/file plus `start`/`end`. Picks here point at a Twitch clip URL with `start: 0`; Editor needs to read `source_url` per pick.

**Next:** chat spikes (live chat message-rate peaks → extra candidates).
