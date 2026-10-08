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

输出位于 `postprocessing/E3/supplementary/center3x3_first_scatter_depth/`，固定为 4 张 300 dpi PNG 和一个单行 summary CSV，不属于正式十文件合同。新增的 `E3_SF4_P4_S4_front_reference_two_panel.png` 用原始 total 计数比较 truth-front 与浅层参考，并在 `z1<55 mm` 内分别归一化比较形态；仅绘图时将跨越 55 mm 的 bin 切开，Pearson 仍按原有 2 mm bin 计算。CSV 保存 truth/slab 总数、slab/truth、slab 浅层比例和浅层 Pearson r；固定深度域以外的有限事件不夹到边界 bin，而是排除并在终端报告。`run_core.py` 应始终显式指定独立输出目录，不能覆盖完整 E3 目录。

真实体素数据辅助入口读取 `results/real_data/defect.npy` 与 `front.npy`。两者的 z 轴均按 1 mm/slice 解释；`front` 在 y/x 方向分别以 2/8 个像素为一块求和到 defect 网格，随后两侧都以宽 3、步长 1 的 z 向滑动窗求和。前层扣除固定为 `R=D-F`（`alpha=1`），不做归一化、横向 ROI、CNR、Poisson 重采样或置信区间：

```bash
conda run -n data python -m scripts.postprocessing.e3.run_real_data_validation \
  --real-data-root results/real_data \
  --results-root results/articlev3_merged \
  --overwrite
```

输出位于 `postprocessing/E3/supplementary/real_data_front_validation/`，固定为 2 张 300 dpi PNG、2 个 CSV 和 3 个 `float64` NPY。三份 NPY 分别保存 windowed defect、rebinned/windowed front 与逐元素 residual，形状均为 `64×103×101`。目标区固定为 0-based slices 46–55；仅在完全落入该区间的三层窗中按 residual 总计数选代表窗，并列时选择较浅窗口。该辅助入口不改变正式 E3 十文件合同。

圆孔 ROI/CNR 入口固定读取上述 D/R NPY 的 window index 49，即 `[49,52) mm`、中心 50.5 mm。定位阶段仅向 `derive_roi_geometry(D)` 传入 D；25 个中心、统一半径、valid mask 和逐孔 defect/background mask 冻结后，`evaluate_cnr(D,R,frozen_roi)` 才读取 R。定位图、平滑图和插值 radial profile 只用于确定几何，CNR 始终在未平滑、未归一化的 D/R 上按 signed `(mu_bg-mu_defect)/sigma_bg`、`ddof=1` 计算：

```bash
conda run -n data python -m scripts.postprocessing.e3.run_real_data_roi_cnr \
  --results-root results/articlev3_merged \
  --window-index 49 \
  --overwrite
```

输出位于 `real_data_front_validation/roi_cnr_analysis/`，固定包含 7 张 300 dpi PNG、5 个 CSV、3 份 bool mask NPY、5 份分析数组以及参数 JSON、summary 与 README。父入口只允许这一子目录，并在 `--overwrite` 时原样保留。当前数据得到 25/25 个圆孔，行/列间距 9.774569/11.183711 px，统一半径为 1.796693/3.203483/3.773614 px；D 与 R 的 mean CNR 分别为 2.867045 和 2.291730，4/25 个孔满足 `R_CNR>D_CNR`。九配置敏感性中 mean/median ΔCNR 始终为负，但改善孔比例跨度为 28 个百分点，故按预设规则判为不稳定；不据此重新选择 ROI。

当前 matched grid 与 81 个 slab 位姿均已通过预检，严格入口已发布正式 6 图 4 表；真实数据深度入口选择 `[50,53) mm`、中心 51.5 mm 的总 residual 代表窗，而圆孔 ROI/CNR 入口按固定协议使用 `[49,52) mm`、中心 50.5 mm，两者用途不同。完整执行合同与数值解释边界见 `docs/articlev2_analysis/E3.md` 和 `docs/articlev2_analysis/Report.md`。
