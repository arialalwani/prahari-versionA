"""The HSRP "IND" mark that OCR reads beside the characters is not part of the plate."""

from app.services.plates import inspect, normalise


def test_ind_label_is_dropped_from_bike_plate():
    # Measured OCR output on a two-row bike plate: label + both rows, O for 0.
    r = inspect("INDPBO8DB3893")
    assert r.plate == "PB08DB3893"
    assert "IND plate label" in r.reason


def test_india_label_is_dropped():
    assert normalise("INDIAGJ01AB1234") == "GJ01AB1234"


def test_label_alone_is_not_a_plate():
    assert inspect("IND").plate is None


def test_plate_without_label_unchanged():
    r = inspect("GJ01AB1234")
    assert r.plate == "GJ01AB1234"
    assert r.reason == "matches Indian plate format"


def test_label_strip_still_requires_a_real_state_code():
    # Dropping the label must not let an invalid state code through.
    assert inspect("INDXX01AB1234").plate is None
