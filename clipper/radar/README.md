# Radar

**Scope:** find moments worth clipping and hand them to the Editor as `picks.json`. Radar does not write hooks/titles (Editor's Writer does).

**HQ decisions (D13, D14):** Twitch Get Clips first (chat spikes later); creators from config; rank by views/hour; dedupe by VOD + overlapping offset; widen to 7 days when thin; table `radar_candidates` via `../db/migrations/002_radar.sql`.

**Status:** v1 built; YouTube live-VOD source added (issue #19, D29); Kick clips source added (issue #69, D45); same moments as the top clippers (D54). `pytest clipper/radar` passes offline (saved responses in `tests/fixtures/`).

## Files
- `config/creators.yaml` — per creator: a plain Twitch login, or `{twitch: kaicenat, youtube_channel: "@KaiCenatLive"}` to also pull that channel's livestream VODs.
- `youtube_vods.py` — yt-dlp metadata only (no API key): `<channel>/streams` → per-video JSON → moments from the `heatmap` ("most replayed", segments with value ≥ 0.5, top 3 per VOD), else `chapters` (weak score), else nothing → `radar_candidates` rows with `source='youtube'` (migration `007_radar_source.sql`). Skips `/shorts/` URLs, videos not from the configured channel, and non-live uploads / still-live streams. VODs from the last 7 days.
- `twitch.py` — app token (client credentials, cached in `/opt/clipper/twitch_token.json`), login → broadcaster id, paginated Get Clips.
- `top_clips.py` — last 24 h per creator (7 days if < N candidates after dedupe) → score → dedupe → `radar_candidates` → ranked list → `--picks N` writes `picks.json`.
- `kick.py` (D45) — Kick channel clips + live status from the public JSON kick.com's own pages load (`kick.com/api/v2/channels/<slug>/clips?sort=view&time=day|week`, 20 per page, `nextCursor`; `/channels/<slug>` → `livestream.is_live`). No key; the documented developer API has no clips. Polite UA `PRM-Clipper/1.0`, 0.5 s between pages. A challenge page / 403 / 429 / 503 raises `KickBlocked` and Kick is skipped for the pass: **no bot-check workarounds**. Skips mature and non-public clips. Candidates: `source='kick'`, `url = https://kick.com/<slug>/clips/<id>`, `video_id` = Kick livestream id, `vod_offset` None. `collect` = top clips of the day **and** the week, merged, ranked by views/hour (a day list of 20 four-view clips used to hide the week's 28k-view hit).
- `capture.py` — yt-dlp download of picked clips into `$CLIPPER_WORK`; marks rows `captured` and the linked `clips` row `captured` + `file_path`.
- `top_clips.register_clips` — with `--picks N`, the chosen candidates become `clips` rows with `state='found'`, linked via `radar_candidates.clips_id` (D22). Idempotent.

## Shorts market scan (`market.py`, D48, Lucas 2026-10-20: "follow what's popping")
Daily (pipeline stage `market`, at most once per 24 h): for every watchlist streamer, the most-viewed English Shorts naming them in the last 48 h, any channel (`search.list` order=viewCount + `videos.list`; ~100 quota units per streamer, metadata only). `market.json` (`$CLIPPER_MARKET`, default `/opt/clipper/formats/market.json`): per streamer `demand_vph` (sum of views/hour of the top 10), the top Shorts (title, channel, views/h, length), median length, hashtags used by 2+ channels. Search is loose, so a Short only counts when it names the streamer as a whole word; names that are ordinary words or famous non-streamers (`AMBIGUOUS`: Sketch, Marlon, Lacy, Ludwig, ...) also need a streaming word or another watchlist streamer in the title/tags (the first scan counted Spanish DIY videos tagged #sketch and Marlon Wayans). Non-English titles are dropped (we post for the English market). Used by: the Heat Index (demand), the Writer (popping titles), the uploader (per-streamer hashtags), `match.py` (D54).
**Trend scan (`trend.py`, D65, Lucas 2026-10-28: "we follow what's trending"):** every 6 h (pipeline stage `trend`), 4 broad searches (`TREND_QUERIES`: twitch, kick streamer, streamer, stream clip; ~404 units) for the most-viewed Shorts of the last 48 h, **without a streamer list**: English, ≤ 60 s, ≥ 1500 views/h, then who is in it: a watchlist name (market rule), a twitch.tv / kick.com link or `twitch: name` in the description, or a hashtag / the clip channel's name ("Asmongold Shorts") that Twitch knows as a partner or affiliate (one users call per 100 names). Nobody identified → dropped. `trending.json` (`$CLIPPER_TRENDING`, default `/opt/clipper/formats/trending.json`): the Shorts with `streamer`, `logins`, `kicks`, `how`. Read by `remake/run.candidates`. 2026-10-28 first run: 194 found, 29 popping with a streamer (VanillaMace, Asmongold, WesleyWAT, LosPollosTV, Aztecross, ...); remake candidates 9 → 32.
**Refresh (D54):** between full scans, the 8 streamers with the most demand (`REFRESH_TOP`) are re-scanned every 6 h (`REFRESH_H`, `market.refresh`, ~800 units each); the others keep the full scan's data; `market.json.refreshed` = time of the last refresh. Each Short also keeps `published` (ISO) and the first 200 chars of its description for matching.

## Same moments as the top clippers (`match.py`, D54, Lucas 2026-10-20: "same clips")
Pipeline stage `match`, once per market scan/refresh (`match_runs`): for the 8 streamers Radar posts (latest Heat snapshot by opportunity, with popping Shorts and a Twitch/Kick channel), Claude Haiku (thinking off) compares their popping English Shorts (title, description, length, posted) with their own Twitch/Kick clips of the last 4 days (`CLIP_DAYS`): the 25 most viewed + the 15 fastest rising by views/hour, so yesterday's moment isn't hidden by last week's big clips (title, made, views, length) and names the clip of the same moment, or null. Kept: confidence ≥ 0.8 (`MIN_CONF`; 0.7 = same stream or guest but maybe another moment) and clip made before the Short was posted. `moment_matches` (migration 013) keeps them 72 h with the Radar candidate. `radar_step` → `same_moments_first`: a matched clip marks the pulled candidate of the same footage, or joins the list (only for streamers with a slot); matched moments rank first by the clipper Short's views/hour, the rest after them as before. The Editor (`clip.same_moment` → `draft_pick(same=...)`) gives the Writer that Short's title (paraphrase with synonyms, never identical; copy guard) and cuts to its length. Their video is never downloaded.
- **Never the same moment twice:** `posted_moments` = Twitch/Kick candidates Radar started in the last 8 days (any state, killed too); a candidate with the same footage is skipped. `same_footage` = same streamer and at least half of the shorter clip shared (`SAME_SHARE`): Twitch VOD offsets when both have them, else `[created_at - duration, created_at]`. Any overlap was too loose: a neighbouring clip (18 of 50 s shared) was posted as the matched moment and then blocked the real one.
- The matched clip itself is posted: a pulled clip with the same footage leaves the ranking for it.

## Heat Index (issue #33, D33)
Decides *which streamers* get today's Shorts slots; Radar then ranks moments only inside them.
- `config/watchlist.yaml` — ~30 English streamers, each entry `{name, platform, id}` (`twitch` | `youtube` | `kick`; Kick on since D45: Adin Ross, N3on, Clavicular, Ice Poseidon, plus xQc's Kick next to his Twitch). Also `daily_cap` (5), `max_per_streamer` (2), `explore_days` (3), `explore_top_n` (15). Add/remove a line, no code. All Twitch logins verified against Helix on 2026-10-19 (`erobb221t` → `erobb221`); Kai's YouTube is `@KaiCenatLive` (`@KaiCenat` has no streams tab).
- `heat.py` — per streamer (entries with the same name are summed): **D** = views on clips created in the last 24 h (Twitch Get Clips; Kick: top 60 clips of the week, `heat.kick_views`; YouTube: views of own live VODs from the last 24 h), **W** = same over 7 d, **B** = W/7, **momentum** = (D+1)/(B+1), `live_now` (Twitch Get Streams / Kick channel `livestream` / YouTube `/live`), **saturation** = competitor Shorts about the streamer in 24 h (Trend Scout), else 0.
  - `heat = ln(1+D) * (1 + 0.5*log2(momentum)) + 0.3*ln(1+B) + 1.0*live_now` (natural log; momentum factor floored at 0.1 so a collapsing streamer is never negative)
  - `opportunity = heat / (1 + 0.1*saturation)`
  - **With a fresh market scan (D48), opportunity follows Shorts demand instead:** `sqrt(demand_vph) * sqrt(min(1, D / 2000)) * (1.15 if live)`. Demand = what is popping on Shorts about the streamer; the second factor = is there fresh footage (Twitch/Kick clip views in 24 h). No demand → no slot. Scan covering < half the watchlist → old formula. `streamer_heat.demand` (migration 011) stores it. 2026-10-20: the old formula ranked xQc, Pokimane, Valkyrae (≈400 views/h of Shorts demand) on top; the market formula ranks Jynxzi, Lacy, Stable Ronaldo, CaseOh.
  - Slots (`allocate`, seedable rng): 1 exploration slot to a random top-15 streamer not posted in 3 days (from `posts` -> `clips` -> `sources` -> `creators`; never-posted counts), the remaining slots proportional to opportunity (D'Hondt), max 2 per streamer, total = cap. No eligible explorer -> that slot goes proportional.
  - Writes `streamer_heat` (migration `008_streamer_heat.sql`), one row per streamer per run.
- `top_clips.py` hook: `collect(..., allowed=[...])` / `filter_allowed`, `apply_allocation(cands, slots, ids)`; CLI `--allocation allocation.json` ranks only allocated streamers and keeps at most `slots` moments per streamer. Without the flag nothing changes.
- Saturation input: `CLIPPER_SATURATION` = JSON `{"Kai Cenat": 7}` (competitor Shorts in 24 h). Missing -> 0.

## Pipeline wiring (issue #47, `run_pipeline.py` radar step)
Every 20-min pass (D22): `radar_step` = **Heat slots → moments → picks**.
- `heat_allocation` re-measures the Heat Index at most every 30 min (`HEAT_REFRESH_MIN`); in between it re-allocates from the latest `streamer_heat` snapshot. Exploration slot is seeded per day, so it stays stable. Slots already used today (clips started, not killed) are subtracted per streamer.
- Per allocated creator: Twitch top clips (`top_clips.collect(allowed=...)`) **and** YouTube VOD most-replayed windows (`youtube_vods.collect`, creators with `youtube_channel`), merged and ranked by score; matched moments first (D54), then `apply_allocation` keeps the best `slots` per streamer, then the 6/day cap (`qc.DAILY_CAP`) trims the total. Already-registered moments are skipped before slots are applied.
- Heat unavailable (error) → logged, falls back to ranking all creators; the cap still holds. A yt-dlp failure keeps the Twitch picks.
- **Pacing (D48, live pipeline `pace=True`):** the day's cap is spread over the UTC day: 1 clip may start at 00:00, then one more every 24 h / cap (every 4 h for 6, D52). Before, all 5 started right after midnight UTC and went up in one 2.5 h burst with moments up to a day old.
- `_picks` reads `clips.start_s/end_s` (set by `pick_window`, D23): Twitch `0 → duration`, YouTube VOD-absolute. `capture_step` gets those as is; `editor_step` gets YouTube picks shifted into the downloaded window file (`start - capture.section(pick)[0]`), same as `python -m radar.capture` does for `picks.json`. Previously every pick was `0 → duration`, wrong for VOD moments.
- Kick (D45): `watchlist_kick_slugs()` (default when `creators` is the default; none when a creator list is passed in) filtered by the Heat slots → `kick_moments` → merged into the same ranking. A Kick failure keeps the other picks. After merging, `kick.dedupe` drops a clip whose footage overlaps a better clip of the same streamer on another platform (a clip covers the `duration_s` before its `created_at`), so one xQc moment clipped on Twitch and Kick is posted once.
- Tests: `radar/tests/test_pipeline_radar.py` (fake Twitch, fake yt-dlp, fake Heat fetchers), `radar/tests/test_kick.py` (saved kick.com JSON in `tests/fixtures/kick/`).
- Radar pulls from `radar_creators()` = `creators.yaml` + every enabled watchlist Twitch login (with that streamer's YouTube channel), so every Heat slot can be served. Before this, the first VM pass allocated Sykkuno/Valkyrae/xQc while only `kaicenat` was pulled → 0 picks.
- A VOD yt-dlp can't read (members-only, premiere, YouTube's "confirm you're not a bot") is skipped; if every VOD on a channel fails it raises and is logged.

## Rules in code
- Score = views / hours since `created_at` (age floored at 15 min).
- Dedupe: same `video_id` + overlapping `[vod_offset, vod_offset+duration]`; no VOD offset → same creator + title similarity ≥ 0.8 + `created_at` within 5 min. Best score kept. Any pair with a Kick clip: same streamer + overlapping `[created_at-duration, created_at]` (Kick titles are often junk like "gg").
- `picks.json`: `[{"start", "end", "source_url", "creator", "clip_id"}]` (D23). `start`/`end` are seconds **inside the file for `source_url`**, max 60 s apart:
  - Twitch: the source is the clip, so `0 → duration`.
  - Kick: the clip too, but Kick clips run up to 180 s and end on the moment, so a clip over 60 s keeps its **last 60 s** (`duration-60 → duration`).
  - YouTube: the source is the whole VOD, so `start`/`end` are **VOD-absolute** (`vod_offset → vod_offset+duration`). `clips.start_s/end_s` and `picks.json` from `youtube_vods` stay VOD-absolute. `capture.py` downloads only each pick's window (`--download-sections "*start-end"`, ±3 s padding, ≤720p, 150 MB cap) as `yt_<videoid>_<s>_<e>.mp4` via a temp file that is removed on failure; `radar_candidates.file_path` points at it. The file starts at the padded start, so `python -m radar.capture` rewrites `picks.json` `start`/`end` file-relative for the Editor. A YouTube URL with no video id raises `ValueError`.
  - Re-render of YouTube window files: fixed (HQ decision 2026-10-18). The DB keeps VOD-absolute times; `editor/rerender.py` shifts them by the `capture.section` offset.
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
| `CLIPPER_MARKET` | market scan file, default `/opt/clipper/formats/market.json` (`market.py`, `match.py`) |
| `YOUTUBE_API_KEY` | market scan + 6-h refresh (metadata only) |
| `ANTHROPIC_API_KEY` | `match.py` (Haiku, ~8 calls per scan/refresh) |

The DB is built by `python db/migrate.py` (needs 002 + 004 + 007).

**Needs:** Twitch app (dev.twitch.tv/console, 2FA, redirect `http://localhost`).

**Infra:** proposed `infra/systemd/clipper-radar.{service,timer}` (every 20 min). Assumes repo at `/opt/clipper/repo`; adjust `WorkingDirectory` if different.

**Editor** now reads `source_url` per pick (D23) and moves the `clips` row on (see `../db/README.md`). Open: `creators.name` is the Twitch login, which may duplicate a hand-made display-name row.

**Open:** YouTube picks make the Editor work from a multi-hour VOD file (large download, seeks by VOD-absolute time); a section download (`--download-sections`) would be lighter but changes the start/end contract. Heatmap segments are ~1% of the VOD, so the 60 s window is centred on the segment, not on the exact peak.

**Needs HQ (issue #33):**
- Trend Scout does not persist per-streamer Shorts counts (`leaderboard_24h` is only in its in-memory summary). `heat.py` reads `CLIPPER_SATURATION` JSON; the analyst should write `{streamer: shorts_24h}` next to `creators_ranking.json`, or HQ confirms another hand-off. Until then saturation = 0.
- No systemd unit for `radar.heat` yet (`.github/` and infra timer every 30 min not added; `top_clips` should read the latest `allocation.json`).
- Heat constants (live bonus 1.0, momentum floor 0.1) are my choice; D33 gives only the shape.
- **YouTube blocks yt-dlp from the VM** ("Sign in to confirm you're not a bot", 2026-10-19): the YouTube VOD source and YouTube heat return nothing until HQ decides how (needs-hq). Twitch clips work.

**Resolved (HQ 2026-10-18):** the DB keeps VOD-absolute `start_s/end_s`; the Editor and re-render both shift into the window file.

**Next:** check the first same-moment matches against what the clippers posted and tune `MIN_CONF` (`select streamer, short_title, clip_id, confidence from moment_matches`); give the matcher the clip's Twitch game name (viewer-typed clip titles are often one word, so recall is low); saturation hand-off; chat spikes (live chat message-rate peaks → extra candidates).
