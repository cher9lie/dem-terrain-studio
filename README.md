# DEM Terrain Studio

把传统的“GIS 导出高度图与色带图，再到 Blender 手工建模和打光”流程，变成可重复的一键渲染工作流。

项目目前处于早期原型阶段。第一版不会试图替代 GIS 软件，而是准确复现一条已经被大量地形渲染教程验证过的轻量流程：

1. 在 QGIS、ArcGIS 或其他 GIS 软件中准备正方形灰度高度图；
2. 导出同尺寸、同范围的地形色带图；
3. DEM Terrain Studio 调用 Blender，自动创建细分平面、施加高程位移、贴图、太阳光、白色承影平面和相机；
4. 输出带柔和阴影的高质量地形图。

## 目标画面

- 白色正方形地图或独立地形模型；
- 蓝—绿—黄—灰等自然高程分层色带；
- 可调地形起伏、太阳方位和太阳高度；
- 正交沙盘视角或透视视角；
- Eevee 快速预览，Cycles 高质量渲染；
- 白色背景、接触阴影和透明 PNG 输出选项。

## 为什么选择 Blender

Blender 已经具备稳定的高度图位移、纹理材质、太阳平行光、阴影、相机和离线渲染能力。项目只负责把这些步骤组织起来，不重新实现一套渲染器。这样能保留传统工作流的视觉效果，也便于用户继续在 `.blend` 文件中手工微调。

轻量实时渲染库仍可能用于后续预览，但不会在第一版同时维护两套场景逻辑。

## 当前原型用法

要求：

- Python 3.10 或更高版本；
- Blender 4.x；
- 一张灰度高度图；
- 一张与高度图完全对齐的 RGB/RGBA 色带图。

复制示例配置：

```powershell
Copy-Item config.example.json config.json
```

修改 `config.json` 中的图片路径，然后运行：

```powershell
py run.py --config config.json
```

如果 Blender 不在 PATH 中：

```powershell
py run.py --config config.json --blender "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
```

也可以先安装为可编辑包：

```powershell
py -m pip install -e .
dem-terrain-studio --config config.json
```

## 配置参数

| 参数 | 含义 |
|---|---|
| `height_map` | 灰度高度图路径 |
| `color_map` | 与高度图对齐的色带图路径 |
| `output` | 输出 PNG 路径 |
| `engine` | `BLENDER_EEVEE_NEXT` 或 `CYCLES` |
| `subdivisions` | 平面横纵细分数，预览建议 256，成图建议 512–1024 |
| `terrain_size` | Blender 场景中的平面宽度 |
| `height_strength` | 高程位移强度 |
| `sun_azimuth` | 太阳方位角，单位为度 |
| `sun_elevation` | 太阳高度角，单位为度 |
| `camera` | `ORTHO` 或 `PERSP` |
| `samples` | 渲染采样数 |

## 项目结构

```text
dem-terrain-studio/
├── blender/
│   └── render_scene.py       # Blender 场景生成与渲染
├── docs/
│   └── roadmap.md            # 分阶段开发计划
├── src/dem_terrain_studio/
│   ├── __init__.py
│   └── cli.py                # 参数检查、Blender 探测和任务启动
├── config.example.json
├── pyproject.toml
├── run.py
└── README.md
```

## 近期计划

- 完成一份真实省级样例的端到端验证；
- 增加 PySide6 桌面界面；
- 自动生成蓝—绿—黄—灰色带图；
- 增加省界 Alpha 掩膜与实体侧壁模式；
- 增加 Eevee 低分辨率预览；
- 增加 Blender/GPU 自动检测和清晰的错误提示；
- 保存 `.blend` 场景，便于二次编辑。

完整计划见 [docs/roadmap.md](docs/roadmap.md)。

## 开源许可

本项目使用 GPL-3.0 许可证。Blender 本身也使用 GPL。用户使用本项目生成的图片和模型不因 Blender 或本项目许可证而自动变为 GPL；输入数据和底图仍需遵守各自的数据许可。
