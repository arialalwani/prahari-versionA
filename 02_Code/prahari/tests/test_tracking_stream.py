"""People-tracking stream for the video wall: playback kind, access checks, MJPEG frames."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app import config, store
from app.engines.bytetrack_backend import engine_available
from app.services import person_tracking, tracking_stream

CAM = "CAM-TRACK-TEST"


@pytest.fixture()
def clip(client):
    """A 6-frame MJPG clip inside a media root, registered as a people camera."""
    path = config.ROOT / "data" / "_test_tracking_clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (320, 240))
    for i in range(6):
        frame = np.full((240, 320, 3), 40, np.uint8)
        cv2.rectangle(frame, (40 + 5 * i, 60), (80 + 5 * i, 200), (200, 200, 200), -1)
        writer.write(frame)
    writer.release()
    store.upsert_camera({
        "camera_id": CAM, "department": "Own", "ownership": "Own", "consent": 1, "lat": 0.0, "lon": 0.0,
        "protocol": "file", "url": str(path), "retention_days": 0, "cam_type": "people", "health": "unknown",
        "location": "test clip", "codec": "mjpg", "width": 320, "height": 240,
        "rtsp": "", "whep": "", "hls": "", "extra_json": "",
    })
    yield path
    tracking_stream.stop(CAM)
    path.unlink(missing_ok=True)


def _one_walker(monkeypatch):
    calls = {"n": 0}

    def detect(frame):
        calls["n"] += 1
        return [{"object_class": "person", "confidence": 0.9, "bbox": [40 + 5 * calls["n"], 60, 40, 140]}]

    monkeypatch.setattr(person_tracking, "_detect_people", detect)


def test_people_camera_plays_as_tracking(client, auth, clip):
    cam = client.get(f"/api/cameras/{CAM}", auth=auth).json()
    assert cam["playback"]["kind"] == "tracking"
    assert "url" not in cam or not cam.get("url")  # the file path never reaches the browser


def test_ordinary_file_camera_is_not_tracked(client, auth):
    cam = client.get("/api/cameras/CAM-OWN-001", auth=auth).json()
    assert cam["playback"]["kind"] != "tracking"
    token = cam["playback"]["token"]
    assert client.get(f"/api/track-stream/CAM-OWN-001?token={token}").status_code == 404


def test_stream_requires_a_valid_token(client, clip):
    assert client.get(f"/api/track-stream/{CAM}?token=forged").status_code == 401


def test_state_requires_login(client, clip):
    assert client.get(f"/api/track-stream/{CAM}/state").status_code == 401


@pytest.mark.skipif(not engine_available(), reason="ultralytics ByteTrack missing")
def test_stream_yields_jpeg_frames_and_publishes_ids(client, auth, clip, monkeypatch):
    _one_walker(monkeypatch)
    parts = list(tracking_stream.mjpeg(CAM, clip, loop=False))
    assert len(parts) == 6
    for part in parts:
        assert part.startswith(b"--frame\r\nContent-Type: image/jpeg")
        assert b"\xff\xd8" in part  # JPEG start-of-image
    state = client.get(f"/api/track-stream/{CAM}/state", auth=auth).json()
    assert state["running"] is False  # finished
    assert state["people"] == 1 and len(state["ids"]) == 1
    assert state["ids_seen"] == 1  # one walker, one stable ID
    assert state["blur"] is True  # privacy default
    assert [p["id"] for p in state["tracked"]] == state["ids"]


@pytest.mark.skipif(not engine_available(), reason="ultralytics ByteTrack missing")
def test_reopening_stops_the_previous_stream(clip, monkeypatch):
    _one_walker(monkeypatch)
    first = tracking_stream.mjpeg(CAM, clip, loop=True)
    next(first)
    second = tracking_stream.mjpeg(CAM, clip, loop=False, max_frames=1)
    next(second)
    with pytest.raises(StopIteration):  # the old stream ends at its next frame
        next(first)
