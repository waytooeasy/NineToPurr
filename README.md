# PRM
# HOPE

**PRM = Puro Rico o Muerto.** One repo for every PRM project; one folder per project.

| Folder | Project | Status |
|---|---|---|
| [`clipper/`](clipper/) | YouTube Shorts channel of big-streamer clips, run by agents | Phase 0 |

## Clipper at a glance
- Our own Shorts channel. Streamer audio, big hook captions, trending edit formats, many Shorts/day. Kai Cenat first.
- Paid by YouTube Shorts ads. Goal ≈ 6.7M PYG/month net.
- Runs on a home Ubuntu VM (VMware), reached over Tailscale.
- Strategy: [`clipper/docs/STRATEGY.md`](clipper/docs/STRATEGY.md)

## Layout
```
clipper/
├── docs/        strategy + module notes
├── infra/       setup.sh, systemd units
├── db/          schema.sql, math.sql, ledger.sql
├── radar/       find hot moments (Twitch)
├── editor/      clip.py: cut, 9:16, captions
├── publisher/   YouTube uploads
└── analyst/     metrics, ledger, daily report
```

## Quick start (on the VM)
```bash
git clone https://github.com/waytooeasy/prm.git ~/prm
bash ~/prm/clipper/infra/setup.sh
```
