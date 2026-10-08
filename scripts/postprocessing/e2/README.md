# E2：缺陷可观测响应与 source-region mechanism

| 脚本 | 职责 | 输入 | 输出 | 主要参数 |
|---|---|---|---|---|
| `run.py` | 生成 matched grid、全局 center/grid-zero 长表和 P1–P6 全深度 F2/F3 | 审计 inventory、P0/P1–P6 grid-zero、matched grid valid events | 正式默认 7 PNG、8 CSV；显式 case 为诊断模式 | `--summary-source`、`--case`、`--min-baseline-count`、`--resample-seed`、`--allow-partial-grid`、`--overwrite` |
| `run_section_3_2.py` | 从零位姿原始事件重算新版图 5、表 6、non-T DTV 与 baseline total F/T/B 组成 | 审计 inventory、P0/P1–P6 matched-profile grid-zero valid events、正式 E2-T1（只作核验） | `E2/supplementary/section_3_2/` 下固定 5 CSV + 4 PNG + 2 YAML，并生成独立 Markdown 结果 | `--results-root`、`--audit-dir`、`--output-dir`、`--summary-output`、`--overwrite` |
| `run_target_scatter_composition.py` | 旧 T 区散射阶次补充分析；保留但不再用于当前第 3.2 节主展示 | 已验收的 grid-zero E2-T1/T2/T3、acceptance 与 manifest | `E2/supplementary/target_scatter_composition/` 下 3 CSV + 1 PNG | `--results-root`、`--output-dir`、`--overwrite` |
| `run_front_source_trends.py` | 旧前方来源趋势补充分析；保留但不再用于当前第 3.2 节主展示 | 已验收 grid-zero E2-T2/T3、正式 E3-T2、E2 controls | `E2/supplementary/front_source_trends/` 下 3 CSV + 2 PNG | `--results-root`、`--output-dir`、`--overwrite` |

严格模式要求 P1-S1 至 P6-S6 的 baseline/defect grid pair 各有完整 81 poses。`results/articlev3_merged` 已满足该条件；本次正式命令为：

```bash
conda run -n data python -m scripts.postprocessing.e2.run \
  --results-root results/articlev3_merged \
  --summary-source grid-zero \
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
```

`--summary-source grid-zero` 使整体计数与 F/T/B 表读取各 matched grid 的 `(0,0)` 100M 数据，并以 `zero_pose` 命名 T1/T3；默认 `center` 保持旧行为。partial 模式仅用于其他不完整 campaign 的诊断，不会用 center 数据、零值或插值替代缺失 grid。

未传 `--case` 时，正式运行固定分析 P1–S1 至 P6–S6 的 `total`、`k1` 与 `ms` 共 18 个 case：每个 scatter class 输出一张 E2-F2 相对响应图和一张 E2-F3 原始计数图，均按 P1–P6 排成 2×3 panel。因此正式合同为 E2-F1 加六张深度图（7 PNG），以及 E2-T1、E2-T3 和六组 E2-T2（8 CSV）。所有 panel 共享 0–220 mm 深度横轴、独立纵轴，并标记各自的 target-depth band。

`--case BASELINE:DEFECT:SLIT:SCATTER_CLASS` 可重复使用，作为诊断性单 case 模式：它只生成显式选择的单图，文件名携带比较条件和 scatter class；同一比较的 E2-T2 只生成一次。E2-T1 保存六深度整体响应，E2-T3 同时保存 P0 基线与相应缺陷模体的 F/T/B 占比；E2-5/E2-6 不生成图片。

F2/F3 和 E2-T2 共用 `run_e2(..., depth_bin_width_mm=...)`；默认值来自脚本顶部 `DEFAULT_DEPTH_BIN_WIDTH_MM = 2.0`，不提供额外 CLI。自定义宽度不能整除全范围或 region 时会追加 residual bin；宽度写入 manifest/report，但不改变文件名。核心定量指标固定使用 5000 次 Poisson 重采样，`--resample-seed` 默认 `20260814`，CSV 保存 95% 区间和有效抽样数。

第 3.2 节入口直接读取每组 P0/defect 的 `(0,0)` 原始事件一次，保持既有 ROI、total/k1/ms、F/T/B 半开边界和 2 mm bins。F、B DTV 分别在真实边界内分箱，non-T 将两段带深度标签的计数向量拼接后联合归一化。它不进行重采样或区间估计；表 5 与正式 E2-T1 只用于 `1e-12` 全精度及一位小数显示核验。输出先在临时目录完成 schema、闭合、图形和文件合同验收，再原子发布；`--overwrite` 只替换 `section_3_2/`。

旧目标深度补充入口不读取或改写 valid events：T 区绝对响应和 baseline `P(T|class)` 原样提取正式 T2/T3，只有 `P(k1|T)` 与 `P(ms|T)` 以固定 seed `20260814`、5000 次独立 Poisson draws 新增计算。输出固定为三张六行 CSV 和一张含区间的双 panel 300 dpi PNG；它们不计入正式 7 PNG + 8 CSV 合同，也不再用于当前第 3.2 节主展示。正式 E2 原子重跑会原样保留 `supplementary/`。

旧前方来源 supplementary 同样不读取或改写 valid events。它直接保存 baseline/defect × total/k1/ms × F/T/B 的 108 行 fractions，及 F 区 `N0→ND`、`C_F`、`D_TV,F` 的 18 行表；E3 只从正式 M5 retention 写出 `1-eta_M5` 并用 `1-ci_high/low` 变换区间。输出固定为三张 CSV、两张双 panel 300 dpi PNG，且不计入正式 7 PNG + 8 CSV 合同，也不再用于当前第 3.2 节主展示。DTV 点估计和重采样分位区间分别绘制，故不强行要求点位于区间内。
