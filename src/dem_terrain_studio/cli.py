from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BLENDER_SCRIPT = PROJECT_ROOT / "blender" / "render_scene.py"


def find_blender(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())

    on_path = shutil.which("blender")
    if on_path:
        candidates.append(Path(on_path))

    program_files = Path("C:/Program Files/Blender Foundation")
    if program_files.exists():
        candidates.extend(sorted(program_files.glob("Blender */blender.exe"), reverse=True))

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

    required = ("height_map", "color_map", "output")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise ValueError(f"配置缺少字段: {', '.join(missing)}")

    base = path.parent.resolve()
    for key in ("height_map", "color_map", "output"):
        value = Path(config[key]).expanduser()
        config[key] = str((base / value).resolve() if not value.is_absolute() else value.resolve())

    for key in ("height_map", "color_map"):
        if not Path(config[key]).is_file():
            raise FileNotFoundError(f"找不到 {key}: {config[key]}")

    Path(config["output"]).parent.mkdir(parents=True, exist_ok=True)
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="使用 Blender 渲染 DEM 高度图。")
    parser.add_argument("--config", type=Path, required=True, help="JSON 配置文件")
    parser.add_argument("--blender", help="blender.exe 的完整路径")
    parser.add_argument("--dry-run", action="store_true", help="只检查并显示命令")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config_path = args.config.resolve()
        config = load_config(config_path)
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
        print(f"高度图: {config['height_map']}")
        print(f"色带图: {config['color_map']}")
        print(f"输出: {config['output']}")
        if args.dry_run:
            print("命令:", subprocess.list2cmdline(command))
            return 0
        completed = subprocess.run(command, check=False)
        return completed.returncode
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

