"""Generate small deterministic images for manual Blender integration tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".integration"


def write_config(name: str, height_map: Path, **overrides) -> Path:
    config = {
        "height_map": str(height_map),
        "output": str(OUTPUT / f"{name}.png"),
        "subdivisions": 64,
        "max_texture_size": 512,
        "resolution": [512, 512],
        "height_strength": 1.6,
        "sun_azimuth": 315.0,
        "sun_elevation": 35.0,
        "save_blend": False,
    }
    config.update(overrides)
    path = OUTPUT / f"{name}.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    OUTPUT.mkdir(exist_ok=True)

    width, height = 320, 180
    y, x = np.mgrid[-1:1:complex(height), -1:1:complex(width)]
    terrain = np.clip(1.0 - np.sqrt((x * 0.8) ** 2 + (y * 1.2) ** 2), 0.0, 1.0)
    terrain += 0.18 * np.sin(x * 13) * np.cos(y * 9)
    terrain = np.clip(terrain, 0.0, 1.0)
    bordered = np.full((height, width), 65535, dtype=np.uint16)
    bordered[14:-14, 18:-18] = (terrain[14:-14, 18:-18] * 60000).astype(np.uint16)
    bordered_path = OUTPUT / "rectangular_white_border_16bit.png"
    Image.fromarray(bordered).save(bordered_path)
    write_config("rectangular_white_border", bordered_path)

    external_color = np.zeros((height, width, 3), dtype=np.uint8)
    external_color[..., 0] = (terrain * 180).astype(np.uint8)
    external_color[..., 1] = (80 + terrain * 150).clip(0, 255).astype(np.uint8)
    external_color[..., 2] = (210 - terrain * 140).clip(0, 255).astype(np.uint8)
    external_color_path = OUTPUT / "matching_color.png"
    Image.fromarray(external_color).save(external_color_path)
    write_config(
        "cycles_perspective_color",
        bordered_path,
        color_map=str(external_color_path),
        engine="CYCLES",
        samples=1,
        subdivisions=32,
        resolution=[256, 256],
        camera="PERSP",
        save_blend=True,
    )

    size = 192
    yy, xx = np.mgrid[-1:1:complex(size), -1:1:complex(size)]
    radius = np.sqrt(xx**2 + yy**2)
    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    valid = radius <= 0.78
    value = np.clip((1.0 - radius) * 255, 0, 255).astype(np.uint8)
    rgba[..., :3] = value[..., None]
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    transparent_path = OUTPUT / "transparent_island_source.png"
    Image.fromarray(rgba).save(transparent_path)
    write_config(
        "transparent_island",
        transparent_path,
        sun_azimuth=135.0,
        transparent_background=True,
    )

    flat = np.full((128, 256), 128, dtype=np.uint8)
    flat_path = OUTPUT / "flat_source.png"
    Image.fromarray(flat).save(flat_path)
    write_config("flat", flat_path)

    mismatch = np.zeros((32, 32, 3), dtype=np.uint8)
    mismatch[..., 1] = 255
    mismatch_path = OUTPUT / "mismatched_color.png"
    Image.fromarray(mismatch).save(mismatch_path)
    write_config("mismatch", flat_path, color_map=str(mismatch_path))

    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
