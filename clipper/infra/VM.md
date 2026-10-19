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

## Host moon: how it was set up (HQ chat, 2026-10-19)
Scripts live in `clipper/infra/windows/`. Run them in PowerShell as Administrator: `Set-ExecutionPolicy -Scope Process Bypass -Force`.

**1. `Enable-PRMRemote.ps1`** (run with `-OpenToAll`; re-check anytime with `-CheckOnly`)
- **Turned on:**
  - RDP, with Network Level Authentication (NLA) required
  - OpenSSH Server, with PowerShell as the default shell
  - WinRM / PowerShell remoting on :5985
  - SMB file sharing and network discovery
  - ping (ICMP)
  - Remote Assistance and Remote Registry
  - Tailscale, unattended mode, so it connects before anyone logs in
- **Firewall scope:** the rules are open to **any** address, not Tailscale/LAN only. The PC is safe only because it sits behind the home router's NAT. **Never add a port forward** on the router to moon. To tighten it, re-run without `-OpenToAll` (Tailscale `100.64.0.0/10` + LocalSubnet).
- **Power:** no sleep or hibernate on AC power, fast startup off, Wake-on-LAN on in the NIC driver. Wake-on-LAN also needs the BIOS setting; not yet confirmed.
- **Check results:** all PASS except RustDesk (winget couldn't find the package; not needed, since RDP works) and VMware (not used).
- **Reboot survival:** confirmed. TermService, sshd and Tailscale are all Automatic. BitLocker has no PIN, so moon reboots unattended and comes back over Tailscale.

**2. `New-PRMVM.ps1`**
- 1st run: enables Hyper-V, then reboot.
- 2nd run:
  - downloads the latest Ubuntu 24.04 live-server ISO into `C:\PRM\vm`
  - creates the external switch `PRM-External`; this drops the network for about 5 s and can cut an RDP session
  - creates the Gen2 VM `prm-clipper` with Secure Boot (UEFI CA), 6 vCPU, 8 GB RAM, an 80 GB disk and no checkpoints, set to auto-start 30 s after Windows boots

**Why Hyper-V and not VMware (D2 updated by HQ):** Hyper-V is built into Windows 11 Pro, costs $0, auto-starts VMs and is scriptable. VMware was never installed. A `192.168.56.1` adapter (probably VirtualBox) also exists on moon; ignore it.

**Claude access to moon:** link the chat in the **Claude desktop app on moon** ("Link to this computer"). From the cloud container, Tailscale is blocked by the egress proxy (tested 2026-10-19: controlplane, derp and pkgs all rejected).

## Security notes on `vm-shell` (HQ review, 2026-10-19)
- `github.actor == 'waytooeasy'` also matches the `PRM_BOT_TOKEN` PAT. Anything holding that token can run commands on the VM. Keep the PAT scoped to this repo only, rotate it if it ever leaks, and never echo it in logs.
- The runner is `self-hosted`. Any workflow file pushed to any branch could target it, and `pull_request` workflows run the branch's own copy. Build agents must never edit `.github/workflows/`; that is a rule in CLAUDE.md. In practice the Claude GitHub App can't push workflow files without the `workflows` permission, so don't grant it.
- `prm` can read `/opt/clipper/.env` (Anthropic, Twitch, Telegram and YouTube secrets). Never `cat` it through vm-shell, because the output becomes an issue comment. Use `grep -c '=' .env` or `cut -d= -f1 .env` to check which keys are present.
- Recommended hardening (HQ to apply, workflow edit): add `github.event.comment.author_association == 'OWNER'` to the `if:`, and give the runner a custom label `prm-vm` used only by `vm-shell.yml`.

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

## State (2026-10-19, evening)
- ✅ VM, Tailscale, `setup.sh` steps 1–7, Whisper `small`, yt-dlp cron, runner `prm-vm` + `vm-shell`.
- ✅ `.env` keys all verified live: Anthropic, YouTube API key, YouTube OAuth upload token (`/opt/clipper/youtube_token.json`, consent screen published with the GitHub Pages home/privacy pages), Twitch, Telegram (`@PRM_Clips_BOT`, chat id set).
- ✅ First real pipeline passes run by hand (`/opt/clipper/work/firstpass.sh`): 5 Twitch clips → captured → rendered → `qc_passed`. Fixes in PR #63.
- ❌ YouTube blocks yt-dlp from this IP ("confirm you're not a bot"): YouTube VOD source empty, issue #64 (needs-hq).
- ❌ Step 8 (systemd units/timers + approval bot) not enabled: `bash /opt/clipper/repo/clipper/infra/setup.sh --units-only` (needs sudo) after #63 is merged and the VM repo is back on `main`.

## Open items
- Root LV uses 38.5 of 76.9 GB. Grow it when clips need room: `sudo lvextend -r -l +100%FREE /dev/ubuntu-vg/ubuntu-lv`.
- Give the VM a DHCP reservation for `192.168.100.123`, or just use the Tailscale IP.
