#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 22.04 / 24.04 server (OVH VPS or dedicated), run as root:
#   DOMAIN=app.example.com ADMIN_DOMAIN=admin.example.com ACME_EMAIL=you@example.com bash deploy/setup.sh
# Safe to run again (it keeps an existing .env and data).
set -euo pipefail

: "${DOMAIN:?Set DOMAIN, e.g. DOMAIN=app.example.com}"
: "${ADMIN_DOMAIN:?Set ADMIN_DOMAIN, e.g. ADMIN_DOMAIN=admin.example.com}"
: "${ACME_EMAIL:?Set ACME_EMAIL (for the HTTPS certificate)}"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "== 1. System updates, Docker, firewall"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y ca-certificates curl ufw unattended-upgrades fail2ban
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
# Only SSH and the web are open.
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
systemctl enable --now fail2ban unattended-upgrades

echo "== 2. Secrets (made once, kept in deploy/.env)"
if [ ! -f "$HERE/.env" ]; then
  rnd() { python3 -c "import secrets; print(secrets.token_hex($1 // 2))"; }
  fernet=$(python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
  cat > "$HERE/.env" <<ENV
DOMAIN=$DOMAIN
ADMIN_DOMAIN=$ADMIN_DOMAIN
ACME_EMAIL=$ACME_EMAIL
POSTGRES_PASSWORD=$(rnd 32)
JWT_SECRET=$(rnd 64)
GATEWAY_WEBHOOK_SECRET=$(rnd 40)
TERMINAL_WEBHOOK_SECRET=$(rnd 40)
DATA_KEY=$fernet
CORS_ORIGINS=*
# Kiosk and status board are "Coming soon"; set COMING_SOON= (empty) to switch them on.
COMING_SOON=kiosk,status
ENV
  chmod 600 "$HERE/.env"
  echo "   wrote $HERE/.env (keep a copy somewhere safe: DATA_KEY decrypts saved payment keys)"
else
  echo "   keeping the existing $HERE/.env"
fi
mkdir -p "$HERE/backups"

echo "== 3. Build and start"
cd "$HERE"
docker compose up -d --build
echo "   waiting for the app..."
for i in $(seq 1 60); do
  if docker compose exec -T app python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/v1/health')" 2>/dev/null; then
    break
  fi
  sleep 3
done
docker compose ps

echo
echo "Done. Next:"
echo "  - Make our team's login (once):"
echo "      cd $HERE && docker compose exec app uv run --no-sync kiosk create-platform-admin --email you@company.lk --password 'a long password'"
echo "  - Our team: https://$ADMIN_DOMAIN   Restaurants: https://$DOMAIN/<code>/owner"
