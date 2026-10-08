# 实验后处理

实验代码与结果按 E1–E3 独立分层，统一读取 `results/<campaign>/events/valid/`，不得回退到 `events_clean.csv/slit_id`。

| 目录/入口 | 职责 | 输入 | 正式输出 | 关键参数 | 失败条件 |
|---|---|---|---|---|---|
| `e1/run.py` | E1 detector ROI、total depth response 和分 acquisition-group 的 first/last 空间比较 | 审计通过的 P0 center valid events | 3 PNG + manifest/report/acceptance | `--results-root`、`--overwrite` | 审计、schema、ROI、归一化或输出合同失败 |
| `e1/analyze_roi_sensitivity.py` | 独立的 ROI 敏感性辅助分析 | valid manifest + boundary JSON | `postprocessing/E1/roi_sensitivity/` | `--boundary-config`、`--overwrite` | hash、标签或配对失败 |
| `e2/run.py` | E2 grid/zero-pose 表、P1–P6 total/k1/ms 深度响应与 source-region 分解 | P0/P1–P6 center 或 grid-zero + matched grid valid events | 正式默认 7 PNG、8 CSV；显式 case 为诊断单图 | `--summary-source`、`--case`、`--min-baseline-count`、`--resample-seed`、`--allow-partial-grid`、`--overwrite` | summary、case、bin width、grid pair、分母、schema 或输出合同失败 |
| `e2/run_section_3_2.py` | 直接从零位姿原始事件重建当前第 3.2 节表图和逐项验证 | P0/P1–P6 matched-profile grid-zero valid events；正式 E2-T1 只作核验 | `E2/supplementary/section_3_2/` 下 5 CSV + 4 PNG + 2 YAML；独立 Markdown 结果 | `--results-root`、`--audit-dir`、`--output-dir`、`--summary-output`、`--overwrite` | 原始选择、schema、计数/权重/贡献闭合、E2-T1 对照、图形或原子输出合同失败 |
| `e2/run_target_scatter_composition.py` | 保留的旧目标来源散射阶次补充分析；不再用于当前第 3.2 节主展示 | 已验收的正式 grid-zero E2-T1/T2/T3 | `E2/supplementary/target_scatter_composition/` 下 3 CSV + 1 PNG | `--results-root`、`--output-dir`、`--overwrite` | 正式 E2 控制文件、schema、计数/比例闭合或输出合同失败 |
| `e2/run_front_source_trends.py` | 保留的旧前方来源趋势补充分析；不再用于当前第 3.2 节主展示 | 已验收 E2-T2/T3、E2 controls、正式 E3-T2 | `E2/supplementary/front_source_trends/` 下 3 CSV + 2 PNG | `--results-root`、`--output-dir`、`--overwrite` | 控制文件、E2/E3 schema、闭合、M5 retention 或输出合同失败 |
| `e3/run.py` | E3 source-conditioned M0–M5、CNR/retention、深度收益与 front-slab 参考比较 | 完整 matched grid + 独立 55 mm slab grid | 固定 6 PNG + 4 CSV | `--slab-grid-root`、`--resample-seed`、`--overwrite` | 任一缺失/重复位姿、schema、恒等式、点估计分母或输出合同失败 |
| `e3/run_core.py` | 不依赖 slab 的 E3 主网格分析 | 完整 matched grid | 固定 5 PNG + 3 CSV | `--resample-seed`、`--overwrite` | 任一主网格、schema、恒等式、数值或输出合同失败 |
| `e3/run_center3x3_depth_histograms.py` | P4-S4 truth-front、slab depth component、逐深度 ROI 及双 panel 浅层参考对比 | P4 matched grid + 独立 55 mm slab grid | `E3/supplementary/` 下固定 4 PNG + 1 summary CSV | `--slab-grid-root`、`--overwrite` | 中心 pose、provenance、depth 或实际历史数无效 |
| `e3/run_real_data_validation.py` | 真实体素数据的前层聚合、z 向三层滑窗与确定性前层扣除 | `results/real_data/defect.npy` + `front.npy` | `E3/supplementary/` 下固定 2 PNG + 2 CSV + 3 NPY | `--real-data-root`、`--results-root`、`--output-dir`、`--overwrite` | NPY 维度/数值、2×8 聚合、滑窗、分母、相关系数或输出合同失败 |
| `e3/run_real_data_roi_cnr.py` | 由 D-only 自动冻结 5×5 圆孔 ROI，并在原始 D/R 上计算配对 signed CNR 与敏感性 | 上一入口生成的 windowed D/R NPY | `real_data_front_validation/roi_cnr_analysis/` 下 7 PNG + 5 CSV + masks/arrays + JSON/Markdown | `--results-root`、`--window-index`、`--output-dir`、`--overwrite` | 边界/坏点、25 孔 lattice、radial 半径、mask 像素数、背景方差或输出合同失败 |
| `_archive/` | 不可执行的旧 schema 源码快照 | 历史 `events_clean/slit_id` | 不得生成正式结果 | 无 | 禁止作为正式入口 |

```bash
conda run -n data python -m scripts.postprocessing.e1.run \
  --results-root results/articlev3_merged --overwrite

conda run -n data python -m scripts.postprocessing.e2.run \
  --results-root results/articlev3_merged --summary-source grid-zero \
  --overwrite

conda run -n data python -m scripts.postprocessing.e2.run_section_3_2 \
  --results-root results/articlev3_merged \
  --overwrite

# 以下两项仅用于重建保留的旧 supplementary
conda run -n data python -m scripts.postprocessing.e2.run_target_scatter_composition \
  --results-root results/articlev3_merged \
  --overwrite

conda run -n data python -m scripts.postprocessing.e2.run_front_source_trends \
  --results-root results/articlev3_merged \
  --overwrite

conda run -n data python -m scripts.postprocessing.e3.run_core \
  --results-root results/articlev3_merged \
  --output-dir results/articlev3_merged/postprocessing/E3_core_diagnostic \
  --overwrite

conda run -n data python -m scripts.postprocessing.e3.run \
  --results-root results/articlev3_merged \
  --slab-grid-root results/articlev3_p4_front_slab_55mm_100m \
  --overwrite

conda run -n data python -m scripts.postprocessing.e3.run_center3x3_depth_histograms \
  --results-root results/articlev3_merged \
  --slab-grid-root results/articlev3_p4_front_slab_55mm_100m \
  --overwrite

conda run -n data python -m scripts.postprocessing.e3.run_real_data_validation \
  --real-data-root results/real_data \
  --results-root results/articlev3_merged \
  --overwrite

conda run -n data python -m scripts.postprocessing.e3.run_real_data_roi_cnr \
  --results-root results/articlev3_merged \
  --window-index 49 \
  --overwrite
```

当前合并层的 matched grid 与独立 P4 55 mm slab 的 81-pose 参考均已完整；E2 严格验收、当前第 3.2 节原始事件重算、保留的两项旧 E2 supplementary、E3 完整 6 图 4 表、中心 3×3 辅助结果、真实数据前层扣除以及 D-only 圆孔 ROI/CNR 均已通过执行合同。第 3.2 节和真实数据目录均采用独立临时目录验收和原子发布；父真实数据入口重跑会原样保留唯一允许的 `roi_cnr_analysis/` 子目录，E2/E3 的其他 `supplementary/` 在正式重跑时也会保留。`e3/run_core.py` 仅用于缺少 slab 时的兼容分析，必须使用独立输出目录，不能覆盖当前完整 E3 目录。
