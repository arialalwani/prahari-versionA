"""OCR fragments must join in reading order, including two-row bike plates."""

from app.engines.easyocr_backend import join_fragments


def test_single_row_reads_left_to_right():
    # Detection order is scrambled; reading order is by left edge.
    frags = [(220.0, 20.0, 60.0, "CC1745"), (10.0, 22.0, 61.0, "MH43")]
    assert join_fragments(frags) == "MH43CC1745"


def test_two_row_bike_plate_reads_top_row_first():
    # "AB" starts further left than "MH" but sits on the lower row.
    frags = [
        (72.0, 22.0, 90.0, "MH"),
        (220.0, 22.0, 90.0, "12"),
        (20.0, 108.0, 176.0, "AB"),
        (158.0, 108.0, 176.0, "1234"),
    ]
    assert join_fragments(frags) == "MH12AB1234"


def test_slight_tilt_stays_one_row():
    # A tilted single-row plate drifts a few pixels but is still one line.
    frags = [(10.0, 30.0, 70.0, "GJ01"), (120.0, 38.0, 78.0, "AB"), (200.0, 44.0, 84.0, "1234")]
    assert join_fragments(frags) == "GJ01AB1234"


def test_angled_plate_with_uneven_boxes_stays_one_row():
    # Real fragments from medium02_angled: tilt gives "HZ" a lower box and
    # "8055" one tall box. All overlap, so it is one row: MH04 HZ 8055.
    frags = [(73.0, 17.0, 35.0, "MH04"), (115.0, 9.0, 53.0, "8055"), (87.0, 33.0, 51.0, "HZ")]
    assert join_fragments(frags) == "MH04HZ8055"


def test_empty():
    assert join_fragments([]) == ""
