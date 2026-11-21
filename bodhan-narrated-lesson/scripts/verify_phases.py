#!/usr/bin/env python
"""Assemble cumulative snapshots (phase 1..N) in a temp dir and run the tests of each.
Proves every phase is self-consistent and runnable on its own."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_phases as bp  # noqa: E402


def main() -> int:
    counts, rc = {}, 0
    bp.build()
    for i, (name, *_rest) in enumerate(bp.PHASES, start=1):
        with tempfile.TemporaryDirectory() as tmp:
            for prev, *_ in bp.PHASES[:i]:
                shutil.copytree(bp.ROOT / "phases" / prev, tmp, dirs_exist_ok=True)
            tests = Path(tmp) / "tests"
            if not any(tests.rglob("test_*.py")):
                print(f"{name}: no tests"); continue
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=tmp,
                               env={**os.environ, "PYTHONPATH": str(Path(tmp) / "src")}, capture_output=True, text=True)
            m = re.search(r"(\d+) passed", r.stdout)
            counts[name] = int(m.group(1)) if m else 0
            ok = r.returncode == 0
            rc |= (not ok)
            print(f"{name}: {'PASS' if ok else 'FAIL'} ({counts[name]} tests, cumulative)")
            if not ok:
                print(r.stdout[-1500:])
    bp.build(counts)       # rewrite PHASE.md with counts
    return rc


if __name__ == "__main__":
    sys.exit(main())
