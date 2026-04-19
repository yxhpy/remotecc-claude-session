#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path = [path for path in sys.path if Path(path or ".").resolve() != SCRIPT_DIR]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from remotecc.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
