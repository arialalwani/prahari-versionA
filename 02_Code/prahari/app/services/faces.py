"""Lawful enrolled-gallery FRS. Never called on Gov / camNN cameras (see analyse.engines_for)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2
import numpy as np

from app import config

log = logging.getLogger("prahari.faces")

_tracks: dict[str, list[str]] = {}
_gallery_cache: dict[str, list[np.ndarray]] = {}
_facenet_gallery: dict[str, list[np.ndarray]] = {}


def reset(camera_id: str | None = None) -> None:
    if camera_id:
        _tracks.pop(camera_id, None)
        return
    _tracks.clear()


def _embed(bgr: np.ndarray) -> np.ndarray:
    small = cv2.resize(bgr, (64, 64))
    hist = cv2.calcHist([small], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    return hist.astype(np.float32)


def _score(a: np.ndarray, b: np.ndarray) -> float:
    ha = a.reshape(8, 8, 8).astype(np.float32)
    hb = b.reshape(8, 8, 8).astype(np.float32)
    return float(cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL))


def _detect_boxes(frame_bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    cascade_path = getattr(cv2.data, "haarcascades", "") + "haarcascade_frontalface_default.xml"
    boxes: list[tuple[int, int, int, int]] = []
    if Path(cascade_path).is_file():
        cascade = cv2.CascadeClassifier(cascade_path)
        found = cascade.detectMultiScale(gray, 1.1, 4)
        boxes = [(int(x), int(y), int(w), int(h)) for x, y, w, h in found]
    h, w = frame_bgr.shape[:2]
    if not boxes and h <= 256 and w <= 256:
        boxes = [(0, 0, w, h)]
    return boxes


def load_gallery(force: bool = False) -> dict[str, list[np.ndarray]]:
    global _gallery_cache
    if _gallery_cache and not force:
        return _gallery_cache
    cache: dict[str, list[np.ndarray]] = {}
    root = config.face_dir()
    if root.is_dir():
        for folder in root.iterdir():
            if not folder.is_dir():
                continue
            embs = []
            for img_path in sorted(folder.glob("*")):
                if img_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                    continue
                bgr = cv2.imread(str(img_path))
                if bgr is None:
                    continue
                embs.append(_embed(bgr))
            if embs:
                cache[folder.name] = embs
    _gallery_cache = cache
    return cache


def _engine() -> str:
    raw = config.getenv("FACE_ENGINE", "histogram").strip().lower()
    if raw in {"lbph", "hist", ""}:
        return "histogram"
    return raw


def _load_facenet_gallery(force: bool = False) -> dict[str, list[np.ndarray]]:
    global _facenet_gallery
    if _facenet_gallery and not force:
        return _facenet_gallery
    cache: dict[str, list[np.ndarray]] = {}
    root = config.face_dir()
    if root.is_dir():
        for folder in root.iterdir():
            if not folder.is_dir():
                continue
            embs: list[np.ndarray] = []
            for npy_path in sorted(folder.glob("*.npy")):
                try:
                    embs.append(np.load(npy_path).astype(np.float32).flatten())
                except Exception:
                    continue
            if embs:
                cache[folder.name] = embs
    _facenet_gallery = cache
    return cache


def _try_write_embedding(path: Path, crop_bgr: np.ndarray) -> None:
    try:
        from app.engines.facenet_backend import get_analyzer

        analyzer = get_analyzer()
        faces = analyzer.extract_faces(crop_bgr)
        if not faces:
            return
        np.save(str(path.with_suffix(".npy")), np.asarray(faces[0]["embedding"], dtype=np.float32))
    except Exception as exc:
        log.warning("facenet enroll embedding skipped: %s", exc)


def enroll(
    gallery_id: str,
    images_bgr: list[np.ndarray],
    allow_facenet: bool | None = None,
) -> dict[str, Any]:
    dest = config.face_dir() / gallery_id
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    if allow_facenet is None:
        want_facenet = _engine() == "facenet"
    else:
        want_facenet = bool(allow_facenet) and _engine() == "facenet"
    for img in images_bgr:
        if img is None:
            continue
        boxes = _detect_boxes(img)
        crop = img
        if boxes:
            x, y, w, h = boxes[0]
            crop = img[y : y + h, x : x + w]
        path = dest / f"{len(list(dest.glob('*'))) + 1}.jpg"
        cv2.imwrite(str(path), crop)
        if want_facenet:
            _try_write_embedding(path, crop)
        n += 1
    load_gallery(force=True)
    _load_facenet_gallery(force=True)
    return {"gallery_id": gallery_id, "n_images": n}


def _histogram_match(
    frame_bgr: np.ndarray, gallery: dict[str, list[np.ndarray]] | None = None
) -> list[dict[str, Any]]:
    gal = gallery if gallery is not None else load_gallery()
    if not gal:
        return []
    out: list[dict[str, Any]] = []
    threshold = float(config.getenv("FACE_MATCH_MIN_CONFIDENCE", str(config.FACE_MATCH_MIN_CONFIDENCE)))
    for x, y, w, h in _detect_boxes(frame_bgr):
        crop = frame_bgr[y : y + h, x : x + w]
        emb = _embed(crop)
        best_id, best = "", -1.0
        for gid, embs in gal.items():
            for other in embs:
                s = _score(emb, other)
                if s > best:
                    best, best_id = s, gid
        hit = {
            "face_id": best_id if best >= threshold else "",
            "confidence": max(0.0, float(best)),
            "bbox": [int(x), int(y), int(w), int(h)],
            "crop_bgr": crop,
        }
        out.append(hit)
    return out


def _facenet_match(frame_bgr: np.ndarray) -> list[dict[str, Any]]:
    from app.engines.facenet_backend import cosine, get_analyzer

    analyzer = get_analyzer()
    gal = _load_facenet_gallery()
    if not gal:
        return []
    threshold = float(config.getenv("FACE_MATCH_MIN_CONFIDENCE", "0.5") or "0.5")
    out: list[dict[str, Any]] = []
    for face in analyzer.extract_faces(frame_bgr):
        emb = np.asarray(face["embedding"], dtype=np.float32).flatten()
        best_id, best = "", -1.0
        for gid, embs in gal.items():
            for other in embs:
                s = cosine(emb, other)
                if s > best:
                    best, best_id = s, gid
        out.append(
            {
                "face_id": best_id if best >= threshold else "",
                "confidence": max(0.0, float(best)),
                "bbox": face.get("bbox") or [0, 0, 0, 0],
                "crop_bgr": face.get("crop"),
            }
        )
    return out


def match(frame_bgr: np.ndarray, gallery: dict[str, list[np.ndarray]] | None = None) -> list[dict[str, Any]]:
    """Identify enrolled people in a frame. Only a real face recogniser may answer.

    The colour-histogram comparison is not face recognition: it measures colour
    mix, so a score above the threshold does not mean two faces are the same
    person. It is disabled for identification and alerts (Phase 0) and stays in
    this module only until the Phase 2 recogniser replaces it. A failed FaceNet
    no longer falls back to it either: no recogniser means no identification.
    """
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return []
    if _engine() == "facenet":
        try:
            return _facenet_match(frame_bgr)
        except Exception as exc:
            log.warning("FACE_ENGINE=facenet unavailable (%s); face identification off", exc)
            return []
    log.info("face identification off: FACE_ENGINE=%s is not a face recogniser", _engine())
    return []
