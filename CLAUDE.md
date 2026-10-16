# PRM — instructions for Claude

PRM = Puro Rico o Muerto. Lucas's money projects. One folder per project.

**Read first, every session:** `clipper/docs/STRATEGY.md` and `clipper/docs/DECISIONS.md`.

## Clipper (active)
- One YouTube Shorts channel, multi-streamer brand (Kai Cenat first). No ties to streamers. Paid by YouTube Shorts ads.
- Every clip gets our angle: context line + storytelling captions. ≤60 s. 3–5/day. Streamer audio, no raw re-uploads.
- Stack: Python + systemd timers + SQLite + Telegram approval bot. Per-clip LLM = **Claude Haiku 5.5** (Anthropic API); daily Analyst = Sonnet 5.5. Runtime n8n/agent team only after the gate in STRATEGY.md.
- **Anthropic API = Lucas's own account only. Never a second account.** `ANTHROPIC_API_KEY` lives in GitHub secrets and `/opt/clipper/.env`, never in git or logs.
- Build agents run via the Claude GitHub Action: Lucas comments `@claude` on an issue → agent builds → opens a PR. Agents never merge, never edit `.github/workflows/`, never touch secrets.
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
- **Build loop:** agent finishes → PR opens itself → CI → if red, the agent is asked to fix it (max 2) → **Lucas merges** → the next ready issue starts. Keep CI green; never weaken or skip tests.
- Issues run in order via the agent queue. Put `Depends on: #N` at the top of an issue body to sequence it. Labels: `agent` (queue it), `hold` (stop), `in-progress` (running), `needs-hq` (decision needed).
- Every PR: tests for new code (`pytest`, sample data, no network), module README updated, `DECISIONS.md` untouched (HQ only).
- Lucas wants short, direct answers and the whole system in mind; ask when unsure instead of assuming.
