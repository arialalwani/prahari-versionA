"""Download the SCRFD face detector into app/models_data/.

SCRFD-2.5G with 5-point landmarks (det_2.5g.onnx), the brief's choice for CPU.
InsightFace publishes it only inside the buffalo_m model pack (about 276 MB),
so this downloads the pack once, extracts the 3 MB detector, and deletes the
rest. Use --small for SCRFD-500M from buffalo_sc (15 MB download) if bandwidth
matters more than small-face accuracy.

LICENCE: InsightFace pretrained weights are for non-commercial research only.
Fine for the hackathon; replace them before any commercial use. The model layer
(app/engines/scrfd_backend.py) takes any SCRFD-format ONNX file, so weights can
be swapped without code changes.

    python scripts/fetch_face_models.py
    python scripts/fetch_face_models.py --small
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST_DIR = ROOT / "app" / "models_data"
BASE = "https://github.com/deepinsight/insightface/releases/download/v0.7/"
PACKS = {
    "2.5g": ("buffalo_m.zip", "det_2.5g.onnx"),
    "500m": ("buffalo_sc.zip", "det_500m.onnx"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--small", action="store_true", help="SCRFD-500M instead of SCRFD-2.5G")
    args = parser.parse_args()
    pack, member = PACKS["500m" if args.small else "2.5g"]
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    dest = DEST_DIR / member
    if dest.is_file():
        print(f"Already present: {dest}")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / pack
        print(f"Downloading {BASE + pack} ...")
        urllib.request.urlretrieve(BASE + pack, zpath)
        with zipfile.ZipFile(zpath) as zf:
            names = [n for n in zf.namelist() if n.endswith("/" + member) or n == member]
            if not names:
                print(f"{member} not found in {pack}", file=sys.stderr)
                return 1
            dest.write_bytes(zf.read(names[0]))
    print(f"Saved {dest} ({dest.stat().st_size // 1024} KB). Licence: non-commercial research only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
