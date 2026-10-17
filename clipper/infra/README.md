# Infra

**Scope:** the box. Ubuntu 24.04 VM (VMware, Win 11 host: i5-12400, 32 GB, 2 TB). Suggested VM: 6 vCPU, 8 GB RAM, 80 GB disk. Auto-start via Task Scheduler (`vmrun -T ws start <vmx> nogui`). Remote access: Tailscale.

**Status:** `setup.sh` ready (packages, firewall, fail2ban, venv, DB via `db/migrate.py` (new DB or pending migrations, idempotent), Whisper model). systemd units for the pipeline and the approval bot ready (D27).

**Run:** `bash clipper/infra/setup.sh`

## systemd units (`systemd/`)
| Unit | What |
|---|---|
| `clipper-pipeline.service` | One pass of `run_pipeline.py`: radar → capture → writer/editor → qc → rerender. `Type=oneshot`. Overlapping runs exit at once (flock on `/opt/clipper/pipeline.lock`). |
| `clipper-pipeline.timer` | Starts the service 2 min after boot, then 20 min after each pass finishes. |
| `clipper-approve-bot.service` | Telegram approval bot (`publisher/approve_bot.py`), always on, `Restart=always`. |

These replace `clipper-radar.service/.timer` (radar is now the first stage of the pipeline pass).

All units read `/opt/clipper/.env` (`ANTHROPIC_API_KEY`, `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_ID`) and set `CLIPPER_DB=/opt/clipper/db/clip.db`. Repo is expected at `/opt/clipper/repo`, venv at `/opt/clipper/venv`.

### Enable on the VM
```
sudo systemctl disable --now clipper-radar.timer 2>/dev/null; sudo rm -f /etc/systemd/system/clipper-radar.{service,timer}
sudo cp /opt/clipper/repo/clipper/infra/systemd/clipper-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now clipper-pipeline.timer clipper-approve-bot.service
```
Check: `systemctl list-timers clipper-pipeline.timer`, `journalctl -u clipper-pipeline -n 50`, `journalctl -u clipper-approve-bot -f`.
Run one pass by hand: `sudo systemctl start clipper-pipeline.service`. Pause: `sudo systemctl stop clipper-pipeline.timer`.
After a deploy re-run `setup.sh` (applies new migrations, e.g. `005_qc`) and `daemon-reload` if a unit file changed.

## Next
Publisher unit once the YouTube upload exists; daily Analyst timer.
