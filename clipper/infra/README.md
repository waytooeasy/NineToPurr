# Infra

**Scope:** the box. Ubuntu 24.04 VM (VMware, Win 11 host: i5-12400, 32 GB, 2 TB). Suggested VM: 6 vCPU, 8 GB RAM, 80 GB disk. Auto-start via Task Scheduler (`vmrun -T ws start <vmx> nogui`). Remote access: Tailscale.

**Status:** `setup.sh` ready (packages, firewall, fail2ban, venv, DB via `db/migrate.py` (new DB or pending migrations, idempotent), Whisper model). systemd units for the pipeline and the approval bot ready (D27).

**Run:** clone to `/opt/clipper/repo`, then `bash /opt/clipper/repo/clipper/infra/setup.sh` (refuses to run from anywhere else). It also copies the units, runs `daemon-reload` and enables `clipper-pipeline.timer`, `clipper-upload.timer`, `clipper-approve-bot.service`. Re-run after a pull; `--units-only` skips the rest. Env vars: copy `.env.example` to `/opt/clipper/.env`.

## systemd units (`systemd/`)
| Unit | What |
|---|---|
| `clipper-pipeline.service` | One pass of `run_pipeline.py`: radar → capture → writer/editor → qc → rerender. `Type=oneshot`. Overlapping runs exit at once (flock on `/opt/clipper/pipeline.lock`). |
| `clipper-pipeline.timer` | Starts the service 2 min after boot, then 20 min after each pass finishes. |
| `clipper-upload.service` / `.timer` | One upload pass (`publisher/upload.py`), 15 min after the last pass finished. `Type=oneshot`. |
| `clipper-approve-bot.service` | Telegram approval bot (`publisher/approve_bot.py`), always on, `Restart=always`. |

These replace `clipper-radar.service/.timer` (radar is now the first stage of the pipeline pass).

All units read `/opt/clipper/.env` (`ANTHROPIC_API_KEY`, `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_ID`) and set `CLIPPER_DB=/opt/clipper/db/clip.db`. Repo is expected at `/opt/clipper/repo`, venv at `/opt/clipper/venv`.

### Enable on the VM
`setup.sh` does this (idempotent). By hand:
```
sudo systemctl disable --now clipper-radar.timer 2>/dev/null; sudo rm -f /etc/systemd/system/clipper-radar.{service,timer}
sudo cp /opt/clipper/repo/clipper/infra/systemd/clipper-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now clipper-pipeline.timer clipper-upload.timer clipper-approve-bot.service
```
Check: `systemctl list-timers clipper-pipeline.timer`, `journalctl -u clipper-pipeline -n 50`, `journalctl -u clipper-approve-bot -f`.
Run one pass by hand: `sudo systemctl start clipper-pipeline.service`. Pause: `sudo systemctl stop clipper-pipeline.timer`.
After a deploy re-run `setup.sh` (applies new migrations, e.g. `005_qc`) and `daemon-reload` if a unit file changed.

## Readiness and end-to-end test
- `../docs/READINESS.md`: ✅/❌ per module, exact first-run VM steps (including `upload.py --auth` on the Windows host and copying the token), top 5 risks.
- `../tests/test_e2e_offline.py` (runs in CI, needs ffmpeg): fresh DB via `db/migrate.py` → one `run_pipeline` pass with a Twitch + YouTube source (Twitch, yt-dlp, Whisper, LLM mocked; tiny synthetic video) → `qc_passed` → approve through the bot handlers → `approved` → `upload.run_once` with a fake uploader → `published`. Run: `pytest clipper/tests`.

## Next
Daily Analyst timer.
