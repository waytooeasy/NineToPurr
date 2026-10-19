# VM runbook: where it runs and how to get in

Source of truth for the box. Update this file when anything here changes. No secrets in this file.

## The machines
| | Host **moon** (Windows) | VM **prm-clipper** (Ubuntu) |
|---|---|---|
| What | Lucas's home PC: Windows 11 Pro, i5-12400, 32 GB, 2 TB NVMe | Hyper-V VM on moon, Ubuntu Server 24.04 |
| Size | — | 6 vCPU, 8 GB RAM, 80 GB disk (root LV only 38.5 GB, see "Open items") |
| Created by | — | `New-PRMVM.ps1` on moon (`C:\Users\apollo11\Downloads`), auto-starts with Windows |
| User | `apollo11` | `prm` (sudo needs a password) |
| LAN IP | — | `192.168.100.123` (DHCP, can change) |
| Tailscale IP | `100.75.233.34` | `100.73.94.67` (`tailscale up --ssh`) |
| Remote in | RDP, SSH, WinRM (Tailscale + LAN only) | SSH |

**Not PRM hardware:** `laptop-9au4kuc4` is Lucas's INFOCENTER work laptop. Never use it for PRM.

## Paths on the VM
| Path | What |
|---|---|
| `/opt/clipper/repo` | git clone of `waytooeasy/PRM` (setup.sh refuses any other path) |
| `/opt/clipper/venv` | Python 3.12 venv |
| `/opt/clipper/.env` | secrets, chmod 600, never in git. Template: `clipper/infra/.env.example` |
| `/opt/clipper/db/clip.db` | SQLite (migrations 001–008 applied) |
| `/opt/clipper/{clips,work,logs}` | rendered clips, scratch, logs |
| `/opt/clipper/actions-runner` | GitHub self-hosted runner `prm-vm` |

## How Claude gets a shell on the VM
Three ways in. Use the first that works.

### 1. SSH from the local shell on moon (Claude desktop app)
The chat must be linked to moon in the Claude desktop app, with the `project` folder (`C:\Users\apollo11\project`) connected. The local Linux shell then reaches the VM directly.
- Needs Claude's network access set to **All domains** (Settings → Capabilities). With the allowlist, direct TCP fails with "Network is unreachable".
- Key: `C:\Users\apollo11\project\.prm-ssh\id_ed25519` (comment `claude-cowork@moon`), `known_hosts` next to it. The public key is in `~prm/.ssh/authorized_keys` on the VM. Revoke: delete that line.
- Each new shell session: copy the key out of the mounted folder (mounted files show 0777):
  ```bash
  cp ~/mnt/project/.prm-ssh/id_ed25519 ~/k && chmod 600 ~/k
  ssh -i ~/k -o UserKnownHostsFile=$HOME/mnt/project/.prm-ssh/known_hosts prm@192.168.100.123 'cmd'
  ```
  If the LAN IP changed, use `100.73.94.67` (Tailscale).

### 2. `vm-shell` runner (any cloud session, no link to moon needed)
- Comment on issue **#58** (label `vm-shell`) as `waytooeasy`:
  ````
  /vm
  ```bash
  cd /opt/clipper/repo && git log -1 --oneline
  ```
  ````
- The runner on the VM runs it as `prm` in `/opt/clipper` (25 min timeout) and replies with output + exit code. Workflow: `.github/workflows/vm-shell.yml`.
- Cloud sessions can't call the Actions API through the proxy. To see the job: read the reply comment, or `gh api repos/waytooeasy/PRM/commits/<main sha>/check-runs` (`queued` = runner offline).
- Service: `actions.runner.waytooeasy-PRM.prm-vm.service`, installed from `/opt/clipper/actions-runner` (`sudo ./svc.sh status|stop|start` from that folder).

### 3. Lucas over SSH
`ssh prm@100.73.94.67` from anywhere on his Tailscale network.

## What Claude can't do
- **sudo:** `prm` needs a password. Claude prepares the command; Lucas pastes it.
- **Typing into terminals on moon** (PowerShell, Windows Terminal): computer use allows view + click only.
- **Hyper-V Manager / VM console window:** they run as admin, so computer-use clicks are ignored.
- **From the cloud container alone:** no route to the home LAN or Tailscale.

## Gotchas we hit (2026-10-19)
- Windows PowerShell 5 has no `&&`. Linux commands go in the VM, not on the host.
- `setup.sh` died silently at step 6 on a fresh box (no crontab + `pipefail`). Fixed; steps 6–7 were then run by hand.
- Runner: `svc.sh` must run from `/opt/clipper/actions-runner`. A runner started with `./run.sh` and paused with Ctrl+Z blocks the service; `kill %1` first.

## State (2026-10-19)
- ✅ VM up, Tailscale up, `setup.sh` steps 1–7 done, 171/171 tests pass on the VM, Whisper `small` downloaded, yt-dlp cron installed.
- ✅ Runner `prm-vm` online; `vm-shell` works.
- ❌ `/opt/clipper/.env` keys not filled (Twitch, Telegram, Anthropic, YouTube).
- ❌ Step 8 (systemd units/timers) not enabled yet. Enable only after `.env` is filled: `bash /opt/clipper/repo/clipper/infra/setup.sh --units-only` (needs sudo).

## Open items
- Root LV uses 38.5 of 76.9 GB. Grow it when clips need room: `sudo lvextend -r -l +100%FREE /dev/ubuntu-vg/ubuntu-lv`.
- Give the VM a DHCP reservation for `192.168.100.123`, or just use the Tailscale IP.
