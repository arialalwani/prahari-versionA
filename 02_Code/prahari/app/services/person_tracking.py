"""Person tracking on video: YOLO person detection, then ByteTrack for stable IDs.

Phase 1 of the face/ReID upgrade. One PersonTracker per camera or video. Feed
it frames in order; it returns the people it is tracking, each with a track ID
that stays the same while that person stays in view.

Detection runs with a low threshold on purpose. ByteTrack uses weak detections
(0.1 to 0.25) only to continue tracks that already exist, and needs a strong
one (0.25 or more) to start a new track, so a weak false detection cannot
create a person on its own.

With stride > 1 the detector runs on every Nth frame only, as the brief
suggests for CPU budgets; frames in between return the last known tracks.
"""

from __future__ import annotations

from typing import Any

import numpy as np

#: Detector threshold for tracking (ByteTrack's low threshold).
DETECT_CONF = 0.1
PERSON = "person"


def _detect_people(frame_bgr: np.ndarray) -> list[dict[str, Any]]:
    from app.engines.yolo_backend import detect_objects

    return [h for h in detect_objects(frame_bgr, conf=DETECT_CONF) if h.get("object_class") == PERSON]


class PersonTracker:
    def __init__(self, camera_id: str, stride: int = 1) -> None:
        from app.engines import bytetrack_backend

        if stride < 1:
            raise ValueError("stride must be at least 1")
        self.camera_id = camera_id
        self.stride = stride
        self.frame_index = -1
        self._last: list[dict[str, Any]] = []
        self._tracker_key = f"person-tracking:{camera_id}"
        bytetrack_backend.reset(self._tracker_key)

    def process(self, frame_bgr: np.ndarray) -> list[dict[str, Any]]:
        """Return tracked people for this frame.

        Each item: track_id (int), bbox [x, y, w, h], confidence, detected
        (True on frames where the detector ran, False on skipped frames that
        repeat the last result).
        """
        from app.engines import bytetrack_backend

        self.frame_index += 1
        if self.frame_index % self.stride != 0:
            return [dict(t, detected=False) for t in self._last]
        people = _detect_people(frame_bgr)
        dets = []
        for p in people:
            x, y, w, h = [float(v) for v in p["bbox"]]
            dets.append({"box": [x, y, x + w, y + h], "conf": float(p["confidence"]), "cls_id": 0})
        tracks = bytetrack_backend.update(self._tracker_key, dets)
        self._last = [
            {
                "track_id": t["track_id"],
                "bbox": [t["box"][0], t["box"][1], t["box"][2] - t["box"][0], t["box"][3] - t["box"][1]],
                "confidence": t["confidence"],
            }
            for t in tracks
        ]
        return [dict(t, detected=True) for t in self._last]

    def close(self) -> None:
        from app.engines import bytetrack_backend

        bytetrack_backend.reset(self._tracker_key)
