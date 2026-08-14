# E2：缺陷可观测响应与 source-region mechanism

| 脚本 | 职责 | 输入 | 输出 | 主要参数 |
|---|---|---|---|---|
| `run.py` | 生成 matched grid、全局 center 表和可选择 case/class 的 bin-wise F2/F3/F4 | 审计 inventory、P0/P1–P6 center、matched grid valid events | 默认 4 PNG、2 CSV；多 case 动态扩展 | `--case`、`--min-baseline-count`、`--allow-partial-grid`、`--overwrite` |

严格模式要求 P1-S1 至 P6-S6 的 baseline/defect grid pair 各有完整 81 poses。当前只有 P2-S2、P4-S4、P6-S6 可用，因此预览命令为：

```bash
conda run -n data python -m scripts.postprocessing.e2.run \
  --results-root results/articlev2 \
  --case P0:P4:S4:total \
  --allow-partial-grid \
  --overwrite
```

partial 模式仍生成最终 3×4 E2-F1 布局；缺失 panels 显示 unavailable，`acceptance_summary.yaml` 为 `partial`。它不会用 center 数据、零值或插值替代缺失 grid。

`--case BASELINE:DEFECT:SLIT:SCATTER_CLASS` 可重复使用；只生成显式选择，不自动穷举。case 图名包含比较条件和 scatter class，同一比较的 E2-T2 只生成一次。未传 `--case` 时默认 `P0:P4:S4:total`。

F2/F3/F4 和 E2-T2 共用 `run_e2(..., depth_bin_width_mm=...)`；默认值来自脚本顶部 `DEFAULT_DEPTH_BIN_WIDTH_MM = 2.0`，不提供额外 CLI。自定义宽度不能整除全范围或 region 时会追加 residual bin；宽度写入 manifest/report，但不改变文件名。
