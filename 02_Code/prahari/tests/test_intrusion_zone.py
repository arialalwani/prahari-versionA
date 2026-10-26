"""Restricted-zone geometry, tested on its own: how much of a person box lies in the zone."""

from __future__ import annotations

import pytest

from app.services.intrusion import ZONE_OVERLAP, _person_area_in_roi

FRAME = (360, 640, 3)  # height, width
BOTTOM_HALF = [[0, 0.5], [1, 0.5], [1, 1], [0, 1]]  # normalised polygon


def test_box_fully_inside_zone():
    assert _person_area_in_roi([100, 200, 80, 140], BOTTOM_HALF, FRAME) == pytest.approx(1.0)


def test_box_fully_outside_zone():
    assert _person_area_in_roi([100, 10, 80, 100], BOTTOM_HALF, FRAME) == 0.0


def test_box_straddling_zone_edge():
    # Zone starts at y=180. Box spans y=130..230, so half of it is inside.
    assert _person_area_in_roi([100, 130, 80, 100], BOTTOM_HALF, FRAME) == pytest.approx(0.5)


def test_overlap_threshold_boundary():
    # 30% of the box inside: exactly the threshold.
    share = _person_area_in_roi([100, 110, 80, 100], BOTTOM_HALF, FRAME)
    assert share == pytest.approx(0.30)
    assert share >= ZONE_OVERLAP
    # 20% inside: below it.
    assert _person_area_in_roi([100, 100, 80, 100], BOTTOM_HALF, FRAME) < ZONE_OVERLAP


def test_normalised_rectangle_zone():
    # [x0, y0, x1, y1] as fractions: right half of the frame.
    assert _person_area_in_roi([400, 50, 60, 60], [0.5, 0.0, 1.0, 1.0], FRAME) == pytest.approx(1.0)
    assert _person_area_in_roi([50, 50, 60, 60], [0.5, 0.0, 1.0, 1.0], FRAME) == 0.0


def test_pixel_rectangle_zone():
    assert _person_area_in_roi([10, 10, 20, 20], [0, 0, 100, 100], FRAME) == pytest.approx(1.0)


def test_zero_size_box_does_not_divide_by_zero():
    assert _person_area_in_roi([10, 10, 0, 0], BOTTOM_HALF, FRAME) == 0.0
