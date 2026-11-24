"""Moteur de templates partagé + helpers Jinja."""
import hashlib
from datetime import date

from fastapi import Request
from fastapi.templating import Jinja2Templates

from . import config, daily

templates = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))

PALETTE = ["#ff4d6d", "#ff8a1f", "#ffc93c", "#3ddc84", "#2fa8ff", "#7b5cff", "#ff5cc8", "#00c2b8"]
EMOJIS = ["🍔", "🍕", "🍜", "🌮", "🥗", "🍣", "🥙", "🍝", "🍛", "🥪", "🍱", "🌯"]
DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def _static_version() -> str:
    h = hashlib.sha1()
    for p in sorted((config.BASE_DIR / "static").rglob("*")):
        if p.is_file():
            h.update(p.name.encode())
            h.update(str(p.stat().st_mtime_ns).encode())
    return h.hexdigest()[:10]


STATIC_VERSION = _static_version()


def static(path: str) -> str:
    return f"/static/{path}?v={STATIC_VERSION}"


def photo_url(name: str | None) -> str | None:
    return f"/uploads/{name}" if name else None


def color_for(seed) -> str:
    return PALETTE[int(hashlib.md5(str(seed).encode()).hexdigest(), 16) % len(PALETTE)]


KEYWORD_EMOJIS = [
    (("burger",), "🍔"), (("pizz", "napoli"), "🍕"), (("sushi", "maki", "japon"), "🍣"),
    (("ramen", "pho", "nouille", "noodle"), "🍜"), (("thai", "thaï", "wok", "asia", "chinois"), "🥡"),
    (("taco", "mexic", "burrito"), "🌮"), (("crêpe", "crepe", "galette"), "🥞"),
    (("salad", "bowl", "green", "veg", "healthy", "poke"), "🥗"),
    (("pasta", "pâtes", "mario", "ital", "trattoria"), "🍝"), (("kebab", "chawarma", "grec"), "🥙"),
    (("liban", "falafel", "mezz"), "🧆"), (("indien", "curry", "inde"), "🍛"),
    (("boulang", "sandwich", "bagel"), "🥪"), (("bistro", "brasserie", "cantine"), "🍽️"),
    (("poulet", "chicken"), "🍗"), (("steak", "grill", "bbq", "barbecue"), "🥩"),
    (("café", "coffee"), "☕"), (("bento", "korea", "coré"), "🍱"),
]


def emoji_for(seed, name: str = "") -> str:
    low = (name or "").lower()
    for keys, emoji in KEYWORD_EMOJIS:
        if any(k in low for k in keys):
            return emoji
    return EMOJIS[int(hashlib.md5(f"e{seed}".encode()).hexdigest(), 16) % len(EMOJIS)]


def initials(name: str) -> str:
    parts = [p for p in (name or "?").replace("-", " ").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def human_day(iso: str) -> str:
    d = date.fromisoformat(iso)
    t = date.fromisoformat(daily.today())
    delta = (t - d).days
    if delta == 0:
        return "Aujourd'hui"
    if delta == 1:
        return "Hier"
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


templates.env.globals.update(static=static, photo_url=photo_url, color_for=color_for,
                             emoji_for=emoji_for, initials=initials, human_day=human_day)
templates.env.filters["human_day"] = human_day


def render(request: Request, name: str, status_code: int = 200, **ctx):
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)
