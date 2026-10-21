#!/usr/bin/env bash
# setup.sh — bootstrap the clipper on Ubuntu 24.04 (home Hyper-V VM or any VPS)
# Usage (from anywhere):  bash clipper/infra/setup.sh
# Expects the repo at /opt/clipper/repo (git clone https://github.com/waytooeasy/prm.git /opt/clipper/repo).
# Idempotent: safe to run again after pulling new code.
# --units-only: just install + enable the systemd units (step 8).
# --cron-only:  just (re)install the daily yt-dlp update cron (step 6).
set -euo pipefail

CLIP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo/clipper
DATA="${CLIPPER_DATA:-/opt/clipper}"                      # runtime data (not in git)
UNIT_DIR="${UNIT_DIR:-/etc/systemd/system}"
SUDO="${SUDO-sudo}"                                       # SUDO="" in tests
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
CRONTAB="${CRONTAB:-crontab}"

install_units() {
  echo "== 8. systemd units (copy, daemon-reload, enable)"
  $SUDO mkdir -p "$UNIT_DIR"
  $SUDO cp "$CLIP"/infra/systemd/clipper-* "$UNIT_DIR"/
  $SUDO $SYSTEMCTL daemon-reload
  $SUDO $SYSTEMCTL enable clipper-pipeline.timer clipper-upload.timer clipper-remake.timer clipper-approve-bot.service
  $SUDO $SYSTEMCTL start clipper-pipeline.timer clipper-upload.timer clipper-remake.timer clipper-approve-bot.service
}

install_ytdlp_cron() {
  echo "== 6. Keep yt-dlp fresh (daily)"
  # A fresh box has no crontab (crontab -l exits 1) and grep -v on empty input exits 1;
  # under set -e/pipefail either one used to kill setup.sh silently here.
  local current
  current="$($CRONTAB -l 2>/dev/null || true)"
  { printf '%s\n' "$current" | grep -v -e 'yt-dlp' -e '^$' || true
    echo "17 4 * * * $DATA/venv/bin/pip install -q --upgrade yt-dlp >> $DATA/logs/ytdlp-update.log 2>&1"
  } | $CRONTAB -
}

if [[ "$CLIP" != "$DATA/repo/clipper" ]]; then
  echo "ERROR: repo must live at $DATA/repo (found $CLIP/..)." >&2
  echo "  sudo mkdir -p $DATA && sudo chown \"\$USER\": $DATA && git clone https://github.com/waytooeasy/prm.git $DATA/repo" >&2
  exit 1
fi
if [[ "${1:-}" == "--units-only" ]]; then install_units; exit 0; fi
if [[ "${1:-}" == "--cron-only" ]]; then install_ytdlp_cron; exit 0; fi
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

echo "== 5. Database (schema + ledger on a new DB, then pending migrations; idempotent)"
CLIPPER_DB=$DATA/db/clip.db $DATA/venv/bin/python "$CLIP/db/migrate.py"

install_ytdlp_cron

echo "== 6b. Caption font (Montserrat, SIL OFL) + YuNet face model (OpenCV zoo) for the market-style layout"
mkdir -p "$DATA/fonts"
for f in Montserrat-Black Montserrat-ExtraBold; do
  [[ -s "$DATA/fonts/$f.ttf" ]] || curl -fsSL -o "$DATA/fonts/$f.ttf" \
    "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/$f.ttf" || echo "WARN: $f download failed (libass falls back)"
done
# condensed face the Jynxzi/CaseOh/Lacy clippers use (D49, SIL OFL)
[[ -s "$DATA/fonts/Anton-Regular.ttf" ]] || curl -fsSL -o "$DATA/fonts/Anton-Regular.ttf" \
  "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf" || echo "WARN: Anton download failed (libass falls back)"
mkdir -p "$DATA/models"
[[ -s "$DATA/models/face_detection_yunet_2023mar.onnx" ]] || curl -fsSL -o "$DATA/models/face_detection_yunet_2023mar.onnx" \
  "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
  || echo "WARN: face model download failed (layout falls back to centre crop)"

echo "== 7. Pre-download Whisper '$WHISPER_MODEL'"
$DATA/venv/bin/python - <<PY
from faster_whisper import WhisperModel
WhisperModel("$WHISPER_MODEL", device="cpu", compute_type="int8")
print("whisper $WHISPER_MODEL ready")
PY

install_units

echo
echo "DONE."; free -h; df -h /
echo "Test a clip:"
echo "  cd $DATA && $DATA/venv/bin/python $CLIP/editor/clip.py <VOD_URL> --model $WHISPER_MODEL --out $DATA/clips"
