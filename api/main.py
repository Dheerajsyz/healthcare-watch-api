"""HealthTrack API — application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.middleware import LoggingMiddleware
from api.routes import auth, patients, vitals, activity, alerts, risk


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing special needed; DB is managed by Alembic
    yield
    # Shutdown


def create_app() -> FastAPI:
    app = FastAPI(
        title="HealthTrack API",
        description=(
            "Real-Time Healthcare Monitoring System — secure REST API for patient "
            "vitals, activity, and alerting workflows."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(LoggingMiddleware)

    # -----------------------------------------------------------------------
    # Global error handlers
    # -----------------------------------------------------------------------
    from sqlalchemy.exc import IntegrityError

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "CONFLICT", "message": "Resource already exists or constraint violated.", "details": str(exc.orig)}},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred.", "details": str(exc)}},
        )

    # -----------------------------------------------------------------------
    # Routers
    # -----------------------------------------------------------------------
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(patients.router, prefix="/patients", tags=["patients"])
    app.include_router(vitals.router, prefix="/patients", tags=["vitals"])
    app.include_router(activity.router, prefix="/patients", tags=["activity"])
    app.include_router(alerts.router, prefix="/patients", tags=["alerts"])
    app.include_router(risk.router, prefix="/patients", tags=["risk"])

    @app.get("/healthz", tags=["system"], summary="Health check")
    async def healthz():
        return {"status": "ok"}

    return app


app = create_app()
