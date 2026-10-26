"""Phase 0 acceptance: images with no people must produce no people and no intrusion.

Runs the real person detector (YOLO, as configured in OBJECT_ENGINE) and the
intrusion check over:

  * built-in synthetic negatives (plain walls, a skin-toned wall, noise, a
    drawn face-like shape), always included, and
  * every image in the negative folder(s) you pass, by default
    03_Data/samples/negatives_people/ (git-ignored; put empty rooms, walls,
    vehicles without people and close-up faces there).

Intrusion is checked against the worst case, a restricted zone covering the
whole frame, so any person detection would count. Exit code 1 if any image
yields a person or an intrusion.

    python scripts/negative_person_check.py
    python scripts/negative_person_check.py path/to/folder --out report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("OBJECT_ENGINE", "yolo")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.services.intrusion import check  # noqa: E402
from app.services.objects import detect  # noqa: E402
from tests.negative_images import synthetic_negatives  # noqa: E402

DEFAULT_DIR = ROOT.parents[1] / "03_Data" / "samples" / "negatives_people"
WHOLE_FRAME_ZONE = {"camera_id": "NEG-CHECK", "extra_json": json.dumps({"roi": [0, 0, 1, 1]})}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def folder_images(folders: list[Path]) -> list[tuple[str, np.ndarray]]:
    out = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if path.suffix.lower() in IMAGE_SUFFIXES:
                img = cv2.imread(str(path))
                if img is not None:
                    out.append((str(path.relative_to(folder.parent)), img))
    return out


def run(images: list[tuple[str, np.ndarray]]) -> list[dict]:
    rows = []
    for name, img in images:
        people = detect(img, camera_id="NEG-CHECK")
        intrusion = check(img, WHOLE_FRAME_ZONE, people)
        rows.append({
            "image": name,
            "people": len(people),
            "confidences": [round(float(p.get("confidence") or 0), 2) for p in people],
            "intrusion": intrusion is not None,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folders", nargs="*", type=Path, help="negative image folders")
    parser.add_argument("--out", type=Path, help="write the report as JSON")
    args = parser.parse_args()
    folders = args.folders or [DEFAULT_DIR]

    images = synthetic_negatives() + folder_images(folders)
    rows = run(images)
    width = max(len(r["image"]) for r in rows)
    print(f"OBJECT_ENGINE={os.environ.get('OBJECT_ENGINE')}  images={len(rows)}  folders={[str(f) for f in folders]}")
    for r in rows:
        flag = "FAIL" if r["people"] or r["intrusion"] else "ok"
        print(f"  {r['image']:<{width}}  people={r['people']} {r['confidences'] or ''}  intrusion={r['intrusion']}  {flag}")
    failed = [r for r in rows if r["people"] or r["intrusion"]]
    print(f"\n{len(rows) - len(failed)}/{len(rows)} clean. Invented people: {sum(r['people'] for r in rows)}. "
          f"False intrusions: {sum(r['intrusion'] for r in rows)}.")
    if args.out:
        args.out.write_text(json.dumps({"rows": rows, "passed": not failed}, indent=2), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
