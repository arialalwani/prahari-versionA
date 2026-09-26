"""Lazy EasyOCR backend. torch/easyocr imported only inside the loader.

EasyOCR is trained on scene text — photographs, angles, uneven light — rather
than scanned documents, which is the regime plate crops actually live in. It
also runs in-process, so unlike the pytesseract path there is no subprocess
spawn per attempt and trying several preprocessing variants stays affordable.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from app import config

log = logging.getLogger("prahari.easyocr")

_reader: Any = None
_loaded = False

#: Plate glyphs only. Constraining the charset stops the reader offering
#: lowercase or punctuation that normalise() would discard anyway.
ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def engine_available() -> bool:
    try:
        import easyocr  # noqa: F401

        return True
    except ImportError:
        return False


def get_reader() -> Any:
    """Build the reader once. First call downloads ~100MB of models."""
    global _reader, _loaded
    if _loaded:
        return _reader
    _loaded = True
    try:
        import easyocr

        gpu = config.getenv("EASYOCR_GPU", "").strip().lower() in {"1", "true", "yes"}
        _reader = easyocr.Reader(["en"], gpu=gpu, verbose=False)
        log.info("easyocr reader ready (gpu=%s)", gpu)
    except Exception as exc:
        log.warning("easyocr unavailable: %s", exc)
        _reader = None
    return _reader


def read(image: np.ndarray) -> tuple[str, float]:
    """Return (text, mean confidence 0-1) for one plate crop.

    Fragments are joined left-to-right: a plate split into "MH43" and "CC1745"
    must reassemble in reading order, not detection order.
    """
    reader = get_reader()
    if reader is None or image is None or getattr(image, "size", 0) == 0:
        return "", 0.0
    try:
        results = reader.readtext(image, allowlist=ALLOWLIST, detail=1, paragraph=False)
    except Exception as exc:
        log.warning("easyocr readtext failed: %s", exc)
        return "", 0.0
    if not results:
        return "", 0.0

    fragments = []
    for item in results:
        if len(item) < 3:
            continue
        box, text, conf = item[0], item[1], item[2]
        token = "".join(ch for ch in str(text).upper() if ch.isalnum())
        if not token:
            continue
        try:
            left = min(float(p[0]) for p in box)
        except (TypeError, ValueError, IndexError):
            left = 0.0
        fragments.append((left, token, float(conf)))

    if not fragments:
        return "", 0.0
    fragments.sort(key=lambda f: f[0])
    text = "".join(f[1] for f in fragments)
    mean = sum(f[2] for f in fragments) / len(fragments)
    return text, max(0.0, min(1.0, mean))


def reset() -> None:
    """Drop the cached reader. Used by tests; the model reload is slow."""
    global _reader, _loaded
    _reader = None
    _loaded = False
