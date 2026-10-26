from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_analyse_source_refuses_cam_prefix():
    analyse = (ROOT / "app" / "services" / "analyse.py").read_text(encoding="utf-8")
    prov = (ROOT / "app" / "services" / "provenance.py").read_text(encoding="utf-8")
    assert "frs_refused" in analyse
    assert "faces_allowed" in analyse
    assert "cam\\d+" in prov or r"^cam\d+" in prov
    assert 'ownership == "Own"' in prov or '!= "Own"' in analyse or '!= "Own"' in prov


def test_facenet_not_constructed_on_cam04(client, auth, monkeypatch, tmp_path):
    """T-V04: FACE_ENGINE=facenet still must not construct FaceAnalyzer on cam04."""
    monkeypatch.setenv("FACE_ENGINE", "facenet")
    from app.engines import facenet_backend as fb
    from tests.synthetic_faces import write_fixture_pair

    fb.reset_analyzer()
    calls = {"n": 0}
    orig = fb.FaceAnalyzer.__init__

    def spy(self, *args, **kwargs):
        calls["n"] += 1
        return orig(self, *args, **kwargs)

    monkeypatch.setattr(fb.FaceAnalyzer, "__init__", spy)
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
    from io import BytesIO

    res = client.post(
        "/api/ingest/analyse",
        files={"file": ("face.png", BytesIO(png), "image/png")},
        data={"camera_id": "cam04", "engines": "anpr,objects,faces"},
        auth=auth,
    )
    assert res.status_code == 200, res.text
    people = [e for e in res.json()["events"] if e.get("entity_type") == "person"]
    assert people == []
    assert calls["n"] == 0
    assert fb._analyzer is None


def test_enroll_refuses_gov_camera(client, auth, tmp_path, monkeypatch):
    """C3: enroll consults the provenance gate before FaceAnalyzer construction."""
    monkeypatch.setenv("FACE_ENGINE", "facenet")
    from app.engines import facenet_backend as fb
    from tests.synthetic_faces import write_fixture_pair

    fb.reset_analyzer()
    calls = {"n": 0}
    orig = fb.FaceAnalyzer.__init__

    def spy(self, *args, **kwargs):
        calls["n"] += 1
        return orig(self, *args, **kwargs)

    monkeypatch.setattr(fb.FaceAnalyzer, "__init__", spy)
    a, _ = write_fixture_pair(tmp_path, "tmpface", seed=4)
    png = Path(a).read_bytes()
    from io import BytesIO

    blocked = client.post(
        "/api/faces/enroll",
        data={"gallery_id": "WL-GOV", "name": "blocked", "camera_id": "CAM-VAL-001"},
        files={"file": ("a.png", BytesIO(png), "image/png")},
        auth=auth,
    )
    assert blocked.status_code == 403, blocked.text
    assert calls["n"] == 0
    assert fb._analyzer is None

    sandbox = client.post(
        "/api/faces/enroll",
        data={"gallery_id": "WL-CAM04", "name": "blocked", "camera_id": "cam04"},
        files={"file": ("a.png", BytesIO(png), "image/png")},
        auth=auth,
    )
    assert sandbox.status_code in {403, 404}
    assert calls["n"] == 0

    ok = client.post(
        "/api/faces/enroll",
        data={"gallery_id": "WL-OWN-C3", "name": "ok", "camera_id": "CAM-OWN-001"},
        files={"file": ("a.png", BytesIO(png), "image/png")},
        auth=auth,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json().get("allow_facenet") is True


def test_runtime_gov_camera_zero_person_events(client, auth):
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (64, 64), (200, 160, 130)).save(buf, format="PNG")
    res = client.post(
        "/api/ingest/analyse",
        files={"file": ("skin.png", BytesIO(buf.getvalue()), "image/png")},
        data={"camera_id": "CAM-VAL-001", "engines": "anpr,objects,faces"},
        auth=auth,
    )
    assert res.status_code == 200
    people = [e for e in res.json()["events"] if e.get("entity_type") == "person"]
    assert people == []
