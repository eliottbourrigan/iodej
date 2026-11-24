"""« Authentification » volontairement minimaliste : prénom + code partagé,
mémorisés dans des cookies longue durée."""
from fastapi import Depends, Request

from . import codes, config, db


class LoginRequired(Exception):
    def __init__(self, target: str = "/login"):
        self.target = target


def set_cookie(response, key: str, value: str) -> None:
    response.set_cookie(
        key,
        value,
        max_age=config.COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
    )


def clear_all_cookies(request: Request, response) -> None:
    for name in set(request.cookies) | {config.USER_COOKIE, config.KEY_COOKIE, config.ADMIN_COOKIE}:
        response.delete_cookie(name)
    response.headers["Clear-Site-Data"] = '"cookies"'


def optional_user(request: Request, conn=Depends(db.get_db)):
    uid = request.cookies.get(config.USER_COOKIE, "")
    key = request.cookies.get(config.KEY_COOKIE, "")
    if not uid.isdigit() or not key:
        return None
    if key != codes.fingerprint(db.get_setting(conn, "access_code") or ""):
        return None  # le code a changé : tout le monde se reconnecte
    return conn.execute("SELECT * FROM users WHERE id = ?", (int(uid),)).fetchone()


def require_user(user=Depends(optional_user)):
    if user is None:
        raise LoginRequired("/login")
    return user


def is_admin(request: Request, conn) -> bool:
    key = request.cookies.get(config.ADMIN_COOKIE, "")
    return bool(key) and key == codes.fingerprint(db.get_setting(conn, "admin_code") or "")


def require_admin(request: Request, conn=Depends(db.get_db)):
    if not is_admin(request, conn):
        raise LoginRequired("/admin/login")
    return True
