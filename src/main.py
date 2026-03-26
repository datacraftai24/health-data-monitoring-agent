"""MetaboCoach — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from src.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)
    logger.info("MetaboCoach starting up (env=%s)", settings.app_env)
    yield
    # Shutdown
    logger.info("MetaboCoach shutting down")


app = FastAPI(
    title="MetaboCoach",
    description="Personal Metabolic AI Agent — glucose monitoring, food analysis, and health coaching",
    version="1.0.0",
    lifespan=lifespan,
)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# --- Register routers ---
from src.api.routes.health import router as health_router  # noqa: E402
from src.api.routes.dashboard import router as dashboard_router  # noqa: E402
from src.api.webhooks.whatsapp import router as whatsapp_router  # noqa: E402
from src.api.webhooks.telegram import router as telegram_router  # noqa: E402
from src.api.webhooks.garmin import router as garmin_router  # noqa: E402

app.include_router(health_router, tags=["health"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(whatsapp_router, prefix="/webhook", tags=["webhooks"])
app.include_router(telegram_router, prefix="/webhook", tags=["webhooks"])
app.include_router(garmin_router, prefix="/webhook", tags=["webhooks"])
