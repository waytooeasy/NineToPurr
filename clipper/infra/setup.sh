#!/usr/bin/env bash
# setup.sh — bootstrap the clipper on Ubuntu 24.04 (home VMware VM or any VPS)
# Usage (from anywhere):  bash clipper/infra/setup.sh
# Idempotent: safe to run again after pulling new code.
set -euo pipefail

CLIP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo/clipper
DATA=/opt/clipper                                         # runtime data (not in git)
WHISPER_MODEL="${WHISPER_MODEL:-small}"                   # base on <4 GB RAM boxes

echo "== 1. System packages"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ffmpeg python3-venv python3-pip sqlite3 git curl jq unzip \
  ufw fail2ban unattended-upgrades fonts-dejavu-core fonts-liberation

echo "== 2. Swap only if RAM < 4 GB"
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if (( MEM_MB < 4000 )) && ! sudo swapon --show | grep -q /swapfile; then
  sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  WHISPER_MODEL="${WHISPER_MODEL_OVERRIDE:-base}"
fi

echo "== 3. Hardening: firewall (SSH only), fail2ban, auto security updates"
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow in on tailscale0 2>/dev/null || true
sudo ufw --force enable
sudo systemctl enable --now fail2ban
sudo dpkg-reconfigure -f noninteractive unattended-upgrades
sudo timedatectl set-timezone UTC

echo "== 4. Runtime dirs + Python env"
sudo mkdir -p $DATA/{work,clips,logs,db}
sudo chown -R "$USER":"$USER" $DATA
[[ -d $DATA/venv ]] || python3 -m venv $DATA/venv
$DATA/venv/bin/pip install --upgrade pip wheel
$DATA/venv/bin/pip install --upgrade -r "$CLIP/requirements.txt"

echo "== 5. Database"
if [[ ! -f $DATA/db/clip.db ]]; then
  sqlite3 $DATA/db/clip.db < "$CLIP/db/schema.sql"
  sqlite3 $DATA/db/clip.db < "$CLIP/db/ledger.sql"
  echo "created $DATA/db/clip.db"
fi

echo "== 6. Keep yt-dlp fresh (daily)"
( crontab -l 2>/dev/null | grep -v 'yt-dlp' ; \
  echo "17 4 * * * $DATA/venv/bin/pip install -q --upgrade yt-dlp >> $DATA/logs/ytdlp-update.log 2>&1" ) | crontab -

echo "== 7. Pre-download Whisper '$WHISPER_MODEL'"
$DATA/venv/bin/python - <<PY
from faster_whisper import WhisperModel
WhisperModel("$WHISPER_MODEL", device="cpu", compute_type="int8")
print("whisper $WHISPER_MODEL ready")
PY

echo
echo "DONE."; free -h; df -h /
echo "Test a clip:"
echo "  cd $DATA && $DATA/venv/bin/python $CLIP/editor/clip.py <VOD_URL> --model $WHISPER_MODEL --out $DATA/clips"
