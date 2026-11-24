"""Pages collègues : connexion, swipe, résultats, historique."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from .. import codes, config, daily, db
from ..auth import clear_all_cookies, optional_user, require_user, set_cookie
from ..grouping import make_groups
from ..web import is_htmx, render

router = APIRouter()

TABS = {"choix": "Les choix", "groupes": "Suggestion", "historique": "Historique"}


# --------------------------------------------------------------------------- helpers

def _swipe_state(conn, user_id: int, day: str):
    shortlist = daily.get_shortlist(conn, day)
    swiped = {
        r["restaurant_id"]: bool(r["liked"])
        for r in conn.execute(
            "SELECT restaurant_id, liked FROM swipes WHERE day = ? AND user_id = ?", (day, user_id)
        )
    }
    remaining = [r for r in shortlist if r["id"] not in swiped]
    return shortlist, swiped, remaining


def _my_meal(conn, user_id: int, day: str):
    return conn.execute(
        "SELECT r.* FROM meals m JOIN restaurants r ON r.id = m.restaurant_id "
        "WHERE m.day = ? AND m.user_id = ?", (day, user_id)
    ).fetchone()


def _is_out(meal) -> bool:
    return meal is not None and meal["kind"] != "restaurant"


def _day_overview(conn, day: str):
    """Qui a liké quoi aujourd'hui, et qui a fini de swiper."""
    shortlist = daily.get_shortlist(conn, day)
    ids = {r["id"] for r in shortlist}
    users = conn.execute("SELECT * FROM users ORDER BY name COLLATE NOCASE").fetchall()
    users_by_id = {u["id"]: u for u in users}
    likes: dict[int, set[int]] = {}
    counts: dict[int, int] = {}
    for s in conn.execute("SELECT user_id, restaurant_id, liked FROM swipes WHERE day = ?", (day,)):
        if s["restaurant_id"] not in ids or s["user_id"] not in users_by_id:
            continue
        counts[s["user_id"]] = counts.get(s["user_id"], 0) + 1
        if s["liked"]:
            likes.setdefault(s["user_id"], set()).add(s["restaurant_id"])
    meals, absent = {}, []
    for m in conn.execute(
        "SELECT m.user_id, m.restaurant_id, r.kind FROM meals m "
        "JOIN restaurants r ON r.id = m.restaurant_id WHERE m.day = ?", (day,)
    ):
        meals[m["user_id"]] = m["restaurant_id"]
        if m["kind"] != "restaurant" and m["user_id"] in users_by_id:
            absent.append((users_by_id[m["user_id"]], m["kind"]))
    absent_ids = {u["id"] for u, _ in absent}
    for uid in absent_ids:  # pas là ce midi : exclu des groupes
        likes.pop(uid, None)
    present = [u for u in users if u["id"] not in absent_ids]
    finished = [u for u in present if shortlist and counts.get(u["id"], 0) >= len(shortlist)]
    in_progress = [u for u in present if 0 < counts.get(u["id"], 0) < len(shortlist)]
    waiting = [u for u in present if counts.get(u["id"], 0) == 0]
    return dict(shortlist=shortlist, users_by_id=users_by_id, likes=likes, finished=finished,
                in_progress=in_progress, waiting=waiting, meals=meals, absent=absent,
                present_count=len(present))


# --------------------------------------------------------------------------- auth

@router.get("/login")
def login_page(request: Request, conn=Depends(db.get_db), user=Depends(optional_user)):
    if user:
        return RedirectResponse("/", status_code=303)
    users = conn.execute("SELECT id, name FROM users ORDER BY name COLLATE NOCASE").fetchall()
    return render(request, "login.html", users=users, error=None, selected=None)


@router.post("/login")
def login(request: Request, user_id: int = Form(0), code: str = Form(""), conn=Depends(db.get_db)):
    users = conn.execute("SELECT id, name FROM users ORDER BY name COLLATE NOCASE").fetchall()
    access = db.get_setting(conn, "access_code") or ""
    error = None
    if not any(u["id"] == user_id for u in users):
        error = "Choisis ton prénom !"
    elif not codes.matches(code, access):
        error = "Code d'accès incorrect"
    if error:
        return render(request, "login.html", status_code=400 if not is_htmx(request) else 200,
                      users=users, error=error, selected=user_id)
    resp = Response(status_code=204, headers={"HX-Redirect": "/"}) if is_htmx(request) \
        else RedirectResponse("/", status_code=303)
    set_cookie(resp, config.USER_COOKIE, str(user_id))
    set_cookie(resp, config.KEY_COOKIE, codes.fingerprint(access))
    return resp


