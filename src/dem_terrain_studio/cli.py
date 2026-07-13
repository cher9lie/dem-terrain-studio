from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BLENDER_SCRIPT = PROJECT_ROOT / "blender" / "render_scene.py"


def find_blender(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())

    if os.environ.get("BLENDER_PATH"):
        candidates.append(Path(os.environ["BLENDER_PATH"]).expanduser())

    on_path = shutil.which("blender")
    if on_path:
        candidates.append(Path(on_path))

    install_roots = (
        Path("C:/Program Files/Blender Foundation"),
        Path("D:/Blender Foundation"),
    )
    for install_root in install_roots:
        if install_root.exists():
            candidates.extend(sorted(install_root.glob("Blender */blender.exe"), reverse=True))

    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved

    raise FileNotFoundError(
        "没有找到 Blender。请安装 Blender 4.x，或使用 --blender 指定 blender.exe。"
    )


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    required = ("height_map", "output")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise ValueError(f"配置缺少字段: {', '.join(missing)}")

    base = path.parent.resolve()
    for key in ("height_map", "color_map", "output"):
        if not config.get(key):
            continue
        value = Path(config[key]).expanduser()
        config[key] = str((base / value).resolve() if not value.is_absolute() else value.resolve())

    for key in ("height_map", "color_map"):
        if not config.get(key):
            continue
        if not Path(config[key]).is_file():
            raise FileNotFoundError(f"找不到 {key}: {config[key]}")

    Path(config["output"]).parent.mkdir(parents=True, exist_ok=True)
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="输入裁切后的 DEM，使用 Blender 直接渲染地形。")
    parser.add_argument("dem", nargs="?", type=Path, help="裁切好的 DEM（推荐 TIFF/PNG）")
    parser.add_argument("--config", type=Path, help="高级用法：JSON 配置文件")
    parser.add_argument("--sun-azimuth", type=float, default=315.0, help="太阳方位角，默认 315°")
    parser.add_argument("--sun-elevation", type=float, default=35.0, help="太阳高度角，默认 35°")
    parser.add_argument("--output", type=Path, help="输出 PNG；默认与 DEM 同目录")
    parser.add_argument("--blender", help="blender.exe 的完整路径")
    parser.add_argument("--dry-run", action="store_true", help="只检查并显示命令")
    return parser


def simple_config(args: argparse.Namespace) -> tuple[dict, Path]:
    if args.dem is None:
        raise ValueError("请提供 DEM 路径，或使用 --config 指定配置文件。")
    dem = args.dem.expanduser().resolve()
    if not dem.is_file():
        raise FileNotFoundError(f"找不到 DEM: {dem}")
    output = args.output.expanduser().resolve() if args.output else dem.with_name(f"{dem.stem}_render.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "height_map": str(dem),
        "output": str(output),
        "engine": "BLENDER_EEVEE",
        "subdivisions": 256,
        "terrain_size": 10.0,
        "height_strength": 1.6,
        "sun_azimuth": args.sun_azimuth,
        "sun_elevation": args.sun_elevation,
        "sun_energy": 3.0,
        "camera": "ORTHO",
        "camera_azimuth": 225.0,
        "camera_elevation": 42.0,
        "resolution": [1600, 1600],
        "samples": 64,
        "transparent_background": False,
        "save_blend": True,
    }
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="dem-terrain-", encoding="utf-8", delete=False
    )
    with handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
    return config, Path(handle.name)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    temporary_config: Path | None = None
    try:
        if args.config:
            config_path = args.config.resolve()
            config = load_config(config_path)
        else:
            config, config_path = simple_config(args)
            temporary_config = config_path
        blender = find_blender(args.blender)
        command = [
            str(blender),
            "--background",
            "--python",
            str(BLENDER_SCRIPT),
            "--",
            "--config",
            str(config_path),
        ]
        print(f"Blender: {blender}")
        print(f"DEM: {config['height_map']}")
        print(f"太阳: 方位角 {config.get('sun_azimuth', 315)}°, 高度角 {config.get('sun_elevation', 35)}°")
        print(f"输出: {config['output']}")
        if args.dry_run:
            print("命令:", subprocess.list2cmdline(command))
            return 0
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            return completed.returncode
        if not Path(config["output"]).is_file():
            print("错误: Blender 已结束，但没有生成输出图片。请检查上方 Blender 日志。", file=sys.stderr)
            return 3
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    finally:
        if temporary_config:
            temporary_config.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
