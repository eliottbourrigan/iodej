"""Logique « du jour » : la journée change à minuit (fuseau configurable),
vérifié à chaque appel — pas de tâche planifiée."""
import json
import random
from datetime import date, datetime, timedelta

from . import config, db


def today() -> str:
    return datetime.now(config.TIMEZONE).date().isoformat()


def last_days(n: int = config.HISTORY_DAYS) -> list[str]:
    d = date.fromisoformat(today())
    return [(d - timedelta(days=i)).isoformat() for i in range(n)]


def get_shortlist_ids(conn, day: str | None = None) -> list[int]:
    """Retourne la shortlist du jour, en la tirant au sort si elle n'existe pas
    encore. Commune à tous les utilisateurs."""
    day = day or today()
    row = conn.execute("SELECT restaurant_ids FROM shortlists WHERE day = ?", (day,)).fetchone()
    if row:
        return json.loads(row["restaurant_ids"])
    with db.transaction(conn):
        row = conn.execute("SELECT restaurant_ids FROM shortlists WHERE day = ?", (day,)).fetchone()
        if row:  # un autre appel l'a créée entre-temps
            return json.loads(row["restaurant_ids"])
        ids = [r["id"] for r in conn.execute("SELECT id FROM restaurants WHERE active = 1 AND kind = 'restaurant'")]
        if not ids:
            return []  # rien à tirer : on ne fige pas une liste vide
        picked = random.SystemRandom().sample(ids, min(config.SHORTLIST_SIZE, len(ids)))
        conn.execute(
            "INSERT INTO shortlists(day, restaurant_ids) VALUES (?, ?)", (day, json.dumps(picked))
        )
    return picked


def get_shortlist(conn, day: str | None = None) -> list:
    ids = get_shortlist_ids(conn, day)
    if not ids:
        return []
    rows = conn.execute(
        f"SELECT * FROM restaurants WHERE id IN ({','.join('?' * len(ids))})", ids
    ).fetchall()
    by_id = {r["id"]: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]  # ordre du tirage, ignore les supprimés


def reset_day(conn, day: str | None = None) -> None:
    day = day or today()
    with db.transaction(conn):
        conn.execute("DELETE FROM shortlists WHERE day = ?", (day,))
        conn.execute("DELETE FROM swipes WHERE day = ?", (day,))
        conn.execute("DELETE FROM meals WHERE day = ?", (day,))
