import sqlite3

from app import config, db

OLD_SCHEMA = """
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '', photo TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE restaurants (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '', photo TEXT, active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE meals (day TEXT NOT NULL, user_id INTEGER NOT NULL, restaurant_id INTEGER NOT NULL,
  PRIMARY KEY (day, user_id));
INSERT INTO settings VALUES ('access_code', 'aaaa-bbbb-cccc'), ('admin_code', 'dddd-eeee-ffff-gggg');
INSERT INTO users(name) VALUES ('Alice');
INSERT INTO restaurants(name, photo) VALUES ('Vieux resto', 'x.webp');
INSERT INTO meals VALUES ('2026-01-01', 1, 1);
"""


def test_existing_database_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "old.sqlite3")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    old = sqlite3.connect(config.DB_PATH)
    old.executescript(OLD_SCHEMA)
    old.close()

    assert db.init() == {}  # les codes existants sont conservés
    db.init()  # idempotent
    conn = db.connect()
    assert db.get_setting(conn, "access_code") == "aaaa-bbbb-cccc"
    vieux = conn.execute("SELECT * FROM restaurants WHERE id = 1").fetchone()
    assert (vieux["name"], vieux["photo"], vieux["kind"]) == ("Vieux resto", "x.webp", "restaurant")
    assert conn.execute("SELECT COUNT(*) FROM meals").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    kinds = [r["kind"] for r in conn.execute("SELECT kind FROM restaurants WHERE kind != 'restaurant'")]
    assert sorted(kinds) == ["client", "lunchbox", "remote"]
