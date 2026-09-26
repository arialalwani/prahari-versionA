"""Score the ANPR pipeline against a labelled test set. Run before and after every phase.

Test set layout (tiers are free-form folder names; "negative" is special):

    03_Data/samples/anpr_testset/
        ground_truth.csv        filename,plate,tier
        easy/*.jpg
        hard/*.jpg
        negative/*.jpg          plate column left empty

A row whose plate is empty is a negative case: returning any plate for it is a
false positive, which is worse than returning nothing.

    python scripts/anpr_benchmark.py
    python scripts/anpr_benchmark.py --save baseline.json
    python scripts/anpr_benchmark.py --compare baseline.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

TESTSET = REPO / "03_Data" / "samples" / "anpr_testset"
GROUND_TRUTH = TESTSET / "ground_truth.csv"


def edit_distance(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


@dataclass
class Row:
    filename: str
    expected: str
    tier: str
    detected: str = ""
    confidence: float = 0.0
    error: str = ""

    #: Ground truth we do not have. Scored neither right nor wrong — marking a
    #: reading wrong against an answer nobody knows would corrupt the metrics.
    UNKNOWN = {"UNKNOWN", "?", "IDK", "N/A"}

    @property
    def is_unknown(self) -> bool:
        return self.expected.upper() in self.UNKNOWN

    @property
    def is_negative(self) -> bool:
        return not self.expected and not self.is_unknown

    @property
    def located(self) -> bool:
        return bool(self.detected)

    @property
    def exact(self) -> bool:
        return bool(self.expected) and not self.is_unknown and self.detected == self.expected

    @property
    def cer(self) -> float:
        """Character error rate against the expected plate."""
        if not self.expected or self.is_unknown:
            return 0.0
        return edit_distance(self.detected, self.expected) / len(self.expected)

    def verdict(self) -> str:
        if self.error:
            return "ERROR"
        if self.is_unknown:
            return "UNSCORED"
        if self.is_negative:
            return "FAIL" if self.located else "PASS"
        return "PASS" if self.exact else "FAIL"


@dataclass
class Tier:
    name: str
    rows: list[Row] = field(default_factory=list)

    def metrics(self) -> dict:
        scored = [r for r in self.rows if not r.is_unknown]
        positives = [r for r in scored if not r.is_negative]
        negatives = [r for r in scored if r.is_negative]
        located = [r for r in positives if r.located]
        # Precision is the number an operator feels: of the plates the system
        # hands over, how many are right? A miss costs an opportunity; a wrong
        # plate costs someone being stopped for nothing.
        return {
            "images": len(self.rows),
            "unscored": sum(1 for r in self.rows if r.is_unknown),
            "returned": len(located),
            "wrong": sum(1 for r in located if not r.exact),
            "precision": (sum(r.exact for r in located) / len(located)) if located else None,
            "detection_rate": len(located) / len(positives) if positives else None,
            "exact_match": sum(r.exact for r in positives) / len(positives) if positives else None,
            "cer": sum(r.cer for r in positives) / len(positives) if positives else None,
            "false_positives": sum(r.located for r in negatives),
            "negatives": len(negatives),
        }


def load_rows() -> list[Row]:
    if not GROUND_TRUTH.is_file():
        raise SystemExit(
            f"no ground truth at {GROUND_TRUTH}\n"
            "Create it as: filename,plate,tier\n"
            "  easy/car1.jpg,GJ01AB1234,easy\n"
            "  negative/wall.jpg,,negative"
        )
    rows: list[Row] = []
    with GROUND_TRUTH.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            name = (raw.get("filename") or "").strip()
            if not name:
                continue
            rows.append(
                Row(
                    filename=name,
                    expected=(raw.get("plate") or "").strip().upper(),
                    tier=(raw.get("tier") or "untiered").strip() or "untiered",
                )
            )
    return rows


def run(rows: list[Row]) -> None:
    import cv2

    from app.services.anpr import recognize

    for row in rows:
        path = TESTSET / row.filename
        if not path.is_file():
            row.error = "missing file"
            continue
        frame = cv2.imread(str(path))
        if frame is None:
            row.error = "unreadable image"
            continue
        try:
            result = recognize(frame)
        except Exception as exc:  # a crash is a result worth recording, not a stop
            row.error = f"{type(exc).__name__}: {exc}"[:120]
            continue
        row.detected = (result.get("plate") or "").upper()
        row.confidence = float(result.get("confidence") or 0.0)


def pct(value: float | None) -> str:
    return "  n/a" if value is None else f"{value * 100:5.1f}%"


def report(rows: list[Row], engines: dict[str, str]) -> dict:
    tiers: dict[str, Tier] = {}
    for row in rows:
        tiers.setdefault(row.tier, Tier(row.tier)).rows.append(row)

    print()
    print("ANPR BENCHMARK")
    print("  engines: " + ", ".join(f"{k}={v}" for k, v in engines.items()))
    print()
    print(f"{'file':<30} {'expected':<12} {'detected':<12} {'conf':>6}  verdict")
    print("-" * 76)
    for row in rows:
        detected = row.detected or ("-" if not row.error else row.error[:12])
        print(
            f"{row.filename[:29]:<30} {row.expected or '(none)':<12} {detected:<12} "
            f"{row.confidence:6.2f}  {row.verdict()}"
        )

    print()
    print(f"{'tier':<14} {'n':>4} {'detected':>9} {'exact':>9} {'precision':>10} "
          f"{'wrong':>6} {'CER':>8}")
    print("-" * 76)
    overall = Tier("ALL", rows)
    for name in sorted(tiers):
        m = tiers[name].metrics()
        print(
            f"{name:<14} {m['images']:>4} {pct(m['detection_rate']):>9} {pct(m['exact_match']):>9} "
            f"{pct(m['precision']):>10} {m['wrong']:>6} {pct(m['cer']):>8}"
        )
    m = overall.metrics()
    print("-" * 76)
    print(
        f"{'OVERALL':<14} {m['images']:>4} {pct(m['detection_rate']):>9} {pct(m['exact_match']):>9} "
        f"{pct(m['precision']):>10} {m['wrong']:>6} {pct(m['cer']):>8}"
    )
    print()
    if m["false_positives"]:
        print(f"  WARNING {m['false_positives']} false positive(s). A wrong plate is worse than no plate.")
        print()

    return {
        "engines": engines,
        "overall": m,
        "tiers": {name: tiers[name].metrics() for name in sorted(tiers)},
        "rows": [
            {
                "filename": r.filename,
                "tier": r.tier,
                "expected": r.expected,
                "detected": r.detected,
                "confidence": round(r.confidence, 4),
                "verdict": r.verdict(),
            }
            for r in rows
        ],
    }


def compare(current: dict, baseline_path: Path) -> None:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    print("COMPARED TO " + baseline_path.name)
    print(f"  baseline engines: " + ", ".join(f"{k}={v}" for k, v in baseline.get("engines", {}).items()))
    print()
    print(f"{'metric':<18} {'before':>9} {'after':>9} {'change':>10}")
    print("-" * 50)
    for key, label in (
        ("detection_rate", "detection rate"),
        ("exact_match", "exact match"),
        ("precision", "precision"),
        ("cer", "char error rate"),
    ):
        before, after = baseline["overall"].get(key), current["overall"].get(key)
        if before is None or after is None:
            continue
        delta = (after - before) * 100
        arrow = "+" if delta > 0 else ""
        print(f"{label:<18} {pct(before):>9} {pct(after):>9} {arrow}{delta:>8.1f}pp")
    for key, label in (("wrong", "wrong plates"), ("false_positives", "false positives")):
        before, after = baseline["overall"].get(key, 0), current["overall"].get(key, 0)
        print(f"{label:<18} {before:>9} {after:>9} {'+' if after > before else ''}{after - before:>8}")
    print()

    was = {r["filename"]: r["verdict"] for r in baseline.get("rows", [])}
    regressions = [r["filename"] for r in current["rows"]
                   if was.get(r["filename"]) == "PASS" and r["verdict"] != "PASS"]
    fixes = [r["filename"] for r in current["rows"]
             if was.get(r["filename"]) not in (None, "PASS") and r["verdict"] == "PASS"]
    if fixes:
        print(f"  FIXED ({len(fixes)}): " + ", ".join(fixes[:6]) + (" ..." if len(fixes) > 6 else ""))
    if regressions:
        print(f"  REGRESSED ({len(regressions)}): " + ", ".join(regressions[:6]))
        print("  Something that used to work no longer does. Investigate before moving on.")
    if not fixes and not regressions:
        print("  No per-image verdict changes.")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", metavar="NAME", help="write results to 05_Output/experiments/anpr/NAME")
    parser.add_argument("--compare", metavar="NAME", help="compare against a saved run")
    args = parser.parse_args()

    from app import config

    engines = {
        "ANPR_ENGINE": config.getenv("ANPR_ENGINE", "tesseract"),
        "OCR_ENGINE": config.getenv("OCR_ENGINE", "tesseract"),
        "OBJECT_ENGINE": config.getenv("OBJECT_ENGINE", "opencv"),
    }

    rows = load_rows()
    if not rows:
        raise SystemExit("ground truth has no rows")
    run(rows)
    results = report(rows, engines)

    out_dir = REPO / "05_Output" / "experiments" / "anpr"
    if args.compare:
        path = Path(args.compare)
        if not path.is_file():
            path = out_dir / args.compare
        if not path.is_file():
            raise SystemExit(f"no saved run at {path}")
        compare(results, path)
    if args.save:
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / args.save
        dest.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"  saved {dest}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
