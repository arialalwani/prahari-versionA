"""Person detection. YOLO only: no detector means no people, never an invented one.

A skin-colour fallback used to label any large skin-toned patch "person" when
YOLO found nothing, so walls, faces and brown cars became people and could
raise intrusion alerts. It was removed in Phase 0 of the face/ReID upgrade.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from app import config

log = logging.getLogger("prahari.objects")

# Only people are reported. Vehicle classes (car, bus, truck, motorcycle,
# bicycle) were logged as separate rows that nothing used; plates are read by
# ANPR, which finds vehicles through its own list in yolo_backend.
CLASSES = {"person"}
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

_tracks: dict[str, list[dict[str, Any]]] = {}
_next_id: dict[str, int] = {}


def reset(camera_id: str | None = None) -> None:
    if camera_id:
        _tracks.pop(camera_id, None)
        _next_id.pop(camera_id, None)
    else:
        _tracks.clear()
        _next_id.clear()
    try:
        from app.engines import bytetrack_backend

        bytetrack_backend.reset(camera_id)
    except Exception:
        pass


def _iou(a: list[int], b: list[int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def _assign_track(camera_id: str, bbox: list[int], cls: str) -> str:
    cam = camera_id or "_"
    live = _tracks.setdefault(cam, [])
    best_i, best = -1, 0.3
    for i, tr in enumerate(live):
        if tr["cls"] != cls:
            continue
        score = _iou(tr["bbox"], bbox)
        if score > best:
            best, best_i = score, i
    if best_i >= 0:
        live[best_i]["bbox"] = bbox
        return live[best_i]["id"]
    nid = _next_id.get(cam, 1)
    _next_id[cam] = nid + 1
    tid = f"{cam}-{nid}"
    live.append({"id": tid, "bbox": bbox, "cls": cls})
    return tid


def _yolo_detect(frame_bgr: np.ndarray) -> list[dict[str, Any]]:
    from app.engines.yolo_backend import detect_objects

    return detect_objects(frame_bgr)


def _center(bbox: list[int]) -> tuple[float, float]:
    x, y, w, h = bbox
    return x + w / 2.0, y + h / 2.0


def _assign_bytetrack(camera_id: str, hits: list[dict[str, Any]]) -> bool:
    from app.engines.bytetrack_backend import update as bt_update

    dets = []
    for hit in hits:
        x, y, w, h = [int(v) for v in hit["bbox"]]
        dets.append(
            {
                "box": [x, y, x + w, y + h],
                "conf": float(hit.get("confidence") or 0),
                "cls_id": int(hit.get("cls_id") or 0),
            }
        )
    tracks = bt_update(camera_id, dets)
    if not tracks:
        return False
    used: set[int] = set()
    for hit in hits:
        cx, cy = _center(hit["bbox"])
        best_i, best = -1, 1e18
        for i, tr in enumerate(tracks):
            if i in used:
                continue
            x1, y1, x2, y2 = tr["box"]
            tcx, tcy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            dist = (cx - tcx) ** 2 + (cy - tcy) ** 2
            if dist < best:
                best, best_i = dist, i
        if best_i >= 0:
            used.add(best_i)
            hit["track_id"] = f"{camera_id or '_'}-bt-{tracks[best_i]['track_id']}"
        else:
            hit["track_id"] = _assign_track(camera_id, hit["bbox"], hit["object_class"])
    return True


def detect(frame_bgr: np.ndarray, camera_id: str = "") -> list[dict[str, Any]]:
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return []
    engine = config.getenv("OBJECT_ENGINE", "yolo").lower()
    if engine != "yolo":
        # Any other value switches person detection off. There is no
        # heuristic substitute: a missing detector reports no people.
        return []
    try:
        hits = _yolo_detect(frame_bgr)
    except Exception as exc:
        log.warning("OBJECT_ENGINE=yolo unavailable (%s); no person detection", exc)
        return []
    hits = [h for h in hits if h.get("object_class") in CLASSES]
    for hit in hits:
        hit["detector"] = "yolo"
    track_engine = config.getenv("TRACK_ENGINE", "iou").lower()
    assigned = False
    if track_engine == "bytetrack" and hits:
        try:
            assigned = _assign_bytetrack(camera_id, hits)
        except Exception as exc:
            log.warning("TRACK_ENGINE=bytetrack unavailable (%s); IoU fallback", exc)
            assigned = False
    if not assigned:
        for hit in hits:
            hit["track_id"] = _assign_track(camera_id, hit["bbox"], hit["object_class"])
    return hits
