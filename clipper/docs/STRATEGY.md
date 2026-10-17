# PRM — Clipper strategy (v4.1, Oct 16, 2026)

PRM = Puro Rico o Muerto. Owner: **PRM · 00 HQ**. Every decision is logged in [`DECISIONS.md`](DECISIONS.md). Evidence: [`research/ai-shorts-2026.md`](research/ai-shorts-2026.md).

## The model
- **One YouTube Shorts channel**, multi-streamer brand (no streamer name in it). Kai Cenat is the first source, not the whole channel.
- No ties to streamers. We clip, add our angle, post. Views and channel are ours.
- Money = YouTube Shorts ads (YPP; Paraguay eligible). English/US audience.
- Goal: **≈6.7M PYG ≈ $1,100/month net** (~$1,450 gross after ~24% US withholding).

## What changed (v3 → v4) and why
| Was | Now | Why |
|---|---|---|
| Raw clips, streamer audio only, copy templates | **Every clip gets our angle:** a context line + storytelling captions (setup → payoff). Recaps of 2–4 moments as a format test. Streamer audio stays. | YouTube's reused-content rules reject "clips with little or no narrative" and "template-based changes". Since Oct 2, 2026, Shorts reach is cut for re-uploads that add nothing of your own. |
| Many Shorts/day | **3–5/day**, curated | Top clip channels post 0.3–2/day. Spam policy bans high volumes of similar AI content. |
| Multiple channels | **One channel** until it holds ≥20M Shorts views/90d | From Feb 1, 2027, Shorts pay only in months with ≥10M views/rolling 90d. One AdSense per person; one termination bars every channel. |
| Kai only | **Multi-streamer config**, Kai first | 759 accounts clip Kai; he streams irregularly. |
| Any length | **≤60 s hard cap** + music flag | A Short over 60 s with any copyright claim is blocked worldwide. |
| Claude API / scheduled chats as the brain | **Claude API (restored Oct 16):** Haiku 5.5 writes per-clip text, Sonnet 5.5 runs the daily report, Claude GitHub Action agents build the code from issues. | Ban lifted; Haiku is the cheapest option; build team runs without the home PC. |
| n8n agent team now | **Plain Python + systemd + SQLite + Telegram bot.** n8n/agent team unlock at a gate. | Bottleneck is views, not tooling. Automate only what has worked by hand. |
| 7 chats | **HQ + one Build session** in the repo (module chats optional) | Hand-off pain came from the split. |

## The math
| RPM case | Views/month for $1,100 net | Avg views per Short at 5/day |
|---|---|---|
| $0.05 (low) | ~29M | ~193K |
| $0.15 (mid) | ~9.7M | ~64K |
| $0.30 (US-heavy) | ~4.8M | ~32K |

YPP today: 1k subs + 10M Shorts views/90d. **From Feb 1, 2027:** new applicants need 20M/90d + 1k subs, and every channel needs ≥10M/90d each month to be paid.

## Pipeline
```
Radar (Twitch Get Clips, views/hour, dedupe) → Capture (yt-dlp) → Writer (Claude Haiku: score, 3 hooks, context line, title)
→ Editor (Whisper captions, face-tracked 9:16, ≤60 s) → QC (rules) → Telegram approve/edit/kill → Publisher (YouTube API)
→ Metrics (engaged views, viewed-vs-swiped, claims) → daily report
```
- Clip states: `found → captured → drafted → edited → qc_passed → approved → published → measured`.
- Measure **engaged views** and viewed-vs-swiped-away, not raw views (Shorts count every play).
- Lucas approves every Short at first (L0). Auto-publish only after 2 clean weeks (≥90% approved unchanged, 0 blocked claims).

## Phases and gates
| Phase | What | Gate |
|---|---|---|
| **0. Validate (2 weeks)** | VM up. 15 Shorts: script cuts + captions, Lucas approves the angle, upload by hand or one API test upload. 3/day. | ≥1 Short over 10K engaged views. None → change format before more code. |
| **1. Automate the proven steps** | Radar + Writer + Editor + Telegram bot + API publisher. 3–5/day. Add 1–2 streamers. | ≥1M engaged views/month pace |
| **2. Learning loop** | Daily metrics, weekly "what won" prompt update, 1 daily Sonnet report via the API. Optional Feb 1 YPP push if pace allows (~111K views/day). | YPP accepted; ≥10M/90d sustained |
| **3. Scale** | n8n / agent team, recap format, more streamers. 2nd channel only with a distinct format and the 1st ≥20M/90d. | ≥$1,100 net for 2 months |

**Kill:** <3M views in the first 90 days → stop the ad model.

## Hard rules
- No raw re-uploads; every clip carries our context line + story captions.
- No detection-evasion edits (speed-up, pitch shift, mirror, heavy filters, crop tricks). Those are spam strikes.
- ≤60 s. Flag music segments. Track claims per streamer; drop sources that claim.
- No duplicate files. Cap 5/day.
- Never a backup channel. Never a second Anthropic account. API key only in secrets / `.env`; Console spend limit always on.
- US tax form (W-8BEN) in AdSense on day 1; contador for Paraguay IRP.
- Secrets in `/opt/clipper/.env`, never in git.

## Cost (monthly)
| Item | Cost |
|---|---|
| Claude API: Haiku per clip + Sonnet daily report + build agents ($30/month Console limit) | ~$5–30 |
| YouTube + Twitch APIs, Telegram, SQLite, n8n self-hosted | $0 |
| Claude subscription | existing |
| **Total** | **~$5–30** (+ electricity) |
