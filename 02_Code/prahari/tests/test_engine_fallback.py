"""T-V01 / T-V02: optional engines fall back when torch/ultralytics are absent."""

from __future__ import annotations

import cv2
import numpy as np

from app.services import faces as faces_mod
from tests.synthetic_faces import write_fixture_pair
from app.services.anpr import recognize
from app.services.objects import detect
from tests.test_objects import _person_blob


def test_facenet_without_torch_identifies_no_one(tmp_path, monkeypatch):
    monkeypatch.setenv("FACE_ENGINE", "facenet")
    monkeypatch.setenv("FACE_DIR", str(tmp_path / "faces"))
    write_fixture_pair(tmp_path / "faces", "WL-004", seed=4)
    write_fixture_pair(tmp_path / "faces", "WL-X", seed=99)
    faces_mod.load_gallery(force=True)

    def boom(*_a, **_k):
        raise ImportError("torch missing")

    monkeypatch.setattr("app.engines.facenet_backend.get_analyzer", boom)
    probe = cv2.imread(str(tmp_path / "faces" / "WL-004" / "a.png"))
    # A failed FaceNet no longer falls back to histogram "matching".
    assert faces_mod.match(probe) == []


def test_yolo_object_engine_without_ultralytics_falls_back(monkeypatch):
    monkeypatch.setenv("OBJECT_ENGINE", "yolo")

    def boom(*_a, **_k):
        raise ImportError("ultralytics missing")

    monkeypatch.setattr("app.engines.yolo_backend.detect_objects", boom)
    frame = cv2.imread(str(_person_blob()))
    hits = detect(frame, camera_id="CAM-OWN-001")
    # Without YOLO there is no person detector, so nothing is invented.
    assert hits == []


def test_yolo_anpr_engine_without_ultralytics_falls_back(monkeypatch):
    monkeypatch.setenv("ANPR_ENGINE", "yolo")

    def boom(*_a, **_k):
        raise ImportError("ultralytics missing")

    monkeypatch.setattr("app.engines.yolo_backend.detect_vehicles", boom)
    frame = np.zeros((80, 160, 3), dtype=np.uint8)
    result = recognize(frame)
    assert isinstance(result, dict)
    assert "plate" in result
