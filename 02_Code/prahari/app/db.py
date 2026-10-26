"""SQLite access, schema, and first-boot seed from 03_Data/samples."""

from __future__ import annotations

import csv
import json
import shutil
import sqlite3
from pathlib import Path

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS cameras (
    camera_id TEXT PRIMARY KEY,
    department TEXT,
    ownership TEXT,
    consent INTEGER,
    lat REAL,
    lon REAL,
    protocol TEXT,
    url TEXT,
    retention_days INTEGER,
    cam_type TEXT,
    health TEXT,
    location TEXT,
    codec TEXT,
    width INTEGER,
    height INTEGER,
    rtsp TEXT,
    whep TEXT,
    hls TEXT,
    extra_json TEXT
);

CREATE TABLE IF NOT EXISTS watchlist (
    source_case_id TEXT PRIMARY KEY,
    entity_type TEXT,
    plate TEXT,
    name TEXT,
    category TEXT,
    priority TEXT,
    source TEXT,
    notes TEXT,
    gallery_id TEXT,
    embedding_uri TEXT
);

CREATE TABLE IF NOT EXISTS detections (
    event_id TEXT PRIMARY KEY,
    plate TEXT,
    plate_raw TEXT,
    confidence REAL,
    camera_id TEXT,
    lat REAL,
    lon REAL,
    ts TEXT,
    pts_ms INTEGER,
    crop_uri TEXT,
    category TEXT,
    priority TEXT,
    source_case_id TEXT,
    entity_type TEXT DEFAULT 'vehicle',
    entity_id TEXT,
    face_id TEXT,
    object_class TEXT,
    bbox_json TEXT,
    track_id TEXT,
    source TEXT DEFAULT '',
    crop_uri_original TEXT,
    crop_uri_enhanced TEXT,
    enhancement_method TEXT DEFAULT 'none',
    is_ai_reconstructed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    event_id TEXT,
    plate TEXT,
    camera_id TEXT,
    ts TEXT,
    category TEXT,
    priority TEXT,
    status TEXT,
    ack_by TEXT,
    ack_ts TEXT,
    counter INTEGER DEFAULT 1,
    entity_type TEXT,
    entity_id TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    actor TEXT,
    action TEXT,
    detail TEXT
);
"""


def connect() -> sqlite3.Connection:
    path = config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _as_int(value: str | int | bool | None, default: int = 0) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    text = str(value).strip().lower()
    if text in {"true", "yes", "1"}:
        return 1
    if text in {"false", "no", "0"}:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return default


def _as_float(value: str | float | None, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _copy_sample(name: str, dest_dir: Path) -> Path | None:
    src = config.SAMPLES_DIR / name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    if src.is_file():
        shutil.copy2(src, dest)
        return dest
    if dest.is_file():
        return dest
    return None


def _seed_cameras(conn: sqlite3.Connection, data_dir: Path) -> None:
    csv_path = _copy_sample("cameras.csv", data_dir)
    if csv_path is None:
        raise FileNotFoundError(
            f"cameras.csv not found in {config.SAMPLES_DIR} or {data_dir}"
        )
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    conn.executemany(
        """
        INSERT OR REPLACE INTO cameras (
            camera_id, department, ownership, consent, lat, lon, protocol, url,
            retention_days, cam_type, health, location, codec, width, height,
            rtsp, whep, hls, extra_json
        ) VALUES (
            :camera_id, :department, :ownership, :consent, :lat, :lon, :protocol, :url,
            :retention_days, :cam_type, :health, :location, :codec, :width, :height,
            :rtsp, :whep, :hls, :extra_json
        )
        """,
        [
            {
                "camera_id": row["camera_id"],
                "department": row.get("department", ""),
                "ownership": row.get("ownership", ""),
                "consent": _as_int(row.get("consent"), 0),
                "lat": _as_float(row.get("lat")),
                "lon": _as_float(row.get("lon")),
                "protocol": row.get("protocol", ""),
                "url": row.get("url", ""),
                "retention_days": _as_int(row.get("retention_days"), 0),
                "cam_type": row.get("cam_type", ""),
                "health": row.get("health", "unknown"),
                "location": row.get("location", ""),
                "codec": row.get("codec", ""),
                "width": _as_int(row.get("width"), 0),
                "height": _as_int(row.get("height"), 0),
                "rtsp": row.get("rtsp", ""),
                "whep": row.get("whep", ""),
                "hls": row.get("hls", ""),
                "extra_json": (
                    json.dumps({"roi": [[0, 0.5], [1, 0.5], [1, 1], [0, 1]]})
                    if row.get("camera_id") == "CAM-FCS-001"
                    else ""
                ),
            }
            for row in rows
        ],
    )


def _seed_watchlist(conn: sqlite3.Connection, data_dir: Path) -> None:
    csv_path = _copy_sample("watchlist.csv", data_dir)
    if csv_path is None:
        raise FileNotFoundError(
            f"watchlist.csv not found in {config.SAMPLES_DIR} or {data_dir}"
        )
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    conn.executemany(
        """
        INSERT OR REPLACE INTO watchlist (
            source_case_id, entity_type, plate, name, category, priority, source, notes,
            gallery_id, embedding_uri
        ) VALUES (
            :source_case_id, :entity_type, :plate, :name, :category, :priority, :source, :notes,
            :gallery_id, :embedding_uri
        )
        """,
        [
            {
                "source_case_id": row["source_case_id"],
                "entity_type": row.get("entity_type", ""),
                "plate": row.get("plate", ""),
                "name": row.get("name", ""),
                "category": row.get("category", ""),
                "priority": row.get("priority", ""),
                "source": row.get("source", ""),
                "notes": row.get("notes", ""),
                "gallery_id": row.get("gallery_id")
                or (
                    row["source_case_id"]
                    if (row.get("entity_type") or "").lower() == "person"
                    else ""
                ),
                "embedding_uri": row.get("embedding_uri", ""),
            }
            for row in rows
        ],
    )


def _seed_detections(conn: sqlite3.Connection) -> None:
    src = config.SAMPLES_DIR / "detections_seed.json"
    if not src.is_file():
        raise FileNotFoundError(f"detections_seed.json not found in {config.SAMPLES_DIR}")
    payload = json.loads(src.read_text(encoding="utf-8"))
    conn.executemany(
        """
        INSERT OR REPLACE INTO detections (
            event_id, plate, plate_raw, confidence, camera_id, lat, lon, ts,
            pts_ms, crop_uri, category, priority, source_case_id,
            entity_type, entity_id, source
        ) VALUES (
            :event_id, :plate, :plate_raw, :confidence, :camera_id, :lat, :lon, :ts,
            :pts_ms, :crop_uri, :category, :priority, :source_case_id,
            :entity_type, :entity_id, :source
        )
        """,
        [
            {
                **row,
                "entity_type": row.get("entity_type") or "vehicle",
                "entity_id": row.get("entity_id") or row.get("plate") or "",
                "source": row.get("source") or "seed",
            }
            for row in payload
        ],
    )


_ADD_COLUMNS = {
    "watchlist": [
        ("gallery_id", "TEXT"),
        ("embedding_uri", "TEXT"),
    ],
    "detections": [
        ("entity_type", "TEXT DEFAULT 'vehicle'"),
        ("entity_id", "TEXT"),
        ("face_id", "TEXT"),
        ("object_class", "TEXT"),
        ("bbox_json", "TEXT"),
        ("track_id", "TEXT"),
        ("source", "TEXT DEFAULT ''"),
        ("crop_uri_original", "TEXT"),
        ("crop_uri_enhanced", "TEXT"),
        ("enhancement_method", "TEXT DEFAULT 'none'"),
        ("is_ai_reconstructed", "INTEGER DEFAULT 0"),
    ],
    "alerts": [
        ("entity_type", "TEXT"),
        ("entity_id", "TEXT"),
    ],
}


def migrate_schema(conn: sqlite3.Connection) -> None:
    for table, cols in _ADD_COLUMNS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols:
            if name not in existing:
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                except sqlite3.OperationalError:
                    pass


def init_db() -> None:
    data_dir = config.ROOT / "data"
    crops = config.crop_dir()
    crops.mkdir(parents=True, exist_ok=True)
    config.face_dir().mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    conn = connect()
    try:
        conn.executescript(SCHEMA)
        migrate_schema(conn)
        camera_count = conn.execute("SELECT COUNT(*) AS n FROM cameras").fetchone()["n"]
        if camera_count == 0:
            _seed_cameras(conn, data_dir)
            _seed_watchlist(conn, data_dir)
            _seed_detections(conn)
        conn.commit()
    finally:
        conn.close()


def count_table(name: str) -> int:
    allowed = {"cameras", "watchlist", "detections", "alerts", "audit"}
    if name not in allowed:
        raise ValueError(f"unknown table {name}")
    conn = connect()
    try:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()
        return int(row["n"])
    finally:
        conn.close()
