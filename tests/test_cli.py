from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dem_terrain_studio import cli


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dem = self.root / "省级 DEM.png"
        self.dem.write_bytes(b"not decoded by CLI")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def valid(self, **overrides):
        raw = {"height_map": str(self.dem), "output": str(self.root / "out.png")}
        raw.update(overrides)
        return cli.validate_config(raw, self.root)

    def test_defaults_and_chinese_path(self):
        config = self.valid()
        self.assertEqual(config["subdivisions"], 256)
        self.assertEqual(config["camera"], "ORTHO")
        self.assertEqual(config["sun_azimuth"], 315.0)

    def test_utf8_bom_config_is_supported(self):
        path = self.root / "config.json"
        payload = {"height_map": self.dem.name, "output": "out.png"}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8-sig")
        self.assertEqual(Path(cli.load_config(path)["height_map"]), self.dem)

    def test_rejects_output_overwriting_input(self):
        with self.assertRaisesRegex(cli.ConfigError, "不能覆盖"):
            self.valid(output=str(self.dem))

    def test_rejects_non_png_output(self):
        with self.assertRaisesRegex(cli.ConfigError, "只输出 PNG"):
            self.valid(output=str(self.root / "out.jpg"))

    def test_rejects_invalid_numeric_values(self):
        for key, value in (
            ("subdivisions", 1),
            ("subdivisions", 1.5),
            ("height_strength", float("nan")),
            ("sun_elevation", 91),
            ("camera_elevation", 0),
            ("samples", True),
        ):
            with self.subTest(key=key, value=value):
                with self.assertRaises(cli.ConfigError):
                    self.valid(**{key: value})

    def test_rejects_invalid_resolution_and_enums(self):
        for override in (
            {"resolution": [1600]},
            {"resolution": [1600, "1600"]},
            {"engine": "UNKNOWN"},
            {"camera": "SIDEWAYS"},
            {"detect_background": "yes"},
        ):
            with self.subTest(override=override):
                with self.assertRaises(cli.ConfigError):
                    self.valid(**override)

    def test_rejects_unknown_config_key(self):
        with self.assertRaisesRegex(cli.ConfigError, "未知字段"):
            self.valid(sun_altitude=35)

    def test_rejects_dem_and_config_together(self):
        args = argparse.Namespace(
            config=self.root / "config.json",
            dem=self.dem,
            output=None,
            sun_azimuth=315.0,
            sun_elevation=35.0,
        )
        with self.assertRaisesRegex(cli.ConfigError, "不能同时"):
            cli.config_from_args(args)


class BlenderDiscoveryTests(unittest.TestCase):
    def test_explicit_non_blender_executable_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            other = Path(folder) / "other.exe"
            other.write_bytes(b"")
            with patch.dict("os.environ", {}, clear=True), patch("shutil.which", return_value=None):
                with self.assertRaises(FileNotFoundError):
                    cli.find_blender(str(other))


class MainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dem = self.root / "dem.png"
        self.dem.write_bytes(b"fake")
        self.output = self.root / "render.png"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_blender_zero_exit_without_marker_is_failure(self):
        with patch.object(cli, "find_blender", return_value=Path("blender.exe")), patch(
            "subprocess.run", return_value=subprocess.CompletedProcess([], 0)
        ):
            result = cli.main([str(self.dem), "--output", str(self.output)])
        self.assertEqual(result, 3)

    def test_success_requires_new_output_and_marker(self):
        def fake_run(command, **_kwargs):
            config_path = Path(command[-1])
            runtime = json.loads(config_path.read_text(encoding="utf-8"))
            Path(runtime["output"]).write_bytes(b"png")
            Path(runtime["_success_file"]).write_text("{}", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0)

        with patch.object(cli, "find_blender", return_value=Path("blender.exe")), patch(
            "subprocess.run", side_effect=fake_run
        ):
            result = cli.main([str(self.dem), "--output", str(self.output)])
        self.assertEqual(result, 0)
        self.assertEqual(self.output.read_bytes(), b"png")

    def test_nonzero_blender_exit_is_propagated(self):
        with patch.object(cli, "find_blender", return_value=Path("blender.exe")), patch(
            "subprocess.run", return_value=subprocess.CompletedProcess([], 10)
        ):
            result = cli.main([str(self.dem), "--output", str(self.output)])
        self.assertEqual(result, 10)


if __name__ == "__main__":
    unittest.main()
