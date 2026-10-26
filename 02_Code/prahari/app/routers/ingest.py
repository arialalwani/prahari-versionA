from __future__ import annotations

import csv
import io
import json
import uuid

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import store
from app.auth import User, assert_write, require_user
from app.services import matcher
from app.services.analyse import analyse
from app.services.anpr import recognize
from app.services.plates import normalise

router = APIRouter()


class ConfirmIn(BaseModel):
    camera_id: str
    plate: str
    ts: str | None = None


def _write_crop(camera_id: str, event_id: str, crop_bgr, entity_type: str = "vehicle") -> dict:
    from app.services.crops import persist

    return persist(camera_id, event_id, crop_bgr, entity_type=entity_type)


def _camera_or_404(camera_id: str) -> dict:
    cam = store.get_camera(camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="unknown camera")
    return cam


def _event_from_anpr(cam: dict, result: dict, pts_ms: int = 0) -> dict:
    wl = matcher.match(result.get("plate"))
    event = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "vehicle",
        "entity_id": result.get("plate") or "",
        "plate": result.get("plate") or "",
        "plate_raw": result.get("plate_raw") or "",
        "confidence": float(result.get("confidence") or 0),
        "camera_id": cam["camera_id"],
        "lat": cam.get("lat") or 0,
        "lon": cam.get("lon") or 0,
        "ts": store.now_iso(),
        "pts_ms": pts_ms,
        "crop_uri": "",
        "category": (wl or {}).get("category") or "",
        "priority": (wl or {}).get("priority") or "",
        "source_case_id": (wl or {}).get("source_case_id") or "",
        "source": "anpr",
    }
    event.update(_write_crop(cam["camera_id"], event["event_id"], result.get("crop_bgr"), "vehicle"))
    return event


def _persist_analyse_event(cam: dict, event: dict) -> dict:
    if not event.get("ts"):
        event["ts"] = store.now_iso()
    crop = event.pop("crop_bgr", None)
    if not event.get("event_id"):
        event["event_id"] = str(uuid.uuid4())
    if crop is not None:
        event.update(
            _write_crop(
                cam["camera_id"],
                event["event_id"],
                crop,
                entity_type=str(event.get("entity_type") or "vehicle"),
            )
        )
    if event.get("bbox") is not None and not event.get("bbox_json"):
        event["bbox_json"] = json.dumps(event.get("bbox"))
    store.insert_detection(event)
    alert = matcher.on_detection(event)
    return {"event": event, "alert": alert}


@router.post("/api/ingest/frame")
async def ingest_frame(
    file: UploadFile = File(...),
    camera_id: str = Form("CAM-OWN-001"),
    user: User = Depends(require_user),
) -> dict:
    """ANPR-only still upload. Use /api/ingest/analyse for objects/faces/intrusion."""
    assert_write(user)
    cam = _camera_or_404(camera_id)
    data = await file.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="could not decode image")
    result = recognize(frame)
    # The full reading travels with every response, accepted or not. Confidence
    # describes the reading; it never decides whether the reading is reported.
    from app.services.anpr import STATUS_LABELS

    status = result.get("status") or ""
    reading = {
        "plate_raw": result.get("plate_raw") or "",
        "plate_candidate": result.get("plate_candidate") or "",
        "confidence": result.get("confidence"),
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "validation": result.get("validation") or "",
        "plate_corrected": bool(result.get("plate_corrected")),
    }
    if not result.get("plate"):
        return {"plate": None, "inserted": False, **reading}
    event = _event_from_anpr(cam, result)
    store.insert_detection(event)
    alert = matcher.on_detection(event)
    return {"inserted": True, "event": event, "alert": alert, **reading}


@router.post("/api/ingest/analyse")
async def ingest_analyse(
    file: UploadFile = File(...),
    camera_id: str = Form("CAM-OWN-001"),
    engines: str | None = Form(None),
    user: User = Depends(require_user),
) -> dict:
    assert_write(user)
    cam = _camera_or_404(camera_id)
    data = await file.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="could not decode image")
    import os

    prev_engines = os.environ.get("ANALYTICS_ENGINES")
    if engines:
        os.environ["ANALYTICS_ENGINES"] = engines
    try:
        raw_events = analyse(frame, cam, pts_ms=0)
    finally:
        if engines:
            if prev_engines is None:
                os.environ.pop("ANALYTICS_ENGINES", None)
            else:
                os.environ["ANALYTICS_ENGINES"] = prev_engines
    persisted = [_persist_analyse_event(cam, ev) for ev in raw_events]
    return {
        "events": [p["event"] for p in persisted],
        "alerts": [p["alert"] for p in persisted if p["alert"]],
        "inserted": bool(persisted),
    }


@router.post("/api/ingest/confirm")
def ingest_confirm(body: ConfirmIn, user: User = Depends(require_user)) -> dict:
    assert_write(user)
    plate = normalise(body.plate)
    if not plate:
        raise HTTPException(status_code=400, detail="plate failed Indian normaliser")
    cam = _camera_or_404(body.camera_id)
    wl = matcher.match(plate)
    event = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "vehicle",
        "entity_id": plate,
        "plate": plate,
        "plate_raw": body.plate,
        "confidence": 1.0,
        "camera_id": cam["camera_id"],
        "lat": cam.get("lat") or 0,
        "lon": cam.get("lon") or 0,
        "ts": body.ts or store.now_iso(),
        "pts_ms": 0,
        "crop_uri": "",
        "category": (wl or {}).get("category") or "",
        "priority": (wl or {}).get("priority") or "",
        "source_case_id": (wl or {}).get("source_case_id") or "",
        "source": "operator_confirm",
    }
    store.insert_detection(event)
    store.audit(user.username, "operator_confirm", f"{plate}@{cam['camera_id']}")
    alert = matcher.on_detection(event)
    return {"inserted": True, "event": event, "alert": alert}


@router.get("/api/detections")
def detections(
    plate: str | None = None,
    camera_id: str | None = None,
    entity_type: str | None = None,
    user: User = Depends(require_user),
) -> list[dict]:
    rows = store.list_detections(plate=plate, camera_id=camera_id, entity_type=entity_type)
    if user.role == "dept_viewer":
        allowed = {c["camera_id"] for c in store.list_cameras(department=user.department)}
        rows = [r for r in rows if r.get("camera_id") in allowed]
    return rows


@router.get("/api/objects/report.csv")
def objects_report(user: User = Depends(require_user)) -> StreamingResponse:
    rows = store.list_detections(entity_type="object")
    buf = io.StringIO()
    fields = ["ts", "camera_id", "object_class", "confidence", "event_id", "pts_ms"]
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "ts": row.get("ts") or "",
                "camera_id": row.get("camera_id") or "",
                "object_class": row.get("object_class") or "",
                "confidence": row.get("confidence") or "",
                "event_id": row.get("event_id") or "",
                "pts_ms": row.get("pts_ms") or 0,
            }
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=objects_report.csv"},
    )


@router.get("/api/intrusion")
def intrusion_alerts(user: User = Depends(require_user)) -> list[dict]:
    rows = [
        a
        for a in store.list_alerts(status="open")
        if (a.get("entity_type") or "") == "intrusion" or (a.get("category") or "") == "INTRUSION"
    ]
    return rows
