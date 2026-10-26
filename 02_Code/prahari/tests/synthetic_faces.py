"""Synthetic face-like images for tests and research harnesses ONLY.

These are drawn shapes (an oval with two dots and an arc), not faces of
people. They exist so tests can exercise enrolment, privacy gating and the
invocation counts in scripts/instrument.py without real biometric data.

They must never be used as demo data, shown to users, or placed in the app's
face gallery. The app no longer creates them (removed in Phase 0 of the
face/ReID upgrade).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def write_synthetic(path: Path, seed: int, shift: int = 0) -> None:
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", (128, 128), (40, 40, 40))
    draw = ImageDraw.Draw(img)
    tone = (180 + (seed * 17) % 50, 130 + (seed * 11) % 40, 110 + (seed * 7) % 30)
    cx, cy = 64 + shift, 70
    draw.ellipse((cx - 40, cy - 50, cx + 40, cy + 50), fill=tone)
    draw.ellipse((cx - 18, cy - 18, cx - 8, cy - 8), fill=(20, 20, 20))
    draw.ellipse((cx + 8, cy - 18, cx + 18, cy - 8), fill=(20, 20, 20))
    draw.arc((cx - 16, cy + 4, cx + 16, cy + 24), 20, 160, fill=(80, 40, 40), width=2)
    noise = rng.integers(0, 40, (128, 128, 3), dtype=np.uint8)
    arr = np.clip(np.array(img, dtype=np.int16) + noise, 0, 255).astype(np.uint8)
    Image.fromarray(arr).save(path)


def write_fixture_pair(root: Path, gallery_id: str, seed: int) -> tuple[Path, Path]:
    folder = Path(root) / gallery_id
    folder.mkdir(parents=True, exist_ok=True)
    a, b = folder / "a.png", folder / "b.png"
    write_synthetic(a, seed=seed)
    write_synthetic(b, seed=seed, shift=2)
    return a, b
