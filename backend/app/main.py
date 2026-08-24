from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin as admin_api
from app.api import devices as devices_api
from app.api import dvr as dvr_api
from app.api import guide as guide_api
from app.api import network_settings as network_settings_api
from app.api import settings as settings_api
from app.api import setup as setup_api
from app.api import streaming as streaming_api
from app.api import tuner as tuner_api
from app.api import users as users_api
from app.api import watch as watch_api
from app.config import settings
from app.dvr.builtin import engine as dvr_engine
from app.guide import schedules_direct as schedules_direct_guide
from app.guide import service as hdhomerun_guide
from app.guide import xmltv as xmltv_guide
from app.logging_config import configure_logging, request_id_ctx
from app.scheduler import scheduler
from app.storage.db import init_db

configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await dvr_engine.dvr_engine.recover_on_startup()
    hdhomerun_guide.register(scheduler)
    xmltv_guide.register(scheduler)
    schedules_direct_guide.register(scheduler)
    dvr_engine.register(scheduler)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="hdhr-open API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,  # required for the device/session cookies (app/auth.py)
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    # A fresh id per request, propagated via contextvars (see
    # app.logging_config.request_id_ctx) so every log line emitted anywhere
    # while handling this request can be correlated, and echoed back in a
    # response header so client-side logs/bug reports can be matched to a
    # specific backend log line.
    request_id = uuid.uuid4().hex[:12]
    request_id_ctx.set(request_id)
    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info("%s %s -> %d (%.1fms)", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


app.include_router(tuner_api.router)
app.include_router(streaming_api.router)
app.include_router(guide_api.router)
app.include_router(dvr_api.router)
app.include_router(network_settings_api.router)
app.include_router(settings_api.router)
app.include_router(devices_api.router)
app.include_router(users_api.router)
app.include_router(setup_api.router)
app.include_router(admin_api.router)
app.include_router(watch_api.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
