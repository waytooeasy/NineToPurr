# PRM
# HOPE

**PRM = Puro Rico o Muerto.** One repo for every PRM project; one folder per project.

| Folder | Project | Status |
|---|---|---|
| [`clipper/`](clipper/) | YouTube Shorts channel of big-streamer clips, run by agents | Phase 0 |

## Clipper at a glance
- One Shorts channel, multi-streamer (Kai Cenat first). Every clip gets our angle: context line + story captions. ≤60 s, 3–5/day.
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
```

## Quick start (on the VM)
```bash
sudo mkdir -p /opt/clipper && sudo chown "$USER": /opt/clipper
git clone https://github.com/waytooeasy/prm.git /opt/clipper/repo
bash /opt/clipper/repo/clipper/infra/setup.sh
cp /opt/clipper/repo/clipper/infra/.env.example /opt/clipper/.env   # then fill in, chmod 600
```
