# Pipeline (design, not built)

Everything heavy runs in the cloud (Gemini API, Claude API); the VM (`prm-clipper`, 6 vCPU, no GPU) only orchestrates, runs ffmpeg and keeps the DB. Same pattern as the clipper: Python + systemd timers + SQLite + a Telegram bot (D9).

## Flow
```
radar (every 6 h) ── popping AI Shorts → watched by Gemini → waves.json, library.md, style.json
        │
room (08:00) ─────── 5 premises in today's popping formats ─► Telegram: Lucas picks (auto #1 at 11:00)
        │
room: script + storyboard ── shots[] (prompt, refs, beats, SFX, first-frame plan), text cards, title
        │
budget guard ─► generator: Omni per shot (9:16, 720p) ─► shot QC ─► retake (max 2 per shot)
        │
assembler: ffmpeg concat → captions (style.json) → loudness → 1080×1920 ─► final QC (Gemini watches it)
        │
Telegram: video + title + cost + QC ─► ✅ Post · ❌ Kill · 🔁 Retake shot N
        │
publisher: upload at the 15:00 slot ─► analyst: stats hourly (48 h), analytics every 6 h, recap 23:00, weekly learn
```
Times are Asunción (UTC-3). 15:00 = 13:00 New York (EST from Nov 1) = 10:00 LA. The radar may move the slot to when our lane's popping Shorts go up.

## Episode states
`idea → picked → boarded → generating → generated → assembled → qc_passed → approved → published → measured`

Side states: `needs_retake` (a shot failed QC; retakes left), `needs_human` (retakes used up or QC unsure), `over_budget`, `killed`, `failed` (with `last_error`).

## Modules (folders under `studio/`, built after go)
| Module | Does | Engine | Runs | Cost |
|---|---|---|---|---|
| [`radar/`](../radar/) | Find popping AI Shorts in our lane, watch and tag them, cluster into waves, write the format files | YouTube Data API + Gemini 3.8 Flash on public URLs | timer, every 6 h | ~$0.25/day |
| [`room/`](../room/) | Premises, then script + storyboard + title for the picked one | Claude Sonnet 5.5, bible prompt-cached | 08:00 + on pick | cents/day |
| [`generator/`](../generator/) | Character refs; shots via Omni; spend ledger and budget guard | Gemini API (Nano Banana, Omni) | on pick | ~$2.40–3/episode |
| [`assembler/`](../assembler/) | Concat, on-screen text, sound mix, upscale | ffmpeg + the clipper's caption renderer | per episode | $0 |
| [`qc/`](../qc/) | Shot checks and final checks ([`QC.md`](QC.md)) | rules + Claude Haiku 5.5 on frames + Gemini 3.8 Flash watching the file | per shot / episode | ~$0.02 |
| [`publisher/`](../publisher/) | Telegram bot (pick, approve, retake, stop) + YouTube upload | the clipper's uploader and bot pattern, new token and bot | always on / every 15 min | $0 |
| [`analyst/`](../analyst/) | Stats, analytics, made-for-kids watch, recap, weekly learn | the clipper's metrics puller + Sonnet weekly | hourly / 6 h / weekly | cents |
| [`db/`](../db/) | Schema and migrations ([`DATA.md`](DATA.md)) | SQLite | — | — |
| [`infra/`](../infra/) | Units, `.env`, health alerts, setup | systemd | — | — |

## Human touchpoints (Telegram, new bot)
| When | Lucas sees | Buttons | If no answer |
|---|---|---|---|
| ~08:00 | 5 premises: format, one-line story, why now (wave + its numbers), est. cost | 1–5 · 🔄 5 more · ⏭️ skip today | #1 auto-picked at 11:00 (logged as `auto`) |
| ~12:00 | Finished Short (≤49 MB inline), title, format, cost, QC notes | ✅ Post · ❌ Kill · 🔁 Retake shot N | Waits. **No auto-post in the test** |
| 23:00 | Recap: views, stayed %, subs, spend vs cap, best and worst Short, top 3 waves | — | — |
| any time | Alerts: budget 50/80/100%, generation failures, quota, made-for-kids flip, policy notice, disk | — | — |

Commands: `/status`, `/stats`, `/budget`, `/waves`, `/pause`, `/resume`. Only `TELEGRAM_ALLOWED_CHAT_ID` gets answers.

## Budget guard
- Every paid call writes a row in `generations` (model, seconds or images or tokens, unit price, cost).
- Before each call: spent + this call's estimate ≤ `STUDIO_BUDGET_USD` (test: 50) and the episode's spend ≤ `EPISODE_MAX_USD` (test: 4). Otherwise the episode goes `over_budget` and Lucas gets an alert. Nothing raises the cap except Lucas.
- Unit prices live in config with the date they were checked; prices change on Jan 1, 2027 (Gemini Flash and TTS double).
- Second cap outside our code: the Gemini API is prepaid (new accounts default to Prepay). At a $0 balance Google answers HTTP 402; the generator treats 402 as `over_budget` and alerts, never retries.

## Failure handling
- Omni error or timeout: 2 retries with backoff, then `failed` + alert.
- Shot fails QC: retake (max 2 per shot, each costs its seconds), then `needs_human`.
- Any upload error: same handling as the clipper's uploader (quota stop for the day, Telegram alert, the YouTube id is saved before the state flips so a retry never posts twice).
- A weak day posts nothing. Quality over quantity (Lucas, Oct 28).

## Autonomy ladder
| Level | Who decides | Unlock |
|---|---|---|
| **L0 (test)** | Lucas picks the premise (or auto at 11:00) and taps ✅ on every Short | default |
| L1 | Premise auto-picked; Lucas still taps ✅ | Day-14 "keep" |
| L2 | Auto-post when QC passes; FYI with 🛑 Stop until the slot (like D44) | 2 weeks with ≥90% of Shorts approved unchanged |
| Never | New channels, real people, raising the budget, changing the bible without Lucas | — |

## What we reuse from the clipper
- `publisher/upload.py` (uploads, slots, quota handling, idempotent posts row), `publisher/approve_bot.py` (bot pattern), `analyst/metrics.py` (`post_metrics` / `post_analytics`), the caption renderer behind `style.json`, `infra/health.py`, `db/migrate.py`.
- First build issue: move those into a `shared/` package with their tests, the clipper's behavior unchanged and CI green. If that's risky, import them with Studio config instead.
- Separate: DB (`/opt/studio/studio.db`), `.env`, OAuth tokens, bot token, Google Cloud project (S3).
