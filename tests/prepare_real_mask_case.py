"""Derive a reproducible irregular research mask from an already accepted real DEM.

This is an elevation-threshold research area, NOT an administrative boundary.
Usage: python tests/prepare_real_mask_case.py outputs/acceptance-20261107 outputs/masked-20261107
"""
import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import ColorInterp
from rasterio.features import shapes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accepted", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--threshold", type=float, default=650)
    parser.add_argument("--subdivisions", type=int, default=256)
    args = parser.parse_args()
    if not 2 <= args.subdivisions <= 1024:
        parser.error("subdivisions must be 2..1024")
    meta = json.loads((args.accepted / "metadata.json").read_text(encoding="utf-8"))
    with rasterio.open(args.accepted / "dem_projected.tif") as src:
        dem = src.read(1, masked=True).filled(np.nan)
        profile = src.profile
        valid = np.isfinite(dem) & (dem >= args.threshold)
        if not valid.any():
            parser.error("threshold leaves no terrain")
        low, high = float(dem[valid].min()), float(dem[valid].max())
        if high <= low:
            parser.error("threshold leaves no relief")
        components = 0
        vector_inner_rings = 0
        for geometry, value in shapes(valid.astype("uint8"), mask=valid):
            components += 1
            vector_inner_rings += len(geometry["coordinates"]) - 1
        # Match the mesh's 4-connected terrain / 8-connected background
        # convention. A ring touching the exterior at one corner is not a
        # topological through-hole after manifold corner splitting.
        holes = 0
        for geometry, value in shapes((~valid).astype("uint8"), mask=~valid, connectivity=8):
            touches_border = any(x in (0, src.width) or y in (0, src.height)
                                 for ring in geometry["coordinates"] for x,y in ring)
            if not touches_border:
                holes += 1
        rgba = np.zeros((4, src.height, src.width), dtype="float32")
        normalized = np.zeros_like(dem)
        normalized[valid] = (dem[valid] - low) / (high - low)
        rgba[:3] = normalized
        rgba[3] = valid
        args.destination.mkdir(parents=True)
        with rasterio.open(args.destination / "height_rgba.tif", "w", driver="GTiff",
                           width=src.width, height=src.height, count=4, dtype="float32",
                           crs=src.crs, transform=src.transform, photometric="RGB") as dst:
            dst.write(rgba)
            dst.colorinterp = (ColorInterp.red, ColorInterp.green, ColorInterp.blue, ColorInterp.alpha)
        dem[~valid] = np.nan
        with rasterio.open(args.destination / "dem_projected.tif", "w", **profile) as dst:
            dst.write(dem, 1)
    meta.update({"mask_kind": "real elevation threshold; not an administrative boundary",
                 "threshold_m": args.threshold, "elevation_range_m": [low, high],
                 "source_mask_components": components, "source_mask_holes": holes,
                 "vector_inner_rings": vector_inner_rings,
                 "invalid_pixels": int((~valid).sum()),
                 "height_strength_1x": 10 * (high-low) / max(meta["extent_m"]) / 0.98})
    for mode in ("white", "transparent"):
        config = json.loads((args.accepted / f"{mode}.json").read_text(encoding="utf-8"))
        config["height_strength"] = meta["height_strength_1x"] * 4
        config["subdivisions"] = args.subdivisions
        (args.destination / f"{mode}.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (args.destination / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k:meta[k] for k in ("source_mask_components", "source_mask_holes", "invalid_pixels", "elevation_range_m")}, indent=2))


if __name__ == "__main__":
    main()
