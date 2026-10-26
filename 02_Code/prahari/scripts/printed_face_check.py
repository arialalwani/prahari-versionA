"""Documented test: what the person detector does on printed faces.

Printed faces (posters, billboards, photos on walls, faces on phone or laptop
screens) are not people, but a person detector can still fire on them. This
script records what happens. It is a documented test, not a pass/fail gate and
not a suppression rule: nothing is filtered out because of it.

It runs the real person detector (YOLO) and the intrusion check, against a
restricted zone covering the whole frame, over every image in
03_Data/samples/printed_faces/ (git-ignored), and writes a report.

    python scripts/printed_face_check.py --out ../../05_Output/experiments/printed_faces.json

Printed faces are kept out of the Phase 0 negative set, which is scenes with
no humans only (scripts/negative_person_check.py).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from negative_person_check import ROOT, folder_images, run  # noqa: E402

DEFAULT_DIR = ROOT.parents[1] / "03_Data" / "samples" / "printed_faces"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folders", nargs="*", type=Path, help="printed-face image folders")
    parser.add_argument("--out", type=Path, help="write the report as JSON")
    args = parser.parse_args()
    folders = args.folders or [DEFAULT_DIR]

    images = folder_images(folders)
    if not images:
        print(f"No images in {[str(f) for f in folders]}. Add posters or screen photos there.")
        return 0
    rows = run(images)
    width = max(len(r["image"]) for r in rows)
    print(f"Printed faces: {len(rows)} image(s). Detections are recorded, not suppressed.")
    for r in rows:
        print(f"  {r['image']:<{width}}  person detections={r['people']} {r['confidences'] or ''}  "
              f"intrusion if zone covered it={r['intrusion']}")
    fired = [r for r in rows if r["people"]]
    print(f"\nDetector fired on {len(fired)}/{len(rows)} printed-face image(s).")
    if args.out:
        args.out.write_text(json.dumps({
            "test": "printed_faces",
            "kind": "documented, not a gate",
            "rows": rows,
            "fired_on": len(fired),
            "images": len(rows),
        }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
