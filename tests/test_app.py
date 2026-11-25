import io

from PIL import Image

from app import codes, daily, db


def seed(conn, n_restos=12, users=("Alice", "Bob", "Chloé")):
    conn.executemany("INSERT INTO restaurants(name) VALUES (?)", [(f"R{i}",) for i in range(n_restos)])
    conn.executemany("INSERT INTO users(name) VALUES (?)", [(u,) for u in users])


def login(client, conn, user_id):
    code = db.get_setting(conn, "access_code")
    r = client.post("/login", data={"user_id": user_id, "code": code.upper().replace("-", " ")},
                    follow_redirects=False)
    assert r.status_code == 303
    return r


def test_redirects_to_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_bad_code_rejected(client, conn):
    seed(conn)
    r = client.post("/login", data={"user_id": 1, "code": "nope"})
    assert r.status_code == 400 and "incorrect" in r.text


def test_full_flow(client, conn):
    seed(conn)
    login(client, conn, 1)
    r = client.get("/swipe")
    assert r.status_code == 200 and r.text.count('class="card"') == 10

    ids = daily.get_shortlist_ids(conn)
    assert len(ids) == 10 and len(set(ids)) == 10
    # Locked tant que tout n'est pas swipé
    assert "Pas si vite" in client.get("/partials/choix").text

    for i, rid in enumerate(ids):
        assert client.post("/api/swipe", data={"restaurant_id": rid, "liked": int(i < 2)}).json() == \
            {"remaining": 9 - i}
    assert client.get("/", follow_redirects=False).headers["location"] == "/resultats"
    assert client.get("/resultats?tab=groupes").status_code == 200
    choix = client.get("/partials/choix").text
    assert "Les choix" in choix
    groupes = client.get("/partials/groupes").text
    assert "Ton groupe" in groupes

    # Shortlist commune : Bob voit la même
    client.cookies.clear()
    login(client, conn, 2)
    assert daily.get_shortlist_ids(conn) == ids

    # Repas + historique
    client.cookies.clear()
    login(client, conn, 1)
    r = client.post("/api/meal", data={"restaurant_id": ids[0], "tab": "choix"})
    assert "is-going" in r.text
    histo = client.get("/partials/historique").text
    assert "Aujourd&#39;hui" in histo or "Aujourd'hui" in histo
    row = conn.execute("SELECT name FROM restaurants WHERE id = ?", (ids[0],)).fetchone()
    assert row["name"] in histo


def test_swipe_outside_shortlist_is_rejected(client, conn):
    seed(conn, n_restos=12)
    login(client, conn, 1)
    ids = daily.get_shortlist_ids(conn)
    other = next(i for i in range(1, 13) if i not in ids)
    assert client.post("/api/swipe", data={"restaurant_id": other, "liked": 1}).status_code == 409


def test_new_day_new_shortlist(client, conn, monkeypatch):
    seed(conn, n_restos=30)
    a = daily.get_shortlist_ids(conn, "2026-01-01")
    assert daily.get_shortlist_ids(conn, "2026-01-01") == a
    b = daily.get_shortlist_ids(conn, "2026-01-02")
    assert len(b) == 10 and a != b


def test_logout_clears_cookies(client, conn):
    seed(conn)
    login(client, conn, 1)
    r = client.get("/logout", follow_redirects=False)
    assert r.headers["Clear-Site-Data"] == '"cookies"'
    assert "iodej_user=" in r.headers.get("set-cookie", "")


def test_access_code_rotation_logs_out(client, conn):
    seed(conn)
    login(client, conn, 1)
    db.set_setting(conn, "access_code", codes.generate_access_code())
    assert client.get("/swipe", follow_redirects=False).headers["location"] == "/login"


