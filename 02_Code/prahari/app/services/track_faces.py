"""Faces for tracked people: detect inside each person, score quality, blur.

Phase 1 of the face/ReID upgrade. For every tracked person the head area (top
of the person box, at full source resolution) is cropped and searched with
SCRFD. Searching per person instead of the whole frame finds small CCTV faces
that a downscaled frame misses, costs less, and ties each face to its track ID.

Privacy: faces are blurred by default (FACE_BLUR=1). If no face is found for
a tracked person, their head area is blurred instead, so a missed detection
never leaves a face visible. Nothing here identifies anyone; recognition and
watchlist exemptions arrive in Phase 2.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from app import config
from app.engines import scrfd_backend
from app.services import face_quality

#: Head area searched for a face: the top share of the person box, widened.
HEAD_SHARE = 0.4
#: Area blurred when no face is found: the top share of the person box.
FALLBACK_HEAD_SHARE = 0.22
#: Margin added around a found face before blurring.
BLUR_MARGIN = 0.3


def blur_enabled() -> bool:
    return (config.getenv("FACE_BLUR", "1").strip().lower() not in {"0", "false", "no", "off"})


def _head_region(bbox: list[float], frame_shape: tuple[int, ...], share: float) -> tuple[int, int, int, int]:
    H, W = frame_shape[:2]
    x, y, w, h = bbox
    x0 = int(max(0, x - w * 0.25))
    x1 = int(min(W, x + w * 1.25))
    y0 = int(max(0, y - h * 0.1))
    y1 = int(min(H, y + h * share))
    return x0, y0, x1, y1


def _input_size(crop: np.ndarray) -> int:
    # Small crops are upscaled to at least 128 so tiny faces reach SCRFD's
    # working size; large ones keep roughly native resolution.
    side = max(crop.shape[:2])
    return int(min(640, max(128, ((side + 31) // 32) * 32)))


def find_faces(frame_bgr: np.ndarray, tracks: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Best face per track ID, in frame coordinates, with its quality assessment."""
    found: dict[int, dict[str, Any]] = {}
    if not scrfd_backend.engine_available():
        return found
    for t in tracks:
        x0, y0, x1, y1 = _head_region(t["bbox"], frame_bgr.shape, HEAD_SHARE)
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        crop = frame_bgr[y0:y1, x0:x1]
        faces = scrfd_backend.detect(crop, input_size=_input_size(crop))
        if not faces:
            continue
        best = max(faces, key=lambda f: f["score"])
        fx, fy, fw, fh = best["bbox"]
        face = {
            "bbox": [fx + x0, fy + y0, fw, fh],
            "score": best["score"],
            "landmarks": [[px + x0, py + y0] for px, py in best["landmarks"]],
        }
        face["quality"] = face_quality.assess(frame_bgr, face)
        found[t["track_id"]] = face
    return found


def _blur_box(img: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> None:
    H, W = img.shape[:2]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    region = img[y0:y1, x0:x1]
    # Pixelate, then smooth: unreadable at any size, and plainly an edit.
    small = cv2.resize(region, (max(1, (x1 - x0) // 8), max(1, (y1 - y0) // 8)), interpolation=cv2.INTER_LINEAR)
    region[:] = cv2.GaussianBlur(cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST), (0, 0), 3)


def blur(frame_bgr: np.ndarray, tracks: list[dict[str, Any]], faces: dict[int, dict[str, Any]]) -> np.ndarray:
    """Return a copy with every tracked person's face (or head area) blurred."""
    out = frame_bgr.copy()
    for t in tracks:
        face = faces.get(t["track_id"])
        if face:
            fx, fy, fw, fh = face["bbox"]
            mx, my = fw * BLUR_MARGIN, fh * BLUR_MARGIN
            _blur_box(out, int(fx - mx), int(fy - my), int(fx + fw + mx), int(fy + fh + my))
        else:
            _blur_box(out, *_head_region(t["bbox"], out.shape, FALLBACK_HEAD_SHARE))
    return out
