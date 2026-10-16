# Analyst & Ops

**Scope:** pull views/retention/subs/claims per Short, score creators + formats + post times, money ledger (USD + PYG), daily report. Trend Scout runs daily in GitHub Actions (`.github/workflows/trend-scout.yml`, HQ-owned); the daily report runs as a Claude scheduled task. Decisions: D29, D30, D32, D33.

**Status:** DB schema + queries + ledger in `../db/` (tested on sample data). Trend Scout built and tested offline. Puller not built.

## Trend Scout (`trend_scout.py`)
Competitor streamer-clip Shorts, **metadata only** (never downloads or stores videos).

```
python clipper/analyst/trend_scout.py --library clipper/formats/library.md --report report.md
```

- Data (`scout_data.py`): YouTube RSS per channel in `config/competitors.yaml`; if `YOUTUBE_API_KEY` is set, `videos.list` adds duration + exact stats; yt-dlp `--skip-download -J` only if RSS fails (bot-blocked on CI is logged and skipped).
- Stats (`scout_stats.py`): views/hour, top 20 of the last 7 days, title templates, length buckets, upload hour (UTC + Asunción UTC-3), streamer leaderboard (Shorts, views, total/avg v/h, clippers = crowding). `test_slot` = above-median avg v/h, at most 2 clippers, not in `creators.yaml`.
- Daily ranking (D33): Twitch clips of the last 24 h for the top-50 EN streamers + `radar/config/creators.yaml`. Score = clip v/h × Shorts v/h ÷ clippers, written to `creators_ranking.json` (`{streamer, platform, score, weight, trend: up/down/new}`). Top-5 entrants are `new`.
- `creator_weights.json` (D32): streamer → 0–1, 7d views × 24h momentum ÷ crowding.
- Claude Sonnet writes `report.md` (≤40 lines) and rewrites `library.md`. The leaderboard, daily ranking, rising hashtags and (Mondays) the weekly 7-day table + add/drop are appended deterministically.
- `creators_ranking.json` and `creator_weights.json` are written next to `--library` (the workflow commits them to the `trends` branch).

**Env:** `ANTHROPIC_API_KEY` (LLM; missing → stats-only report, library untouched), `YOUTUBE_API_KEY` (optional), `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` (optional; missing → Shorts-only ranking).

**Tests:** `pytest -q clipper/analyst` (fixtures: RSS XML, API JSON, yt-dlp JSON; LLM and Twitch mocked).

**Open / needs HQ:**
- `config/competitors.yaml` has 10 seed channels with **empty `channel_id`** (skipped with a warning). Real UC… ids can't be verified offline.
- The workflow must `pip install -r clipper/requirements.txt` (now includes `anthropic`).
- Streamer detection in titles is alias matching (config + creators.yaml + Twitch names); short aliases like "Speed" can false-positive.

**Next:** fill channel ids; YouTube Analytics API puller → `post_metrics`.