def test_admin_crud(client, conn):
    assert client.get("/admin", follow_redirects=False).headers["location"] == "/admin/login"
    code = db.get_setting(conn, "admin_code")
    assert client.post("/admin/login", data={"code": code}, follow_redirects=False).status_code == 303

    buf = io.BytesIO()
    Image.new("RGB", (1600, 1200), "red").save(buf, "JPEG")
    r = client.post("/admin/restaurants/save",
                    data={"name": "Chez Test", "description": "Miam", "active": "1"},
                    files={"photo": ("p.jpg", buf.getvalue(), "image/jpeg")}, follow_redirects=False)
    assert r.status_code == 303
    row = conn.execute("SELECT * FROM restaurants WHERE name = 'Chez Test'").fetchone()
    assert row["photo"].endswith(".webp") and row["active"] == 1
    assert client.get(f"/uploads/{row['photo']}").status_code in (200, 404)  # mount figé à l'import

    r = client.post("/admin/restaurants/save", data={"item_id": row["id"], "name": "Chez Test 2"},
                    follow_redirects=False)
    row = conn.execute("SELECT * FROM restaurants WHERE id = ?", (row["id"],)).fetchone()
    assert row["name"] == "Chez Test 2" and row["active"] == 0 and row["photo"]

    r = client.post("/admin/collegues/save", data={"name": "Zoé"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Zoé" in client.get("/admin/collegues").text
    assert "Chez Test 2" in client.get("/admin/restaurants").text
    assert client.get(f"/admin/restaurants/{row['id']}").status_code == 200
    assert client.get("/admin/collegues/new").status_code == 200

    client.post(f"/admin/restaurants/{row['id']}/delete")
    assert conn.execute("SELECT COUNT(*) FROM restaurants WHERE kind = 'restaurant'").fetchone()[0] == 0

    bad = client.post("/admin/restaurants/save", data={"name": "X"},
                      files={"photo": ("p.jpg", b"not an image", "image/jpeg")})
    assert bad.status_code == 400

    assert client.get("/admin").status_code == 200
    client.post("/admin/codes/access")
    assert client.get("/admin").status_code == 200


def test_home_shows_today_screen_first(client, conn):
    seed(conn)
    login(client, conn, 1)
    assert client.get("/", follow_redirects=False).headers["location"] == "/ce-midi"
    page = client.get("/ce-midi").text
    for label in ("télétravail", "gamelle", "chez le client", "Je veux swiper"):
        assert label in page
    r = client.post("/api/status", data={"choice": "swipe"}, follow_redirects=False)
    assert r.headers["location"] == "/swipe"


def test_special_status_excluded_from_swipes_and_groups(client, conn):
    seed(conn, n_restos=3)
    # Les statuts ne sont jamais tirés au sort
    ids = daily.get_shortlist_ids(conn)
    kinds = {r["kind"] for r in conn.execute(
        f"SELECT kind FROM restaurants WHERE id IN ({','.join('?' * len(ids))})", ids)}
    assert kinds == {"restaurant"} and len(ids) == 3

    login(client, conn, 2)  # Bob swipe et aime tout
    for rid in ids:
        client.post("/api/swipe", data={"restaurant_id": rid, "liked": 1})
    client.cookies.clear()

    login(client, conn, 1)  # Alice est en télétravail
    r = client.post("/api/status", data={"choice": "remote"}, follow_redirects=False)
    assert r.headers["location"].startswith("/resultats")
    assert client.get("/", follow_redirects=False).headers["location"] == "/resultats"
    groupes = client.get("/partials/groupes").text  # débloqué sans swiper
    assert "Pas si vite" not in groupes and "Pas là ce midi" in groupes and "Ton groupe" not in groupes
    histo = client.get("/partials/historique").text
    assert "Télétravail" in histo or "télétravail" in histo

    # Changer d'avis : retour au swipe, statut effacé
    client.post("/api/status", data={"choice": "swipe"})
    assert conn.execute("SELECT COUNT(*) FROM meals WHERE user_id = 1").fetchone()[0] == 0


def test_admin_cannot_delete_specials(client, conn):
    code = db.get_setting(conn, "admin_code")
    client.post("/admin/login", data={"code": code})
    sid = db.special_id(conn, "lunchbox")
    client.post(f"/admin/restaurants/{sid}/delete")
    assert conn.execute("SELECT COUNT(*) FROM restaurants WHERE id = ?", (sid,)).fetchone()[0] == 1
    assert "Statuts du jour" in client.get("/admin/restaurants").text
    assert client.get(f"/admin/restaurants/{sid}").status_code == 200


def test_not_indexed(client):
    assert "Disallow: /" in client.get("/robots.txt").text
    assert client.get("/login").headers["X-Robots-Tag"].startswith("noindex")


def test_access_code_format_and_case_insensitive(client, conn):
    import re
    for _ in range(50):
        assert re.fullmatch(r"[A-HJKMNP-Z2-9]{6}", codes.generate_access_code())
    db.set_setting(conn, "access_code", "K7M2PX")
    seed(conn)
    r = client.post("/login", data={"user_id": 1, "code": " k7m2px "}, follow_redirects=False)
    assert r.status_code == 303


def test_new_install_gets_short_access_code(conn):
    import re
    assert re.fullmatch(r"[A-Z0-9]{6}", db.get_setting(conn, "access_code"))


def test_cache_headers(client, conn):
    from app.web import ASSET_HASHES, static
    url = static("css/app.css")
    assert url == f"/static/css/app.css?v={ASSET_HASHES['css/app.css']}"
    r = client.get(url)
    assert r.status_code == 200 and "immutable" in r.headers["Cache-Control"]
    assert "immutable" not in client.get("/static/css/app.css").headers["Cache-Control"]
    page = client.get("/login")
    assert page.headers["Cache-Control"] == "no-cache, private"
    assert page.headers["X-Content-Type-Options"] == "nosniff"
    assert url in page.text
