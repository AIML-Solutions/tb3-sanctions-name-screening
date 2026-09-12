#!/usr/bin/env python3
"""Thin wrapper: the generator ships with the task under tests/generate_data.py."""
import runpy
import sys
from pathlib import Path

sys.exit(runpy.run_path(str(Path(__file__).resolve().parents[1] / "tasks" / "sanctions-name-screening" / "tests" / "generate_data.py"), run_name="__main__") and 0)
