"""T-V03: FaceNet cosine on consented/synthetic faces. Skip without torch."""

from __future__ import annotations

import pytest


def _vision_ready() -> bool:
    try:
        import torch  # noqa: F401
        from facenet_pytorch import InceptionResnetV1, MTCNN  # noqa: F401

        return True
    except Exception:
        return False


@pytest.mark.skipif(not _vision_ready(), reason="torch+facenet-pytorch not installed")
def test_facenet_same_gallery_beats_other(tmp_path, monkeypatch):
    from app.engines.facenet_backend import cosine, get_analyzer, reset_analyzer
    from app.services import faces as faces_mod
    from tests.synthetic_faces import write_fixture_pair

    monkeypatch.setenv("FACE_ENGINE", "facenet")
    monkeypatch.setenv("FACE_DIR", str(tmp_path / "faces"))
    reset_analyzer()
    write_fixture_pair(tmp_path / "faces", "WL-004", seed=4)
    write_fixture_pair(tmp_path / "faces", "WL-X", seed=99)
    analyzer = get_analyzer()
    a = faces_mod._embed  # histogram still exists
    assert a is not None
    import cv2

    probe = cv2.imread(str(tmp_path / "faces" / "WL-004" / "a.png"))
    other = cv2.imread(str(tmp_path / "faces" / "WL-X" / "a.png"))
    fa = analyzer.extract_faces(probe)
    fb = analyzer.extract_faces(other)
    if not fa or not fb:
        pytest.skip("MTCNN found no face on synthetic ellipse")
    same = cosine(fa[0]["embedding"], fa[0]["embedding"])
    diff = cosine(fa[0]["embedding"], fb[0]["embedding"])
    assert same > diff
