"""PersonTracker: stable IDs per person across frames, with YOLO stubbed."""

from __future__ import annotations

import numpy as np
import pytest

from app.engines.bytetrack_backend import engine_available
from app.services import person_tracking
from app.services.person_tracking import PersonTracker

pytestmark = pytest.mark.skipif(not engine_available(), reason="ultralytics ByteTrack missing")

FRAME = np.zeros((480, 640, 3), np.uint8)


def _person(x: float, conf: float = 0.9) -> dict:
    return {"object_class": "person", "confidence": conf, "bbox": [x, 100, 60, 180]}


def _feed(monkeypatch, frames_of_detections):
    queue = list(frames_of_detections)
    monkeypatch.setattr(person_tracking, "_detect_people", lambda frame: [dict(d) for d in queue.pop(0)])


def test_each_person_keeps_one_id(monkeypatch):
    frames = [[_person(20 + 5 * i), _person(500 - 5 * i)] for i in range(20)]
    _feed(monkeypatch, frames)
    tracker = PersonTracker("cam-test")
    seen = [tracker.process(FRAME) for _ in frames]
    ids_per_frame = [sorted(t["track_id"] for t in tracks) for tracks in seen]
    assert all(len(ids) == 2 for ids in ids_per_frame)
    assert len({tuple(ids) for ids in ids_per_frame}) == 1


def test_non_person_classes_are_ignored(monkeypatch):
    monkeypatch.setattr("app.engines.yolo_backend.detect_objects",
                        lambda frame, conf=None: [{"object_class": "car", "confidence": 0.9, "bbox": [0, 0, 50, 50]}])
    assert PersonTracker("cam-cars").process(FRAME) == []


def test_stride_skips_detection_and_repeats_last_tracks(monkeypatch):
    calls = {"n": 0}

    def detect(frame):
        calls["n"] += 1
        return [_person(100 + 6 * calls["n"])]

    monkeypatch.setattr(person_tracking, "_detect_people", detect)
    tracker = PersonTracker("cam-stride", stride=3)
    out = [tracker.process(FRAME) for _ in range(9)]
    assert calls["n"] == 3  # frames 0, 3, 6
    assert [t[0]["detected"] for t in out[:3]] == [True, False, False]
    assert out[1][0]["track_id"] == out[0][0]["track_id"]
    assert out[6][0]["track_id"] == out[0][0]["track_id"]


def test_weak_detection_alone_never_creates_a_person(monkeypatch):
    _feed(monkeypatch, [[_person(50, conf=0.15)]] * 5)
    tracker = PersonTracker("cam-weak")
    assert all(tracker.process(FRAME) == [] for _ in range(5))


def test_bbox_is_xywh(monkeypatch):
    _feed(monkeypatch, [[_person(40)]])
    track = PersonTracker("cam-box").process(FRAME)[0]
    x, y, w, h = track["bbox"]
    assert (round(w), round(h)) == (60, 180)
    assert round(x) == 40 and round(y) == 100


def test_stride_must_be_positive():
    with pytest.raises(ValueError):
        PersonTracker("cam-bad", stride=0)
