# PRM — Clipping Engine strategy (v3, Oct 15, 2026)

PRM = Puro Rico o Muerto. This doc is the main strategy. Build details live in separate chats.

## The idea (locked)
- Our own **YouTube Shorts** channel of big-streamer clips. No ties to the streamers: we clip, we post, the views and channel are ours.
- Streamer's own audio, big hook captions, **copy whatever edit formats are trending**. No voiceover, no long videos.
- **Many Shorts a day**, several creators. Start with **Kai Cenat**, add creators by data.
- Money = **YouTube Shorts ad revenue** (YPP is available in Paraguay). US/English audience.
- Goal: **~6.7M PYG ≈ $1,100/month net** (≈ half a salary).
- Lucas: ~1 h/day. Clips auto-post, daily review.

## The math
| Item | Number |
|---|---|
| Shorts RPM (entertainment) | ~$0.03–0.08 per 1k views |
| US tax withholding | 30% on US-viewer revenue (no US treaty for Paraguay; W-8BEN still required, otherwise 24% of everything) |
| Net after withholding (~80% US audience) | ~76% of gross |
| Gross needed for $1,100 net | ~$1,450/month |
| Views needed | **~18–48M/month ≈ 0.6–1.6M/day** |
| At 10 Shorts/day | **~60k–160k avg views per Short** |
| YPP gate (before any $) | 1,000 subs + 10M Shorts views in 90 days |

Benchmark: top streamer-clip channels do 60–110M views/month. The target is mid-tier.

## The engine
| Agent | Job | Runs on |
|---|---|---|
| **Radar** | Each creator's most-viewed Twitch clips (last 24h) + live chat spikes, ranked | Home VM, code |
| **Capture** | Downloads the raw moment | Home VM, yt-dlp |
| **Editor** | Trending format preset: 9:16, facecam crop, hook text, word captions, zooms, title + tags | Home VM, ffmpeg + Whisper |
| **QC** | Kills dupes/weak clips, daily cap, spacing | Home VM, rules |
| **Publisher** | Spaced uploads | Home VM, YouTube API (manual phone upload until audit) |
| **Analyst** | Views 1h/24h/72h, retention, subs, Content ID claims → scores creators, formats, hooks, post times | Home VM, YouTube Analytics API + SQLite |
| **Trend Scout** | Studies competitor Shorts daily, updates the format library | Claude scheduled task |
| **Orchestrator** | Daily report + changes for tomorrow | Claude scheduled task |

No Claude API (account banned there). Real-time work is plain code; the thinking runs as daily scheduled tasks on the current Claude plan.

## Infra ($0)
- Home PC: i5-12400, 32 GB, 2 TB NVMe, Win 11 → **VMware Ubuntu Server 24.04 VM** (6 vCPU, 8 GB RAM, 80 GB).
- Auto-start the VM via Task Scheduler (`vmrun ... nogui`). Bot runs as systemd services.
- Remote access: **Tailscale** in the VM + personal phone/laptop. No DNS, no open ports (everything is outbound).
- Data: SQLite (`schema.sql`, `math.sql`, `ledger.sql`), money tracked in USD + PYG.

## Hard constraints
- **YouTube API:** a new project uploads private-only until audited, ~6 uploads/day on the default quota. Apply for audit + quota on day 1.
- **YPP review:** raw reuploads get rejected. The edit layer (captions, zooms, cuts) keeps the channel monetizable.
- **Content ID:** a claimed Short's revenue goes to the claimant. The Analyst tracks claim rate per creator, and creators who claim a lot get swapped out.
- **Taxes:** W-8BEN in AdSense on day 1. Foreign income in Paraguay: RUC/IRP, ask a contador before the first payout.

## Phases and gates
| Phase | What | Gate |
|---|---|---|
| **0 — Week 1** | VM + `clip.py`, Kai only, 3–5 Shorts/day, manual upload. Apply for API audit. AdSense + W-8BEN. | ≥100k total views |
| **1 — Weeks 2–4** | Radar + Capture + Editor + QC automated, 5–8/day, 2nd creator | ≥1M views/month pace, ≥500 subs |
| **2 — Months 2–3** | Analyst + Trend Scout + Orchestrator, 8–12/day, 3–5 creators | YPP: 1k subs + 10M views/90 days |
| **3 — Monetized** | Scale what the data says works. 2nd channel only after the 1st makes ≥ $500/month. | ≥ $1,100/month net |

**Kill / pivot:** under 1M views in the first 60 days → change creator/format. Under 3M in 90 days → stop.

## Chat split
- **Main (this one):** strategy, numbers, gates, decisions.
- **Build chats:** Infra (VM, Tailscale, setup.sh) · Radar + Capture · Editor (formats) · Publisher (YouTube API) · Analyst + ledger · Trend Scout/Orchestrator.

## Built so far
`clip.py` (cut + captions) ✅ · `schema.sql` + `math.sql` ✅ · `ledger.sql` ✅ · `setup.sh` ✅

## Sources
- YPP availability (Paraguay listed): support.google.com/youtube/answer/7101720
- YPP thresholds: support.google.com/youtube/answer/72851
- Shorts RPM: joyspace.ai/youtube-shorts-rpm-2026-calculator · 1of10.com/blog/youtube-pay-per-view
- US withholding on YouTube earnings: wiki.private.law/en/platform-withholding
- YouTube API quota: outlierkit.com/resources/youtube-api-quota
- Top clip channels: creatordb.app/creator-news/the-rise-of-the-clip-economy
