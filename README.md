# PRM
# HOPE

**PRM = Puro Rico o Muerto.** One repo for every PRM project; one folder per project.

| Folder | Project | Status |
|---|---|---|
| [`studio/`](studio/) | **Nine to Purr**: AI cat office comedy Shorts on YouTube (@NineToPurr) | **Active**, go 2026-10-29 ([status](studio/docs/STATUS.md)) |
| [`clipper/`](clipper/) | YouTube Shorts channel of big-streamer clips, run by agents | Paused 2026-10-29 (D67); its channel became Nine to Purr ([status](clipper/docs/STATUS.md)) |

## Nine to Purr at a glance
- Mochi (lazy orange cat), Pearl (overachiever white cat) and Gus (pigeon boss) at Clawporate Inc. Comedy with a payoff in every Short; formats follow what's popping in AI Shorts.
- Goal: YouTube Partner Program before Feb 1, 2027. Test: $30 + $20, then a sprint if the numbers say so ([`studio/docs/STRATEGY.md`](studio/docs/STRATEGY.md)).
- Gemini Omni makes the shots, Claude writes, a radar follows the market, Lucas picks and approves in Telegram.

## Clipper at a glance (paused)
- One Shorts channel, multi-streamer (Heat Index picks daily). Follows the market's format daily; every clip gets our hook + story captions + title. ≤60 s, max 5/day.
- **Live 2026-10-19 → paused 2026-10-29.** State: [`clipper/docs/STATUS.md`](clipper/docs/STATUS.md).
- Paid by YouTube Shorts ads. Goal ≈ 6.7M PYG/month net.
- Python + systemd + SQLite + Telegram approvals; Claude Haiku writes per-clip text; Claude agents build the code from GitHub issues.
- Runs on a home Ubuntu VM (Hyper-V on Lucas's PC), reached over Tailscale. Access + state: `clipper/infra/VM.md`.
- Strategy: [`clipper/docs/STRATEGY.md`](clipper/docs/STRATEGY.md) · Decisions: [`clipper/docs/DECISIONS.md`](clipper/docs/DECISIONS.md)

## Layout
```
clipper/
├── docs/        strategy + module notes
├── infra/       setup.sh, systemd units
├── db/          schema.sql, math.sql, ledger.sql, migrate.py, migrations/
├── radar/       find hot moments (Twitch)
├── editor/      clip.py: cut, 9:16, captions
├── publisher/   YouTube uploads
└── analyst/     metrics, ledger, daily report
studio/          Nine to Purr: docs/, series/, formats/ + one design README per module (see studio/README.md)
```

## Quick start (on the VM)
```bash
sudo mkdir -p /opt/clipper && sudo chown "$USER": /opt/clipper
git clone https://github.com/waytooeasy/prm.git /opt/clipper/repo
bash /opt/clipper/repo/clipper/infra/setup.sh
cp /opt/clipper/repo/clipper/infra/.env.example /opt/clipper/.env   # then fill in, chmod 600
```
