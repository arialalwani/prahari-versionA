"""Register the pedestrian test clip as a people-tracking camera (CAM-OWN-002).

Phase 1 test camera for the video wall. Not part of the seed data, so the demo
numbers (11 cameras) are unchanged; run this once per database. Safe to re-run.

    python scripts/add_people_test_camera.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import store  # noqa: E402
from app.db import init_db  # noqa: E402

CAMERA = {
    "camera_id": "CAM-OWN-002",
    "department": "Own",
    "ownership": "Own",
    "consent": 1,
    "lat": 0.0,
    "lon": 0.0,
    "protocol": "file",
    "url": "../../03_Data/recordings/pedestrians/vtest.avi",
    "retention_days": 0,
    "cam_type": "people",
    "health": "unknown",
    "location": "Pedestrian test clip (people tracking)",
    "codec": "xvid",
    "width": 768,
    "height": 576,
    "rtsp": "",
    "whep": "",
    "hls": "",
    "extra_json": "",
}


def main() -> int:
    init_db()
    clip = (ROOT / CAMERA["url"]).resolve()
    if not clip.is_file():
        print(f"Clip missing: {clip}\nDownload it: https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/vtest.avi")
        return 1
    store.upsert_camera(CAMERA)
    print(f"{CAMERA['camera_id']} registered: {CAMERA['location']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
