# Infra (design only)

**Status:** not built. Runs on the existing VM `prm-clipper` (see `clipper/infra/VM.md`); data in `/opt/studio`, never in git.

**systemd units (planned)**
| Unit | When |
|---|---|
| `studio-radar.timer` | every 6 h |
| `studio-room.timer` | 08:00 Asunción |
| `studio-make.service` | started by the bot on a pick (flock: one episode at a time) |
| `studio-upload.timer` | every 15 min (slot check) |
| `studio-metrics.timer` | hourly |
| `studio-bot.service` | always on |
| `studio-learn.timer` | Sundays |

**`.env` keys (names only; values never in git or chat):** `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` (a separate Studio key on Lucas's account), `YOUTUBE_API_KEY` (in `prm-studio`), `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_TOKEN_FILE`, `YOUTUBE_ANALYTICS_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_ID`, `STUDIO_DB`, `STUDIO_BUDGET_USD`, `EPISODE_MAX_USD`, `STUDIO_SLOT_LOCAL`, `STUDIO_TZ`.

**Health (every pass):** disk (the root volume is 38.5 GB, shared with the clipper; alert at 80%), budget at 50/80/100%, generation failures, quota errors, bot heartbeat.
