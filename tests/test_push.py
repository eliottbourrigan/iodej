import base64
import json
import os
from datetime import datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app import daily, db, push


def fake_subscription(n=0):
    """Abonnement valide comme en produirait un navigateur (vraies clés EC)."""
    key = ec.generate_private_key(ec.SECP256R1())
    pub = key.public_key().public_bytes(serialization.Encoding.X962,
                                        serialization.PublicFormat.UncompressedPoint)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    return {"endpoint": f"https://push.example.com/sub/{n}",
            "keys": {"p256dh": b64(pub), "auth": b64(os.urandom(16))}}


class FakeResponse:
    def __init__(self, status):
        self.status_code = status
        self.text = ""
        self.headers = {}
        self.reason = "Gone" if status == 410 else "Created"


@pytest.fixture()
def sent(monkeypatch):
    calls = []

    def fake_post(url, data=None, headers=None, timeout=None, **kw):
        calls.append({"url": url, "headers": headers, "data": data})
        return FakeResponse(410 if "gone" in url else 201)

    import pywebpush
    monkeypatch.setattr(pywebpush.requests, "post", fake_post)
    return calls


def users(conn, *names):
    conn.executemany("INSERT INTO users(name) VALUES (?)", [(n,) for n in names])
    conn.executemany("INSERT INTO restaurants(name) VALUES (?)", [(f"R{i}",) for i in range(10)])


def login(client, conn, uid):
    client.post("/login", data={"user_id": uid, "code": db.get_setting(conn, "access_code")})


def test_public_key_is_valid_vapid_key(client, conn):
    users(conn, "Alice")
    login(client, conn, 1)
    key = client.get("/api/push/key").json()["key"]
    raw = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
    assert len(raw) == 65 and raw[0] == 4  # point EC non compressé
    assert push.public_key(conn) == key  # stable


def test_subscribe_unsubscribe_and_reassign(client, conn):
    users(conn, "Alice", "Bob")
    sub = fake_subscription()
    login(client, conn, 1)
    assert client.post("/api/push/subscribe", json=sub).json() == {"ok": True}
    assert client.post("/api/push/subscribe", json={"endpoint": "http://x"}).status_code == 400
    client.cookies.clear()
    login(client, conn, 2)  # même téléphone, autre collègue
    client.post("/api/push/subscribe", json=sub)
    rows = conn.execute("SELECT user_id FROM push_subscriptions").fetchall()
    assert [r["user_id"] for r in rows] == [2]
    client.post("/api/push/unsubscribe", json={"endpoint": sub["endpoint"]})
    assert conn.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0] == 0


def test_only_people_who_did_nothing_are_notified(client, conn, sent):
    users(conn, "Alice", "Bob", "Chloé", "David")
    for uid in (1, 2, 3, 4):
        push.subscribe(conn, uid, fake_subscription(uid))
    day = daily.today()
    ids = daily.get_shortlist_ids(conn, day)
    # Bob a fini de swiper, Chloé est en télétravail, David a swipé à moitié
    for rid in ids:
        conn.execute("INSERT INTO swipes(day, user_id, restaurant_id, liked) VALUES (?, 2, ?, 1)", (day, rid))
    conn.execute("INSERT INTO meals(day, user_id, restaurant_id) VALUES (?, 3, ?)", (day, db.special_id(conn, "remote")))
    conn.execute("INSERT INTO swipes(day, user_id, restaurant_id, liked) VALUES (?, 4, ?, 1)", (day, ids[0]))

    who = sorted(r["user_id"] for r in push.recipients(conn, day))
    assert who == [1, 4]

    stats = push.send(conn, push.recipients(conn, day), "reminder")
    assert stats == {"sent": 2, "removed": 0, "failed": 0}
    req = sent[0]
    assert req["url"].startswith("https://push.example.com/")
    assert req["headers"]["content-encoding"] == "aes128gcm"
    assert req["headers"]["authorization"].startswith("vapid t=")
    assert b"Plus que 5 minutes" not in req["data"]  # le contenu est bien chiffré


def test_expired_subscriptions_are_removed(conn, sent):
    users(conn, "Alice")
    gone = fake_subscription()
    gone["endpoint"] = "https://push.example.com/gone"
    push.subscribe(conn, 1, gone)
    assert push.send_test(conn) == {"recipients": 1, "sent": 0, "removed": 1, "failed": 0}
    assert conn.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0] == 0


def test_no_notification_on_weekends(conn, sent, monkeypatch):
    users(conn, "Alice")
    push.subscribe(conn, 1, fake_subscription())

    class Saturday(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 28, 11, 30, tzinfo=tz)

    monkeypatch.setattr(push, "datetime", Saturday)
    assert push.send_daily(conn, "first") == {"skipped": "week-end"}
    assert push.send_daily(conn, "first", force=True)["sent"] == 1


def test_messages():
    assert push.MESSAGES["first"][1] == "🍔 C'est l'heure de choisir !"
    assert push.MESSAGES["reminder"][1] == "Plus que 5 minutes ! Merci de respecter les process !"


def test_admin_test_button(client, conn, sent):
    users(conn, "Alice")
    push.subscribe(conn, 1, fake_subscription())
    client.post("/admin/login", data={"code": db.get_setting(conn, "admin_code")})
    r = client.post("/admin/push/test")
    assert "1 envoy" in r.text and "1 appareil" in r.text
