# Infra

**Scope:** the box. Ubuntu 24.04 VM (VMware, Win 11 host: i5-12400, 32 GB, 2 TB). Suggested VM: 6 vCPU, 8 GB RAM, 80 GB disk. Auto-start via Task Scheduler (`vmrun -T ws start <vmx> nogui`). Remote access: Tailscale.

**Status:** `setup.sh` ready (packages, firewall, fail2ban, venv, DB, Whisper model).

**Run:** `bash clipper/infra/setup.sh`

**Next:** systemd units for each module.
