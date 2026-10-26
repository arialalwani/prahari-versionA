"""Images with no person in them, for the Phase 0 acceptance check.

Shared by tests/test_phase0_negatives.py and scripts/negative_person_check.py.
The skin-toned wall is deliberate: it is exactly what the removed skin-colour
fallback used to call a person.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np

from tests.synthetic_faces import write_synthetic


def synthetic_negatives() -> list[tuple[str, np.ndarray]]:
    h, w = 360, 640
    out = [
        ("synthetic/grey_wall", np.full((h, w, 3), 90, np.uint8)),
        ("synthetic/white_wall", np.full((h, w, 3), 235, np.uint8)),
        ("synthetic/skin_toned_wall", np.full((h, w, 3), (140, 170, 210), np.uint8)),  # BGR
        ("synthetic/noise", np.random.default_rng(0).integers(60, 160, (h, w, 3), dtype=np.uint8)),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "face.png"
        write_synthetic(path, seed=4)
        face = cv2.imread(str(path))
    if face is not None:
        out.append(("synthetic/drawn_face_closeup", cv2.resize(face, (480, 480))))
    return out
