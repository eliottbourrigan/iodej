#!/usr/bin/env bash
# Lancement local avec rechargement auto et données de démo.
#   ./scripts/dev.sh            → http://localhost:8000
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
uv sync
uv run iodej seed
uv run iodej codes
exec uv run iodej serve --host 0.0.0.0 --port "${PORT:-8000}" --reload
