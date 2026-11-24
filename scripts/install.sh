#!/usr/bin/env bash
# Installation sur un VPS Ubuntu (Hostinger ou autre), à lancer depuis le dépôt cloné :
#
#   sudo ./scripts/install.sh                      # HTTP sur le port 80 (IP du VPS)
#   sudo ./scripts/install.sh --domain dej.example.com   # HTTPS auto (Let's Encrypt via Caddy)
#
# Options : --domain <nom>  --port <port interne, défaut 8000>  --no-caddy
set -euo pipefail

DOMAIN=""
PORT=8000
WITH_CADDY=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --no-caddy) WITH_CADDY=0; shift ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1"; exit 1 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "Lance ce script avec sudo."; exit 1; }

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="$(stat -c %U "$APP_DIR")"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
SERVICE=iodej

say() { printf '\n\033[1;35m▶ %s\033[0m\n' "$*"; }

say "Paquets système"
apt-get update -qq
apt-get install -y -qq curl git ca-certificates >/dev/null

say "uv (gestionnaire Python) pour l'utilisateur $APP_USER"
UV="$APP_HOME/.local/bin/uv"
if [[ ! -x "$UV" ]]; then
  sudo -u "$APP_USER" -H bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh' >/dev/null
fi
"$UV" --version

say "Dépendances Python"
sudo -u "$APP_USER" -H bash -c "cd '$APP_DIR' && '$UV' sync --frozen --no-dev"

say "Base de données & codes d'accès"
sudo -u "$APP_USER" -H bash -c "cd '$APP_DIR' && '$UV' run --frozen --no-dev iodej codes"

say "Service systemd ($SERVICE)"
SECURE=0; [[ -n "$DOMAIN" ]] && SECURE=1
cat > /etc/systemd/system/$SERVICE.service <<UNIT
[Unit]
Description=Iodej — On mange où ?
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment=IODEJ_COOKIE_SECURE=$SECURE
Environment=IODEJ_TZ=${IODEJ_TZ:-Europe/Paris}
ExecStart=$UV run --frozen --no-dev iodej serve --host 127.0.0.1 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now $SERVICE
systemctl restart $SERVICE

if [[ $WITH_CADDY -eq 1 ]]; then
  say "Reverse proxy Caddy"
  if ! command -v caddy >/dev/null; then
    apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https gnupg >/dev/null
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
      | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
      > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq && apt-get install -y -qq caddy >/dev/null
  fi
  SITE="${DOMAIN:-:80}"
  cat > /etc/caddy/Caddyfile <<CADDY
$SITE {
    encode zstd gzip
    reverse_proxy 127.0.0.1:$PORT
}
CADDY
  systemctl enable caddy >/dev/null
  systemctl reload caddy || systemctl restart caddy
  if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
    ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
  fi
fi

sleep 2
if curl -fs "http://127.0.0.1:$PORT/healthz" >/dev/null; then
  say "C'est en ligne !"
else
  echo "⚠ Le service ne répond pas encore : journalctl -u $SERVICE -n 50"
fi
IP="$(curl -fs https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
echo "  URL     : ${DOMAIN:+https://$DOMAIN}${DOMAIN:-http://$IP}"
echo "  Admin   : …/admin"
echo "  Codes   : sudo -u $APP_USER $UV run iodej codes   (depuis $APP_DIR)"
echo "  Logs    : journalctl -u $SERVICE -f"
