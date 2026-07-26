import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import (
    auth,
    database,
    models,
)
from .database import engine
from .routers import auth as auth_routes
from .routers import audio as audio_routes
from .routers import auto_sync as auto_sync_routes
from .routers import bd2 as bd2_routes
from .routers import creators as creators_routes
from .routers import dedup as dedup_routes
from .routers import external as external_routes
from .routers import media as media_routes
from .routers import recommend as recommend_routes
from .routers import root as root_routes
from .routers import stats as stats_routes
from .routers import x_import as x_import_routes
from .dedup import worker as dedup_worker
from .services import job_lifecycle
from .services.thumbnails import THUMBNAIL_DIR, cleanup_orphaned_thumbnails


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run DB schema migrations
    models.Base.metadata.create_all(bind=engine)
    from .migrations import run_schema_migrations
    run_schema_migrations()
    database.secure_data_permissions()
    db = database.SessionLocal()
    try:
        auth.cleanup_access_tokens(db)
    finally:
        db.close()

    # Startup tasks
    job_lifecycle.recover_interrupted_jobs()
    job_lifecycle.cleanup_job_history()
    dedup_worker.recover_checking_jobs()
    auto_sync_routes.init_scheduler()
    cleanup_orphaned_thumbnails()
    try:
        yield
    finally:
        auto_sync_routes.stop_scheduler()

_docs_enabled = os.getenv("HE_ENABLE_DOCS", "").lower() in {"1", "true", "yes", "on"}
app = FastAPI(
    title="HE Manager API",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
    lifespan=lifespan,
)


def _cors_origins() -> list[str]:
    raw = os.getenv("HE_ALLOWED_ORIGINS", "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    # Keep development and Sakura-FRP ad-hoc access working by default. The app
    # does not use cookie auth, so credentials stay disabled below.
    return ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stats_routes.router)
app.include_router(creators_routes.router)
app.include_router(dedup_routes.router)
app.include_router(external_routes.router)
app.include_router(auto_sync_routes.router)
app.include_router(bd2_routes.router)
app.include_router(auth_routes.router)
app.include_router(media_routes.router)
app.include_router(audio_routes.router)
app.include_router(recommend_routes.router)
app.include_router(x_import_routes.router)
app.include_router(root_routes.router)

app.mount("/thumbnails", StaticFiles(directory=THUMBNAIL_DIR), name="thumbnails")


PUBLIC_PATHS = {
    "/healthz",
    "/auth/status",
    "/auth/login",
    "/auth/bootstrap",
}
ADMIN_PREFIXES = (
    "/users",
    "/folders",
    "/search-folder",
    "/system",
    "/external",
    "/x",
    "/dedup",
    "/auto-sync",
)
ADMIN_EXACT_PATHS = {
    "/ai/recommendations/config",
    "/recommend/manga-profiles/analyze",
    "/recommend/manga-metadata/analyze",
}


def _public_path(path: str) -> bool:
    norm = path[4:] if path.startswith("/api/") else path
    if norm in PUBLIC_PATHS or norm.startswith("/bd2/spine") or norm.startswith("/bd2/characters"):
        return True
    # Allow loading frontend SPA page and assets without auth (WebView access)
    if norm in {"/", "/index.html", "/favicon.ico"} or norm.startswith("/assets/"):
        return True
    return False


def _admin_path(method: str, path: str) -> bool:
    if path.startswith(ADMIN_PREFIXES):
        return True
    if path in ADMIN_EXACT_PATHS:
        return True
    if method == "DELETE" and path.startswith("/media/"):
        return True
    if method == "POST" and path.startswith("/media/") and path.endswith("/regenerate-thumbnail"):
        return True
    return False


def _json_error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


@app.middleware("http")
async def require_authenticated_request(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or _public_path(path):
        response = await call_next(request)
    else:
        query_token = (
            request.query_params.get("token")
            if auth.query_token_allowed(request.method, path)
            else None
        )
        raw_token = auth.extract_token(
            authorization=request.headers.get("authorization"),
            query_token=query_token,
        )
        if not raw_token:
            print(f"*** AUTH INTERCEPTED: {request.method} {path}")
            return _json_error(401, "Missing access token")

        db = database.SessionLocal()
        try:
            user = auth.authenticate_access_token(db, raw_token)
            if _admin_path(request.method, path) and not user.is_admin:
                return _json_error(403, "Admin permission required")
            request.state.current_user = user
        except HTTPException as exc:
            return _json_error(exc.status_code, str(exc.detail))
        finally:
            db.close()
        response = await call_next(request)

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


# Mount frontend build directory (SPA) at the root
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
