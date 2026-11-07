# DEM Terrain Studio

将裁切好的省、市 DEM 自动转换为带自然分层色、太阳光和阴影的 Blender 地形渲染图。

第一版刻意保持简单：用户只提供 DEM 和太阳角度；色带、相机、垂直夸张、白色承影平面、网格精度和渲染参数均有默认值。

## 当前能力

- 输入 TIFF、PNG、JPEG 或 EXR 高程图；
- 自动把整数、16 位或浮点像素归一化到统一高度范围；
- 自动识别透明背景或四周近乎一致的白色/黑色 NoData 背景；
- 保留非正方形 DEM 的宽高比；
- 对没有 NoData 的矩形高程图生成封闭侧壁和平底；含掩膜的省界轮廓暂仍按原有贴图方式显示；
- 自动生成白—蓝—绿—黄—灰自然色带；
- 根据方位角和高度角设置 Blender Sun；
- 自动创建白色承影平面和正交相机；
- 使用 Eevee 输出 PNG，并保存可编辑的 `.blend` 文件；
- 可选透明背景；透明模式会隐藏 NoData 区并移除白色承影平面，因此不会保留地面投影；
- 兼容 Blender 4.3+ 与 Blender 5.x；
- 对路径、配置范围、输出覆盖和 Blender 脚本失败做明确检查。

## 要求

- Windows；
- Python 3.10 或更高版本；
- Blender 4.3 或更高版本。

程序会依次寻找：

1. `--blender` 指定的路径；
2. `BLENDER_PATH` 环境变量；
3. PATH 中的 Blender；
4. `C:\Program Files\Blender Foundation`；
5. `D:\Blender Foundation`。

## 最简单的用法

```powershell
Set-Location D:\DEM-Terrain-Studio
.\run.cmd "D:\data\beijing_dem.tif"
```

指定太阳角度：

```powershell
.\run.cmd "D:\data\beijing_dem.tif" --sun-azimuth 315 --sun-elevation 35
```

指定输出位置：

```powershell
.\run.cmd "D:\data\beijing_dem.tif" --output "D:\renders\beijing.png"
```

默认输出为 DEM 同目录下的 `<DEM文件名>_render.png`，并生成同名 `.blend`。

如果没有自动找到 Blender：

```powershell
.\run.cmd "D:\data\beijing_dem.tif" `
  --blender "D:\Blender Foundation\Blender 5.1\blender.exe"
```

## 默认参数

| 项目 | 默认值 |
|---|---|
| 渲染器 | Eevee |
| 网格最长边细分 | 256 |
| 处理纹理最长边 | 2048 像素 |
| 输出尺寸 | 1600 × 1600 |
| 相机 | 正交相机 |
| 色带 | 白 / 蓝 / 绿 / 黄 / 灰 |
| 太阳方位角 | 315° |
| 太阳高度角 | 35° |
| 输出 | PNG + BLEND |

## 高级配置

复制并修改 [`config.example.json`](config.example.json)：

```powershell
Copy-Item config.example.json config.json
.\run.cmd --config config.json
```

使用 `--config` 时，太阳和输出参数应写在 JSON 中，不再同时传位置参数或 `--sun-*`。

`detect_background` 默认为 `true`。它会把透明像素以及占据至少 85% 图像边缘的同一灰度值视为 NoData，并将其保持为白色平面。如果 DEM 的真实区域本来就有完全一致的边缘值，可在配置中将其设为 `false`。

如果单独提供 `color_map`，它必须与原始 DEM 像素尺寸完全一致；否则程序会停止，而不是静默错位。

## 输入说明

程序会对可见像素做最小值—最大值归一化。这样 GIS 导出的 8/16 位灰度图和常见浮点图能够得到一致的相对起伏。现阶段表现的是相对高程，不保留原始海拔单位和绝对比例。

Blender 并不是完整的 GIS 栅格读取器。某些带特殊压缩、多个波段或特殊 NoData 元数据的 GeoTIFF 可能无法直接打开；遇到这种情况，请先在 QGIS/ArcGIS 中导出单波段 TIFF 或 16 位 PNG。

原始地理 DEM 推荐先使用下面的预处理入口。RGB 三通道不一致的高程输入会被拒绝，避免把 elevation/slope/aspect 等多波段数据混成错误地形。单波段原始 GeoTIFF 直接走轻量入口时，仍不解析其 CRS、NoData 和垂直单位。

## 真实地理 DEM 的准备

安装可选 GIS 依赖后，显式选择高程波段和研究范围。原始文件只读，输出目录必须尚不存在；范围坐标使用输入 CRS，目标 CRS 必须是米制投影，高程单位必须事先确认为米。

```powershell
python -m pip install ".[geo]"
python tools/prepare_geodem.py "D:\data\dem.tif" outputs/my-region --bounds 113.03 34.35 113.45 34.65 --target-crs EPSG:32649 --band 1 --elevation-unit metre --source-url "原始数据来源URL" --license "数据许可"
.\run.cmd --config outputs/my-region/white.json
.\run.cmd --config outputs/my-region/transparent.json
.\run.cmd --config outputs/my-region/scale_1x.json
```

工具输出投影后的单波段 DEM、带有效区 alpha 的浮点高程纹理、元数据及三套配置。默认艺术化夸张为 4 倍，`scale_1x.json` 保持水平与垂直的相对米制比例。两者均平移了海拔基准并增加陈列底座，不表示绝对海拔；太阳方位以投影网格北为 0°。蓝色仅表示色带低值，不代表水体。

预处理限制：仅接受来源范围内的小裁片（最多 1600 万原始像元）；按等距米制像元双线性重采样；为去除重投影矩形边缘的空白会向内收边，并在元数据记录收边量。内部真实缺测不填补。复杂省界、多岛和内部孔洞的封闭实体尚未实现。

真实数据验收与本地复现命令见 [2026-11-07 验收记录](docs/acceptance-20261107.md)，待合并内容见 [合并说明草稿](docs/merge-notes-20261107.md)。预处理及审计工具随源码仓库提供，基础 wheel 保持轻量。

## 项目结构

```text
dem-terrain-studio/
├── src/dem_terrain_studio/
│   ├── blender/render_scene.py  # 随 Python 包发布的 Blender 场景脚本
│   └── cli.py                   # 校验、Blender 探测和任务启动
├── tests/test_cli.py
├── config.example.json
├── docs/roadmap.md
├── pyproject.toml
├── run.cmd                    # Windows 主入口
├── run.ps1                    # 自动寻找现代 Python
└── run.py
```

## 开发检查

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src run.py
```

当前机器上的 `py` 可能默认指向 ArcGIS 自带的 Python 2.7，因此 Windows 下优先使用 `run.cmd`。它只启动仓库内的 `run.ps1`，不会修改系统执行策略。如果你已经确认 `python --version` 为 3.10 或更高，也可以运行 `python run.py ...`。

## 开源许可

本项目使用 GPL-3.0-only。生成的图片和模型不会仅因使用本项目或 Blender 而自动变为 GPL；输入 DEM、行政边界和底图仍应遵守各自的数据许可。
