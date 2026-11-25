"""Notifications Web Push (rappel du midi).

- Les clés VAPID (identité du serveur auprès d'Apple/Google) sont générées une
  fois et stockées dans `settings`.
- Chaque appareil abonné est une ligne de `push_subscriptions`.
- `send_daily()` est appelé par une tâche planifiée (systemd timer) à 11h30 et
  11h55, du lundi au vendredi.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush

from . import config, daily, db

log = logging.getLogger("iodej.push")

MESSAGES = {
    "first": ("IODEJ", "🍔 C'est l'heure de choisir !"),
    "reminder": ("IODEJ", "Plus que 5 minutes ! Merci de respecter les process !"),
    "test": ("IODEJ", "🔔 Notification de test : tout fonctionne !"),
}


# --------------------------------------------------------------------------- clés VAPID

def ensure_keys(conn) -> None:
    if db.get_setting(conn, "vapid_private_pem"):
        return
    v = Vapid02()
    v.generate_keys()
    db.set_setting(conn, "vapid_private_pem", v.private_pem().decode())


def _vapid(conn) -> Vapid02:
    ensure_keys(conn)
    return Vapid02.from_pem(db.get_setting(conn, "vapid_private_pem").encode())


def public_key(conn) -> str:
    """Clé publique au format attendu par `pushManager.subscribe` (base64url)."""
    raw = _vapid(conn).public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# --------------------------------------------------------------------------- abonnements

def subscribe(conn, user_id: int, sub: dict) -> None:
    endpoint = sub["endpoint"]
    keys = sub["keys"]
    # Un appareil = un abonnement : s'il change d'utilisateur, on le réattribue.
    conn.execute(
        "INSERT INTO push_subscriptions(endpoint, user_id, p256dh, auth) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(endpoint) DO UPDATE SET user_id = excluded.user_id, "
        "p256dh = excluded.p256dh, auth = excluded.auth",
        (endpoint, user_id, keys["p256dh"], keys["auth"]),
    )


def unsubscribe(conn, endpoint: str) -> None:
    conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))


# --------------------------------------------------------------------------- envoi

def recipients(conn, day: str) -> list:
    """Abonnements des collègues qui n'ont encore rien fait aujourd'hui :
    ni fini leurs swipes, ni choisi un resto ou un statut (télétravail…)."""
    shortlist = daily.get_shortlist_ids(conn, day)
    n = len(shortlist)
    rows = conn.execute(
        "SELECT ps.*, "
        " (SELECT COUNT(*) FROM swipes s WHERE s.day = ? AND s.user_id = ps.user_id) AS swiped, "
        " (SELECT COUNT(*) FROM meals m WHERE m.day = ? AND m.user_id = ps.user_id) AS has_meal "
        "FROM push_subscriptions ps",
        (day, day),
    ).fetchall()
    return [r for r in rows if not r["has_meal"] and (n == 0 or r["swiped"] < n)]


def _claims() -> dict:
    # Apple exige un « sub » en mailto: ou https:.
    return {"sub": os.environ.get("IODEJ_VAPID_SUB") or "mailto:iodej@example.com"}


def send(conn, rows, kind: str) -> dict:
    title, body = MESSAGES[kind]
    payload = json.dumps({"title": title, "body": body, "url": "/", "tag": f"iodej-{kind}"})
    vapid = _vapid(conn)
    stats = {"sent": 0, "removed": 0, "failed": 0}
    for r in rows:
        info = {"endpoint": r["endpoint"], "keys": {"p256dh": r["p256dh"], "auth": r["auth"]}}
        try:
            webpush(info, payload, vapid_private_key=vapid, vapid_claims=_claims(),
                    ttl=20 * 60, timeout=10)
            stats["sent"] += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):  # abonnement expiré ou révoqué
                unsubscribe(conn, r["endpoint"])
                stats["removed"] += 1
            else:
                log.warning("Échec d'envoi (%s) : %s", status, exc)
                stats["failed"] += 1
    return stats


def send_daily(conn, kind: str, force: bool = False) -> dict:
    now = datetime.now(config.TIMEZONE)
    if now.weekday() >= 5 and not force:
        return {"skipped": "week-end"}
    rows = recipients(conn, daily.today())
    return {"recipients": len(rows), **send(conn, rows, kind)}


def send_test(conn) -> dict:
    rows = conn.execute("SELECT * FROM push_subscriptions").fetchall()
    return {"recipients": len(rows), **send(conn, rows, "test")}
