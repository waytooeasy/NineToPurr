# PRM — instructions for Claude

PRM = Puro Rico o Muerto. Lucas's money projects. One folder per project.

**Read first, every session:** `clipper/docs/STRATEGY.md` and `clipper/docs/DECISIONS.md`.

## Clipper (active)
- One YouTube Shorts channel, multi-streamer brand (Kai Cenat first). No ties to streamers. Paid by YouTube Shorts ads.
- Every clip gets our angle: context line + storytelling captions. ≤60 s. 3–5/day. Streamer audio, no raw re-uploads.
- Stack: Python + systemd timers + SQLite + Telegram approval bot. Per-clip LLM = Gemini 3.1 Flash-Lite. n8n/agent team only after the gate in STRATEGY.md.
- **No Anthropic API, no second account, no `ANTHROPIC_API_KEY`, no `--bare`.** Claude writes and maintains the code.
- Runs on a home Ubuntu 24.04 VM (VMware on Win 11, i5-12400, 32 GB), reached over Tailscale. Data in `/opt/clipper`, never in git.

## Sessions
| Session | Owns |
|---|---|
| **PRM · 00 HQ** | Strategy, numbers, gates, `STRATEGY.md`, `DECISIONS.md` |
| **PRM · Build** | All code in `clipper/` (radar, editor, publisher, analyst, db, infra) |
| Module sessions (optional) | One folder each, same rules |

## Rules
- Work on a branch; open a PR. Never push to `main`.
- Anything that changes strategy or another module's contract → open a GitHub issue labeled `needs-hq` and keep building around it.
- Schema changes only as `clipper/db/migrations/NNN_name.sql`.
- Each module keeps a `README.md`: scope, status, how to run, next step. Update it before ending a session.
- Never commit secrets (`.env`, OAuth tokens, `client_secret*.json`) or media/DB files.
- Never add detection-evasion edits (speed-up, pitch shift, mirroring, heavy filters).
- Lucas wants short, direct answers and the whole system in mind; ask when unsure instead of assuming.
