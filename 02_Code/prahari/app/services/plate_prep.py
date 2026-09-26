"""Plate candidate ranking, rectification and preprocessing.

Split out of anpr.py so the recogniser stays an orchestrator. Nothing here calls
OCR; it returns candidate regions and preprocessed variants for anpr.py to try.

The scoring is deliberately shape-and-position based rather than tuned to any
particular image: an Indian plate is a wide light rectangle, usually low on the
vehicle, and roughly 4.5:1 (single row) or 2:1 (two row).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

# Single-row Indian plates run about 4.5:1; two-row (many two-wheelers and
# commercial vehicles) about 2:1. Score against whichever is closer.
ASPECT_TARGETS = (4.5, 2.0)
ASPECT_MIN = 1.4
ASPECT_MAX = 7.0

# OCR needs a minimum number of pixels per character to have any chance. Below
# this a candidate is not worth an OCR call.
MIN_CANDIDATE_W = 36
MIN_CANDIDATE_H = 11

# Margin added around a candidate, as a share of its own width/height. Measured:
# widening recovered MH43CC1745 in full where the tight crop read "PHH43CC1745".
PAD_X_FRAC = 0.25
PAD_Y_FRAC = 0.60

# Target height for the rectified crop. Tesseract does best around 30-40px of
# character height, and plate glyphs are roughly 60% of plate height.
TARGET_H = 64
MAX_UPSCALE = 6.0

# Tesseract normally wants a quiet zone, but padding measurably HURT here: it
# cost car1 its read entirely (detection 40% -> 20%). Plate crops already carry
# vehicle bodywork as margin, and synthetic padding confuses layout analysis.
# Left at 0 deliberately; re-measure before changing.
QUIET_ZONE = 0


@dataclass
class Candidate:
    """A possible plate region inside a search area."""

    x: int
    y: int
    w: int
    h: int
    score: float
    contour: Any = None

    @property
    def box(self) -> list[int]:
        return [self.x, self.y, self.w, self.h]

    def crop(self, region_bgr: np.ndarray, pad: int | None = None) -> np.ndarray:
        """Crop the candidate with generous, proportional margin.

        The morphology contour usually captures only part of the plate text, so a
        tight crop cuts characters off the ends — measured: a fixed 3px pad turned
        GJ01AB1234 into "AB1234" and KL11BD3333 into "HD3333". Padding by a share
        of the candidate's own size recovers the full plate, and the extra
        bodywork costs nothing because OCR ignores it.
        """
        h, w = region_bgr.shape[:2]
        if pad is None:
            padx, pady = max(4, int(self.w * PAD_X_FRAC)), max(3, int(self.h * PAD_Y_FRAC))
        else:
            padx = pady = pad
        x0, y0 = max(0, self.x - padx), max(0, self.y - pady)
        x1, y1 = min(w, self.x + self.w + padx), min(h, self.y + self.h + pady)
        if x1 <= x0 or y1 <= y0:
            return region_bgr
        return region_bgr[y0:y1, x0:x1]


def _aspect_score(aspect: float) -> float:
    """1.0 at an ideal plate ratio, falling off smoothly either side."""
    best = 0.0
    for target in ASPECT_TARGETS:
        # tolerance scales with the target so 4.5 is not penalised more than 2.0
        spread = target * 0.45
        best = max(best, float(np.exp(-((aspect - target) ** 2) / (2 * spread**2))))
    return best


def _size_score(w: int, h: int, region_w: int, region_h: int) -> float:
    """Prefer plates that occupy a plausible share of the vehicle, not slivers."""
    if region_w <= 0 or region_h <= 0:
        return 0.0
    width_frac = w / region_w
    # A plate is typically 15-45% of vehicle width. Ramp up to 0.15, flat to 0.45,
    # then fall away so whole-vehicle-sized boxes do not win.
    if width_frac < 0.05:
        return 0.0
    if width_frac < 0.15:
        return width_frac / 0.15
    if width_frac <= 0.50:
        return 1.0
    return max(0.0, 1.0 - (width_frac - 0.50) * 2.0)


def _position_score(y: int, h: int, region_h: int) -> float:
    """Plates sit low on a vehicle. Centre of mass in the lower half scores best."""
    if region_h <= 0:
        return 0.5
    centre = (y + h / 2.0) / region_h
    if centre < 0.25:
        return 0.2       # roof line, windscreen banners
    if centre < 0.45:
        return 0.6
    return 1.0           # lower half, where plates live


def _fill_score(contour: Any, w: int, h: int) -> float:
    """A plate contour fills most of its bounding box. Thin diagonals do not."""
    area = float(cv2.contourArea(contour))
    box_area = float(w * h)
    if box_area <= 0:
        return 0.0
    return min(1.0, area / box_area)


def find_candidates(region_bgr: np.ndarray, limit: int = 3) -> list[Candidate]:
    """Rank plate-shaped regions inside region_bgr, best first.

    Replaces the previous behaviour of taking the first contour that happened to
    pass an aspect filter, which depended on OpenCV's arbitrary contour order.
    """
    if region_bgr is None or getattr(region_bgr, "size", 0) == 0:
        return []
    region_h, region_w = region_bgr.shape[:2]
    gray = cv2.cvtColor(region_bgr, cv2.COLOR_BGR2GRAY)

    # Two passes: blackhat finds dark-on-light characters, tophat catches the
    # light plate body itself. Real plates show up in one or the other.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5))
    found: list[Candidate] = []
    for op in (cv2.MORPH_BLACKHAT, cv2.MORPH_TOPHAT):
        morphed = cv2.morphologyEx(gray, op, kernel)
        _, thresh = cv2.threshold(morphed, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        closed = cv2.morphologyEx(
            thresh, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (19, 5))
        )
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if h <= 0 or w < MIN_CANDIDATE_W or h < MIN_CANDIDATE_H:
                continue
            aspect = w / h
            if not (ASPECT_MIN <= aspect <= ASPECT_MAX):
                continue
            score = (
                0.40 * _aspect_score(aspect)
                + 0.25 * _size_score(w, h, region_w, region_h)
                + 0.20 * _position_score(y, h, region_h)
                + 0.15 * _fill_score(cnt, w, h)
            )
            found.append(Candidate(x, y, w, h, score, cnt))

    found.sort(key=lambda c: c.score, reverse=True)
    return _dedupe(found)[:limit]


def _iou(a: Candidate, b: Candidate) -> float:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1 = min(a.x + a.w, b.x + b.w)
    y1 = min(a.y + a.h, b.y + b.h)
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union else 0.0


def _dedupe(cands: list[Candidate], thresh: float = 0.5) -> list[Candidate]:
    """Blackhat and tophat often find the same plate. Keep the better copy."""
    kept: list[Candidate] = []
    for cand in cands:
        if all(_iou(cand, other) < thresh for other in kept):
            kept.append(cand)
    return kept


def rectify(crop_bgr: np.ndarray, contour: Any = None, min_angle: float = 2.5) -> np.ndarray:
    """Warp an angled plate to a frontal rectangle.

    Uses the contour's minimum-area rectangle. Returns the input unchanged when
    the plate is already square-on or the warp would be degenerate.
    """
    if crop_bgr is None or getattr(crop_bgr, "size", 0) == 0 or contour is None:
        return crop_bgr
    try:
        rect = cv2.minAreaRect(contour)
    except cv2.error:
        return crop_bgr
    (_, _), (rw, rh), angle = rect
    if rw < 1 or rh < 1:
        return crop_bgr
    # minAreaRect reports angle in [-90, 0) or [0, 90) depending on build; fold it
    # to "how far from horizontal is this rectangle".
    skew = abs(angle) if abs(angle) <= 45 else 90 - abs(angle)
    if skew < min_angle:
        return crop_bgr

    box = cv2.boxPoints(rect).astype(np.float32)
    # Order the four corners: top-left, top-right, bottom-right, bottom-left.
    ordered = _order_corners(box)
    width = int(max(np.linalg.norm(ordered[0] - ordered[1]), np.linalg.norm(ordered[3] - ordered[2])))
    height = int(max(np.linalg.norm(ordered[0] - ordered[3]), np.linalg.norm(ordered[1] - ordered[2])))
    if width < MIN_CANDIDATE_W or height < MIN_CANDIDATE_H:
        return crop_bgr
    dest = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32
    )
    try:
        matrix = cv2.getPerspectiveTransform(ordered, dest)
        return cv2.warpPerspective(crop_bgr, matrix, (width, height))
    except cv2.error:
        return crop_bgr


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Return corners as top-left, top-right, bottom-right, bottom-left."""
    ordered = np.zeros((4, 2), dtype=np.float32)
    total = pts.sum(axis=1)
    ordered[0] = pts[np.argmin(total)]
    ordered[2] = pts[np.argmax(total)]
    diff = np.diff(pts, axis=1).ravel()
    ordered[1] = pts[np.argmin(diff)]
    ordered[3] = pts[np.argmax(diff)]
    return ordered


