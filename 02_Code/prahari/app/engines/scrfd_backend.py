"""SCRFD face detection with 5-point landmarks, via ONNX Runtime (lazy).

Phase 1 of the face/ReID upgrade. Returns face boxes, a detector score and
five landmarks (left eye, right eye, nose, left and right mouth corner) used
for alignment and the quality score. Detection only: nothing here identifies
anyone.

Model: det_2.5g.onnx (SCRFD-2.5G, the brief's CPU choice), fetched by
scripts/fetch_face_models.py. Any SCRFD-format ONNX with landmarks works, so
the weights can be swapped (InsightFace weights are non-commercial only).

Decoding follows the published SCRFD format: three strides (8, 16, 32), two
anchors per location, outputs ordered scores, then boxes, then landmarks, with
box and landmark values as distances in units of the stride.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app import config

log = logging.getLogger("prahari.scrfd")

DEFAULT_MODEL = "det_2.5g.onnx"
INPUT_SIZE = 640
SCORE_THRESH = 0.5
NMS_THRESH = 0.4
STRIDES = (8, 16, 32)
NUM_ANCHORS = 2

_session: Any = None
_loaded = False
_centers: dict[tuple[int, int, int], np.ndarray] = {}


def model_path() -> Path:
    raw = config.getenv("SCRFD_WEIGHTS", "").strip()
    return Path(raw) if raw else config.ROOT / "app" / "models_data" / DEFAULT_MODEL


def engine_available() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    return model_path().is_file()


def _get_session() -> Any:
    global _session, _loaded
    if _loaded:
        return _session
    _loaded = True
    try:
        import onnxruntime as ort

        _session = ort.InferenceSession(str(model_path()), providers=["CPUExecutionProvider"])
        log.info("SCRFD loaded from %s", model_path().name)
    except Exception as exc:
        log.warning("SCRFD unavailable: %s", exc)
        _session = None
    return _session


def _anchor_centers(height: int, width: int, stride: int) -> np.ndarray:
    key = (height, width, stride)
    if key not in _centers:
        ys, xs = np.mgrid[:height, :width]
        centers = (np.stack([xs, ys], axis=-1).astype(np.float32) * stride).reshape(-1, 2)
        _centers[key] = np.repeat(centers, NUM_ANCHORS, axis=0)
    return _centers[key]


def _nms(boxes: np.ndarray, scores: np.ndarray, thresh: float) -> list[int]:
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1 + 1) * np.maximum(0.0, yy2 - yy1 + 1)
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[1:][iou <= thresh]
    return keep


def decode(outputs: list[np.ndarray], input_hw: tuple[int, int], score_thresh: float = SCORE_THRESH):
    """Turn raw SCRFD outputs into (boxes xyxy, scores, landmarks 5x2), in input pixels."""
    fmc = len(STRIDES)
    in_h, in_w = input_hw
    boxes, scores, kpss = [], [], []
    for idx, stride in enumerate(STRIDES):
        score = outputs[idx].reshape(-1)
        dist = outputs[idx + fmc].reshape(-1, 4) * stride
        kps = outputs[idx + 2 * fmc].reshape(-1, 10) * stride
        centers = _anchor_centers(in_h // stride, in_w // stride, stride)
        pos = np.where(score >= score_thresh)[0]
        if pos.size == 0:
            continue
        c = centers[pos]
        d = dist[pos]
        boxes.append(np.stack([c[:, 0] - d[:, 0], c[:, 1] - d[:, 1], c[:, 0] + d[:, 2], c[:, 1] + d[:, 3]], axis=1))
        k = kps[pos].reshape(-1, 5, 2) + c[:, None, :]
        kpss.append(k)
        scores.append(score[pos])
    if not boxes:
        return np.zeros((0, 4), np.float32), np.zeros(0, np.float32), np.zeros((0, 5, 2), np.float32)
    return np.vstack(boxes), np.concatenate(scores), np.vstack(kpss)


def detect(frame_bgr: np.ndarray, score_thresh: float = SCORE_THRESH,
           input_size: int = INPUT_SIZE, pad: float = 0.0) -> list[dict[str, Any]]:
    """Detect faces. Each: bbox [x, y, w, h], score, landmarks [[x, y] x 5], in frame pixels.

    pad adds a black border of that share of the longer side before detecting.
    SCRFD misses a face that fills the whole image (measured: 0 faces on a
    close-up, 0.81 with pad=0.5), so close-ups such as enrolment photos need it.
    CCTV frames do not.
    """
    if pad > 0 and frame_bgr is not None and frame_bgr.size:
        border = int(max(frame_bgr.shape[:2]) * pad)
        padded = cv2.copyMakeBorder(frame_bgr, border, border, border, border, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        faces = detect(padded, score_thresh, input_size)
        h, w = frame_bgr.shape[:2]
        out = []
        for f in faces:
            x, y, fw, fh = f["bbox"]
            x0, y0 = max(0.0, x - border), max(0.0, y - border)
            x1, y1 = min(float(w), x - border + fw), min(float(h), y - border + fh)
            if x1 > x0 and y1 > y0:
                out.append({"bbox": [x0, y0, x1 - x0, y1 - y0], "score": f["score"],
                            "landmarks": [[px - border, py - border] for px, py in f["landmarks"]]})
        return out
    session = _get_session()
    if session is None or frame_bgr is None or frame_bgr.size == 0:
        return []
    h, w = frame_bgr.shape[:2]
    scale = min(input_size / w, input_size / h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    canvas = np.zeros((input_size, input_size, 3), np.uint8)
    canvas[:nh, :nw] = cv2.resize(frame_bgr, (nw, nh))
    blob = cv2.dnn.blobFromImage(canvas, 1.0 / 128, (input_size, input_size), (127.5, 127.5, 127.5), swapRB=True)
    try:
        outputs = session.run(None, {session.get_inputs()[0].name: blob})
    except Exception as exc:
        log.warning("SCRFD inference failed: %s", exc)
        return []
    boxes, scores, kpss = decode(outputs, (input_size, input_size), score_thresh)
    if not len(scores):
        return []
    boxes, kpss = boxes / scale, kpss / scale
    faces = []
    for i in _nms(boxes, scores, NMS_THRESH):
        x1, y1, x2, y2 = boxes[i]
        x1, y1 = max(0.0, x1), max(0.0, y1)
        x2, y2 = min(float(w), x2), min(float(h), y2)
        if x2 <= x1 or y2 <= y1:
            continue
        faces.append({
            "bbox": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
            "score": float(scores[i]),
            "landmarks": kpss[i].astype(float).tolist(),
        })
    return faces
