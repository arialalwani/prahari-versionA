"""Face quality: how usable a detected face is for recognition.

Phase 1 of the face/ReID upgrade. Four factors from the brief, each scored 0..1:

  size        face height in pixels: tiny faces carry little identity
  sharpness   variance of the Laplacian on the face, normalised to 64x64
  pose        how frontal the face is, from the 5 landmarks (yaw and roll)
  brightness  mean grey level: very dark or blown-out faces score low

The weighted sum maps to a band: High, Medium or Low. In Phase 2 the bands
route matching (High: automatic matching, Medium: matching goes to review,
Low: no live matching). The band cut-offs and size limits below are
PROVISIONAL defaults, set in .env; the brief requires calibrating them on the
evaluation set before they drive any decision.
"""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np

from app import config

WEIGHTS = {"size": 0.35, "sharpness": 0.25, "pose": 0.25, "brightness": 0.15}
HIGH, MEDIUM, LOW = "High", "Medium", "Low"


def _setting(name: str, default: float) -> float:
    try:
        return float(config.getenv(name, str(default)) or default)
    except ValueError:
        return default


def size_score(face_height: float) -> float:
    lo, hi = _setting("FACE_Q_MIN_PX", 16), _setting("FACE_Q_GOOD_PX", 80)
    return float(np.clip((face_height - lo) / (hi - lo), 0.0, 1.0))


def sharpness_score(face_bgr: np.ndarray) -> float:
    if face_bgr is None or face_bgr.size == 0:
        return 0.0
    grey = cv2.cvtColor(cv2.resize(face_bgr, (64, 64)), cv2.COLOR_BGR2GRAY)
    variance = float(cv2.Laplacian(grey, cv2.CV_64F).var())
    return float(np.clip(variance / _setting("FACE_Q_SHARP_VAR", 300), 0.0, 1.0))


def pose_score(landmarks: list[list[float]]) -> float:
    """1.0 for a frontal face, falling with yaw (nose off-centre) and roll (tilted eyes)."""
    if not landmarks or len(landmarks) < 3:
        return 0.0
    (lx, ly), (rx, ry), (nx, _ny) = landmarks[0], landmarks[1], landmarks[2]
    eye_dist = math.hypot(rx - lx, ry - ly)
    if eye_dist < 1e-6:
        return 0.0
    yaw = abs(nx - (lx + rx) / 2) / eye_dist          # 0 frontal, ~0.5 near profile
    roll = abs(math.degrees(math.atan2(ry - ly, rx - lx)))
    roll = min(roll, 180 - roll)
    return float(np.clip(1 - yaw / 0.5, 0, 1) * np.clip(1 - roll / 45, 0, 1))


def brightness_score(face_bgr: np.ndarray) -> float:
    if face_bgr is None or face_bgr.size == 0:
        return 0.0
    mean = float(cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY).mean())
    # Best between 80 and 180; linear fall-off towards black and white.
    if mean < 80:
        return float(np.clip((mean - 25) / 55, 0, 1))
    if mean > 180:
        return float(np.clip((235 - mean) / 55, 0, 1))
    return 1.0


def band(score: float) -> str:
    if score >= _setting("FACE_Q_HIGH", 0.65):
        return HIGH
    if score >= _setting("FACE_Q_MEDIUM", 0.40):
        return MEDIUM
    return LOW


def assess(frame_bgr: np.ndarray, face: dict[str, Any]) -> dict[str, Any]:
    """Score one detected face: {score, band, factors: {size, sharpness, pose, brightness}}."""
    x, y, w, h = [int(round(v)) for v in face["bbox"]]
    crop = frame_bgr[max(0, y):max(0, y) + max(1, h), max(0, x):max(0, x) + max(1, w)]
    factors = {
        "size": size_score(h),
        "sharpness": sharpness_score(crop),
        "pose": pose_score(face.get("landmarks") or []),
        "brightness": brightness_score(crop),
    }
    score = sum(WEIGHTS[k] * v for k, v in factors.items())
    return {"score": round(score, 3), "band": band(score), "factors": {k: round(v, 3) for k, v in factors.items()}}
