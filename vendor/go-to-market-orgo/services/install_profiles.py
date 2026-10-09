#!/usr/bin/env python3
"""Compatibility entrypoint for the AI Guy fleet release contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from install_assets import main as install_assets_main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--mode", default="all")
    args, _ = parser.parse_known_args()
    sys.argv = [sys.argv[0], "--root", str(args.root), "--home", str(args.home)]
    raise SystemExit(install_assets_main())
