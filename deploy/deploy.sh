#!/bin/bash
# Usage: ./deploy/deploy.sh <droplet-ip>
# Run from your local machine in the weather-bot directory.
# Requires: ssh key set up for root@<droplet-ip>

set -e

IP=$1
if [ -z "$IP" ]; then
  echo "Usage: $0 <droplet-ip>"
  exit 1
fi

echo "==> Deploying to $IP"

# 1. Copy project files (exclude secrets and caches)
rsync -avz --progress \
  --exclude '.env' \
  --exclude 'api_keys/' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'logs/' \
  --exclude '.tmp/' \
  ./ root@$IP:/root/weather-bot/

# 2. Copy secrets separately (never in git)
echo "==> Uploading .env and private key"
scp .env root@$IP:/root/weather-bot/.env
ssh root@$IP "mkdir -p /root/weather-bot/api_keys"
scp api_keys/*.pem root@$IP:/root/weather-bot/api_keys/

# 3. Install dependencies + tmux + gemini CLI
ssh root@$IP << 'REMOTE'
  cd /root/weather-bot
  pip3 install -r requirements.txt -q
  sudo apt-get install -y tmux -q
  # Install Gemini CLI if not present
  if ! command -v gemini &> /dev/null; then
    echo "NOTE: Gemini CLI not found. Install manually: https://github.com/google-gemini/gemini-cli"
    echo "      Reddit research will be skipped until it is installed."
  fi
REMOTE

# 4. Install and start systemd service
echo "==> Installing systemd service"
scp deploy/kalshi-bot.service root@$IP:/tmp/kalshi-bot.service
ssh root@$IP << 'REMOTE'
  sudo mv /tmp/kalshi-bot.service /etc/systemd/system/kalshi-bot.service
  sudo systemctl daemon-reload
  sudo systemctl enable kalshi-bot
  sudo systemctl restart kalshi-bot
  echo "==> Service status:"
  sudo systemctl status kalshi-bot --no-pager
REMOTE

echo ""
echo "==> Deploy complete."
echo "    View live logs:  ssh root@$IP 'journalctl -u kalshi-bot -f'"
echo "    View trade logs: ssh root@$IP 'cat /root/weather-bot/logs/trades_\$(date +%Y-%m-%d).json'"
echo "    Stop bot:        ssh root@$IP 'sudo systemctl stop kalshi-bot'"
