"""Phase 0 acceptance: images with no people raise no person and no intrusion.

Runs the synthetic negatives through the full analyse pipeline on the godown
camera, which has a restricted zone, so any invented person would surface as
a person row or a CRITICAL intrusion alert.
"""

from __future__ import annotations

from io import BytesIO

import cv2
import pytest

from tests.negative_images import synthetic_negatives


def _png(img) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _yolo_ready() -> bool:
    try:
        import ultralytics  # noqa: F401
        from app.engines.yolo_backend import weights_path

        return weights_path().is_file()
    except Exception:
        return False


def _analyse_all(client, auth):
    results = []
    for name, img in synthetic_negatives():
        res = client.post(
            "/api/ingest/analyse",
            files={"file": ("neg.png", BytesIO(_png(img)), "image/png")},
            data={"camera_id": "CAM-FCS-001", "engines": "objects"},
            auth=auth,
        )
        assert res.status_code == 200, (name, res.text)
        results.append((name, res.json()))
    return results


def _assert_clean(results):
    for name, body in results:
        people = [e for e in body["events"] if e.get("object_class") == "person"]
        intrusions = [e for e in body["events"] if e.get("entity_type") == "intrusion"]
        assert people == [], f"{name}: invented person {people}"
        assert intrusions == [], f"{name}: false intrusion"
        assert body["alerts"] == [], f"{name}: false alert"


def test_negatives_clean_without_detector(client, auth):
    # The test default has no YOLO. Nothing may stand in for it.
    _assert_clean(_analyse_all(client, auth))


@pytest.mark.skipif(not _yolo_ready(), reason="ultralytics or yolov8n.pt missing")
def test_negatives_clean_with_real_yolo(client, auth, monkeypatch):
    monkeypatch.setenv("OBJECT_ENGINE", "yolo")
    _assert_clean(_analyse_all(client, auth))
