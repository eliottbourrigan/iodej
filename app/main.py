"""Point d'entrée FastAPI."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
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
