# 实验后处理

实验代码与结果按 E1–E3 独立分层，统一读取 `results/<campaign>/events/valid/`，不得回退到 `events_clean.csv/slit_id`。

| 目录/入口 | 职责 | 输入 | 正式输出 | 关键参数 | 失败条件 |
|---|---|---|---|---|---|
| `e1/run.py` | E1 detector ROI、total depth response 和分 acquisition-group 的 first/last 空间比较 | 审计通过的 P0 center valid events | 3 PNG + manifest/report/acceptance | `--results-root`、`--overwrite` | 审计、schema、ROI、归一化或输出合同失败 |
| `e1/analyze_roi_sensitivity.py` | 独立的 ROI 敏感性辅助分析 | valid manifest + boundary JSON | `postprocessing/E1/roi_sensitivity/` | `--boundary-config`、`--overwrite` | hash、标签或配对失败 |
| `e2/run.py` | E2 grid/center 表及可选 case/class、函数级自定义 bin width 的响应与 source-region 分解 | P0/P1–P6 center 或 grid-zero + matched grid valid events | 默认 3 PNG、3 CSV；多 case 动态扩展 | `--summary-source`、`--case`、`--min-baseline-count`、`--resample-seed`、`--allow-partial-grid`、`--overwrite` | summary、case、bin width、grid pair、分母、schema 或输出合同失败 |
| `e3/run.py` | E3 source-conditioned M0–M5、CNR/retention、深度收益与 front-slab 参考比较 | 完整 matched grid + 独立 55 mm slab grid | 固定 6 PNG + 4 CSV | `--slab-grid-root`、`--resample-seed`、`--overwrite` | 任一缺失/重复位姿、schema、恒等式、点估计分母或输出合同失败 |
| `e3/run_core.py` | 不依赖 slab 的 E3 主网格分析 | 完整 matched grid | 固定 5 PNG + 3 CSV | `--resample-seed`、`--overwrite` | 任一主网格、schema、恒等式、数值或输出合同失败 |
| `_archive/` | 不可执行的旧 schema 源码快照 | 历史 `events_clean/slit_id` | 不得生成正式结果 | 无 | 禁止作为正式入口 |

```bash
conda run -n data python -m scripts.postprocessing.e1.run \
  --results-root results/articlev3_merged --overwrite

conda run -n data python -m scripts.postprocessing.e2.run \
  --results-root results/articlev3_merged --summary-source grid-zero \
  --case P0:P4:S4:total --case P0:P4:S4:k1 --case P0:P4:S4:ms \
  --overwrite

conda run -n data python -m scripts.postprocessing.e3.run_core \
  --results-root results/articlev3_merged --overwrite

conda run -n data python -m scripts.postprocessing.e3.run \
  --results-root results/articlev3_merged \
  --slab-grid-root /path/to/P4_front_slab_55mm_grid \
  --overwrite
```

当前合并层的 matched grid 已完整，E2 严格验收和 E3 core 均可直接完成。尚缺的唯一数据是 P4 55 mm slab 的 81-pose 独立参考；因此完整 `e3/run.py` 仍会在创建 6 图 4 表前报告 slab 缺项并非零退出。
