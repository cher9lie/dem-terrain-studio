# 异形 DEM 掩膜的封闭地形建模

本轮在 `f6fc09f` 的真实数据验收基础上，补齐输入有效区的外侧墙、内部孔洞、平底和分离地块。无需用户增加必填参数，已有灰度高程图或经过预处理的带 alpha 高程纹理继续使用相同入口。

## 实现行为

- 网格单元中心以最近邻读取有效区；仅对保留单元生成顶部和对应底部。
- 沿所有暴露边生成侧墙，因此内部孔洞拥有内壁，底板不会堵住孔洞。
- 顶点高度仅由同一局部连通扇区内的有效高程平均得到；NoData 数值不参与，避免边界塌向零值或 −9999。
- 仅对角接触的有效单元使用不同顶点，保持独立封闭壳；顶点连接和边连接均可核验。
- 顶面保留 UV 与自然色带，侧面/底部使用独立材质。轮廓外纹理延展只防止插值白边，不改变有效区或几何。
- 白底与透明模式使用同一实体几何，区别是背景及承影地面；空白区不再依赖材质透明来隐藏矩形薄片。
- 地理预处理默认保留掩膜；此前的矩形向内收边改为显式 `--trim-border`。

## 验证数据

仍使用此前已核实的本机 FABDEM v1.2。来源、许可及原件哈希见 [首次真实数据验收](acceptance-20261107.md)。派生成果仍按 CC BY-NC-SA 4.0 留存于被忽略的 outputs 目录，没有加入源码推送。

从既有 978×844 米制投影研究区中，提取高程 ≥650 m 的真实山地区域。这是地形阈值掩膜，不是行政边界。源掩膜保留 87226 个像元，包含 37 个分离区域和 2 个独立内部孔洞。使用前景四连通、背景八连通计数；仅在对角点接通外界的空缺不计作独立贯穿孔洞。

验证环境：Python 3.12、Blender 5.1.2、Eevee，输出 1200×1200。艺术化垂直夸张为 4 倍；1 倍参数为 0.2231720593，白底与透明参数一致。

最终产物位于 `D:\DEM-Terrain-Studio\outputs\masked-native-20261107\`：

- `white.png` / `white.blend`：白色承影地面与不规则实体。
- `transparent.png` / `transparent.blend`：相同实体，背景和孔洞区域透明。
- `metadata.json`、`white.json`、`transparent.json`、`height_rgba.tif`、`dem_projected.tif`：复现输入。
- `white.mask-audit.json` / `transparent.mask-audit.json`：重新打开保存场景后的检查结果。

## 已通过的检查

| 检查 | 结果 |
|---|---|
| 全部单元级掩膜 | 511 种非空 3×3 掩膜与 64 组随机 8×8 掩膜通过 |
| 单元拓扑 | 每条边恰好相邻两面、方向相反；每个顶点的连接为单个闭环 |
| 孔洞/体积 | 环形掩膜欧拉特征正确；实体有向体积与期望值一致 |
| 错误输入 | 空掩膜、非有限有效高程、采样后无有效单元明确报错 |
| 单元测试总计 | 18 项通过（包含原 CLI 回归）；未重跑旧合成图片渲染矩阵 |
| 原像元网格 | 978×844，有效单元 87226 |
| 实体组件/孔洞 | 37 个封闭组件、2 个贯穿孔洞，与源掩膜计数一致 |
| 非流形边/顶点 | 两份保存场景均为 0 / 0 |
| 逐格射线 | 两份场景分别检查 825432 个网格单元，命中/空缺与源掩膜全部一致 |
| 欧拉特征 | 70，符合 2×37−2×2 |
| 白底/透明 alpha | 白底 255–255；透明 0–255 |
| 独立安装 | wheel 包含新 terrain_mesh.py；独立 venv 实际完成带掩膜透明渲染及审计 |

已目视检查两张最终原像元精度成图，侧壁、岛块、背景空缺正常，山地起伏及白底投影可见。另进行了默认 256 网格的真实数据检查，确认粗网格可能改变窄连接和小孔；因此不把低分辨率预览当作原始轮廓的精确重建。

## 复现

以下假设上一轮 `outputs/acceptance-20261107` 的投影 DEM 和元数据仍存在；输出目录应使用新名称。

```powershell
python tests/prepare_real_mask_case.py outputs/acceptance-20261107 outputs/masked-new --subdivisions 1024 --threshold 650
.\run.cmd --config outputs/masked-new/white.json
.\run.cmd --config outputs/masked-new/transparent.json
& "D:\Blender Foundation\Blender 5.1\blender.exe" -b outputs/masked-new/white.blend --python-exit-code 10 --python tools/audit_masked_scene.py -- outputs/masked-new/white.json
& "D:\Blender Foundation\Blender 5.1\blender.exe" -b outputs/masked-new/transparent.blend --python-exit-code 10 --python tools/audit_masked_scene.py -- outputs/masked-new/transparent.json
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps --wheel-dir outputs/masked-new/dist
```

如果从其他地理 DEM 开始，先按 README 使用 prepare_geodem.py，不添加 `--trim-border`；如果高程图已经裁好并带透明掩膜，可以直接运行 `run.cmd input.tif`。复杂边界建议在 JSON 中提高 subdivisions，并适当提高 max_texture_size。当前网格最长边上限为 1024；小于网格单元的岛、孔、细颈可能消失或改变，轮廓为网格阶梯状，不具备矢量边界的亚像元精度。

## 分支和发布范围

本轮提交继续放在 `codex/real-dem-acceptance`，其祖先包括未合并的 `3f94974` 和本地 `f6fc09f`。本次按用户要求推送该功能分支，供完整审阅；main 保持原样，没有发布 Release。下一阶段可针对视觉效果完善自动构图和色带预设，或引入矢量边界约束三角化以消除网格阶梯。