@router.get("/logout")
def logout(request: Request):
    resp = RedirectResponse("/login", status_code=303)
    clear_all_cookies(request, resp)
    return resp


# --------------------------------------------------------------------------- swipe

@router.get("/")
def home(conn=Depends(db.get_db), user=Depends(require_user)):
    day = daily.today()
    if _my_meal(conn, user["id"], day):
        return RedirectResponse("/resultats", status_code=303)
    shortlist, swiped, remaining = _swipe_state(conn, user["id"], day)
    if not swiped:  # premier passage du jour : « Ce midi, tu… »
        return RedirectResponse("/ce-midi", status_code=303)
    return RedirectResponse("/swipe" if remaining else "/resultats", status_code=303)


@router.get("/ce-midi")
def today_page(request: Request, conn=Depends(db.get_db), user=Depends(require_user)):
    day = daily.today()
    meal = _my_meal(conn, user["id"], day)
    _, swiped, _ = _swipe_state(conn, user["id"], day)
    current = meal["kind"] if _is_out(meal) else ("swipe" if swiped or meal else None)
    return render(request, "today.html", user=user, day=day, current=current,
                  specials=db.special_rows(conn), active="swipe")


@router.post("/api/status")
def api_status(choice: str = Form(...), conn=Depends(db.get_db), user=Depends(require_user)):
    day = daily.today()
    if choice in db.SPECIALS:
        conn.execute(
            "INSERT INTO meals(day, user_id, restaurant_id) VALUES (?, ?, ?) "
            "ON CONFLICT(day, user_id) DO UPDATE SET restaurant_id = excluded.restaurant_id",
            (day, user["id"], db.special_id(conn, choice)),
        )
        return RedirectResponse("/resultats?tab=groupes", status_code=303)
    # « Je veux swiper ! » : on annule un éventuel statut d'absence.
    meal = _my_meal(conn, user["id"], day)
    if _is_out(meal):
        conn.execute("DELETE FROM meals WHERE day = ? AND user_id = ?", (day, user["id"]))
    return RedirectResponse("/swipe", status_code=303)


@router.get("/swipe")
def swipe_page(request: Request, conn=Depends(db.get_db), user=Depends(require_user)):
    day = daily.today()
    shortlist, swiped, remaining = _swipe_state(conn, user["id"], day)
    if shortlist and not remaining:
        return RedirectResponse("/resultats", status_code=303)
    return render(request, "swipe.html", user=user, day=day, shortlist=shortlist,
                  remaining=remaining, done=len(swiped), active="swipe")


@router.post("/api/swipe")
def api_swipe(restaurant_id: int = Form(...), liked: int = Form(...),
              conn=Depends(db.get_db), user=Depends(require_user)):
    day = daily.today()
    if restaurant_id not in daily.get_shortlist_ids(conn, day):
        # La journée a peut-être changé pendant que l'appli était ouverte.
        return JSONResponse({"error": "stale", "redirect": "/swipe"}, status_code=409)
    conn.execute(
        "INSERT INTO swipes(day, user_id, restaurant_id, liked) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(day, user_id, restaurant_id) DO UPDATE SET liked = excluded.liked",
        (day, user["id"], restaurant_id, 1 if liked else 0),
    )
    _, _, remaining = _swipe_state(conn, user["id"], day)
    return {"remaining": len(remaining)}


@router.post("/api/swipes/reset")
def api_reset_swipes(conn=Depends(db.get_db), user=Depends(require_user)):
    day = daily.today()
    conn.execute("DELETE FROM swipes WHERE day = ? AND user_id = ?", (day, user["id"]))
    return Response(status_code=204, headers={"HX-Redirect": "/swipe"})


# --------------------------------------------------------------------------- résultats

