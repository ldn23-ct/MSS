# E2：缺陷可观测响应与 source-region mechanism

| 脚本 | 职责 | 输入 | 输出 | 主要参数 |
|---|---|---|---|---|
| `run.py` | 生成 matched grid、全局 center/grid-zero 长表和可选择 case/class 的 bin-wise F2/F3 | 审计 inventory、P0/P1–P6 center 或 grid-zero、matched grid valid events | 默认 3 PNG、3 CSV；多 case 动态扩展 | `--summary-source`、`--case`、`--min-baseline-count`、`--resample-seed`、`--allow-partial-grid`、`--overwrite` |

严格模式要求 P1-S1 至 P6-S6 的 baseline/defect grid pair 各有完整 81 poses。`results/articlev3_merged` 已满足该条件；本次正式命令为：

```bash
conda run -n data python -m scripts.postprocessing.e2.run \
  --results-root results/articlev3_merged \
  --summary-source grid-zero \
  --case P0:P4:S4:total \
  --case P0:P4:S4:k1 \
  --case P0:P4:S4:ms \
  --overwrite
```

`--summary-source grid-zero` 使整体计数与 F/T/B 表读取各 matched grid 的 `(0,0)` 100M 数据，并以 `zero_pose` 命名 T1/T3；默认 `center` 保持旧行为。partial 模式仅用于其他不完整 campaign 的诊断，不会用 center 数据、零值或插值替代缺失 grid。

`--case BASELINE:DEFECT:SLIT:SCATTER_CLASS` 可重复使用；只生成显式选择，不自动穷举。case 图名包含比较条件和 scatter class，同一比较的 E2-T2 只生成一次。未传 `--case` 时默认 `P0:P4:S4:total`。E2-T1 保存六深度整体响应，E2-T3 同时保存 P0 基线与相应缺陷模体的 F/T/B 占比；E2-5/E2-6 不生成图片。

F2/F3 和 E2-T2 共用 `run_e2(..., depth_bin_width_mm=...)`；默认值来自脚本顶部 `DEFAULT_DEPTH_BIN_WIDTH_MM = 2.0`，不提供额外 CLI。自定义宽度不能整除全范围或 region 时会追加 residual bin；宽度写入 manifest/report，但不改变文件名。核心定量指标固定使用 5000 次 Poisson 重采样，`--resample-seed` 默认 `20260814`，CSV 保存 95% 区间和有效抽样数。
