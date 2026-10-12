import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.database import get_engine
from app.errors import RequestContextMiddleware, register_error_handlers
from app.routers import auth, companies, contacts, deals, interactions, pipelines, users

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app() -> FastAPI:
    settings = get_settings()
    production = settings.environment == "production"

    app = FastAPI(
        title="CRM B2B API",
        version="0.1.0",
        description="API do CRM para equipes de vendas B2B (funil Kanban, RBAC, JWT e LGPD).",
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )

    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    # CORS por último = camada mais externa (também decora respostas de erro).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    prefix = "/api/v1"
    for module in (auth, users, companies, contacts, pipelines, deals, interactions):
        app.include_router(module.router, prefix=prefix)

    @app.get("/health", tags=["Infra"])
    def health():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["Infra"])
    def ready():
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready"}

    return app


app = create_app()
