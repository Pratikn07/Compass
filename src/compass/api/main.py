from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from compass.api.routes import advisor, governance, health, operations, research


def create_app() -> FastAPI:
    application = FastAPI(
        title="Compass API",
        version="0.1.0",
        description="Private, owner-scoped investment research and advisory API.",
    )

    origins = ["http://localhost:3000"]
    if web_origin := os.getenv("COMPASS_WEB_ORIGIN"):
        origins.append(web_origin)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Compass-Key"],
    )

    application.include_router(health.router)
    application.include_router(advisor.router)
    application.include_router(governance.router)
    application.include_router(research.router)
    application.include_router(operations.router)
    return application


app = create_app()
