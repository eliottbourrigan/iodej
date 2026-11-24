"""Configuration via variables d'environnement (toutes optionnelles)."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("IODEJ_DATA_DIR", BASE_DIR.parent / "data")).resolve()
DB_PATH = DATA_DIR / "iodej.sqlite3"
UPLOAD_DIR = DATA_DIR / "uploads"

TIMEZONE = ZoneInfo(os.environ.get("IODEJ_TZ", "Europe/Paris"))
SHORTLIST_SIZE = int(os.environ.get("IODEJ_SHORTLIST_SIZE", "10"))
HISTORY_DAYS = 7

# Cookies "définitifs" : 10 ans.
COOKIE_MAX_AGE = 10 * 365 * 24 * 3600
COOKIE_SECURE = os.environ.get("IODEJ_COOKIE_SECURE", "0") == "1"

USER_COOKIE = "iodej_user"
KEY_COOKIE = "iodej_key"
ADMIN_COOKIE = "iodej_admin"
