#!/usr/bin/env python3
"""Run the ComfySprites webapp test suite."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    cmd = [sys.executable, "-m", "pytest", "test", "-q"]
    print(f"\n>> {' '.join(cmd)}\n")
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