@router.get("/resultats")
def results_page(request: Request, tab: str = "choix", conn=Depends(db.get_db),
                 user=Depends(require_user)):
    tab = tab if tab in TABS else "choix"
    _, _, remaining = _swipe_state(conn, user["id"], daily.today())
    remaining = [] if _is_out(_my_meal(conn, user["id"], daily.today())) else remaining
    return render(request, "results.html", user=user, tab=tab, tabs=TABS, day=daily.today(),
                  locked=bool(remaining), remaining=len(remaining), active=tab)


@router.get("/partials/{tab}")
def results_partial(request: Request, tab: str, refresh: int = 0, conn=Depends(db.get_db),
                    user=Depends(require_user)):
    if tab not in TABS:
        return Response(status_code=404)
    day = daily.today()
    ctx = dict(user=user, day=day, refresh=bool(refresh))

    if tab == "historique":
        return render(request, "partials/historique.html", **ctx, history=_history(conn, user["id"]))

    _, _, remaining = _swipe_state(conn, user["id"], day)
    my_status = _my_meal(conn, user["id"], day)
    if remaining and not _is_out(my_status):
        return render(request, "partials/locked.html", **ctx, remaining=len(remaining))

    ov = _day_overview(conn, day)
    ctx.update(ov, my_meal=ov["meals"].get(user["id"]),
               my_status=my_status["kind"] if _is_out(my_status) else None, specials=db.special_rows(conn))
    if tab == "choix":
        rows = []
        for r in ov["shortlist"]:
            likers = [ov["users_by_id"][u] for u, rs in ov["likes"].items() if r["id"] in rs]
            likers.sort(key=lambda u: (u["id"] != user["id"], u["name"].lower()))
            rows.append((r, likers))
        rows.sort(key=lambda x: -len(x[1]))
        return render(request, "partials/choix.html", **ctx, rows=rows)

    groups = make_groups(ov["likes"], seed=day)
    restaurants = {r["id"]: r for r in ov["shortlist"]}
    grouped = []
    for g in groups:
        members = sorted((ov["users_by_id"][u] for u in g.user_ids),
                         key=lambda u: (u["id"] != user["id"], u["name"].lower()))
        grouped.append((restaurants[g.restaurant_id], members, user["id"] in g.user_ids))
    grouped.sort(key=lambda x: not x[2])  # mon groupe en premier
    no_like = [u for u in ov["finished"] if u["id"] not in ov["likes"]]
    return render(request, "partials/groupes.html", **ctx, groups=grouped, no_like=no_like)


def _history(conn, user_id: int):
    days = daily.last_days()
    rows = conn.execute(
        f"SELECT m.day, r.* FROM meals m JOIN restaurants r ON r.id = m.restaurant_id "
        f"WHERE m.user_id = ? AND m.day IN ({','.join('?' * len(days))})",
        (user_id, *days),
    ).fetchall()
    by_day = {r["day"]: r for r in rows}
    out = []
    for d in days:
        resto = by_day.get(d)
        mates = []
        if resto and resto["kind"] == "restaurant":
            mates = conn.execute(
                "SELECT u.* FROM meals m JOIN users u ON u.id = m.user_id "
                "WHERE m.day = ? AND m.restaurant_id = ? AND m.user_id != ? ORDER BY u.name",
                (d, resto["id"], user_id),
            ).fetchall()
        out.append((d, resto, mates))
    return out


@router.post("/api/meal")
def api_meal(request: Request, restaurant_id: int = Form(...), tab: str = Form("groupes"),
             conn=Depends(db.get_db), user=Depends(require_user)):
    day = daily.today()
    if restaurant_id in daily.get_shortlist_ids(conn, day):
        current = conn.execute("SELECT restaurant_id FROM meals WHERE day = ? AND user_id = ?",
                               (day, user["id"])).fetchone()
        if current and current["restaurant_id"] == restaurant_id:
            conn.execute("DELETE FROM meals WHERE day = ? AND user_id = ?", (day, user["id"]))
        else:
            conn.execute(
                "INSERT INTO meals(day, user_id, restaurant_id) VALUES (?, ?, ?) "
                "ON CONFLICT(day, user_id) DO UPDATE SET restaurant_id = excluded.restaurant_id",
                (day, user["id"], restaurant_id),
            )
    return results_partial(request, tab if tab in ("choix", "groupes") else "groupes", 1, conn, user)
