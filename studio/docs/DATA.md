# Data (design)

SQLite at `/opt/studio/studio.db`. Times in UTC ISO-8601. Migrations will live in `studio/db/migrations/NNN_name.sql` (same rule as the clipper). This file is the contract every module codes against; changes go through HQ.

## Tables
| Table | One row per | Key fields |
|---|---|---|
| `series` | cast | `slug`, `name`, `bible_path`, `status` (draft/live/retired) |
| `characters` | character | `series_id`, `name`, `species`, `look` (fixed prompt words), `ref_paths` (JSON), `status` |
| `breakouts` | popping Short seen by the radar | `video_id`, `channel_id`, `channel_subs`, `channel_created`, `title`, `published_at`, `duration_s`, `views`, `views_per_h`, `views_per_sub`, `lang`, `seen_at`, `tags` (JSON from Gemini, below), `wave_id` |
| `waves` | popping cluster | `format_id`, `family` (e.g. animals-in-human-life), `status` (rising/peak/fading), `shorts_7d`, `median_views_per_h`, `median_len_s`, `examples` (JSON video ids), `first_seen`, `last_seen` |
| `watch_channels` | competitor channel followed by RSS | `channel_id`, `why` (≥2 breakouts), `added_at` |
| `premises` | idea offered to Lucas | `date`, `series_id`, `wave_id`, `format_id`, `logline`, `beats` (JSON), `why_now`, `est_cost`, `rank`, `similarity_max`, `picked_by` (lucas/auto/null), `state` |
| `episodes` | Short | `premise_id`, `state`, `state_changed_at`, `title`, `description`, `hashtags`, `target_s`, `file_path`, `cost_usd`, `qc` (JSON), `approval_sent_at`, `last_error` |
| `shots` | generated shot | `episode_id`, `n`, `prompt`, `refs` (JSON), `first_frame`, `duration_s`, `resolution`, `state`, `attempts`, `qc_score`, `file_path` |
| `generations` | paid API call (the ledger) | `kind` (video/image/llm/tts/watch), `model`, `units` (seconds/images/tokens), `unit_price`, `cost_usd`, `status`, `latency_s`, `error`, `episode_id`/`shot_id`, `created_at` |
| `approvals` | Telegram decision | `episode_id` or `premise_id`, `action` (pick/post/kill/retake/stop), `detail`, `at` |
| `posts` | upload | `episode_id`, `youtube_id`, `published_at`, `made_for_kids` (as YouTube reports it), `synthetic_flag`, `playlist_id` |
| `post_metrics` | stats pull | same shape as the clipper's: `views`, `likes`, `comments`, `pulled_at` |
| `post_analytics` | analytics pull | same shape as the clipper's (`012_post_analytics.sql`): engaged views, stayed %, average view %, subs gained |
| `votes` (Phase 2) | comment vote tally for an `episode` arc | `post_id`, `option`, `count`, `read_at` |
| `learnings` | weekly learn result | `week`, `finding`, `evidence` (JSON), `accepted_by` |

## Radar `tags` (what Gemini returns per watched Short)
| Field | Example |
|---|---|
| `format_id` | `reversal` (a seed id from `formats/README.md`, or `new:<short name>`) |
| `cast_type` | animals-human-life / food / humans / creatures / objects |
| `len_s`, `shots` | 24, 3 |
| `hook_first_2s` | what happens or shows in the first 2 s, in our words |
| `beats` | 3–5 one-line beats |
| `payoff` | reversal / reveal / punchline / cliffhanger / none |
| `voice` | wordless / narrator / dialogue |
| `text_style` | caption look in words (case, colours, position, words per card) |
| `kid_coded` | true if it looks made for kids |
| `policy_flags` | real_person, brand, kids, distress, sexual, music |
| `why_it_works` | one line |

## Files on the VM
```
/opt/studio/
├── .env                      keys (chmod 600, never in git)
├── studio.db
├── youtube_token.json        upload token for the Studio channel (chmod 600)
├── analytics_token.json      read-only analytics token (chmod 600)
├── formats/                  waves.json, library.md, style.json (radar)
├── series/<slug>/refs/       character refs (PNG), Lucas keeps a copy
├── work/<episode_id>/        shots/, narrator.wav, captions.ass, sidecar.json (cleared 3 days after upload)
└── out/<episode_id>.mp4      final Short, kept: weekly long-form compilations reuse them (~20 MB each)
```
