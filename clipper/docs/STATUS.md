# Clipper status (live)

**Read this first in any new PRM chat.** It says what is running right now, what is waiting and who it waits on. Strategy: [`STRATEGY.md`](STRATEGY.md) · decisions: [`DECISIONS.md`](DECISIONS.md) · the box and how to get a shell: [`../infra/VM.md`](../infra/VM.md).
**Rule:** any session that changes what runs, what's next or who something waits on updates this file in the same PR.

_Last updated: 2026-10-19 19:00 UTC_

## Running now (VM `prm-clipper` on moon)
| Piece | State |
|---|---|
| Pipeline (`clipper-pipeline.timer`, every 20 min) | ✅ live: formats → radar → capture → Writer → render → QC → re-render |
| Telegram bot `@PRM_Clips_BOT` | ✅ live: sends each `qc_passed` clip with **✅ Post / ❌ Kill**; re-renders first if it was made in an older style |
| Uploader (`clipper-upload.timer`) | ✅ live: approved clips go up **as soon as approved**, any hour, ≥30 min apart, max 5/day (`.env`: UTC window 00:00–23:59) |
| Trend Scout (GitHub Actions, 10:30 UTC daily) | ✅ report issue + `trends` branch: `library.md` (titles/hooks) + `style.json` (caption style) |
| Keys in `/opt/clipper/.env` | ✅ Anthropic, YouTube API key + upload token (OAuth app published), Twitch, Telegram |
| Access for Claude | ✅ SSH from moon's local shell, `/vm` on issue #58, scoped sudo for restarting `clipper-*` services |

## The format today (follow the market, D36)
- **Sources:** Twitch clips only (Heat Index picks from the ~30-streamer watchlist daily). YouTube footage blocked, see #64.
- **Length:** the length viewers chose (the Twitch clip / most-replayed window), trim ≤2 s per end, ≤60 s.
- **Look:** full-bleed 9:16 centred on the face, or facecam on top + gameplay below. Captions per today's `style.json` (2026-10-19: ALL CAPS, white, black outline, 3 words, highlight colour rotating cyan/lime/pink per clip). Hook only for 2.5 s. No context-line banner.
- **Text:** Writer (Haiku 5.5) follows today's format library: short casual titles with emoji, hook templates.

## Clips so far
| Date | Made | Approved | Published | Notes |
|---|---|---|---|---|
| 2026-10-19 | 5 | 4 (xQc, Valkyrae, emiru, Lacy) | uploading from 19:05 UTC, 30 min apart | Sykkuno's clip still waiting (his own burned-in captions double ours → kill) |

Check live: `sqlite3 /opt/clipper/db/clip.db "select id,state,title from clips"` on the VM.

## Waiting on Lucas
- **Create the YouTube channel "Peakz Recaps" (@Peakz) on the.prm.project@gmail.com**, phone-verify it, upload the profile picture + banner (design canvas "Peakz Recaps brand"). The first upload failed with `youtubeSignupRequired` until the channel exists.
- AdSense signup + W-8BEN.
- Anthropic Console spend limit.
- Decision on YouTube footage (#64).

## Next for Claude
- Watch the first real uploads (first ever YouTube API upload) and the first metrics.
- Metrics puller + daily Analyst after launch (D35).

## On hold (until the first Shorts perform, D35)
#69 Kick source · #70 YouTube streamers (Speed) source · #45 · #28.
