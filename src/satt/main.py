"""FastAPI application entry point for Salt All The Things."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from satt.config import get_settings
from satt.routes.ai import router as ai_router
from satt.routes.auth import router as auth_router
from satt.routes.data import router as data_router
from satt.routes.health import router as health_router
from satt.routes.guests import router as guests_router
from satt.routes.postproduction import router as postproduction_router
from satt.routes.public import router as public_router
from satt.routes.songs import router as songs_router
from satt.routes.top3 import router as top3_router
from satt.routes.users import router as users_router
from satt.version import APP_VERSION

_settings = get_settings()

app = FastAPI(title="Salt All The Things API", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(data_router, prefix="/api")
app.include_router(guests_router, prefix="/api")
app.include_router(songs_router, prefix="/api")
app.include_router(top3_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(postproduction_router, prefix="/api")
app.include_router(public_router, prefix="/public")

# Serve only explicitly public frontend assets from the same immutable image as
# the API. Server configuration, source, .env, and repository metadata remain
# unreachable.
_frontend_root = Path(__file__).resolve().parents[2]
for _asset_directory in ("css", "images", "js"):
    app.mount(
        f"/{_asset_directory}",
        StaticFiles(directory=_frontend_root / _asset_directory),
        name=_asset_directory,
    )

_frontend_pages = {
    "config.html",
    "guests.html",
    "index.html",
    "jokes.html",
    "login.html",
    "postproduction.html",
    "register.html",
    "show_management.html",
    "songs.html",
    "top3.html",
}


@app.get("/", include_in_schema=False)
async def frontend_index() -> FileResponse:
    return FileResponse(_frontend_root / "index.html")


@app.get("/{page_name}.html", include_in_schema=False)
async def frontend_page(page_name: str) -> FileResponse:
    filename = f"{page_name}.html"
    if filename not in _frontend_pages:
        raise HTTPException(status_code=404)
    return FileResponse(_frontend_root / filename)
