# E3 source-conditioned imaging

`run.py` 是当前正式入口，读取 Article V3 合并主网格与独立 55 mm slab 参考，从 `k1_F/k1_T/k1_B/ms_F/ms_T/ms_B` 构建 M0–M5，并生成 E3-F1～F6 与 E3-T1～T4（6 PNG + 4 CSV）。`run_core.py` 保留为缺少 slab 时的 5 PNG + 3 CSV 兼容入口。target 始终按 first-scatter depth 的 `[zc-5,zc+5)` 区域定义，不使用缺陷三维体积。

入口执行以下严格合同：

- P0 与 P1–P6 matched profile 均须具有完整、无重复的 9×9 物理位姿；
- recorded slit label 与随 pose 平移的闭区间 detector ROI 必须同时满足；
- P4 front-slab root 须包含 `reference_manifest.yaml`，声明 `reference_type: uniform_pmma_front_slab`、`thickness_mm: 55.0` 和与 run metadata 一致的 `vehicle_geometry_file`；81 份 metadata 还须逐项匹配 100M primary、model ID 和唯一 seed 11000–11080；
- 5000 次 pose/category-level Poisson 重采样重建所有派生量，默认 seed 为 `20260814`；无效 draw 按指标排除并记录有效抽样数；
- 缺数或数值合同失败时不创建正式输出，不提供 partial flag；
- core 成功时输出目录根只有冻结的八个文件；严格入口成功时根目录包含十个正式文件，并允许唯一的辅助目录 `supplementary/`。严格入口重跑时会原样保留该辅助目录，其他未知根级内容仍会阻止发布；正式入口本身不写 manifest、report、PDF 或调试产物。

```bash
conda run -n data python -m scripts.postprocessing.e3.run_core \
  --results-root results/articlev3_merged \
  --output-dir results/articlev3_merged/postprocessing/E3_core_diagnostic \
  --overwrite
```

```bash
conda run -n data python -m scripts.postprocessing.e3.run \
  --results-root results/articlev3_merged \
  --slab-grid-root results/articlev3_p4_front_slab_55mm_100m \
  --overwrite
```

中心 3×3 first-scatter-depth 辅助入口直接比较 P4 Total、从 P4 事件以 `z<55 mm` 选出的 truth front、按实际 pooled histories 比例缩放的 slab front，以及二者的 signed residual。深度分布固定使用 `[0,220]` mm、2 mm bin，不做独立归一化或平滑。入口还用完整 P4 9×9 网格和正式 E3 的 25 点 defect/32 点 background ROI，计算 truth-front 的逐深度 `mu_BG`、`mu_ROI` 与 `Delta=mu_BG-mu_ROI`：

```bash
conda run -n data python -m scripts.postprocessing.e3.run_center3x3_depth_histograms \
  --results-root results/articlev3_merged \
  --slab-grid-root results/articlev3_p4_front_slab_55mm_100m \
  --overwrite
```

输出位于 `postprocessing/E3/supplementary/center3x3_first_scatter_depth/`，固定为 3 张 300 dpi PNG 和一个单行 summary CSV，不属于正式十文件合同。CSV 保存 truth/slab 总数、slab/truth、slab 浅层比例和浅层 Pearson r；固定深度域以外的有限事件不夹到边界 bin，而是排除并在终端报告。`run_core.py` 应始终显式指定独立输出目录，不能覆盖完整 E3 目录。

当前 matched grid 与 81 个 slab 位姿均已通过预检，严格入口已发布正式 6 图 4 表。完整执行合同与数值解释边界见 `docs/articlev2_analysis/E3.md` 和 `docs/articlev2_analysis/Report.md`。
