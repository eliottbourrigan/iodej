#!/usr/bin/env bash
# Sauvegarde à chaud de la base SQLite + photos dans ./backups (garde les 30 dernières).
#   ./scripts/backup.sh
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${IODEJ_DATA_DIR:-$APP_DIR/data}"
[[ -f "$DATA_DIR/iodej.sqlite3" ]] || { echo "Pas de base à sauvegarder."; exit 0; }
DEST="$APP_DIR/backups"; mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M%S)"
TMP="$(mktemp -d)"
python3 - "$DATA_DIR/iodej.sqlite3" "$TMP/iodej.sqlite3" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
src.backup(dst)
PY
tar -czf "$DEST/iodej-$STAMP.tar.gz" -C "$TMP" iodej.sqlite3 -C "$DATA_DIR" uploads
rm -rf "$TMP"
ls -1t "$DEST"/iodej-*.tar.gz | tail -n +31 | xargs -r rm --
echo "✔ Sauvegarde : $DEST/iodej-$STAMP.tar.gz"
