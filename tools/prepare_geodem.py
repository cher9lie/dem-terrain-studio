"""Prepare a small, explicitly selected geospatial DEM for the lightweight renderer.

Requires numpy and rasterio. Bounds are in the input CRS; elevations must be metres.
Originals are read-only. Outputs go into a new directory, never over existing files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import ColorInterp, Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--bounds", type=float, nargs=4, required=True, metavar=("W", "S", "E", "N"))
    parser.add_argument("--target-crs", required=True, help="Projected metre CRS, e.g. EPSG:32649")
    parser.add_argument("--band", type=int, required=True)
    parser.add_argument("--elevation-unit", choices=["metre"], required=True)
    parser.add_argument("--long-edge", type=int, default=1024)
    parser.add_argument("--exaggeration", type=float, default=4)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--license", required=True)
    parser.add_argument("--trim-border", action="store_true",
                        help="Explicitly trim rectangular reprojection borders; omit to preserve irregular masks")
    args = parser.parse_args()
    if not 64 <= args.long_edge <= 2048:
        parser.error("--long-edge must be 64..2048")
    if not math.isfinite(args.exaggeration) or not 0 < args.exaggeration <= 100:
        parser.error("--exaggeration must be finite and in (0,100]")
    if not all(math.isfinite(x) for x in args.bounds):
        parser.error("bounds must be finite")
    w, s, e, n = args.bounds
    if w >= e or s >= n:
        parser.error("bounds must have W<E and S<N")
    target = rasterio.crs.CRS.from_user_input(args.target_crs)
    if not target.is_projected or target.linear_units_factor[1] != 1:
        parser.error("target CRS must be projected in metres")
    # mkdir without exist_ok prevents accidental overwrites of prior acceptance.
    with rasterio.open(args.source) as src:
        if not src.crs or not 1 <= args.band <= src.count:
            parser.error("source needs a CRS and a valid explicit band")
        if w < src.bounds.left or e > src.bounds.right or s < src.bounds.bottom or n > src.bounds.top:
            parser.error("requested bounds must lie inside source")
        window = from_bounds(w, s, e, n, src.transform).round_offsets().round_lengths()
        if window.width * window.height > 16_000_000:
            parser.error("crop exceeds 16 million pixels; choose a smaller region")
        data = src.read(args.band, window=window, masked=True).astype("float32")
        values = data.filled(np.nan)
        values[~np.isfinite(values)] = np.nan
        left, bottom, right, top = transform_bounds(src.crs, target, w, s, e, n, densify_pts=21)
        resolution = max(right - left, top - bottom) / args.long_edge
        width = math.ceil((right - left) / resolution)
        height = math.ceil((top - bottom) / resolution)
        affine = from_origin(left, top, resolution, resolution)
        dem = np.full((height, width), np.nan, dtype="float32")
        reproject(values, dem, src_transform=src.window_transform(window), src_crs=src.crs,
                  dst_transform=affine, dst_crs=target, src_nodata=np.nan, dst_nodata=np.nan,
                  resampling=Resampling.bilinear)
        # A reprojected lat/lon rectangle has curved edges. Keep the largest
        # centred valid rectangle so the rendered slab has no artificial mask.
        # Do not fill actual internal holes: they remain explicitly transparent.
        trim = 0
        while args.trim_border and min(dem.shape) > 64 and not (
            np.isfinite(dem[0]).all() and np.isfinite(dem[-1]).all()
            and np.isfinite(dem[:, 0]).all() and np.isfinite(dem[:, -1]).all()
        ):
            dem = dem[1:-1, 1:-1]
            trim += 1
        affine = affine * rasterio.Affine.translation(trim, trim)
        height, width = dem.shape
        valid = np.isfinite(dem)
        if not valid.any():
            parser.error("crop has no valid elevations")
        low, high = float(dem[valid].min()), float(dem[valid].max())
        if high <= low:
            parser.error("crop is flat; choose a region with relief for this acceptance")
        rgba = np.zeros((4, height, width), dtype="float32")
        normalized = np.zeros_like(dem)
        normalized[valid] = (dem[valid] - low) / (high - low)
        rgba[:3] = normalized
        rgba[3] = valid
        terrain_size = 10.0
        longest_m = max(width, height) * resolution
        true_strength = terrain_size * (high - low) / longest_m / 0.98
        metadata = {
            "source": str(args.source.resolve()), "source_sha256": sha256(args.source),
            "source_url": args.source_url, "license": args.license,
            "source_crs": str(src.crs), "source_band": args.band, "source_tags": src.tags(),
            "requested_bounds_source_crs": args.bounds, "source_nodata": src.nodata,
            "target_crs": str(target), "horizontal_unit": "metre", "elevation_unit_asserted": "metre",
            "vertical_datum": "not independently verified; relative relief only",
            "resolution_m": resolution, "width": width, "height": height,
            "extent_m": [width * resolution, height * resolution], "transform": list(affine),
            "elevation_range_m": [low, high], "invalid_pixels": int((~valid).sum()),
            "border_trim_pixels": trim, "height_strength_1x": true_strength,
            "artistic_exaggeration": args.exaggeration,
            "sun_convention": "clockwise from projected grid north (+Y); not corrected to true north",
        }
    args.destination.mkdir(parents=True)
    with rasterio.open(args.destination / "height_rgba.tif", "w", driver="GTiff", width=width,
                       height=height, count=4, dtype="float32", photometric="RGB") as dst:
        dst.write(rgba)
        dst.colorinterp = (ColorInterp.red, ColorInterp.green, ColorInterp.blue, ColorInterp.alpha)
    with rasterio.open(args.destination / "dem_projected.tif", "w", driver="GTiff", width=width,
                       height=height, count=1, dtype="float32", crs=target, transform=affine,
                       nodata=np.nan, compress="deflate") as dst:
        dst.write(dem, 1)
    for name, factor, transparent in (("white", args.exaggeration, False),
                                      ("transparent", args.exaggeration, True), ("scale_1x", 1, False)):
        config = {"height_map": "height_rgba.tif", "output": f"{name}.png",
                  "detect_background": False, "height_strength": true_strength * factor,
                  "subdivisions": 256, "resolution": [1200, 1200], "samples": 64,
                  "sun_azimuth": 315, "sun_elevation": 35,
                  "transparent_background": transparent}
        (args.destination / f"{name}.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (args.destination / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
