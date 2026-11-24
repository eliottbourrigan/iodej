#!/usr/bin/env bash
# Mise à jour : récupère la dernière version, synchronise les dépendances, redémarre.
#   sudo ./scripts/update.sh
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="$(stat -c %U "$APP_DIR")"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
UV="$APP_HOME/.local/bin/uv"; [[ -x "$UV" ]] || UV="$(command -v uv)"

run() { if [[ $EUID -eq 0 ]]; then sudo -u "$APP_USER" -H bash -c "$1"; else bash -c "$1"; fi; }

run "'$APP_DIR/scripts/backup.sh'" || true
run "cd '$APP_DIR' && git pull --ff-only && '$UV' sync --frozen --no-dev"
if [[ $EUID -eq 0 ]]; then systemctl restart iodej; else sudo systemctl restart iodej; fi
echo "✔ Iodej mis à jour et redémarré."
