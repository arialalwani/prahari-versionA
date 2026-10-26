"""Person-tracking stream for the video wall (Phase 1).

GET /api/track-stream/{camera_id}?token=...   MJPEG with boxes and stable IDs
GET /api/track-stream/{camera_id}/state       people in view and their IDs

The stream uses the same short-lived stream token as /api/stream, so an <img>
can load it without headers and the camera's file path never reaches the
browser.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app import store
from app.auth import User, require_user, verify_stream_token
from app.paths import resolve_media_path
from app.services import tracking_stream

router = APIRouter()


def _tracking_camera(camera_id: str) -> dict:
    cam = store.get_camera(camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="unknown camera")
    if not tracking_stream.is_tracking_camera(cam):
        raise HTTPException(status_code=404, detail="person tracking is not enabled for this camera")
    return cam


@router.get("/api/track-stream/{camera_id}")
def track_stream(camera_id: str, token: str = Query(...)) -> StreamingResponse:
    verify_stream_token(token, camera_id)
    cam = _tracking_camera(camera_id)
    try:
        path = resolve_media_path(cam.get("url") or "")
    except ValueError:
        raise HTTPException(status_code=400, detail="file url outside media roots")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="video file missing")
    return StreamingResponse(
        tracking_stream.mjpeg(camera_id, path),
        media_type=f"multipart/x-mixed-replace; boundary={tracking_stream.BOUNDARY}",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/track-stream/{camera_id}/state")
def track_state(camera_id: str, user: User = Depends(require_user)) -> dict:
    _tracking_camera(camera_id)
    return tracking_stream.state(camera_id)
