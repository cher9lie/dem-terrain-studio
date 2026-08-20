from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


BLENDER_SCRIPT = Path(__file__).with_name("blender") / "render_scene.py"
SUPPORTED_INPUTS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".exr"}
ENGINES = {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "CYCLES"}
CAMERAS = {"ORTHO", "PERSP"}

DEFAULTS: dict[str, Any] = {
    "engine": "BLENDER_EEVEE",
    "subdivisions": 256,
    "max_texture_size": 2048,
    "terrain_size": 10.0,
    "height_strength": 1.6,
    "sun_azimuth": 315.0,
    "sun_elevation": 35.0,
    "sun_energy": 3.0,
    "camera": "ORTHO",
    "camera_azimuth": 225.0,
    "camera_elevation": 42.0,
    "resolution": [1600, 1600],
    "samples": 64,
    "transparent_background": False,
    "save_blend": True,
    "detect_background": True,
}
ALLOWED_CONFIG_KEYS = set(DEFAULTS) | {"height_map", "color_map", "output"}


class ConfigError(ValueError):
    """Raised when user configuration cannot produce a safe render."""


def _version_key(path: Path) -> tuple[int, ...]:
    numbers: list[int] = []
    for part in path.parent.name.replace("Blender", "").strip().split("."):
        if part.isdigit():
            numbers.append(int(part))
        else:
            break
    return tuple(numbers)


