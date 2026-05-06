from __future__ import annotations

from fastapi import FastAPI

from aps_registry.routes import router, set_storage
from aps_registry.storage.sqlite import SqliteStorage


def create_app(db_path: str = "aps_registry.db") -> FastAPI:
    app = FastAPI(title="APS Registry", version="0.1.0")

    storage = SqliteStorage(db_path)
    storage.initialize()
    set_storage(storage)

    app.include_router(router)
    return app
