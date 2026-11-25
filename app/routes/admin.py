"""Backoffice : CRUD restaurants & collègues, gestion des codes."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from .. import codes, config, daily, db, images, push
from ..auth import is_admin, require_admin, set_cookie
from ..web import render

router = APIRouter(prefix="/admin")

ENTITIES = {
    "restaurants": {
        "table": "restaurants",
        "label": "Restaurants",
        "one": "restaurant",
        "new": "Nouveau restaurant",
        "photo_required": False,
        "has_active": True,
        "emoji": "🍽️",
    },
    "collegues": {
        "table": "users",
        "label": "Collègues",
        "one": "collègue",
        "new": "Nouveau collègue",
        "photo_required": False,
        "has_active": False,
        "emoji": "🧑‍🍳",
    },
}


def _back(path: str, msg: str | None = None):
    url = path + (f"?msg={quote(msg)}" if msg else "")
    return RedirectResponse(url, status_code=303)


# --------------------------------------------------------------------------- login

@router.get("/login")
def admin_login_page(request: Request, conn=Depends(db.get_db)):
    if is_admin(request, conn):
        return RedirectResponse("/admin", status_code=303)
    return render(request, "admin/login.html", error=None)


@router.post("/login")
def admin_login(request: Request, code: str = Form(""), conn=Depends(db.get_db)):
    expected = db.get_setting(conn, "admin_code") or ""
    if not codes.matches(code, expected):
        return render(request, "admin/login.html", status_code=400, error="Code admin incorrect")
    resp = RedirectResponse("/admin", status_code=303)
    set_cookie(resp, config.ADMIN_COOKIE, codes.fingerprint(expected))
    return resp


@router.get("/logout")
def admin_logout():
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie(config.ADMIN_COOKIE)
    return resp


# --------------------------------------------------------------------------- dashboard

@router.get("")
def dashboard(request: Request, msg: str | None = None, conn=Depends(db.get_db), _=Depends(require_admin)):
    day = daily.today()
    stats = {
        "restaurants": conn.execute("SELECT COUNT(*) FROM restaurants WHERE active = 1 AND kind = 'restaurant'").fetchone()[0],
        "collegues": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "swipers": conn.execute("SELECT COUNT(DISTINCT user_id) FROM swipes WHERE day = ?", (day,)).fetchone()[0],
        "push": conn.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0],
    }
    return render(request, "admin/dashboard.html", msg=msg, stats=stats, day=day,
                  access_code=db.get_setting(conn, "access_code"),
                  admin_code=db.get_setting(conn, "admin_code"),
                  shortlist=daily.get_shortlist(conn, day), section="dashboard")


@router.post("/codes/{which}")
def rotate_code(which: str, conn=Depends(db.get_db), _=Depends(require_admin)):
    if which == "access":
        db.set_setting(conn, "access_code", codes.generate_access_code())
        return _back("/admin", "Nouveau code collègues généré : tout le monde doit se reconnecter.")
    if which == "admin":
        new = codes.generate_admin_code()
        db.set_setting(conn, "admin_code", new)
        resp = _back("/admin", "Nouveau code admin généré.")
        set_cookie(resp, config.ADMIN_COOKIE, codes.fingerprint(new))
        return resp
    return _back("/admin")


@router.post("/push/test")
def push_test(conn=Depends(db.get_db), _=Depends(require_admin)):
    r = push.send_test(conn)
    return _back("/admin", f"Notification de test : {r['sent']} envoyée(s) sur {r['recipients']} appareil(s)"
                           + (f", {r['removed']} abonnement(s) expiré(s) retiré(s)" if r["removed"] else "")
                           + (f", {r['failed']} échec(s)" if r["failed"] else "") + ".")


@router.post("/reset-day")
def reset_day(conn=Depends(db.get_db), _=Depends(require_admin)):
    daily.reset_day(conn)
    return _back("/admin", "Tirage du jour relancé : swipes et repas du jour effacés.")


# --------------------------------------------------------------------------- CRUD générique

def _entity(kind: str):
    ent = ENTITIES.get(kind)
    if ent is None:
        from fastapi import HTTPException
        raise HTTPException(404)
    return ent


@router.get("/{kind}")
def entity_list(request: Request, kind: str, msg: str | None = None, conn=Depends(db.get_db),
                _=Depends(require_admin)):
    ent = _entity(kind)
    rows = conn.execute(f"SELECT * FROM {ent['table']} ORDER BY name COLLATE NOCASE").fetchall()
    specials = []
    if kind == "restaurants":
        specials = [r for r in rows if r["kind"] != "restaurant"]
        rows = [r for r in rows if r["kind"] == "restaurant"]
    return render(request, "admin/list.html", kind=kind, ent=ent, rows=rows, specials=specials,
                  msg=msg, section=kind)


@router.get("/{kind}/new")
def entity_new(request: Request, kind: str, _=Depends(require_admin)):
    return render(request, "admin/form.html", kind=kind, ent=_entity(kind), row=None, error=None, section=kind)


@router.get("/{kind}/{item_id}")
def entity_edit(request: Request, kind: str, item_id: int, conn=Depends(db.get_db), _=Depends(require_admin)):
    ent = _entity(kind)
    row = conn.execute(f"SELECT * FROM {ent['table']} WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return _back(f"/admin/{kind}")
    return render(request, "admin/form.html", kind=kind, ent=ent, row=row, error=None, section=kind)


@router.post("/{kind}/save")
async def entity_save(
    request: Request,
    kind: str,
    item_id: int = Form(0),
    name: str = Form(""),
    description: str = Form(""),
    active: str | None = Form(None),
    remove_photo: str | None = Form(None),
    photo: UploadFile | None = File(None),
    conn=Depends(db.get_db),
    _=Depends(require_admin),
):
    ent = _entity(kind)
    table = ent["table"]
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone() if item_id else None
    name, description = name.strip(), description.strip()

    def fail(error: str):
        return render(request, "admin/form.html", status_code=400, kind=kind, ent=ent, row=row,
                      error=error, section=kind, draft={"name": name, "description": description})

    if not name:
        return fail("Le nom est obligatoire.")
    try:
        new_photo = await images.save_upload(photo)
    except images.InvalidImage as exc:
        return fail(str(exc))

    photo_name = row["photo"] if row else None
    if new_photo or remove_photo:
        images.delete(photo_name)
        photo_name = new_photo

    fields = {"name": name, "description": description, "photo": photo_name}
    is_special = row is not None and "kind" in row.keys() and row["kind"] != "restaurant"
    if ent["has_active"] and not is_special:
        fields["active"] = 1 if active else 0
    if row:
        sets = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*fields.values(), row["id"]))
        msg = f"« {name} » mis à jour."
    else:
        cols = ", ".join(fields)
        conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({','.join('?' * len(fields))})",
                     tuple(fields.values()))
        msg = f"« {name} » ajouté."
    return _back(f"/admin/{kind}", msg)


@router.post("/{kind}/{item_id}/delete")
def entity_delete(kind: str, item_id: int, conn=Depends(db.get_db), _=Depends(require_admin)):
    ent = _entity(kind)
    row = conn.execute(f"SELECT * FROM {ent['table']} WHERE id = ?", (item_id,)).fetchone()
    if row and "kind" in row.keys() and row["kind"] != "restaurant":
        return _back(f"/admin/{kind}", "Les statuts du jour ne peuvent pas être supprimés.")
    if row:
        conn.execute(f"DELETE FROM {ent['table']} WHERE id = ?", (item_id,))
        images.delete(row["photo"])
        return _back(f"/admin/{kind}", f"« {row['name']} » supprimé.")
    return _back(f"/admin/{kind}")
