"""Generate geometric face fixtures. No real biometric data."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.synthetic_faces import write_fixture_pair  # noqa: E402


def main() -> int:
    dest = ROOT / "tests" / "fixtures" / "faces"
    write_fixture_pair(dest, "WL-004", seed=4)
    write_fixture_pair(dest, "WL-X", seed=99)
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
