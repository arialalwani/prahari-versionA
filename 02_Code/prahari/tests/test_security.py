from app.auth import issue_stream_token, lookup_user, verify_stream_token
from fastapi import HTTPException


def test_cameras_require_auth(client):
    res = client.get("/api/cameras")
    assert res.status_code == 401


def test_home_viewer_hides_mall(client):
    res = client.get("/api/cameras", auth=("home.viewer", "viewer"))
    assert res.status_code == 200
    ids = [c["camera_id"] for c in res.json()]
    assert "CAM-MALL-001" not in ids
    assert "CAM-VAL-001" in ids


def test_confirm_requires_auth(client):
    res = client.post("/api/ingest/confirm", json={"camera_id": "CAM-OWN-001", "plate": "GJ01AB1234"})
    assert res.status_code == 401


def test_auditor_cannot_write(client):
    res = client.post(
        "/api/watchlist",
        json={"source_case_id": "WL-X", "plate": "GJ00XX0000", "category": "OBSERVE", "priority": "LOW"},
        auth=("auditor", "auditor"),
    )
    assert res.status_code == 403


def test_expired_stream_token():
    token = issue_stream_token("CAM-VAL-001", "judge", ttl_s=-5)
    try:
        verify_stream_token(token, "CAM-VAL-001")
        raise AssertionError("expired token should 401")
    except HTTPException as exc:
        assert exc.status_code == 401


def test_viewer_cannot_enroll_faces(client):
    res = client.post(
        "/api/faces/enroll",
        data={"gallery_id": "WL-004", "name": "nope"},
        files={"file": ("x.png", b"xxxx", "image/png")},
        auth=("home.viewer", "viewer"),
    )
    assert res.status_code == 403


def test_confirm_face_endpoint_removed(client, auth):
    res = client.post(
        "/api/ingest/confirm-face",
        json={"camera_id": "CAM-OWN-001", "gallery_id": "WL-004"},
        auth=auth,
    )
    assert res.status_code in {404, 405}


def test_unauthenticated_analyse_401(client):
    res = client.post(
        "/api/ingest/analyse",
        files={"file": ("x.png", b"xxxx", "image/png")},
        data={"camera_id": "CAM-OWN-001"},
    )
    assert res.status_code == 401


def test_tampered_password_fails_lookup():
    from app import config

    assert lookup_user("judge", config.JUDGE_PASSWORD) is not None
    assert lookup_user("judge", "wrong-password-value") is None
    assert lookup_user("judge", "x") is None
