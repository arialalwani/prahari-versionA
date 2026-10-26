"""Phase 1 faces: SCRFD decoding and face quality."""

from __future__ import annotations

import numpy as np
import pytest

from app.engines import scrfd_backend
from app.services import face_quality

FRONTAL = [[40, 40], [60, 40], [50, 52], [42, 62], [58, 62]]
TURNED = [[40, 40], [60, 40], [63, 52], [52, 62], [64, 62]]   # nose far off-centre: near profile
TILTED = [[40, 30], [60, 50], [50, 52], [42, 62], [58, 62]]   # eyes at 45 degrees


# ---------- SCRFD decoding ----------

def _fake_outputs(input_size: int, stride: int, cell: tuple[int, int], dist: list[float], kps_offsets: list[float]):
    """Raw SCRFD outputs with one confident anchor at `cell` of `stride`."""
    outs_score, outs_box, outs_kps = [], [], []
    for s in scrfd_backend.STRIDES:
        n = (input_size // s) ** 2 * scrfd_backend.NUM_ANCHORS
        score, box, kps = np.zeros((n, 1), np.float32), np.zeros((n, 4), np.float32), np.zeros((n, 10), np.float32)
        if s == stride:
            gx, gy = cell
            idx = (gy * (input_size // s) + gx) * scrfd_backend.NUM_ANCHORS
            score[idx] = 0.9
            box[idx] = np.array(dist) / s
            kps[idx] = np.array(kps_offsets) / s
        outs_score.append(score), outs_box.append(box), outs_kps.append(kps)
    return outs_score + outs_box + outs_kps


def test_decode_recovers_box_and_landmarks():
    # Anchor centre at stride 16, cell (5, 3) = (80, 48). Box extends 10/12/14/16 px.
    kps = [-6, -4, 6, -4, 0, 2, -5, 8, 5, 8]
    boxes, scores, landmarks = scrfd_backend.decode(_fake_outputs(160, 16, (5, 3), [10, 12, 14, 16], kps), (160, 160))
    assert len(scores) == 1 and scores[0] == pytest.approx(0.9)
    assert boxes[0].tolist() == pytest.approx([70, 36, 94, 64])
    assert landmarks[0][0].tolist() == pytest.approx([74, 44])  # left eye
    assert landmarks[0][2].tolist() == pytest.approx([80, 50])  # nose


def test_decode_ignores_low_scores():
    outs = _fake_outputs(160, 8, (2, 2), [4, 4, 4, 4], [0] * 10)
    outs[0][outs[0] > 0] = 0.3
    boxes, scores, _ = scrfd_backend.decode(outs, (160, 160))
    assert len(scores) == 0


@pytest.mark.skipif(not scrfd_backend.engine_available(), reason="onnxruntime or SCRFD weights missing")
def test_real_model_finds_no_face_on_a_blank_wall():
    assert scrfd_backend.detect(np.full((480, 640, 3), 90, np.uint8)) == []


# ---------- Face quality ----------

def test_frontal_beats_turned_and_tilted():
    assert face_quality.pose_score(FRONTAL) == pytest.approx(1.0)
    assert face_quality.pose_score(TURNED) < 0.5
    assert face_quality.pose_score(TILTED) < 0.1


def test_size_and_brightness_scores():
    assert face_quality.size_score(10) == 0.0
    assert face_quality.size_score(200) == 1.0
    assert 0 < face_quality.size_score(48) < 1
    assert face_quality.brightness_score(np.full((20, 20, 3), 128, np.uint8)) == 1.0
    assert face_quality.brightness_score(np.full((20, 20, 3), 10, np.uint8)) == 0.0
    assert face_quality.brightness_score(np.full((20, 20, 3), 250, np.uint8)) == 0.0


def test_sharp_face_scores_above_blurred_face():
    rng = np.random.default_rng(1)
    sharp = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    flat = np.full((64, 64, 3), 128, np.uint8)
    assert face_quality.sharpness_score(sharp) > face_quality.sharpness_score(flat)


def test_bands_follow_configurable_thresholds(monkeypatch):
    assert face_quality.band(0.9) == "High"
    assert face_quality.band(0.5) == "Medium"
    assert face_quality.band(0.1) == "Low"
    monkeypatch.setenv("FACE_Q_HIGH", "0.95")
    assert face_quality.band(0.9) == "Medium"


def test_assess_returns_band_and_factors():
    frame = np.random.default_rng(2).integers(60, 200, (200, 200, 3), dtype=np.uint8)
    q = face_quality.assess(frame, {"bbox": [30, 20, 80, 90], "landmarks": [[x + 30, y + 10] for x, y in FRONTAL]})
    assert q["band"] in {"High", "Medium", "Low"}
    assert set(q["factors"]) == {"size", "sharpness", "pose", "brightness"}
