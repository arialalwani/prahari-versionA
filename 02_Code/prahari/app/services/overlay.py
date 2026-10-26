"""Draw tracked people onto a frame: box, stable ID label, frame caption.

Shared by the live tracking stream and scripts/tracking_check.py. Colours are
picked from the track ID, so one person keeps one colour while tracked.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

_PALETTE = [(66, 135, 245), (245, 130, 48), (60, 180, 75), (230, 25, 75), (145, 30, 180),
            (70, 240, 240), (240, 50, 230), (210, 245, 60), (0, 128, 128), (170, 110, 40)]


def colour(track_id: int) -> tuple[int, int, int]:
    return _PALETTE[int(track_id) % len(_PALETTE)]


def draw_tracks(frame: np.ndarray, tracks: list[dict[str, Any]], caption: str = "") -> np.ndarray:
    """Return a copy of `frame` with each track's box and "ID n" label drawn on it."""
    out = frame.copy()
    scale = max(0.45, min(1.0, out.shape[0] / 720))
    for t in tracks:
        x, y, w, h = [int(round(v)) for v in t["bbox"]]
        c = colour(t["track_id"])
        cv2.rectangle(out, (x, y), (x + w, y + h), c, 2)
        label = f"ID {t['track_id']}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5 * scale + 0.1, 1)
        top = max(0, y - th - 8)
        cv2.rectangle(out, (x, top), (x + tw + 8, top + th + 8), c, -1)
        cv2.putText(out, label, (x + 4, top + th + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5 * scale + 0.1,
                    (255, 255, 255), 1, cv2.LINE_AA)
    if caption:
        cv2.putText(out, caption, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(out, caption, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    return out