def _upscale(gray: np.ndarray) -> np.ndarray:
    h = gray.shape[0]
    if h <= 0 or h >= TARGET_H:
        return gray
    factor = min(MAX_UPSCALE, TARGET_H / float(h))
    if factor <= 1.05:
        return gray
    return cv2.resize(gray, (0, 0), fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)


def variants(crop_bgr: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Preprocessed images to try OCR on, cheapest-likeliest first.

    Real plates vary between dark-on-light (most Indian private plates) and
    light-on-dark (commercial, and many night captures), so both polarities are
    offered rather than assuming one.
    """
    if crop_bgr is None or getattr(crop_bgr, "size", 0) == 0:
        return []
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY) if crop_bgr.ndim == 3 else crop_bgr
    gray = _upscale(gray)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)

    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    _, otsu_inv = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 9
    )

    # Tesseract wants dark glyphs on a light ground. Most Indian private plates
    # are dark-on-light, but commercial, EV and night captures are the reverse.
    # Measuring which we have lets the likely variant go first, so the caller's
    # early exit fires on attempt one instead of after all four. Each attempt is
    # a subprocess spawn, so ordering is worth more than it looks.
    dark_text_on_light = float(clahe.mean()) >= 110.0
    if dark_text_on_light:
        out = [("clahe_otsu", otsu), ("clahe", clahe), ("adaptive", adaptive), ("clahe_otsu_inv", otsu_inv)]
    else:
        out = [("clahe_otsu_inv", otsu_inv), ("adaptive", adaptive), ("clahe", clahe), ("clahe_otsu", otsu)]
    return [(name, cv2.cvtColor(_quiet_zone(img), cv2.COLOR_GRAY2RGB)) for name, img in out]


def _quiet_zone(gray: np.ndarray, pad: int = QUIET_ZONE) -> np.ndarray:
    """Pad with the image's own border tone so the margin matches the background.

    Padding a light-text-on-dark plate with white would put a bright frame around
    dark pixels and confuse layout analysis, so take the tone from the edges.
    """
    if gray is None or gray.size == 0:
        return gray
    border = np.concatenate(
        [gray[0, :].ravel(), gray[-1, :].ravel(), gray[:, 0].ravel(), gray[:, -1].ravel()]
    )
    fill = int(np.median(border))
    return cv2.copyMakeBorder(
        gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=fill
    )
