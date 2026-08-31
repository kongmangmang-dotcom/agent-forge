from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import agents, events, providers, runs, schedule, workflows
from app.core.config import settings
from app.core.exceptions import AppError
from app.db.session import SessionLocal, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="AgentForge API",
    version="0.1.0",
    description="Agent orchestration platform — multi-provider, workflow BPM, schedule",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


API = "/api/v1"
app.include_router(providers.router, prefix=API)
app.include_router(agents.router, prefix=API)
app.include_router(workflows.router, prefix=API)
app.include_router(runs.router, prefix=API)
app.include_router(schedule.router, prefix=API)
app.include_router(events.router, prefix=API)


async def _check_database() -> tuple[str, str | None]:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return "ok", None
    except Exception as exc:
        return "error", str(exc)


async def _check_redis() -> tuple[str, str | None]:
    try:
        client = aioredis.from_url(settings.redis_url)
        try:
            await client.ping()
            return "ok", None
        finally:
            await client.aclose()
    except Exception as exc:
        return "error", str(exc)


@app.get("/health")
async def health():
    db_status, db_err = await _check_database()
    redis_status, redis_err = await _check_redis()
    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    details = {}
    if db_err:
        details["database"] = db_err
    if redis_err:
        details["redis"] = redis_err
    return {
        "status": overall,
        "service": "agent-forge-api",
        "database": db_status,
        "redis": redis_status,
        "details": details or None,
    }


@app.get("/")
async def root():
    return {"docs": "/docs", "health": "/health", "api": API}
