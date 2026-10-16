# PRM — Clipper strategy (v5, Oct 16, 2026)

PRM = Puro Rico o Muerto. **Sin miedo al éxito.** Owner: **PRM · 00 HQ**. Every decision is logged in [`DECISIONS.md`](DECISIONS.md). Evidence: [`research/ai-shorts-2026.md`](research/ai-shorts-2026.md).

## The model
- **One YouTube Shorts channel**, multi-streamer brand with a **point of view** in the name (not a streamer's name, not "clips"). Kai Cenat + 2–3 less-clipped US streamers.
- No ties to streamers. We clip, add our angle, post. Views and channel are ours.
- Money = YouTube Shorts ads (YPP; Paraguay eligible) → later long-form recaps. English/US audience.
- Goal: **≈6.7M PYG ≈ $1,100/month net** (~$1,450 gross after ~24% US withholding). Built to go past it.
- Lucas: **~5 h/day**. Start now.

## What changed (v4.1 → v5) and why
| Was | Now | Why |
|---|---|---|
| Start after probation, ~1 h/day | **Start now, ~5 h/day** | YPP at 10M/90d closes Feb 1, 2027; after that it's 20M. Every week counts. |
| Build Publisher/metrics first, then post | **Post by hand now, build in parallel** | Data beats code. 0 Shorts posted so far. |
| Angle = context line + captions | **Point of view** (channel premise a viewer can repeat) + context line + story captions + **Lucas's voice** on the top 1–2/day | Captions alone read as "template-based changes"; real commentary is the strongest originality signal and a moat farms can't copy. |
| Compete on curation only | **Compete on speed too:** live capture (Twitch Create Clip) is build priority #2 | 759 accounts clip Kai, most from VODs ~1 h late. 5 h/day makes fast approvals possible. |
| Shorts only | **Weekly long-form recap test** (weeks 3–4) | Long-form earns ~10–30× per view. Shorts = funnel, long-form = money. |
| Gates: ≥1M/month, kill <3M/90d | **Gates tied to the Feb 2027 floor** (below) | The old gates passed a channel that earns $0. |

## The math
| RPM case | Views/month for $1,100 net | Avg views per Short at 5/day |
|---|---|---|
| $0.05 (low) | ~29M | ~193K |
| $0.15 (mid) | ~9.7M | ~64K |
| $0.30 (US-heavy) | ~4.8M | ~32K |

YPP today: 1k subs + 10M Shorts views/90d. **From Feb 1, 2027:** new applicants need 20M/90d + 1k subs, and every channel needs ≥10M/90d each month to be paid. Old-rules window: 10M in the 90 days ending Jan 31 ≈ **~111K views/day**.

## Pipeline
```
Radar (Twitch Get Clips + live Create Clip, views/hour, dedupe) → Capture (yt-dlp) → Writer (Claude Haiku: score, 3 hooks, context line, title)
→ Editor (Whisper captions, face-tracked 9:16, ≤60 s, optional Lucas voice track) → QC (rules) → Telegram approve/edit/kill → Publisher (YouTube API)
→ Metrics (engaged views, viewed-vs-swiped, claims) → daily report
```
- Clip states: `found → captured → drafted → edited → qc_passed → approved → published → measured`.
- Measure **engaged views** and viewed-vs-swiped-away, not raw views.
- Lucas approves every Short (L0). Auto-publish only after 2 clean weeks (≥90% approved unchanged, 0 blocked claims).

## Build order
1. **Publisher** (YouTube API upload + one test upload to confirm public).
2. **Live capture** (Twitch Create Clip on chat/viewer spikes while streamers are live).
3. **Metrics puller** (Analytics API → `post_metrics`).
4. Voice track in Editor (record on phone → mixed under streamer audio).
5. Long-form recap renderer (stitch the week's top moments + voice).
Anything else waits for data.

## Plan and gates
| When | Do | Gate / checkpoint |
|---|---|---|
| **This weekend** | Channel live with a POV name. First 6 Shorts by hand. 3 hook styles. Post 00:00–02:00 Asunción (US evening). | — |
| **Week 1–2** | Publisher + live capture. 3–5 Shorts/day. Lucas's voice on the top 1–2. | Signal check: ≥1 Short over 10K engaged views. None → change angle/streamers, not code. |
| **Week 3–4** | Metrics puller. Weekly long-form recap test. Verify Whop/Vyro pay out to Paraguay. | ≥1M views/month pace |
| **Dec 31** | Checkpoint | On pace for 10M/90d by Jan 31 → apply under the old rules. Not on pace → plan for 20M or switch format. |
| **Jan 15** | Kill check | **<3M views/month → stop the ad model**; keep the engine, switch to campaigns/another PRM project. |
| **After YPP** | Learning loop, autonomy L1+, more streamers, second format | ≥10M/90d sustained, then ≥$1,100 net for 2 months |

## If it works (sin miedo al éxito)
- Weekly long-form recaps as the main revenue line.
- More streamers under the same brand; second channel only with a distinct format and the first ≥20M/90d.
- Paid clipping campaigns (Whop/Vyro) as extra revenue, once Paraguay payouts are confirmed.
- Sell the engine: run official Shorts for mid-tier streamers (authorized, no reuse risk).
- n8n / agent team once a stream makes money.

## Hard rules
- No raw re-uploads; every clip carries our context line + story captions.
- Voice = real opinion/context, never just describing the screen. No synthetic AI narration.
- No detection-evasion edits (speed-up, pitch shift, mirror, heavy filters, crop tricks). Those are spam strikes.
- ≤60 s. Flag music segments. Track claims **and strikes** per streamer; drop sources that claim or strike.
- No duplicate files. Cap 5 Shorts/day.
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
