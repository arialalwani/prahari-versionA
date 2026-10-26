"""Runtime configuration. Missing SENTINEL_HOST is allowed; the PoC runs on samples."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
SAMPLES_DIR = REPO_ROOT / "03_Data" / "samples"
ENV_PATH = ROOT / ".env"


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(ENV_PATH)


def getenv(key: str, default: str = "") -> str:
    value = os.environ.get(key)
    if value is None or value == "":
        return default
    return value


APP_HOST = getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(getenv("APP_PORT", "8080") or "8080")
JUDGE_USER = getenv("JUDGE_USER", "judge")
JUDGE_PASSWORD = getenv("JUDGE_PASSWORD", "set-this-before-submit")
SECRET_KEY = getenv("SECRET_KEY", "change-me")

SENTINEL_HOST = getenv("SENTINEL_HOST", "")
SENTINEL_CATALOGUE_PATH = getenv("SENTINEL_CATALOGUE_PATH", "/cameras.json")
SENTINEL_USER = getenv("SENTINEL_USER", "") or getenv("SENTINEL_EMAIL", "")
SENTINEL_PASSWORD = getenv("SENTINEL_PASSWORD", "")
SENTINEL_RTSP_HOST = getenv("SENTINEL_RTSP_HOST", "")

RTSP_TRANSPORT = getenv("RTSP_TRANSPORT", "tcp")
RECONNECT_MIN_S = int(getenv("RECONNECT_MIN_S", "2") or "2")
RECONNECT_MAX_S = int(getenv("RECONNECT_MAX_S", "30") or "30")
SAMPLE_FPS = int(getenv("SAMPLE_FPS", "1") or "1")
ANPR_MIN_CONFIDENCE = float(getenv("ANPR_MIN_CONFIDENCE", "0.35") or "0.35")
MAX_OPEN_CAPTURES = int(getenv("MAX_OPEN_CAPTURES", "4") or "4")
ANPR_ENGINE = getenv("ANPR_ENGINE", "tesseract")
STREAM_TOKEN_TTL_S = int(getenv("STREAM_TOKEN_TTL_S", "60") or "60")
ANALYTICS_ENGINES = getenv("ANALYTICS_ENGINES", "anpr,objects")
OBJECT_ENGINE = getenv("OBJECT_ENGINE", "yolo")
# Intrusion fires only on a YOLO person at or above this confidence.
INTRUSION_MIN_CONFIDENCE = float(getenv("INTRUSION_MIN_CONFIDENCE", "0.5") or "0.5")
OBJECT_MIN_CONFIDENCE = float(getenv("OBJECT_MIN_CONFIDENCE", "0.45") or "0.45")
FACE_ENGINE = getenv("FACE_ENGINE", "histogram")
FACE_MATCH_MIN_CONFIDENCE = float(getenv("FACE_MATCH_MIN_CONFIDENCE", "0.55") or "0.55")
TRACK_ENGINE = getenv("TRACK_ENGINE", "iou")
YOLO_VEHICLE_WEIGHTS = getenv("YOLO_VEHICLE_WEIGHTS", "app/models_data/yolov8n.pt")
YOLO_PLATE_WEIGHTS = getenv("YOLO_PLATE_WEIGHTS", "")


def users() -> list[dict]:
    return [
        {
            "username": getenv("JUDGE_USER", "judge"),
            "password": getenv("JUDGE_PASSWORD", "set-this-before-submit"),
            "role": "soc_operator",
            "department": None,
        },
        {
            "username": getenv("ADMIN_USER", "admin"),
            "password": getenv("ADMIN_PASSWORD", "admin"),
            "role": "superadmin",
            "department": None,
        },
        {
            "username": getenv("VIEWER_HOME", "home.viewer"),
            "password": getenv("VIEWER_PASSWORD", "viewer"),
            "role": "dept_viewer",
            "department": "Home",
        },
        {
            "username": getenv("AUDITOR_USER", "auditor"),
            "password": getenv("AUDITOR_PASSWORD", "auditor"),
            "role": "auditor",
            "department": None,
        },
    ]


def db_path() -> Path:
    raw = getenv("DB_PATH", "data/prahari.db")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def crop_dir() -> Path:
    raw = getenv("CROP_DIR", "data/crops")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def face_dir() -> Path:
    raw = getenv("FACE_DIR", "data/faces")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def sentinel_host_configured() -> bool:
    return bool(getenv("SENTINEL_HOST", "").strip())
