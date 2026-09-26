"""Download a YOLO licence-plate detector into app/models_data/.

LICENCE NOTE: the default weights are AGPL-3.0 (morsetechlab, fine-tuned on a
Roboflow Universe plate dataset). That is fine for internal R&D and benchmarking
but conflicts with shipping PRAHARI under a proprietary licence as a hosted
service. Resolve the licence route before any deployment. The authors also warn
the upstream dataset has train/test contamination, so their published accuracy
figures should not be quoted — measure on our own test set instead.

    python scripts/fetch_plate_weights.py            # small (19 MB, default)
    python scripts/fetch_plate_weights.py --size n   # nano (5 MB, fastest)
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST_DIR = ROOT / "app" / "models_data"
BASE = (
    "https://huggingface.co/morsetechlab/yolov11-license-plate-detection"
    "/resolve/main/license-plate-finetune-v1{size}.pt"
)
SIZES = ("n", "s", "m", "l", "x")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", choices=SIZES, default="s")
    args = parser.parse_args()

    dest = DEST_DIR / f"license-plate-v1{args.size}.pt"
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        print("already present", dest)
        return 0

    url = BASE.format(size=args.size)
    print("downloading", url)
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception as exc:
        print(f"download failed: {exc}", file=sys.stderr)
        return 1
    print("wrote", dest, "bytes", dest.stat().st_size)
    print()
    print("Enable it with this line in .env:")
    print(f"  YOLO_PLATE_WEIGHTS=app/models_data/{dest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
