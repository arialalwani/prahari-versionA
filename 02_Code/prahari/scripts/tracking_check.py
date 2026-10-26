"""Phase 1 check: how stable are person track IDs on a real video?

Runs PersonTracker (YOLO + ByteTrack) over a video and reports stability
measures. The default clip has no ground-truth labels, so this reports proxies,
not accuracy (IDF1/MOTA need labelled tracks):

  * unique IDs vs. people in view: many more IDs than people means identities
    are breaking up (ID switches or fragments)
  * track lifetime: how many processed frames each ID lasts
  * fragments: IDs seen on fewer than FRAGMENT_FRAMES processed frames
  * gaps: IDs that disappear and later return under the same ID (good: the
    tracker held the identity through a miss)

It also writes annotated snapshots and a contact sheet for checking by eye.

    python scripts/tracking_check.py                       # default clip, stride 1
    python scripts/tracking_check.py --stride 2 --out ../../05_Output/experiments/tracking_stride2.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.services.person_tracking import PersonTracker  # noqa: E402

DEFAULT_VIDEO = ROOT.parents[1] / "03_Data" / "recordings" / "pedestrians" / "vtest.avi"
DEFAULT_SNAPS = ROOT.parents[1] / "05_Output" / "experiments" / "tracking_snapshots"
FRAGMENT_FRAMES = 5
_PALETTE = [(66, 135, 245), (245, 130, 48), (60, 180, 75), (230, 25, 75), (145, 30, 180),
            (70, 240, 240), (240, 50, 230), (210, 245, 60), (0, 128, 128), (170, 110, 40)]


def _colour(track_id: int) -> tuple[int, int, int]:
    return _PALETTE[track_id % len(_PALETTE)]


def annotate(frame: np.ndarray, tracks: list[dict], frame_index: int) -> np.ndarray:
    out = frame.copy()
    for t in tracks:
        x, y, w, h = [int(round(v)) for v in t["bbox"]]
        c = _colour(t["track_id"])
        cv2.rectangle(out, (x, y), (x + w, y + h), c, 2)
        label = f"ID {t['track_id']}"
        cv2.rectangle(out, (x, y - 18), (x + 8 + 9 * len(label), y), c, -1)
        cv2.putText(out, label, (x + 4, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(out, f"frame {frame_index}  people {len(tracks)}", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 2, cv2.LINE_AA)
    return out


def run(video: Path, stride: int, max_frames: int | None, snaps_dir: Path | None, snap_every: int) -> dict:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"Cannot open {video}")
    tracker = PersonTracker(f"check-{video.stem}", stride=stride)
    seen: dict[int, list[int]] = defaultdict(list)  # track_id -> processed-frame numbers
    per_frame_people: list[int] = []
    snaps: list[np.ndarray] = []
    detect_time = 0.0
    frame_index = processed = 0
    if snaps_dir:
        snaps_dir.mkdir(parents=True, exist_ok=True)
    while True:
        ok, frame = cap.read()
        if not ok or (max_frames and frame_index >= max_frames):
            break
        t0 = time.perf_counter()
        tracks = tracker.process(frame)
        if frame_index % stride == 0:
            detect_time += time.perf_counter() - t0
            for t in tracks:
                seen[t["track_id"]].append(processed)
            per_frame_people.append(len(tracks))
            processed += 1
        if snaps_dir and frame_index % snap_every == 0:
            img = annotate(frame, tracks, frame_index)
            cv2.imwrite(str(snaps_dir / f"frame_{frame_index:04d}.jpg"), img)
            snaps.append(img)
        frame_index += 1
    cap.release()
    tracker.close()

    lifetimes = {tid: len(f) for tid, f in seen.items()}
    gaps = {tid: sum(1 for a, b in zip(f, f[1:]) if b - a > 1) for tid, f in seen.items()}
    fragments = sorted(tid for tid, n in lifetimes.items() if n < FRAGMENT_FRAMES)
    if snaps_dir and snaps:
        _contact_sheet(snaps, snaps_dir / "contact_sheet.jpg")
    return {
        "video": video.name,
        "stride": stride,
        "frames_read": frame_index,
        "frames_processed": processed,
        "ms_per_processed_frame": round(1000 * detect_time / max(1, processed), 1),
        "effective_fps_cpu": round(processed / detect_time, 1) if detect_time else None,
        "people_in_view": {
            "mean": round(statistics.mean(per_frame_people), 2) if per_frame_people else 0,
            "max": max(per_frame_people) if per_frame_people else 0,
        },
        "unique_ids": len(lifetimes),
        "lifetime_frames": {
            "median": statistics.median(lifetimes.values()) if lifetimes else 0,
            "mean": round(statistics.mean(lifetimes.values()), 1) if lifetimes else 0,
            "max": max(lifetimes.values()) if lifetimes else 0,
        },
        "fragments": {"threshold_frames": FRAGMENT_FRAMES, "count": len(fragments), "ids": fragments},
        "ids_held_through_a_gap": sum(1 for g in gaps.values() if g),
        "tracks": {str(tid): {"first": f[0], "last": f[-1], "frames": len(f), "gaps": gaps[tid]}
                   for tid, f in sorted(seen.items())},
        "note": "No ground truth: proxies only. Use labelled footage for IDF1/MOTA.",
    }


def _contact_sheet(images: list[np.ndarray], path: Path, cols: int = 3, max_images: int = 9) -> None:
    picks = [images[round(i * (len(images) - 1) / (max_images - 1))] for i in range(max_images)] \
        if len(images) > max_images else images
    h, w = picks[0].shape[:2]
    scale = 420 / w
    tiles = [cv2.resize(im, (int(w * scale), int(h * scale))) for im in picks]
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    cv2.imwrite(str(path), np.vstack(rows))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("video", nargs="?", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--stride", type=int, default=1, help="run the detector on every Nth frame")
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--snapshots", type=Path, default=DEFAULT_SNAPS, help="folder for annotated frames")
    parser.add_argument("--snap-every", type=int, default=50)
    parser.add_argument("--no-snapshots", action="store_true")
    parser.add_argument("--out", type=Path, help="write the report as JSON")
    args = parser.parse_args()

    report = run(args.video, args.stride, args.max_frames, None if args.no_snapshots else args.snapshots,
                 args.snap_every)
    summary = {k: v for k, v in report.items() if k != "tracks"}
    print(json.dumps(summary, indent=2))
    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
