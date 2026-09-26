"""Lazy ByteTrack. torch/ultralytics imported only inside update()."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

log = logging.getLogger("prahari.bytetrack")

_OPEN: dict[str, Any] = {}


def engine_available() -> bool:
    try:
        from ultralytics.trackers.byte_tracker import BYTETracker  # noqa: F401

        return True
    except ImportError:
        return False


class _TrackArgs:
    # ultralytics >= 8.4 takes frame_rate on args; older builds took it as a
    # BYTETracker keyword. Both are handled in _get_tracker.
    track_thresh = 0.25
    track_high_thresh = 0.25
    track_low_thresh = 0.1
    new_track_thresh = 0.25
    track_buffer = 30
    match_thresh = 0.8
    fuse_score = False
    frame_rate = 30
    mot20 = False


def _get_tracker(camera_id: str) -> Any:
    if not engine_available():
        return None
    from ultralytics.trackers.byte_tracker import BYTETracker

    cam = camera_id or "_"
    if cam not in _OPEN:
        try:
            _OPEN[cam] = BYTETracker(args=_TrackArgs())
        except TypeError:
            _OPEN[cam] = BYTETracker(args=_TrackArgs(), frame_rate=30)
    return _OPEN[cam]


def update(camera_id: str, detections: list[Any]) -> list[dict[str, Any]]:
    """detections: dicts with box [x1,y1,x2,y2], conf, cls_id — or objects with those attrs."""
    tracker = _get_tracker(camera_id)
    if not tracker or not detections:
        return []
    try:
        import torch
    except ImportError:
        return []
    arr = []
    for item in detections:
        if isinstance(item, dict):
            box = item.get("box") or []
            conf = float(item.get("conf") or item.get("confidence") or 0)
            cls_id = int(item.get("cls_id") or 0)
        else:
            box = list(getattr(item, "box", []) or [])
            conf = float(getattr(item, "conf", 0) or 0)
            cls_id = int(getattr(item, "cls_id", 0) or 0)
        if len(box) != 4:
            continue
        x1, y1, x2, y2 = [float(v) for v in box]
        arr.append([x1, y1, x2, y2, conf, cls_id])
    if not arr:
        return []
    det_tensor = torch.tensor(arr, dtype=torch.float32)
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    try:
        tracks = tracker.update(det_tensor, img)
    except Exception as exc:
        log.warning("ByteTrack update failed: %s", exc)
        return []
    results: list[dict[str, Any]] = []
    for track in tracks:
        if hasattr(track, "is_activated") and not track.is_activated:
            continue
        tlbr = getattr(track, "tlbr", None)
        if tlbr is None:
            continue
        results.append(
            {
                "track_id": int(track.track_id),
                "box": [float(tlbr[0]), float(tlbr[1]), float(tlbr[2]), float(tlbr[3])],
                "confidence": float(getattr(track, "score", 1.0) or 1.0),
                "cls_id": int(getattr(track, "cls", 0) or 0),
            }
        )
    return results


def reset(camera_id: str | None = None) -> None:
    if camera_id:
        _OPEN.pop(camera_id, None)
        _OPEN.pop(camera_id or "_", None)
        return
    _OPEN.clear()
