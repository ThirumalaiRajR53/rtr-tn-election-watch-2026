"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import APP_TITLE

APP_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    application = FastAPI(title=APP_TITLE, docs_url="/docs")

    application.mount(
        "/static",
        StaticFiles(directory=str(APP_DIR / "static")),
        name="static",
    )

    from app.routers.pages import router as pages_router
    from app.routers.api import router as api_router

    application.include_router(pages_router)
    application.include_router(api_router, prefix="/api")

    return application


app = create_app()
