from __future__ import annotations

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from agentpassport_registry.limiter import limiter
from agentpassport_registry.routes import router, set_storage
from agentpassport_registry.storage.sqlite import SqliteStorage


def create_app(db_path: str = "agentpassport_registry.db") -> FastAPI:
    app = FastAPI(title="agentpassport Registry", version="0.1.0")

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    storage = SqliteStorage(db_path)
    storage.initialize()
    set_storage(storage)

    app.include_router(router)
    return app
