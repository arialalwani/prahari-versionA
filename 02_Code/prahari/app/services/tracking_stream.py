"""Person-tracking video stream for the video wall (Phase 1).

Reads a camera's recorded video file, runs PersonTracker on every frame, draws
the boxes and stable IDs onto the frame on the server, and yields the result as
MJPEG (multipart JPEG). The browser shows it in an <img>, so any video format
works and boxes can never drift out of sync with the picture. Later phases
blur faces here too, before the image leaves the server.

The latest tracks per camera are kept in memory for the status endpoint.
Opening the stream again for the same camera stops the previous one, so a
closed-and-reopened tile never leaves two trackers running.

Cameras opt in with cam_type "people" and a file URL. Live RTSP cameras come
later.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Iterator

import cv2

from app.services import track_faces
from app.services.overlay import draw_tracks
from app.services.person_tracking import PersonTracker

log = logging.getLogger("prahari.tracking_stream")

PEOPLE_CAM_TYPE = "people"
JPEG_QUALITY = 80
BOUNDARY = "frame"

_lock = threading.Lock()
_generation: dict[str, int] = {}
_state: dict[str, dict[str, Any]] = {}


def is_tracking_camera(camera: dict[str, Any]) -> bool:
    return (camera.get("cam_type") or "").lower() == PEOPLE_CAM_TYPE and (camera.get("protocol") or "").lower() == "file"


def state(camera_id: str) -> dict[str, Any]:
    with _lock:
        return dict(_state.get(camera_id) or {"running": False, "people": 0, "ids": []})


def _publish(camera_id: str, **fields: Any) -> None:
    with _lock:
        _state[camera_id] = {**_state.get(camera_id, {}), **fields, "updated": time.time()}


def mjpeg(camera_id: str, path: Path, loop: bool = True, max_frames: int | None = None) -> Iterator[bytes]:
    """Yield MJPEG parts for `path` with tracked people drawn on each frame."""
    with _lock:
        gen = _generation.get(camera_id, 0) + 1
        _generation[camera_id] = gen
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(f"cannot open video {path.name}")
    # Playback is paced by each frame's own timestamp (PTS), never by the
    # declared frame rate, which the project does not trust.
    clock_zero: float | None = None
    tracker = PersonTracker(f"stream:{camera_id}")
    seen_ids: set[int] = set()
    frame_no = sent = 0
    proc_ms = 0.0
    try:
        while _generation.get(camera_id) == gen:
            started = time.perf_counter()
            ok, frame = cap.read()
            if not ok:
                if not loop:
                    break
                # The clip loops: a hard scene cut, so start tracking afresh.
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                tracker.close()
                tracker = PersonTracker(f"stream:{camera_id}")
                seen_ids.clear()
                frame_no = 0
                clock_zero = None
                continue
            pts = (cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0) / 1000.0
            if clock_zero is None:
                clock_zero = started - pts
            tracks = tracker.process(frame)
            seen_ids.update(t["track_id"] for t in tracks)
            # Faces are found per person, blurred on the server (privacy by
            # default), then IDs and quality badges are drawn. Counts are shown
            # in the tile's status line, not on the frame.
            faces = track_faces.find_faces(frame, tracks)
            shown = track_faces.blur(frame, tracks, faces) if track_faces.blur_enabled() else frame
            img = draw_tracks(shown, tracks, faces=faces)
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            proc_ms = 0.9 * proc_ms + 0.1 * (1000 * (time.perf_counter() - started)) if sent else \
                1000 * (time.perf_counter() - started)
            _publish(camera_id, running=True, frame=frame_no, people=len(tracks),
                     ids=sorted(t["track_id"] for t in tracks), ids_seen=len(seen_ids),
                     tracked=[{"id": t["track_id"],
                               "face": (faces[t["track_id"]]["quality"]["band"] if t["track_id"] in faces else None)}
                              for t in sorted(tracks, key=lambda t: t["track_id"])],
                     faces_found=len(faces), blur=track_faces.blur_enabled(),
                     ms_per_frame=round(proc_ms, 1), video_seconds=round(pts, 1))
            if ok:
                data = buf.tobytes()
                yield (f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(data)}\r\n\r\n"
                       .encode() + data + b"\r\n")
                sent += 1
            frame_no += 1
            if max_frames and sent >= max_frames:
                break
            # Play at the clip's own speed when processing is faster than that;
            # when it is slower, never wait.
            due = clock_zero + pts if pts > 0 else started
            spare = due - time.perf_counter()
            if spare > 0:
                time.sleep(min(spare, 1.0))
    finally:
        cap.release()
        tracker.close()
        if _generation.get(camera_id) == gen:
            _publish(camera_id, running=False)


def stop(camera_id: str) -> None:
    """Stop any stream running for this camera."""
    with _lock:
        _generation[camera_id] = _generation.get(camera_id, 0) + 1
        if camera_id in _state:
            _state[camera_id] = {**_state[camera_id], "running": False}
