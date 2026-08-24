# E3 source-conditioned imaging

`run_core.py` 是当前主网格正式入口，读取 Article V3 合并层 `events/valid/grid`，从 `k1_F/k1_T/k1_B/ms_F/ms_T/ms_B` 构建 M0–M5，并生成固定的 E3-F1～F5 与 E3-T1～T3（5 PNG + 3 CSV）。`run.py` 保持包含 55 mm slab 参考的严格完整入口，数据齐备时生成 6 PNG + 4 CSV。target 始终按 first-scatter depth 的 `[zc-5,zc+5)` 区域定义，不使用缺陷三维体积。

入口执行以下严格合同：

- P0 与 P1–P6 matched profile 均须具有完整、无重复的 9×9 物理位姿；
- recorded slit label 与随 pose 平移的闭区间 detector ROI 必须同时满足；
- P4 front-slab root 须包含 `reference_manifest.yaml`，声明 `reference_type: uniform_pmma_front_slab`、`thickness_mm: 55.0` 和与 run metadata 一致的 `vehicle_geometry_file`；
- 5000 次 pose/category-level Poisson 重采样重建所有派生量，默认 seed 为 `20260814`；无效 draw 按指标排除并记录有效抽样数；
- 缺数或数值合同失败时不创建正式输出，不提供 partial flag；
- core 成功时输出目录根只有冻结的八个文件；严格入口成功时只有十个文件，不写 manifest、report、PDF 或调试产物。

```bash
conda run -n data python -m scripts.postprocessing.e3.run_core \
  --results-root results/articlev3_merged \
  --overwrite
```

```bash
conda run -n data python -m scripts.postprocessing.e3.run \
  --results-root results/articlev3_merged \
  --slab-grid-root /path/to/P4_front_slab_55mm_grid \
  --overwrite
```

当前 Article V3 合并层的全部 matched grid 已通过预检，core 已发布正式 5 图 3 表。尚缺 81 个 slab 位姿，因此严格完整入口仍应在预检中失败且不生成 E3-F6/E3-T4。完整执行合同见 `docs/articlev2_analysis/E3.md`。
