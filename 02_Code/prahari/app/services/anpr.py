"""recognize() is the only AI interface. Tesseract now; YOLO later behind ANPR_ENGINE."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from app import config
from app.services.plates import normalise

log = logging.getLogger("prahari.anpr")

# Windows installers do not put tesseract.exe on PATH, and a service started before
# the install inherits the old PATH anyway. Resolve the binary explicitly.
_TESSERACT_FALLBACKS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def _bind_tesseract(pytesseract: Any) -> None:
    from pathlib import Path
    from shutil import which

    configured = config.getenv("TESSERACT_CMD", "").strip()
    if configured:
        pytesseract.pytesseract.tesseract_cmd = configured
        return
    if which("tesseract"):
        return
    for candidate in _TESSERACT_FALLBACKS:
        if Path(candidate).is_file():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return


_WHITELIST = "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
# psm 7 reads a single text line (single-row plates); psm 8 reads a single word
# and does better on tight crops. Each mode costs a subprocess spawn, so this is
# deliberately short — see _read_region for the rest of the cost control.
_PSM_MODES = ("--psm 7", "--psm 8")

#: Stop searching once a well-formed plate reaches this confidence. Lower than a
#: "certain" read, because every further attempt costs another tesseract spawn
#: and spawns dominate runtime.
_GOOD_ENOUGH = 0.55

# Why a reading is or is not trusted. Kept separate from the reading itself so a
# weak or malformed result is still reported rather than silently dropped.
STATUS_VERIFIED = "verified"          # passes format, state code and confidence
STATUS_LOW_CONFIDENCE = "low_confidence"  # valid plate, OCR was unsure
STATUS_UNVERIFIED = "unverified"      # OCR read something that is not a valid plate
STATUS_NO_TEXT = "no_text"            # OCR found nothing to read

#: Human labels for the UI. The distinction that matters to an operator is
#: "we read this but do not trust it" versus "we read nothing".
STATUS_LABELS = {
    STATUS_VERIFIED: "Verified",
    STATUS_LOW_CONFIDENCE: "Unverified / Low confidence",
    STATUS_UNVERIFIED: "Unverified / Failed validation",
    STATUS_NO_TEXT: "No text read",
}


def _ocr_once(pytesseract: Any, rgb: np.ndarray, psm: str) -> tuple[str, str | None, float]:
    """Return (raw text, normalised plate or None, mean confidence 0-1).

    Uses image_to_data only: it carries both the words and their confidences, so
    calling image_to_string as well would double the subprocess count for nothing.
    """
    cfg = f"{psm} {_WHITELIST}"
    try:
        data = pytesseract.image_to_data(rgb, config=cfg, output_type=pytesseract.Output.DICT)
    except Exception as exc:  # a bad crop must not kill the whole frame
        log.warning("tesseract call failed: %s", exc)
        return "", None, 0.0
    words, confs = [], []
    for word, conf in zip(data.get("text", []), data.get("conf", [])):
        token = "".join(ch for ch in str(word) if ch.isalnum())
        if not token:
            continue
        words.append(token)
        if str(conf).lstrip("-").isdigit() and int(conf) >= 0:
            confs.append(int(conf))
    raw = "".join(words)
    plate = normalise(raw)
    mean = (sum(confs) / len(confs) / 100.0) if confs else (0.5 if plate else 0.0)
    if plate and mean <= 0:
        mean = 0.5
    return raw, plate, mean


def ocr_engine() -> str:
    """Which OCR engine reads the characters, independent of how we crop.

    ANPR_ENGINE selects the *localisation* strategy (heuristic vs vehicle-first
    YOLO); OCR_ENGINE selects the *reader*. They are orthogonal, so either can be
    swapped and measured on its own.
    """
    raw = config.getenv("OCR_ENGINE", "tesseract").strip().lower()
    return raw or "tesseract"


def _attempts(rgb: np.ndarray, engine: str, pytesseract: Any):
    """Yield (label, raw text, plate, confidence) for one preprocessed image.

    Tesseract needs several page-segmentation modes tried; EasyOCR has no such
    concept and does its own layout analysis, so it gets one pass.
    """
    if engine == "easyocr":
        from app.engines import easyocr_backend

        raw, conf = easyocr_backend.read(rgb)
        yield "easyocr", raw, normalise(raw), conf
        return
    for psm in _PSM_MODES:
        raw, plate, conf = _ocr_once(pytesseract, rgb, psm)
        yield psm.split()[-1], raw, plate, conf


def _read_region(pytesseract: Any, region_bgr: np.ndarray, cand: Any = None) -> dict[str, Any]:
    """Try every preprocessing variant on one region; keep the best reading.

    A result that normalises to a valid plate always beats one that does not,
    regardless of raw OCR confidence — an unparseable high-confidence string is
    not a plate.
    """
    from app.services import plate_prep

    engine = ocr_engine()
    crop = region_bgr
    if cand is not None:
        crop = plate_prep.rectify(crop, getattr(cand, "contour", None))

    best = {"plate": None, "plate_raw": "", "confidence": 0.0, "variant": ""}
    # EasyOCR handles colour and contrast itself, so the original crop is worth
    # trying first; binarising can destroy information it would have used.
    images: list[tuple[str, np.ndarray]] = []
    if engine == "easyocr":
        images.append(("raw", crop))
    images.extend(plate_prep.variants(crop) or [])

    for name, rgb in images:
        for label, raw, plate, conf in _attempts(rgb, engine, pytesseract):
            better = (plate and not best["plate"]) or (
                bool(plate) == bool(best["plate"]) and conf > best["confidence"]
            )
            if better:
                best = {
                    "plate": plate,
                    "plate_raw": raw,
                    "confidence": conf,
                    "variant": f"{name}/{label}",
                }
            # A well-formed plate at usable confidence ends the search. Trying the
            # remaining variants costs more than the marginal accuracy is worth.
            if plate and conf >= _GOOD_ENOUGH:
                return {**best, "crop_bgr": crop}
    return {**best, "crop_bgr": crop}


def _tesseract_recognize(frame_bgr: np.ndarray) -> dict[str, Any]:
    """Rank plate candidates in the region, then OCR the best few.

    Named for history; the reader is whatever OCR_ENGINE selects. Localisation
    is the same either way.
    """
    from app.services import plate_prep

    pytesseract: Any = None
    if ocr_engine() != "easyocr":
        import pytesseract as _pt

        pytesseract = _pt
        _bind_tesseract(pytesseract)
        try:
            pytesseract.get_tesseract_version()
        except Exception:
            return {
                "plate": None,
                "plate_raw": "",
                "confidence": 0.0,
                "crop_bgr": frame_bgr,
                "box": None,
            }

    candidates = plate_prep.find_candidates(frame_bgr, limit=3)

    # The two readers want opposite crops, measured on the test set: EasyOCR runs
    # its own text detection and needs surrounding context (a tight crop truncated
    # GJ01AB1234 to "AB1234"), while Tesseract wants a tight single line and lost
    # both its reads when given the wider crop.
    pad = None if ocr_engine() == "easyocr" else 3

    best: dict[str, Any] = {"plate": None, "plate_raw": "", "confidence": 0.0, "crop_bgr": frame_bgr}
    best_box = None
    for cand in candidates:
        result = _read_region(pytesseract, cand.crop(frame_bgr, pad=pad), cand)
        if (result["plate"] and not best["plate"]) or (
            bool(result["plate"]) == bool(best["plate"]) and result["confidence"] > best["confidence"]
        ):
            best, best_box = result, cand.box
        if result["plate"] and result["confidence"] >= _GOOD_ENOUGH:
            break

    # No candidate produced a plate: fall back to reading the region whole. This
    # preserves the original behaviour for images that are already a plate crop.
    if not best["plate"]:
        whole = _read_region(pytesseract, frame_bgr)
        if whole["plate"] or whole["confidence"] > best["confidence"]:
            best, best_box = whole, best_box if best["plate"] else None

    plate = best["plate"]
    conf = float(best["confidence"])
    if plate and conf < config.ANPR_MIN_CONFIDENCE:
        plate = None
    return {
        "plate": plate,
        "plate_raw": best["plate_raw"],
        "confidence": conf,
        "crop_bgr": best.get("crop_bgr", frame_bgr),
        "box": best_box,
    }


def _crop_xyxy(frame_bgr: np.ndarray, box: list[float]) -> tuple[np.ndarray, list[int]]:
    x1, y1, x2, y2 = [int(v) for v in box[:4]]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(frame_bgr.shape[1], x2), min(frame_bgr.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return frame_bgr, [0, 0, int(frame_bgr.shape[1]), int(frame_bgr.shape[0])]
    return frame_bgr[y1:y2, x1:x2], [x1, y1, x2 - x1, y2 - y1]


def _box_area(det: Any) -> float:
    box = getattr(det, "box", None) or []
    if len(box) < 4:
        return 0.0
    return max(0.0, float(box[2]) - float(box[0])) * max(0.0, float(box[3]) - float(box[1]))


def rank_vehicles(vehicles: list[Any]) -> list[Any]:
    """Most plate-bearing vehicle first.

    Detector order is arbitrary, so the previous vehicles[0] could pick a distant
    parked car over the one filling the frame. Rank by apparent size — a nearer
    vehicle has a larger, more readable plate — with confidence as a tiebreak.
    """
    if not vehicles:
        return []
    largest = max(_box_area(v) for v in vehicles) or 1.0
    return sorted(
        vehicles,
        key=lambda v: 0.8 * (_box_area(v) / largest) + 0.2 * float(getattr(v, "conf", 0.0) or 0.0),
        reverse=True,
    )


def _plate_box_iou(a: list[int], b: list[int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


class YoloEngine:
    #: How many vehicles to attempt per frame. Multi-vehicle frames are common;
    #: stopping at the largest would miss the others.
    MAX_VEHICLES = 2
    #: How many plate boxes to OCR before giving up on a frame.
    MAX_PLATES = 3
    #: Padding around a detected plate box, as a share of its size. The detector
    #: boxes the plate tightly; EasyOCR reads better with a little context.
    PLATE_PAD = 0.12

    def _plate_boxes(self, frame_bgr: np.ndarray) -> list[tuple[list[int], float]]:
        """Frame-coordinate plate boxes from two passes, best first.

        The whole-frame pass matters on its own: measured, the plate model finds
        plates on frames where vehicle detection returns nothing (a partially
        framed car in poor light). The vehicle pass then catches small plates that
        are easy to miss at full-frame scale.
        """
        from app.engines.yolo_backend import detect_plates, detect_vehicles

        found: list[tuple[list[int], float]] = []
        for det in detect_plates(frame_bgr):
            _, box = _crop_xyxy(frame_bgr, det.box)
            found.append((box, det.conf))

        for vehicle in rank_vehicles(detect_vehicles(frame_bgr))[: self.MAX_VEHICLES]:
            vehicle_crop, vbox = _crop_xyxy(frame_bgr, vehicle.box)
            for det in detect_plates(vehicle_crop):
                _, local = _crop_xyxy(vehicle_crop, det.box)
                found.append(([vbox[0] + local[0], vbox[1] + local[1], local[2], local[3]], det.conf))

        found.sort(key=lambda item: item[1], reverse=True)
        kept: list[tuple[list[int], float]] = []
        for box, conf in found:
            if all(_plate_box_iou(box, other) < 0.5 for other, _ in kept):
                kept.append((box, conf))
        return kept[: self.MAX_PLATES]

    def _pad(self, frame_bgr: np.ndarray, box: list[int]) -> np.ndarray:
        x, y, w, h = box
        px, py = int(w * self.PLATE_PAD), int(h * self.PLATE_PAD)
        fh, fw = frame_bgr.shape[:2]
        return frame_bgr[max(0, y - py):min(fh, y + h + py), max(0, x - px):min(fw, x + w + px)]

    def recognize(self, frame_bgr: np.ndarray) -> dict[str, Any]:
        import pytesseract as _pt

        boxes = self._plate_boxes(frame_bgr)
        if boxes:
            use_tesseract = ocr_engine() != "easyocr"
            if use_tesseract:
                _bind_tesseract(_pt)
            best: dict[str, Any] | None = None
            for box, _conf in boxes:
                crop = self._pad(frame_bgr, box)
                result = _read_region(_pt if use_tesseract else None, crop)
                result["box"] = box
                if result.get("plate"):
                    if best is None or result["confidence"] > best["confidence"]:
                        best = result
                    if result["confidence"] >= _GOOD_ENOUGH:
                        return best
                elif best is None:
                    best = result
            if best is not None and best.get("plate"):
                return best

        # No plate model, or it found nothing worth accepting: fall back to the
        # shape heuristic over the vehicle, then the whole frame.
        vehicles = rank_vehicles(_safe_vehicles(frame_bgr))
        for vehicle in vehicles[: self.MAX_VEHICLES]:
            vehicle_crop, vbox = _crop_xyxy(frame_bgr, vehicle.box)
            result = _tesseract_recognize(vehicle_crop)
            if result.get("plate"):
                if result.get("box"):
                    bx, by, bw, bh = result["box"]
                    result["box"] = [vbox[0] + bx, vbox[1] + by, bw, bh]
                else:
                    result["box"] = vbox
                return result
        return _tesseract_recognize(frame_bgr)


def _safe_vehicles(frame_bgr: np.ndarray) -> list[Any]:
    from app.engines.yolo_backend import detect_vehicles

    try:
        return detect_vehicles(frame_bgr)
    except Exception as exc:
        log.warning("vehicle detect failed: %s", exc)
        return []


def recognize(frame_bgr: np.ndarray) -> dict[str, Any]:
    """Read a plate from one frame.

    Always reports what OCR actually saw alongside the verdict: an empty result
    and a rejected-but-real reading are different failures, and an operator can
    only act on the difference if we show it.
    """
    from app.services.plates import inspect

    engine = config.getenv("ANPR_ENGINE", "tesseract").lower()
    result: dict[str, Any] | None = None
    if engine == "yolo":
        try:
            result = YoloEngine().recognize(frame_bgr)
        except Exception as exc:
            log.warning("ANPR_ENGINE=yolo unavailable (%s); tesseract fallback", exc)
    if result is None:
        result = _tesseract_recognize(frame_bgr)

    raw = result.get("plate_raw") or ""
    reading = inspect(raw)
    conf = float(result.get("confidence") or 0.0)

    # Four separate facts, never collapsed into one:
    #   plate_raw       what OCR produced, always kept whatever its confidence
    #   confidence      how sure OCR was, a description not a gate on display
    #   status          why the reading is or is not trusted
    #   plate           the verified result, set only when everything passes
    #
    # A weak reading is evidence, not noise: temporal voting will weigh several
    # of them against each other, so discarding them here would throw away the
    # input that resolves single-frame ambiguity.
    result["plate_candidate"] = reading.plate or ""
    result["plate_corrected"] = reading.corrected

    if not raw:
        result["status"] = STATUS_NO_TEXT
        result["validation"] = "no text read"
    elif not reading.ok:
        result["status"] = STATUS_UNVERIFIED
        result["validation"] = reading.reason
    elif conf < config.ANPR_MIN_CONFIDENCE:
        result["status"] = STATUS_LOW_CONFIDENCE
        result["validation"] = (
            f"reads as {reading.plate}, but OCR confidence {conf:.2f} is below the "
            f"{config.ANPR_MIN_CONFIDENCE:.2f} threshold for a verified plate"
        )
    else:
        result["status"] = STATUS_VERIFIED
        result["validation"] = reading.reason

    # The verified plate is the only field gated on confidence. Everything above
    # it stays visible regardless.
    result["plate"] = reading.plate if result["status"] == STATUS_VERIFIED else None
    return result
