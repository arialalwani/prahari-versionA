"""Lazy ByteTrack (Ultralytics implementation). ultralytics is imported only on first use.

One tracker per camera. Call update() once per processed frame, including
frames with no detections: ByteTrack ages lost tracks frame by frame, so
skipping empty frames would keep dead tracks alive too long.

Ultralytics >= 8.1 expects a results-like object (conf, cls, xywh, boolean
indexing) and returns rows [x1, y1, x2, y2, track_id, score, cls, det_index].
An earlier version of this module passed a raw tensor and read STrack.tlbr,
which no longer exists, so it silently returned no tracks.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

log = logging.getLogger("prahari.bytetrack")

_OPEN: dict[str, Any] = {}

#: ByteTrack thresholds. Detections above HIGH start and extend tracks; those
#: between LOW and HIGH only extend existing tracks (ByteTrack's second pass),
#: which is why the detector should run with a low threshold when tracking.
TRACK_HIGH_THRESH = 0.25
TRACK_LOW_THRESH = 0.1
NEW_TRACK_THRESH = 0.25
#: Association cost limit: a detection joins a track if 1 - IoU <= this, i.e.
#: IoU >= 0.1 at 0.9. Ultralytics' default is 0.8 (IoU >= 0.2), tuned for 30 fps.
#: At 10 fps small, distant people move further than that between frames:
#: measured on a 10 fps pedestrian clip, 0.8 broke 22 tracks into new IDs and
#: 0.9 broke 4, with no ID jumps between people at either setting.
#: Set TRACK_MATCH_THRESH in .env to change it.
MATCH_THRESH = 0.9
#: Frames a lost track is kept before it is dropped.
TRACK_BUFFER = 30


def engine_available() -> bool:
    try:
        from ultralytics.trackers.byte_tracker import BYTETracker  # noqa: F401

        return True
    except ImportError:
        return False


def _match_thresh() -> float:
    from app import config

    try:
        return float(config.getenv("TRACK_MATCH_THRESH", str(MATCH_THRESH)) or MATCH_THRESH)
    except ValueError:
        return MATCH_THRESH


class _TrackArgs:
    tracker_type = "bytetrack"
    track_high_thresh = TRACK_HIGH_THRESH
    track_low_thresh = TRACK_LOW_THRESH
    new_track_thresh = NEW_TRACK_THRESH
    track_buffer = TRACK_BUFFER
    match_thresh = MATCH_THRESH
    fuse_score = True
    frame_rate = 30
    mot20 = False


class _Detections:
    """Minimal results-like container: what BYTETracker.update reads."""

    def __init__(self, xyxy: np.ndarray, conf: np.ndarray, cls: np.ndarray) -> None:
        self.xyxy = xyxy.reshape(-1, 4).astype(np.float32)
        self.conf = conf.reshape(-1).astype(np.float32)
        self.cls = cls.reshape(-1).astype(np.float32)

    @property
    def xywh(self) -> np.ndarray:
        x1, y1, x2, y2 = self.xyxy.T
        return np.stack([(x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1], axis=1)

    def __len__(self) -> int:
        return len(self.conf)

    def __getitem__(self, index: Any) -> "_Detections":
        return _Detections(self.xyxy[index], self.conf[index], self.cls[index])


def _get_tracker(camera_id: str) -> Any:
    if not engine_available():
        return None
    from ultralytics.trackers.byte_tracker import BYTETracker

    cam = camera_id or "_"
    if cam not in _OPEN:
        args = _TrackArgs()
        args.match_thresh = _match_thresh()
        try:
            _OPEN[cam] = BYTETracker(args=args)
        except TypeError:  # older ultralytics took frame_rate as a keyword
            _OPEN[cam] = BYTETracker(args=args, frame_rate=30)
    return _OPEN[cam]


def _parse(item: Any) -> tuple[list[float], float, int] | None:
    if isinstance(item, dict):
        box, conf, cls_id = item.get("box") or [], item.get("conf", item.get("confidence")), item.get("cls_id")
    else:
        box, conf, cls_id = list(getattr(item, "box", []) or []), getattr(item, "conf", 0), getattr(item, "cls_id", 0)
    if len(box) != 4:
        return None
    return [float(v) for v in box], float(conf or 0.0), int(cls_id or 0)


def update(camera_id: str, detections: list[Any]) -> list[dict[str, Any]]:
    """Advance the camera's tracker by one frame.

    detections: dicts (or objects) with box [x1, y1, x2, y2], conf, cls_id.
    Returns active tracks: track_id, box [x1, y1, x2, y2], confidence, cls_id,
    and det_index, the position in `detections` of the box that matched.
    """
    tracker = _get_tracker(camera_id)
    if tracker is None:
        return []
    parsed = [p for p in (_parse(d) for d in detections or []) if p is not None]
    if parsed:
        dets = _Detections(
            np.array([p[0] for p in parsed]), np.array([p[1] for p in parsed]), np.array([p[2] for p in parsed])
        )
    else:
        dets = _Detections(np.zeros((0, 4)), np.zeros(0), np.zeros(0))
    try:
        rows = tracker.update(dets)
    except Exception as exc:
        log.warning("ByteTrack update failed: %s", exc)
        return []
    out: list[dict[str, Any]] = []
    for row in np.asarray(rows).reshape(-1, 8) if len(rows) else []:
        x1, y1, x2, y2, track_id, score, cls_id, det_index = row.tolist()
        out.append(
            {
                "track_id": int(track_id),
                "box": [x1, y1, x2, y2],
                "confidence": float(score),
                "cls_id": int(cls_id),
                "det_index": int(det_index),
            }
        )
    return out


def reset(camera_id: str | None = None) -> None:
    if camera_id:
        _OPEN.pop(camera_id, None)
        return
    _OPEN.clear()
