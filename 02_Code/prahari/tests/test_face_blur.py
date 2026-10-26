"""Phase 1 faces: per-person face search and blurring on the video wall."""

from __future__ import annotations

import numpy as np

from app.engines import scrfd_backend
from app.services import track_faces

FRONTAL = [[40, 40], [60, 40], [50, 52], [42, 62], [58, 62]]


# ---------- Faces per person and blurring ----------

def _frame():
    return np.random.default_rng(3).integers(0, 255, (300, 400, 3), dtype=np.uint8)


PERSON = {"track_id": 7, "bbox": [100, 50, 80, 200]}


def test_face_found_in_head_crop_maps_back_to_frame(monkeypatch):
    monkeypatch.setattr(scrfd_backend, "engine_available", lambda: True)
    monkeypatch.setattr(scrfd_backend, "detect", lambda crop, **kw: [
        {"bbox": [30, 15, 20, 24], "score": 0.8, "landmarks": [[35, 22], [45, 22], [40, 28], [36, 33], [44, 33]]}])
    faces = track_faces.find_faces(_frame(), [PERSON])
    # Head crop starts at x = 100 - 80/4 = 80, y = 50 - 200/10 = 30.
    assert faces[7]["bbox"] == [110, 45, 20, 24]
    assert faces[7]["landmarks"][2] == [120, 58]
    assert faces[7]["quality"]["band"] in {"High", "Medium", "Low"}


def test_blur_covers_the_face_and_leaves_the_rest(monkeypatch):
    frame = _frame()
    face = {"bbox": [120, 60, 30, 36], "score": 0.9, "landmarks": FRONTAL}
    out = track_faces.blur(frame, [PERSON], {7: face})
    assert not np.array_equal(out[60:96, 120:150], frame[60:96, 120:150])
    assert np.array_equal(out[200:300, 0:100], frame[200:300, 0:100])


def test_head_area_blurred_when_no_face_found():
    frame = _frame()
    out = track_faces.blur(frame, [PERSON], {})
    assert not np.array_equal(out[50:90, 100:180], frame[50:90, 100:180])  # top of the person
    assert np.array_equal(out[200:250, 100:180], frame[200:250, 100:180])  # legs untouched


def test_blur_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("FACE_BLUR", "0")
    assert track_faces.blur_enabled() is False
    monkeypatch.setenv("FACE_BLUR", "1")
    assert track_faces.blur_enabled() is True
