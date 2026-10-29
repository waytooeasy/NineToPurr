# PRM
# HOPE

**PRM = Puro Rico o Muerto.** One repo for every PRM project; one folder per project.

| Folder | Project | Status |
|---|---|---|
| [`clipper/`](clipper/) | YouTube Shorts channel of big-streamer clips, run by agents | Live since 2026-10-19; pauses at Studio's go (D66) ([status](clipper/docs/STATUS.md)) |
| [`studio/`](studio/) | Original AI character Shorts: a recurring animal cast in today's popping formats | Design only, waits for Lucas's go ([status](studio/docs/STATUS.md)) |

## Studio at a glance
- One new channel, one recurring cast of animals living adult human life; every Short plays a format that's popping in AI Shorts today, with an original story.
- Gemini Omni makes the shots, Claude writes, a radar follows the market, Lucas picks and approves in Telegram.
- 2-week test: 14 Shorts, $50 hard cap, Day-14 keep/kill numbers in [`studio/docs/STRATEGY.md`](studio/docs/STRATEGY.md).

## Clipper at a glance
- One Shorts channel, multi-streamer (Heat Index picks daily). Follows the market's format daily; every clip gets our hook + story captions + title. ≤60 s, max 5/day.
- **Live since 2026-10-19.** What runs now: [`clipper/docs/STATUS.md`](clipper/docs/STATUS.md).
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
studio/          design only: docs/, series/, formats/ + one README per future module (see studio/README.md)
```

## Quick start (on the VM)
```bash
sudo mkdir -p /opt/clipper && sudo chown "$USER": /opt/clipper
git clone https://github.com/waytooeasy/prm.git /opt/clipper/repo
bash /opt/clipper/repo/clipper/infra/setup.sh
cp /opt/clipper/repo/clipper/infra/.env.example /opt/clipper/.env   # then fill in, chmod 600
```
