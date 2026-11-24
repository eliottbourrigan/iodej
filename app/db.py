"""Accès SQLite (sqlite3 brut, sans ORM)."""
import sqlite3
from contextlib import contextmanager

from . import codes, config

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    photo       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS restaurants (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    photo       TEXT,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS shortlists (
    day            TEXT PRIMARY KEY,
    restaurant_ids TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS swipes (
    day           TEXT NOT NULL,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    liked         INTEGER NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (day, user_id, restaurant_id)
);
CREATE TABLE IF NOT EXISTS meals (
    day           TEXT NOT NULL,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    PRIMARY KEY (day, user_id)
);
CREATE INDEX IF NOT EXISTS idx_swipes_day ON swipes(day);
CREATE INDEX IF NOT EXISTS idx_meals_user ON meals(user_id, day);
"""


# Statuts du jour stockés comme des restaurants (kind != 'restaurant') :
# ils alimentent l'historique mais ne sont jamais tirés au sort.
SPECIALS = {
    "remote": ("Télétravail", "Je suis en télétravail", "🏠"),
    "lunchbox": ("Gamelle", "J'ai ramené ma gamelle", "🍱"),
    "client": ("Chez le client", "Je suis chez le client", "💼"),
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def get_db():
    """Dépendance FastAPI : une connexion par requête."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def get_setting(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def init() -> dict[str, str]:
    """Crée le schéma et les codes manquants. Retourne les codes créés."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    created: dict[str, str] = {}
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _migrate(conn)
        if get_setting(conn, "access_code") is None:
            created["access_code"] = codes.generate_code(3)
            set_setting(conn, "access_code", created["access_code"])
        if get_setting(conn, "admin_code") is None:
            created["admin_code"] = codes.generate_code(4)
            set_setting(conn, "admin_code", created["admin_code"])
    finally:
        conn.close()
    return created


def _migrate(conn) -> None:
    """Migrations additives et idempotentes : aucune donnée existante n'est modifiée."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(restaurants)")}
    if "kind" not in cols:
        conn.execute("ALTER TABLE restaurants ADD COLUMN kind TEXT NOT NULL DEFAULT 'restaurant'")
    for kind, (name, description, _emoji) in SPECIALS.items():
        if conn.execute("SELECT 1 FROM restaurants WHERE kind = ?", (kind,)).fetchone() is None:
            conn.execute(
                "INSERT INTO restaurants(name, description, kind) VALUES (?, ?, ?)",
                (name, description, kind),
            )


def special_id(conn, kind: str) -> int:
    return conn.execute("SELECT id FROM restaurants WHERE kind = ?", (kind,)).fetchone()["id"]


def special_rows(conn) -> dict:
    """{kind: ligne restaurants} dans l'ordre de SPECIALS."""
    rows = {r["kind"]: r for r in conn.execute("SELECT * FROM restaurants WHERE kind != 'restaurant'")}
    return {k: rows[k] for k in SPECIALS if k in rows}
