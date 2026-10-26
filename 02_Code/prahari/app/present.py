"""Strip RTSP and filesystem URLs before anything reaches the browser."""

from __future__ import annotations

from typing import Any

from app.auth import User, issue_stream_token
from app.paths import resolve_media_path


def playback_for(camera: dict[str, Any], actor: str) -> dict[str, Any]:
    protocol = (camera.get("protocol") or "").lower()
    token = issue_stream_token(camera["camera_id"], actor)
    if protocol == "file":
        try:
            path = resolve_media_path(camera.get("url") or "")
        except ValueError:
            return {"kind": "unavailable", "token": token, "reason": "file url outside media roots"}
        if not path.is_file():
            return {
                "kind": "unavailable",
                "token": token,
                "reason": "Drop own_feed.mp4 into 03_Data/recordings",
            }
        from app.services.tracking_stream import is_tracking_camera

        if is_tracking_camera(camera):
            # Served as an MJPEG stream with person boxes and IDs drawn on it.
            return {"kind": "tracking", "token": token}
        return {"kind": "file", "token": token}
    if camera.get("hls"):
        return {"kind": "hls", "token": token}
    if camera.get("rtsp") or protocol == "rtsp":
        return {"kind": "hls", "token": token, "needs_session": True}
    return {"kind": "unavailable", "token": token, "reason": "no playable URL"}


def camera_public(camera: dict[str, Any], user: User) -> dict[str, Any]:
    protocol = (camera.get("protocol") or "").lower()
    body = {
        "camera_id": camera.get("camera_id"),
        "department": camera.get("department"),
        "ownership": camera.get("ownership"),
        "consent": bool(camera.get("consent")),
        "lat": camera.get("lat"),
        "lon": camera.get("lon"),
        "protocol": protocol,
        "retention_days": camera.get("retention_days"),
        "cam_type": camera.get("cam_type"),
        "health": camera.get("health"),
        "location": camera.get("location"),
        "codec": camera.get("codec"),
        "width": camera.get("width"),
        "height": camera.get("height"),
        "playback": playback_for(camera, user.username),
    }
    if protocol == "hls" and camera.get("url") and not str(camera.get("url")).startswith("rtsp://"):
        body["url"] = None
    return body
