# 真实 DEM 验收：2026-11-07

本次完成小型真实地理 DEM 的源数据→投影/掩膜→尺度配置→Blender→PNG/BLEND 闭环。没有重跑先前已通过的合成数据测试。结论仅覆盖下述矩形山地研究区，不等同于完成任意省界、多岛或内部孔洞的实体建模验收。

## 仓库基线

正式仓库为 `D:\DEM-Terrain-Studio`，origin 为 `https://github.com/cher9lie/dem-terrain-studio.git`。更新远端跟踪后，`origin/main` 为 `d2cb243`，`origin/codex/stability-audit` 为 `3f94974`；祖先检查确认后者仍未合并 main。开始时正式仓库工作区干净。

`C:\Users\ChenNan\Documents\DEM三维渲染` 是另一份无提交、无 origin 的工作副本，现有源码均为未跟踪状态；这些文件完整保留。本轮使用其中新增的 `acceptance_work` 作为补丁暂存区，正式开发及产物仍位于 D 盘。

## 数据与许可

选用本机 `G:\洪水模拟\data\raw\dem\fabdem\tiles\N34E113_FABDEM_V1-2.tif`。其 TIFF 标签明确记录 FABDEM v1-2、University of Bristol and Fathom，以及 CC BY-NC-SA 4.0。已有下载脚本 `G:\洪水模拟\scripts\fabdem_remote_subset.py` 指向布里斯托大学原始 ZIP。未修改原始瓦片。

