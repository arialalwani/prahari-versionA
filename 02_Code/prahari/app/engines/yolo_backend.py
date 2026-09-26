"""Lazy YOLO backend. ultralytics is imported only inside loader functions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from app import config

log = logging.getLogger("prahari.yolo")

# COCO: 0 person, 1 bicycle, 2 car, 3 motorcycle, 5 bus, 7 truck
_OBJECT_CLASSES = [0, 1, 2, 3, 5, 7]
_VEHICLE_CLASSES = [2, 3, 5, 7]
_COCO_TO_OURS = {
    "person": "person",
    "car": "car",
    "motorcycle": "motorcycle",
    "motorbike": "motorcycle",
    "bus": "bus",
    "truck": "truck",
    "bicycle": "bicycle",
    "bike": "bicycle",
}

_vehicle_model: Any = None
_vehicle_loaded = False
_plate_model: Any = None
_plate_loaded = False


class Detection:
    def __init__(self, box: list[float], conf: float, cls_id: int, label: str) -> None:
        self.box = box
        self.conf = conf
        self.cls_id = cls_id
        self.label = label


def weights_path() -> Path:
    raw = config.getenv("YOLO_VEHICLE_WEIGHTS", "")
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = config.ROOT / path
        return path
    return config.ROOT / "app" / "models_data" / "yolov8n.pt"


def _get_vehicle_model() -> Any:
    global _vehicle_model, _vehicle_loaded
    if _vehicle_loaded:
        return _vehicle_model
    _vehicle_loaded = True
    try:
        from ultralytics import YOLO

        path = weights_path()
        _vehicle_model = YOLO(str(path) if path.is_file() else "yolov8n.pt")
        log.info("loaded YOLO vehicle weights %s", path)
    except Exception as exc:
        log.warning("YOLO vehicle model unavailable: %s", exc)
        _vehicle_model = None
    return _vehicle_model


def _get_plate_model() -> Any:
    global _plate_model, _plate_loaded
    if _plate_loaded:
        return _plate_model
    _plate_loaded = True
    raw = config.getenv("YOLO_PLATE_WEIGHTS", "")
    if not raw:
        _plate_model = None
        return None
    try:
        from ultralytics import YOLO

        _plate_model = YOLO(raw)
    except Exception as exc:
        log.warning("YOLO plate model unavailable: %s", exc)
        _plate_model = None
    return _plate_model


def detect_objects(frame_bgr: np.ndarray, conf: float | None = None) -> list[dict[str, Any]]:
    """Person + vehicle COCO subset. Used by OBJECT_ENGINE=yolo."""
    model = _get_vehicle_model()
    if model is None or frame_bgr is None:
        return []
    threshold = float(conf if conf is not None else config.OBJECT_MIN_CONFIDENCE)
    try:
        results = model(frame_bgr, conf=threshold, classes=_OBJECT_CLASSES, verbose=False)
    except Exception as exc:
        log.warning("YOLO object detect failed: %s", exc)
        return []
    out: list[dict[str, Any]] = []
    if not results:
        return out
    names = results[0].names if results else {}
    for box in results[0].boxes:
        cls_id = int(box.cls[0])
        raw_name = str(names.get(cls_id, "")).lower()
        name = _COCO_TO_OURS.get(raw_name)
        if not name:
            continue
        score = float(box.conf[0])
        if score < threshold:
            continue
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
        crop = frame_bgr[y1:y2, x1:x2]
        out.append(
            {
                "object_class": name,
                "confidence": score,
                "bbox": [x1, y1, x2 - x1, y2 - y1],
                "crop_bgr": crop,
                "cls_id": cls_id,
            }
        )
    return out


def detect_vehicles(frame_bgr: np.ndarray, conf: float = 0.35) -> list[Detection]:
    """Vehicle-only boxes for ANPR_ENGINE=yolo (person excluded)."""
    model = _get_vehicle_model()
    if model is None or frame_bgr is None:
        return []
    try:
        results = model(frame_bgr, conf=conf, classes=_VEHICLE_CLASSES, verbose=False)
    except Exception as exc:
        log.warning("YOLO vehicle detect failed: %s", exc)
        return []
    dets: list[Detection] = []
    if not results:
        return dets
    names = results[0].names if results else {}
    for box in results[0].boxes:
        b = [float(v) for v in box.xyxy[0].tolist()]
        c = float(box.conf[0])
        cls_id = int(box.cls[0])
        label = str(names.get(cls_id, "vehicle"))
        dets.append(Detection(b, c, cls_id, label))
    return dets


def detect_plates(image_bgr: np.ndarray, conf: float = 0.30) -> list[Detection]:
    """All plate boxes in the image, most confident first.

    Works on a whole frame as well as a vehicle crop — measured, the plate model
    finds plates on frames where vehicle detection returns nothing at all, so the
    caller should not assume a vehicle box is a prerequisite.
    """
    model = _get_plate_model()
    if model is None or image_bgr is None or getattr(image_bgr, "size", 0) == 0:
        return []
    try:
        results = model(image_bgr, conf=conf, verbose=False)
    except Exception as exc:
        log.warning("YOLO plate detect failed: %s", exc)
        return []
    if not results or len(results[0].boxes) == 0:
        return []
    names = getattr(model, "names", {}) or {}
    out: list[Detection] = []
    for box in results[0].boxes:
        cls_id = int(box.cls[0])
        out.append(
            Detection(
                [float(v) for v in box.xyxy[0].tolist()],
                float(box.conf[0]),
                cls_id,
                str(names.get(cls_id, "plate")),
            )
        )
    out.sort(key=lambda d: d.conf, reverse=True)
    return out


def detect_plate(vehicle_crop_bgr: np.ndarray, conf: float = 0.30) -> Detection | None:
    """Single best plate box, or None. Thin wrapper over detect_plates()."""
    plates = detect_plates(vehicle_crop_bgr, conf=conf)
    return plates[0] if plates else None
