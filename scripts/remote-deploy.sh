#!/usr/bin/env bash
# Déploiement côté VPS, appelé par GitHub Actions après l'envoi du code dans un
# dossier temporaire :   sudo bash <release>/scripts/remote-deploy.sh --domain iodej.ebgn.fr
#
# - utilisateur dédié « iodej », code dans /home/iodej/app, données dans /home/iodej/data
#   (les données ne sont jamais écrasées par un déploiement) ;
# - reprend les données d'une ancienne installation manuelle (git clone) si besoin ;
# - sauvegarde avant chaque mise à jour.
set -euo pipefail

DOMAIN=""
PORT=8000
SERVICE=iodej
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --service) SERVICE="$2"; shift 2 ;;
    *) echo "Option inconnue : $1"; exit 1 ;;
  esac
done
[[ $EUID -eq 0 ]] || { echo "À lancer en root (ou sudo)."; exit 1; }

RELEASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="$SERVICE"
HOME_DIR="/home/$APP_USER"
APP_DIR="$HOME_DIR/app"
DATA_DIR="$HOME_DIR/data"
say() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

FIRST=0
if ! id "$APP_USER" >/dev/null 2>&1; then
  say "Création de l'utilisateur $APP_USER"
  useradd --create-home --home-dir "$HOME_DIR" --shell /usr/sbin/nologin "$APP_USER"
  FIRST=1
fi
[[ -f /etc/systemd/system/$SERVICE@.service || -f /etc/systemd/system/$SERVICE.service ]] || FIRST=1
mkdir -p "$APP_DIR" "$DATA_DIR"

# Ancienne installation (git clone + install.sh) : on récupère sa base et ses photos.
OLD_DIR="$(systemctl show -p WorkingDirectory --value "$SERVICE" 2>/dev/null || true)"
if [[ -n "$OLD_DIR" && "$OLD_DIR" != "$APP_DIR" && -f "$OLD_DIR/data/iodej.sqlite3" \
      && ! -f "$DATA_DIR/iodej.sqlite3" ]]; then
  say "Reprise des données de l'ancienne installation ($OLD_DIR/data)"
  systemctl stop "$SERVICE" || true
  cp -a "$OLD_DIR/data/." "$DATA_DIR/"
  FIRST=1
fi

if [[ -f "$DATA_DIR/iodej.sqlite3" ]]; then
  say "Sauvegarde"
  IODEJ_DATA_DIR="$DATA_DIR" bash "$RELEASE/scripts/backup.sh" || echo "⚠ sauvegarde impossible"
  mkdir -p "$HOME_DIR/backups"
  mv "$RELEASE"/backups/*.tar.gz "$HOME_DIR/backups/" 2>/dev/null || true
  ls -1t "$HOME_DIR"/backups/iodej-*.tar.gz 2>/dev/null | tail -n +31 | xargs -r rm --
fi

say "Mise à jour du code"
command -v rsync >/dev/null || { apt-get update -qq && apt-get install -y -qq rsync >/dev/null; }
rsync -a --delete --exclude data --exclude .venv --exclude backups "$RELEASE/" "$APP_DIR/"
chown -R "$APP_USER": "$HOME_DIR"

ARGS=(--port "$PORT" --data-dir "$DATA_DIR" --service "$SERVICE")
[[ -n "$DOMAIN" ]] && ARGS+=(--domain "$DOMAIN")
[[ $FIRST -eq 0 ]] && ARGS+=(--skip-system)
bash "$APP_DIR/scripts/install.sh" "${ARGS[@]}"

rm -rf "$RELEASE"
