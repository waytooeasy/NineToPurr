# PRM — instructions for Claude

PRM = Puro Rico o Muerto. Lucas's money projects. One folder per project.

## Clipper (active)
- Own YouTube Shorts channel of big-streamer clips (Kai Cenat first). No ties to streamers. Paid by YouTube Shorts ads.
- Copy trending edit formats; don't reinvent. Streamer audio, no voiceover, no long videos.
- No Claude API (account can't use it). Real-time pipeline = plain code; "thinking" (trend scouting, daily report) = Claude scheduled tasks.
- Runs on a home Ubuntu 24.04 VM (VMware on Win 11, i5-12400, 32 GB), reached over Tailscale. Data lives in /opt/clipper, never in git.

## How chats are split
| Chat | Owns | Folder / doc |
|---|---|---|
| PRM · 00 HQ | strategy, numbers, gates | `clipper/docs/STRATEGY.md` |
| PRM · 01 Infra | VM, Tailscale, setup, systemd | `clipper/infra/` |
| PRM · 02 Radar | finding + downloading moments | `clipper/radar/` |
| PRM · 03 Editor | formats, ffmpeg, captions | `clipper/editor/` |
| PRM · 04 Publisher | YouTube API, uploads | `clipper/publisher/` |
| PRM · 05 Analyst & Ops | DB, metrics, ledger, reports | `clipper/analyst/`, `clipper/db/` |

## Rules
- Stay in your chat's scope. Strategy changes go to HQ.
- Each module keeps a `README.md` with: scope, status, how to run, next step. Update it at the end of every session.
- Never commit secrets (OAuth tokens, client_secret.json, .env) or media/DB files.
- Lucas wants short, direct answers and the whole system in mind; ask when unsure instead of assuming.
