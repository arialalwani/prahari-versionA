"""ByteTrack keeps a stable ID per person. Skips only when ultralytics is not installed.

An earlier backend returned no tracks at all and this test skipped instead of
failing, hiding the bug. Tracks must now come back whenever ultralytics exists.
"""

from __future__ import annotations

import pytest

from app.engines.bytetrack_backend import engine_available, reset, update

pytestmark = pytest.mark.skipif(not engine_available(), reason="ultralytics ByteTrack missing")


def _person(x: float, y: float = 20, conf: float = 0.9) -> dict:
    return {"box": [x, y, x + 60, y + 180], "conf": conf, "cls_id": 0}


def _ids(tracks: list[dict]) -> dict[int, int]:
    """det_index -> track_id"""
    return {t["det_index"]: t["track_id"] for t in tracks}


def test_two_walkers_keep_their_ids():
    reset("T1")
    first = None
    for step in range(15):
        tracks = update("T1", [_person(20 + 4 * step), _person(500 - 4 * step)])
        assert len(tracks) == 2, f"frame {step}: {tracks}"
        ids = _ids(tracks)
        if first is None:
            first = ids
        assert ids == first, f"frame {step}: IDs changed {first} -> {ids}"


def test_track_survives_short_detection_gap():
    reset("T2")
    for step in range(5):
        before = update("T2", [_person(50 + 5 * step)])
    track_id = before[0]["track_id"]
    for _ in range(3):  # detector misses the person for 3 frames
        update("T2", [])
    after = update("T2", [_person(50 + 5 * 8)])
    assert after and after[0]["track_id"] == track_id


def test_low_confidence_detection_extends_but_does_not_start_a_track():
    reset("T3")
    assert update("T3", [_person(50, conf=0.15)]) == []  # too weak to start a track
    update("T3", [_person(50)])
    started = update("T3", [_person(54)])
    assert started
    kept = update("T3", [_person(58, conf=0.15)])  # weak, but continues the track
    assert kept and kept[0]["track_id"] == started[0]["track_id"]


def test_det_index_points_at_the_matched_detection():
    reset("T4")
    for step in range(3):
        tracks = update("T4", [_person(400 - 3 * step), _person(30 + 3 * step)])
    for t in tracks:
        x1 = t["box"][0]
        expected = 0 if x1 > 200 else 1
        assert t["det_index"] == expected


def test_reset_starts_fresh_and_cameras_are_independent():
    reset()
    a = update("CAM-A", [_person(10)])
    b = update("CAM-B", [_person(10)])
    assert a and b
    reset("CAM-A")
    assert update("CAM-A", []) == []
    reset()