def find_blender(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidate = Path(explicit).expanduser()
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise FileNotFoundError(f"指定的 Blender 不存在: {candidate}") from exc
        if not resolved.is_file() or resolved.name.lower() not in {"blender", "blender.exe"}:
            raise FileNotFoundError(f"指定路径不是 blender.exe: {resolved}")
        return resolved
    if os.environ.get("BLENDER_PATH"):
        candidates.append(Path(os.environ["BLENDER_PATH"]).expanduser())
    on_path = shutil.which("blender")
    if on_path:
        candidates.append(Path(on_path))

    for install_root in (
        Path("C:/Program Files/Blender Foundation"),
        Path("D:/Blender Foundation"),
    ):
        if install_root.exists():
            found = list(install_root.glob("Blender */blender.exe"))
            candidates.extend(sorted(found, key=_version_key, reverse=True))

    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file() and resolved.name.lower() in {"blender", "blender.exe"}:
            return resolved

    raise FileNotFoundError(
        "没有找到 Blender。请安装 Blender 4.3 或更高版本，或使用 --blender 指定 blender.exe。"
    )


def _finite_number(config: dict[str, Any], key: str, minimum: float, maximum: float) -> float:
    value = config[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key} 必须是数字。")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ConfigError(f"{key} 必须在 {minimum:g} 到 {maximum:g} 之间。")
    return result


def _integer(config: dict[str, Any], key: str, minimum: int, maximum: int) -> int:
    value = config[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} 必须是整数。")
    if not minimum <= value <= maximum:
        raise ConfigError(f"{key} 必须在 {minimum} 到 {maximum} 之间。")
    return value


def _resolve_path(value: Any, base: Path, key: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} 必须是非空文件路径。")
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def validate_config(raw: dict[str, Any], base: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ConfigError("配置文件的顶层必须是 JSON 对象。")
    unknown = sorted(set(raw) - ALLOWED_CONFIG_KEYS)
    if unknown:
        raise ConfigError(f"配置包含未知字段: {', '.join(unknown)}")
    config = {**DEFAULTS, **raw}

    missing = [key for key in ("height_map", "output") if not config.get(key)]
    if missing:
        raise ConfigError(f"配置缺少字段: {', '.join(missing)}")

    height_map = _resolve_path(config["height_map"], base, "height_map")
    if not height_map.is_file():
        raise FileNotFoundError(f"找不到 DEM: {height_map}")
    if height_map.suffix.lower() not in SUPPORTED_INPUTS:
        supported = ", ".join(sorted(SUPPORTED_INPUTS))
        raise ConfigError(f"暂不支持 {height_map.suffix or '无扩展名'} 输入；支持: {supported}")

    color_map: Path | None = None
    if config.get("color_map"):
        color_map = _resolve_path(config["color_map"], base, "color_map")
        if not color_map.is_file():
            raise FileNotFoundError(f"找不到色带图: {color_map}")
        if color_map.suffix.lower() not in SUPPORTED_INPUTS:
            raise ConfigError(f"不支持色带图格式: {color_map.suffix}")

    output = _resolve_path(config["output"], base, "output")
    if output.suffix.lower() != ".png":
        raise ConfigError("第一版只输出 PNG，请让 output 以 .png 结尾。")
    input_paths = {height_map}
    if color_map:
        input_paths.add(color_map)
    if output in input_paths:
        raise ConfigError("输出路径不能覆盖 DEM 或色带图。")

    engine = str(config["engine"]).upper()
    if engine not in ENGINES:
        raise ConfigError(f"engine 必须是: {', '.join(sorted(ENGINES))}")
    camera = str(config["camera"]).upper()
    if camera not in CAMERAS:
        raise ConfigError(f"camera 必须是: {', '.join(sorted(CAMERAS))}")

    resolution = config["resolution"]
    if (
        not isinstance(resolution, list)
        or len(resolution) != 2
        or any(isinstance(v, bool) or not isinstance(v, int) for v in resolution)
        or any(not 64 <= v <= 16384 for v in resolution)
    ):
        raise ConfigError("resolution 必须是两个 64–16384 之间的整数，例如 [1600, 1600]。")

    for key in ("transparent_background", "save_blend", "detect_background"):
        if not isinstance(config[key], bool):
            raise ConfigError(f"{key} 必须是 true 或 false。")

    config.update(
        {
            "height_map": str(height_map),
            "color_map": str(color_map) if color_map else None,
            "output": str(output),
            "engine": engine,
            "camera": camera,
            "subdivisions": _integer(config, "subdivisions", 2, 1024),
            "max_texture_size": _integer(config, "max_texture_size", 256, 8192),
            "samples": _integer(config, "samples", 1, 4096),
            "terrain_size": _finite_number(config, "terrain_size", 0.01, 100000.0),
            "height_strength": _finite_number(config, "height_strength", 0.0, 10000.0),
            "sun_azimuth": _finite_number(config, "sun_azimuth", -360000.0, 360000.0) % 360.0,
            "sun_elevation": _finite_number(config, "sun_elevation", 0.0, 90.0),
            "sun_energy": _finite_number(config, "sun_energy", 0.0, 1000.0),
            "camera_azimuth": _finite_number(config, "camera_azimuth", -360000.0, 360000.0) % 360.0,
            "camera_elevation": _finite_number(config, "camera_elevation", 1.0, 89.0),
            "resolution": resolution,
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    return config


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        raw = json.load(handle)
    return validate_config(raw, path.parent.resolve())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="输入裁切后的 DEM，使用 Blender 直接渲染地形。")
    parser.add_argument("dem", nargs="?", type=Path, help="裁切好的 DEM（TIFF/PNG/JPEG/EXR）")
    parser.add_argument("--config", type=Path, help="高级用法：JSON 配置文件")
    parser.add_argument("--sun-azimuth", type=float, default=315.0, help="太阳方位角，默认 315°")
    parser.add_argument("--sun-elevation", type=float, default=35.0, help="太阳高度角，默认 35°")
    parser.add_argument("--output", type=Path, help="输出 PNG；默认与 DEM 同目录")
    parser.add_argument("--blender", help="blender.exe 的完整路径")
    parser.add_argument("--dry-run", action="store_true", help="只检查并显示命令")
    return parser


def config_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.config and args.dem:
        raise ConfigError("DEM 位置参数与 --config 不能同时使用。")
    if args.config:
        if args.output is not None or args.sun_azimuth != 315.0 or args.sun_elevation != 35.0:
            raise ConfigError("使用 --config 时，请在 JSON 中设置输出和太阳参数。")
        return load_config(args.config.expanduser().resolve())
    if args.dem is None:
        raise ConfigError("请提供 DEM 路径，或使用 --config 指定配置文件。")

    dem = args.dem.expanduser().resolve()
    output = args.output.expanduser().resolve() if args.output else dem.with_name(f"{dem.stem}_render.png")
    return validate_config(
        {
            "height_map": str(dem),
            "output": str(output),
            "sun_azimuth": args.sun_azimuth,
            "sun_elevation": args.sun_elevation,
        },
        Path.cwd(),
    )


def _write_runtime_config(config: dict[str, Any], success_file: Path) -> Path:
    runtime = {**config, "_success_file": str(success_file)}
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="dem-terrain-", encoding="utf-8", delete=False
    )
    with handle:
        json.dump(runtime, handle, ensure_ascii=False, indent=2, allow_nan=False)
    return Path(handle.name)


def _emit_child_output(data: bytes | None, stream: Any) -> None:
    if not data:
        return
    text = data.decode("utf-8", errors="replace")
    print(text, file=stream, end="" if text.endswith("\n") else "\n")


def main(argv: list[str] | None = None) -> int:
    runtime_config: Path | None = None
    success_file: Path | None = None
    try:
        args = build_parser().parse_args(argv)
        config = config_from_args(args)
        blender = find_blender(args.blender)
        if not BLENDER_SCRIPT.is_file():
            raise FileNotFoundError(f"缺少 Blender 渲染脚本: {BLENDER_SCRIPT}")

        with tempfile.NamedTemporaryFile(prefix="dem-terrain-success-", suffix=".json", delete=False) as handle:
            success_file = Path(handle.name)
        success_file.unlink(missing_ok=True)
        runtime_config = _write_runtime_config(config, success_file)

        command = [
            str(blender),
            "--background",
            "--python-exit-code",
            "10",
            "--python",
            str(BLENDER_SCRIPT),
            "--",
            "--config",
            str(runtime_config),
        ]
        print(f"Blender: {blender}")
        print(f"DEM: {config['height_map']}")
        print(f"太阳: 方位角 {config['sun_azimuth']}°, 高度角 {config['sun_elevation']}°")
        print(f"输出: {config['output']}")
        if args.dry_run:
            print("命令:", subprocess.list2cmdline(command))
            return 0

        output = Path(config["output"])
        previous_mtime = output.stat().st_mtime_ns if output.exists() else None
        print("正在渲染，请稍候……", flush=True)
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
        _emit_child_output(completed.stdout, sys.stdout)
        _emit_child_output(completed.stderr, sys.stderr)
        if completed.returncode != 0:
            print(f"错误: Blender 渲染失败，退出码 {completed.returncode}。", file=sys.stderr)
            return completed.returncode
        if not success_file.is_file():
            print("错误: Blender 未写入成功标记，请检查上方日志。", file=sys.stderr)
            return 3
        if not output.is_file() or (previous_mtime is not None and output.stat().st_mtime_ns == previous_mtime):
            print("错误: Blender 没有生成新的输出图片。", file=sys.stderr)
            return 3
        return 0
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130
    except (OSError, ConfigError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    finally:
        if runtime_config:
            runtime_config.unlink(missing_ok=True)
        if success_file:
            success_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
