from __future__ import annotations

from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _person_blob() -> Path:
    path = FIXTURE_DIR / "person_blob.png"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (640, 360), (90, 90, 90))
    # skin-tone rectangle, ~11% of frame, lower half so FCS ROI can overlap
    for x in range(260, 380):
        for y in range(140, 360):
            img.putpixel((x, y), (210, 170, 140))
    img.save(path)
    return path


def _empty_noise() -> Path:
    path = FIXTURE_DIR / "empty_noise.png"
    rng = np.random.default_rng(0)
    arr = rng.integers(80, 120, (360, 640), dtype=np.uint8)
    Image.fromarray(arr).convert("RGB").save(path)
    return path


# A real YOLO person hit, used where a test needs a person to exist. The
# skin-coloured fixture is now a negative: it used to be labelled "person".
_YOLO_PERSON = {"object_class": "person", "confidence": 0.82, "bbox": [260, 140, 120, 220]}


def _stub_yolo(monkeypatch, hits):
    from app.services import objects

    monkeypatch.setenv("OBJECT_ENGINE", "yolo")
    monkeypatch.setattr(objects, "_yolo_detect", lambda frame: [dict(h) for h in hits])


def test_skin_coloured_patch_is_not_a_person(monkeypatch):
    from app.services.objects import detect

    _stub_yolo(monkeypatch, [])  # YOLO sees no one
    frame = cv2.imread(str(_person_blob()))
    assert detect(frame, camera_id="CAM-OWN-001") == []


def test_no_detector_means_no_people():
    from app.services.objects import detect

    # conftest sets OBJECT_ENGINE=opencv, i.e. no YOLO: nothing is invented.
    frame = cv2.imread(str(_person_blob()))
    assert detect(frame, camera_id="CAM-OWN-001") == []


def test_yolo_person_is_reported_and_marked(monkeypatch):
    from app.services.objects import detect

    _stub_yolo(monkeypatch, [_YOLO_PERSON])
    hits = detect(cv2.imread(str(_person_blob())), camera_id="CAM-OWN-001")
    assert [h["object_class"] for h in hits] == ["person"]
    assert hits[0]["detector"] == "yolo"


def test_noise_returns_empty():
    from app.services.objects import detect

    frame = cv2.imread(str(_empty_noise()))
    hits = detect(frame)
    assert hits == []


def test_classes_are_mapped():
    from app.services.objects import CLASSES, _COCO_TO_OURS

    # Only people are reported; the COCO name map is kept for the detector.
    assert CLASSES == {"person"}
    assert _COCO_TO_OURS["motorbike"] == "motorcycle"


def test_vehicle_hits_are_not_reported(monkeypatch):
    import numpy as np

    from app.services import objects

    fake = [
        {"object_class": "car", "confidence": 0.9, "bbox": [0, 0, 10, 10]},
        {"object_class": "person", "confidence": 0.8, "bbox": [20, 20, 10, 10]},
        {"object_class": "truck", "confidence": 0.7, "bbox": [40, 40, 10, 10]},
    ]
    monkeypatch.setenv("OBJECT_ENGINE", "yolo")
    monkeypatch.setattr(objects, "_yolo_detect", lambda frame: [dict(h) for h in fake])
    hits = objects.detect(np.zeros((64, 64, 3), np.uint8))
    assert [h["object_class"] for h in hits] == ["person"]


def test_vehicles_only_frame_has_no_people(monkeypatch):
    import numpy as np

    from app.services import objects

    _stub_yolo(monkeypatch, [{"object_class": "car", "confidence": 0.9, "bbox": [0, 0, 10, 10]}])
    assert objects.detect(np.zeros((64, 64, 3), np.uint8)) == []


def test_yolo_failure_reports_no_people(monkeypatch):
    from app.services import objects

    def boom(frame):
        raise RuntimeError("model failed")

    monkeypatch.setenv("OBJECT_ENGINE", "yolo")
    monkeypatch.setattr(objects, "_yolo_detect", boom)
    assert objects.detect(cv2.imread(str(_person_blob()))) == []


def test_analyse_inserts_object_rows(client, auth, monkeypatch):
    _stub_yolo(monkeypatch, [_YOLO_PERSON])
    png = _person_blob().read_bytes()
    res = client.post(
        "/api/ingest/analyse",
        files={"file": ("person.png", BytesIO(png), "image/png")},
        data={"camera_id": "CAM-OWN-001", "engines": "objects"},
        auth=auth,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    types = [e.get("entity_type") for e in body["events"]]
    assert "object" in types


def test_objects_report_csv(client, auth, monkeypatch):
    _stub_yolo(monkeypatch, [_YOLO_PERSON])
    png = _person_blob().read_bytes()
    client.post(
        "/api/ingest/analyse",
        files={"file": ("person.png", BytesIO(png), "image/png")},
        data={"camera_id": "CAM-OWN-001", "engines": "objects"},
        auth=auth,
    )
    csv = client.get("/api/objects/report.csv", auth=auth)
    assert csv.status_code == 200
    assert "object_class" in csv.text
    assert "camera_id" in csv.text


def test_yolo_engine_without_weights_does_not_crash(monkeypatch):
    from app.services.objects import detect

    monkeypatch.setenv("OBJECT_ENGINE", "yolo")
    frame = cv2.imread(str(_person_blob()))
    hits = detect(frame)
    assert isinstance(hits, list)
