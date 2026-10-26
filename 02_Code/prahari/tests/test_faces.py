from __future__ import annotations

from io import BytesIO
from pathlib import Path

import cv2
import numpy as np

from app.services import faces as faces_mod
from tests.synthetic_faces import write_fixture_pair


def test_histogram_never_identifies(tmp_path, monkeypatch):
    # Even an exact copy of an enrolled image is not identified: colour
    # histograms are not face recognition, so they may not name anyone.
    monkeypatch.setenv("FACE_ENGINE", "histogram")
    monkeypatch.setenv("FACE_DIR", str(tmp_path / "faces"))
    root = Path(tmp_path / "faces")
    write_fixture_pair(root, "WL-004", seed=4)
    faces_mod.load_gallery(force=True)
    probe = cv2.imread(str(root / "WL-004" / "a.png"))
    assert faces_mod.match(probe) == []


def test_analyse_raises_no_face_alert_on_own_camera(client, auth, tmp_path, monkeypatch):
    # The Own camera may run faces, but with no recogniser it must not
    # produce a person identity or an alert from an enrolled photo.
    monkeypatch.setenv("FACE_DIR", str(tmp_path / "faces"))
    a, _ = write_fixture_pair(tmp_path / "faces", "WL-004", seed=4)
    faces_mod.load_gallery(force=True)
    res = client.post(
        "/api/ingest/analyse",
        files={"file": ("face.png", BytesIO(Path(a).read_bytes()), "image/png")},
        data={"camera_id": "CAM-OWN-001", "engines": "faces"},
        auth=auth,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert [e for e in body["events"] if e.get("entity_type") == "person"] == []
    assert body["alerts"] == []


def test_enroll_api_and_no_manual_confirm_face(client, auth, tmp_path, monkeypatch):
    from tests.synthetic_faces import write_fixture_pair

    a, _ = write_fixture_pair(tmp_path, "WL-004", seed=4)
    png = Path(a).read_bytes()
    res = client.post(
        "/api/faces/enroll",
        data={"gallery_id": "WL-004", "name": "Ramesh K"},
        files={"file": ("a.png", BytesIO(png), "image/png")},
        auth=auth,
    )
    assert res.status_code == 200, res.text
    gal = client.get("/api/faces/gallery", auth=auth).json()
    blob = str(gal)
    assert "embedding" not in blob.lower()
    assert "descriptor" not in blob.lower()
    assert "lbph" not in blob.lower()
    # Manual "Confirm face" is gone: it recorded an identity with no
    # verification. The Phase 2 review queue replaces it.
    confirm = client.post(
        "/api/ingest/confirm-face",
        json={"camera_id": "CAM-OWN-001", "gallery_id": "WL-004"},
        auth=auth,
    )
    assert confirm.status_code in {404, 405}
    alerts = client.get("/api/alerts", auth=auth).json()
    assert not [a for a in alerts if a.get("entity_type") == "person"]


def test_no_face_events_on_cam04(client, auth, tmp_path):
    from tests.synthetic_faces import write_fixture_pair

    a, _ = write_fixture_pair(tmp_path, "tmpface", seed=4)
    client.post(
        "/api/cameras",
        json={
            "camera_id": "cam04",
            "ownership": "Gov",
            "consent": True,
            "lat": 23.01,
            "lon": 72.57,
            "location": "Paldi Circle",
            "department": "Home",
        },
        auth=auth,
    )
    png = Path(a).read_bytes()
    res = client.post(
        "/api/ingest/analyse",
        files={"file": ("face.png", BytesIO(png), "image/png")},
        data={"camera_id": "cam04", "engines": "anpr,objects,faces"},
        auth=auth,
    )
    assert res.status_code == 200, res.text
    people = [e for e in res.json()["events"] if e.get("entity_type") == "person"]
    assert people == []


def test_no_face_events_on_gov_ownership(client, auth, tmp_path):
    from tests.synthetic_faces import write_fixture_pair

    a, _ = write_fixture_pair(tmp_path, "tmpface", seed=4)
    png = Path(a).read_bytes()
    res = client.post(
        "/api/ingest/analyse",
        files={"file": ("face.png", BytesIO(png), "image/png")},
        data={"camera_id": "CAM-VAL-001", "engines": "faces"},
        auth=auth,
    )
    assert res.status_code == 200
    people = [e for e in res.json()["events"] if e.get("entity_type") == "person"]
    assert people == []


def test_unknown_face_no_alert(tmp_path, monkeypatch):
    monkeypatch.setenv("FACE_DIR", str(tmp_path / "faces"))
    write_fixture_pair(Path(tmp_path / "faces"), "WL-004", seed=4)
    faces_mod.load_gallery(force=True)
    blank = np.zeros((128, 128, 3), dtype=np.uint8)
    blank[:] = (10, 10, 10)
    hits = faces_mod.match(blank)
    if hits:
        assert hits[0]["face_id"] == ""
