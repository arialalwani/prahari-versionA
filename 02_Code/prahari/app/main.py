from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config
from app.db import init_db
from app.routers import alerts, cameras, faces, health, ingest, login, predict, query, stream, track, tracking, watchlist
from app.services import matcher

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    config.crop_dir().mkdir(parents=True, exist_ok=True)
    (config.ROOT / "data" / "hls").mkdir(parents=True, exist_ok=True)
    matcher.reload()
    matcher.seed_from_detections()
    yield


app = FastAPI(title="PRAHARI", lifespan=lifespan)
app.include_router(health.router)
app.include_router(login.router)
app.include_router(cameras.router)
app.include_router(stream.router)
app.include_router(tracking.router)
app.include_router(ingest.router)
app.include_router(faces.router)
app.include_router(watchlist.router)
app.include_router(alerts.router)
app.include_router(track.router)
app.include_router(predict.router)
app.include_router(query.router)
config.crop_dir().mkdir(parents=True, exist_ok=True)
app.mount("/crops", StaticFiles(directory=str(config.crop_dir())), name="crops")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
