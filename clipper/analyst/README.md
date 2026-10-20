# Analyst & Ops

**Scope:** pull views/retention/subs/claims per Short, score creators + formats + post times, money ledger (USD + PYG), daily report. Trend Scout runs daily in GitHub Actions (`.github/workflows/trend-scout.yml`, HQ-owned); the daily report runs as a Claude scheduled task. Decisions: D29, D30, D32, D33.

**Status:** DB schema + queries + ledger in `../db/` (tested on sample data). Trend Scout built and tested offline. Puller not built.

## Trend Scout (`trend_scout.py`)
Competitor streamer-clip Shorts, **metadata only** (never downloads or stores videos).

```
python clipper/analyst/trend_scout.py --library clipper/formats/library.md --report report.md
```

- Channels (`scout_resolve.py`): `config/competitors.yaml` takes `handle: "@Name"` (channel_id optional). Resolved each run: cache (`config/channel_cache.json`) -> `channels.list?forHandle=` if `YOUTUBE_API_KEY` -> `yt-dlp --skip-download -J --playlist-items 0`. `discover:` slots (IShowSpeed / Kai Cenat / CaseOh) use `search.list` type=channel for `"<streamer> clips" shorts`, top `count` (seed: 3 / 3 / 2) by subscribers; needs the key, else skipped with a note. Unresolved handles show under **Fix me** at the top of the report.
- Data (`scout_data.py`): YouTube RSS per channel in `config/competitors.yaml`; if `YOUTUBE_API_KEY` is set, `videos.list` adds duration + exact stats; yt-dlp `--skip-download -J` only if RSS fails (bot-blocked on CI is logged and skipped).
- Null durations / missing discovery in a report = `YOUTUBE_API_KEY` repo secret not set (RSS has no duration). @DaPlug and @StreamVortex were dropped (unresolvable, 2026-10-17).
- Stats (`scout_stats.py`): views/hour, top 20 of the last 7 days, title templates, length buckets, upload hour (UTC + Asunción UTC-3), streamer leaderboard (Shorts, views, total/avg v/h, clippers = crowding). `test_slot` = above-median avg v/h, at most 2 clippers, not in `creators.yaml`.
- Daily ranking (D33): Twitch clips of the last 24 h for the top-50 EN streamers + `radar/config/creators.yaml`. Score = clip v/h × Shorts v/h ÷ clippers, written to `creators_ranking.json` (`{streamer, platform, score, weight, trend: up/down/new}`). Top-5 entrants are `new`.
- `creator_weights.json` (D32): streamer → 0–1, 7d views × 24h momentum ÷ crowding.
- Claude Sonnet writes `report.md` (≤40 lines) and rewrites `library.md`. The leaderboard, daily ranking, rising hashtags and (Mondays) the weekly 7-day table + add/drop are appended deterministically.
- `creators_ranking.json` and `creator_weights.json` are written next to `--library` (the workflow commits them to the `trends` branch).

**Env:** `ANTHROPIC_API_KEY` (LLM; missing → stats-only report, library untouched), `YOUTUBE_API_KEY` (optional), `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` (optional; missing → Shorts-only ranking).

**Tests:** `pytest -q clipper/analyst` (fixtures: RSS XML, API JSON, yt-dlp JSON; LLM and Twitch mocked).

**Open / needs HQ:**
- Seed handles (CreatorDB Aug 2026) are unverified: the first live run shows bad spellings under 'Fix me'. The cache only persists if the workflow commits `channel_cache.json` (HQ-owned workflow); otherwise it re-resolves daily (cheap).
- Discovery slots: `count: 1` per streamer (issue text was ambiguous: one slot per streamer vs top 3); change `count` if wanted.
- The workflow must `pip install -r clipper/requirements.txt` (now includes `anthropic`).
- Streamer detection in titles is alias matching (config + creators.yaml + Twitch names); short aliases like "Speed" can false-positive.

**Next:** correct 'Fix me' handles after the first live run; YouTube Analytics API puller → `post_metrics`.

## Style scout (`style_scout.py`, Lucas 2026-10-19)
Each Trend Scout run sends the thumbnails (no video) of the day's top Shorts to Claude Haiku and writes `clipper/formats/style.json` (caption case, fill/highlight/outline colours, words per line, position, layout) to the `trends` branch. Needs ≥3 captioned thumbnails, else the old file stays. The VM copies it every pass (`run_pipeline.refresh_formats`); `editor/style.py` renders with it; the Telegram bot re-renders any clip made in an older style before sending it (`clips.style_version`, migration 009).

## Hashtag scout (`hashtag_scout.py`, Lucas 2026-10-19)
Each Trend Scout run also reads description + tags of the competitor Shorts (`videos.list` snippet, same quota) and writes `clipper/formats/hashtags.json` to the `trends` branch, view-weighted over the top 40 Shorts of 7 days: `title_share` (share of views with a hashtag in the title), `generic` (tags naming no streamer, used by 2+ channels, so no channel brand tags), `streamers` (the tag the market uses per streamer), `keywords` (hidden tags). The VM copies it every pass; `publisher/hashtags.py` applies it.

## Metrics puller (`metrics.py`, D35 post-launch)
Every pipeline pass runs `metrics` first: public stats (views, likes, comments) of our own Shorts via the YouTube Data API key → `post_metrics`, at most hourly per Short, for 30 days. `python clipper/analyst/metrics.py --report` prints the table. Engaged views / swipe-away need the YouTube Analytics API (token with `yt-analytics.readonly`, not granted yet). Next: feed views per streamer/format back into the Heat Index and the Writer.
