# 实验后处理

实验代码与结果按 E1–E3 独立分层，统一读取 `results/<campaign>/events/valid/`，不得回退到 `events_clean.csv/slit_id`。

| 目录/入口 | 职责 | 输入 | 正式输出 | 关键参数 | 失败条件 |
|---|---|---|---|---|---|
| `e1/run.py` | E1 detector ROI、total depth response 和分 acquisition-group 的 first/last 空间比较 | 审计通过的 P0 center valid events | 3 PNG + manifest/report/acceptance | `--results-root`、`--overwrite` | 审计、schema、ROI、归一化或输出合同失败 |
| `e1/analyze_roi_sensitivity.py` | 独立的 ROI 敏感性辅助分析 | valid manifest + boundary JSON | `postprocessing/E1/roi_sensitivity/` | `--boundary-config`、`--overwrite` | hash、标签或配对失败 |
| `e2/run.py` | E2 grid/center 表及可选 case/class、函数级自定义 bin width 的响应与 source-region 分解 | P0/P1–P6 center + matched grid valid events | 默认 4 PNG、2 CSV；多 case 动态扩展 | `--case`、`--min-baseline-count`、`--allow-partial-grid`、`--overwrite` | center、case、bin width、grid pair、分母、schema 或输出合同失败 |
| `e3/` | 后续 source-truth imaging utility 接口 | 待冻结 | 无 | 无 | 尚未实现 |
| `_archive/` | 不可执行的旧 schema 源码快照 | 历史 `events_clean/slit_id` | 不得生成正式结果 | 无 | 禁止作为正式入口 |

```bash
conda run -n data python -m scripts.postprocessing.e1.run \
  --results-root results/articlev2 --overwrite

conda run -n data python -m scripts.postprocessing.e2.run \
  --results-root results/articlev2 --case P0:P4:S4:total \
  --allow-partial-grid --overwrite
```

当前 E2 grid 缺少 P0/P1/P3/P5 的 P002 条件，所以上述 E2 命令生成明确标为 `partial` 的 3×4 预览。数据齐备后去掉 `--allow-partial-grid` 执行严格完整验收。
