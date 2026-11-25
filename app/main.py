"""Point d'entrée FastAPI."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, db
from .auth import LoginRequired
from .routes import admin, public
from .web import is_htmx


@asynccontextmanager
async def lifespan(_app: FastAPI):
    created = db.init()
    for key, value in created.items():
        label = "Code d'accès collègues" if key == "access_code" else "Code admin"
        print(f"\n  ★ {label} généré : {value}\n")
    yield


app = FastAPI(title="Iodej", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=config.BASE_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")
app.include_router(public.router)
app.include_router(admin.router)


ONE_YEAR = "public, max-age=31536000, immutable"


@app.middleware("http")
async def http_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    h = response.headers
    # --- cache
    if path.startswith("/static/"):
        # URL versionnée (?v=<hash du contenu>) : le fichier ne changera jamais.
        h["Cache-Control"] = ONE_YEAR if "v" in request.query_params else "public, max-age=86400"
    elif path.startswith("/uploads/") and response.status_code == 200:
        h["Cache-Control"] = ONE_YEAR  # noms de fichiers aléatoires, jamais réécrits
    elif "Cache-Control" not in h:
        h["Cache-Control"] = "no-cache, private"  # pages personnelles : toujours revalider
    if request.headers.get("HX-Request"):
        h["Vary"] = ", ".join(filter(None, [h.get("Vary"), "HX-Request"]))
    # --- sécurité (pas de CSP : Alpine.js a besoin d'unsafe-eval)
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "SAMEORIGIN"
    h["Referrer-Policy"] = "strict-origin-when-cross-origin"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if config.COOKIE_SECURE:
        h["Strict-Transport-Security"] = "max-age=31536000"
    # Appli interne : on demande aux moteurs de recherche de ne rien indexer.
    h["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.get("/robots.txt", include_in_schema=False)
async def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    if is_htmx(request):
        return Response(status_code=200, headers={"HX-Redirect": exc.target})
    if request.url.path.startswith("/api/"):
        return Response(status_code=401)
    return RedirectResponse(exc.target, status_code=303)


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    # Servi à la racine pour couvrir tout le site.
    return FileResponse(
        config.BASE_DIR / "static" / "js" / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@app.get("/manifest.webmanifest", include_in_schema=False)
async def manifest():
    return FileResponse(config.BASE_DIR / "static" / "manifest.webmanifest",
                        media_type="application/manifest+json")


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}


@app.get("/healthz/lb", include_in_schema=False)
async def healthz_lb():
    """Santé vue par Caddy. Mise hors trafic avant un redémarrage : install.sh crée
    data/drain-<port>, Caddy voit l'instance indisponible et sert tout depuis l'autre,
    puis on l'arrête sans perdre de requête."""
    port = os.environ.get("IODEJ_PORT")
    if port and (config.DATA_DIR / f"drain-{port}").exists():
        return Response('{"ok":false,"draining":true}', status_code=503, media_type="application/json")
    return {"ok": True}
