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


def join_fragments(fragments: list[tuple[float, float, float, str]]) -> str:
    """Join (left, top, bottom, token) fragments in reading order.

    Two-row plates (most two-wheelers) put the state and district on the top
    row and the series and number below. Sorting by left edge alone interleaves
    the rows ("AB" sits left of "MH"), so group fragments into rows first.

    A fragment joins the current row when it overlaps the row's vertical span
    by at least half its own height; otherwise it starts a new row. Overlap,
    not centre distance, is the test because an angled single-row plate yields
    boxes of uneven height and offset (measured: "MH04", "HZ" and one tall
    "8055" box on medium02_angled), which all still overlap one another. The
    two rows of a bike plate do not overlap at all. Rows read top to bottom,
    each left to right.
    """
    if not fragments:
        return ""
    rows: list[list[tuple[float, float, float, str]]] = []
    span = (0.0, 0.0)
    for frag in sorted(fragments, key=lambda f: f[1]):
        top, bottom = frag[1], frag[2]
        height = max(1.0, bottom - top)
        if rows:
            overlap = min(bottom, span[1]) - max(top, span[0])
            if overlap >= 0.5 * height:
                rows[-1].append(frag)
                span = (min(span[0], top), max(span[1], bottom))
                continue
        rows.append([frag])
        span = (top, bottom)
    return "".join(f[3] for row in rows for f in sorted(row, key=lambda f: f[0]))


def read(image: np.ndarray) -> tuple[str, float]:
    """Return (text, mean confidence 0-1) for one plate crop.

    Fragments are joined in reading order (see join_fragments): a plate split
    into "MH43" and "CC1745", or a two-row bike plate, must reassemble the way
    a person reads it, not in detection order.
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
            top = min(float(p[1]) for p in box)
            bottom = max(float(p[1]) for p in box)
        except (TypeError, ValueError, IndexError):
            left = top = bottom = 0.0
        fragments.append((left, top, bottom, token, float(conf)))

    if not fragments:
        return "", 0.0
    text = join_fragments([f[:4] for f in fragments])
    mean = sum(f[4] for f in fragments) / len(fragments)
    return text, max(0.0, min(1.0, mean))


def reset() -> None:
    """Drop the cached reader. Used by tests; the model reload is slow."""
    global _reader, _loaded
    _reader = None
    _loaded = False