- 发布者与引用：Neal, Hawker, Uhe 等，FABDEM V1-2 (2023)，[DOI / 官方数据记录](https://research-information.bris.ac.uk/en/datasets/fabdem-v1-2/)。
- 原始包：`https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/N30E110-N40E120_FABDEM_V1-2.zip`。
- 本次研究与验收为非商业用途；渲染图片和派生栅格按 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 留存，不能把软件 GPL 许可误当作数据的商业授权。
- 原件 SHA-256（处理前后相同）：`031543c0b4585d6636d60073a65ca4abab2a3e7986c70356f379c408f5083a36`。

本机另有 `SRTM_Terrain.tif`，其三波段为 elevation/slope/aspect，但原始导出来源链不完整，因此不作为已确认许可的成图数据。只读取该文件验证多波段输入的拒绝行为，没有发布其数据或派生图。

## 地理与尺度记录

| 项目 | 实测或处理值 |
|---|---|
| 原始 CRS / 像元 | EPSG:4326，约 1 角秒，3600×3600 |
| 选取范围（经纬度） | 113.03–113.45°E，34.35–34.65°N，郑州西南附近山地矩形研究区 |
| 原始 NoData | −9999；按掩膜读取，非有限值同样剔除 |
| 目标 CRS | EPSG:32649，UTM 49N，米制正方像元 |
| 重采样 | 双线性；重投影后向内收边 23 像元去除矩形边缘空白 |
| 渲染用尺寸 | 978×844，像元约 38.38393 m |
| 地理范围宽×高 | 37539.4843 × 32396.0376 m |
| 高程范围 | 154.1419–1471.0359 m |
| 裁片缺测数 | 0；本次没有覆盖真实内部 NoData 孔洞场景 |
| Blender XY | 10 × 8.629857；与投影栅格宽高比相符，误差约 2.5×10⁻⁸ |
| 1 倍高度参数 | 0.3579616035；扣除归一化的 0.98 编码系数 |
| 4 倍高度参数 | 1.4318464142；用于 white / transparent |
| 太阳 | 方位 315°，高度 35°，从 +Y 网格北顺时针计算 |

1 倍模式保持相对地形起伏与水平距离的米制比例；实际网格采样后最大起伏比预期低约 0.334%，来自纹理/网格采样。4 倍模式的起伏恰为 1 倍的 4 倍。两者均去掉绝对海拔偏移，底座厚度、离地间隔是陈列参数。垂直基准没有独立核验，不用于绝对海拔、海平面或水文计算。太阳未做真北/网格北收敛角修正。

## 结果与检查

本机 Python 3.12、Blender 5.1.2、Eevee 实际渲染。产物位于 `outputs/acceptance-20261107/`（被 Git 忽略，未公开上传）：

- `white.png` / `white.blend`：1200×1200，4 倍起伏，白色承影材质、侧壁和平底。
- `transparent.png` / `transparent.blend`：1200×1200，4 倍起伏，无承影地面；alpha 范围 0–255。
- `scale_1x.png` / `scale_1x.blend`：1200×1200，1 倍相对地理尺度。
- `dem_projected.tif`、`height_rgba.tif`、三份配置、`metadata.json` 和 `*.audit.json`：预处理与核验记录。
- `dist/`、`venv/`：本地构建的 wheel 与独立安装验证环境。

已目视检查三张成图：地形方向一致、山脊与谷地可见、矩形边缘无异常尖峰，4 倍起伏明显增强；白底地面可见柔和投影，透明图不含地面。当前默认光照和色带较柔和，属于高程分层设色，蓝色不是水体分类，也不是真实卫星地表颜色。

重新打开保存的三份 BLEND 进行检查：非流形边均为 0；纹理已打包；横纵比例通过；太阳实测为 315° / 34.999997°。白底场景的 UV 方向检查确认 +U 对应东、+V 对应网格北。透明场景 film_transparent 为 true，且不存在 White Ground。

独立 venv 安装 wheel 后，确认 CLI 来自 `venv/Lib/site-packages`，打包渲染脚本存在，并成功完成同一真实 DEM 白底渲染。没有调用源码路径代替已安装包。源码和已安装入口的 UTF-8 日志修复分别通过 dry-run/真实调用核验。

## 本次修正

1. RGB 高程通道不一致时明确拒绝，防止 elevation/slope/aspect 被静默混合成错误高程。用本机真实三波段文件验证：退出码 10，且没有错误成图。
2. 无 NoData 的矩形地形生成封闭侧壁和平底。含掩膜的省界仍保留既有显示方式，不虚构轮廓封闭能力。
3. 高程纹理及外部颜色纹理打包进 BLEND，重开场景可检查。
4. Windows 启动器和 CLI 统一 UTF-8，修正本次实际出现的中文乱码。
5. 构建依赖由 setuptools>=68 改为 >=77.0.3，与 SPDX license / license-files 配置匹配；依据 [Python 官方打包指南](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)。隔离构建 wheel 通过，未升级系统构建依赖。
6. 增加显式波段、投影、有效区和尺度记录的预处理工具，以及保存场景的验收脚本。

## 复现命令

以下在仓库根目录执行；输出目录已存在时须换一个新目录，保护已有产物。

```powershell
python -m pip install ".[geo]"
python tools/prepare_geodem.py "G:\洪水模拟\data\raw\dem\fabdem\tiles\N34E113_FABDEM_V1-2.tif" outputs/acceptance-new --bounds 113.03 34.35 113.45 34.65 --target-crs EPSG:32649 --band 1 --elevation-unit metre --exaggeration 4 --source-url "https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/N30E110-N40E120_FABDEM_V1-2.zip" --license CC-BY-NC-SA-4.0
.\run.cmd --config outputs/acceptance-new/white.json
.\run.cmd --config outputs/acceptance-new/transparent.json
.\run.cmd --config outputs/acceptance-new/scale_1x.json
& "D:\Blender Foundation\Blender 5.1\blender.exe" -b outputs/acceptance-new/white.blend --python-exit-code 10 --python tools/audit_scene.py -- outputs/acceptance-new/metadata.json outputs/acceptance-new/white.json
python -m pip wheel . --no-deps --wheel-dir outputs/acceptance-new/dist
python -m venv outputs/acceptance-new/venv
& ".\outputs\acceptance-new\venv\Scripts\python.exe" -m pip install --no-deps --no-index outputs/acceptance-new/dist/dem_terrain_studio-0.1.0-py3-none-any.whl
& ".\outputs\acceptance-new\venv\Scripts\dem-terrain-studio.exe" --config outputs/acceptance-new/white.json
```

最小输入：来源/使用权限明确、有效 CRS、可显式选择的高程波段、已确认米制高程单位的小型 GeoTIFF；有非矩形边界时应包含正确有效区掩膜。直接使用轻量入口则要求已准备好的灰度高程图，像元宽高相等，且接受相对归一化高度。

下一步优先实现真实行政边界及内部孔洞的约束网格、侧墙和封底，再用来源明确的完整市域 DEM 进行验收。本轮未合并 main、未发布 Release、未推送新增源码。
