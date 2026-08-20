# -*- coding: utf-8 -*-
"""Run DEM Terrain Studio directly from a source checkout."""

import sys


if sys.version_info < (3, 10):
    sys.stderr.write(
        "DEM Terrain Studio requires Python 3.10 or newer. "
        "On Windows, run .\\run.cmd instead of using an ArcGIS Python 2 launcher.\n"
    )
    raise SystemExit(2)

from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from dem_terrain_studio.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
