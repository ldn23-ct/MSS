# 实验后处理

实验代码与结果按 E1–E3 独立分层，统一读取 `results/<campaign>/events/valid/`，不得回退到 `events_clean.csv/slit_id`。

| 目录/入口 | 职责 | 输入文件/schema | 输出目录/文件 | 主要参数 | 失败条件 | 示例命令 |
|---|---|---|---|---|---|---|
| `e1/run.py` | 正式 E1 深度响应分析 | 审计通过的 P0 center valid events | `postprocessing/E1/` | `--results-root`、`--audit-dir`、`--output-dir`、`--overwrite` | 审计、schema、标签、ROI 或输出合同失败 | `python -m scripts.postprocessing.e1.run --results-root results/articlev2` |
| `e1/analyze_roi_sensitivity.py` | E1 detector ROI 敏感性分析 | valid events manifest + boundary JSON | `postprocessing/E1/roi_sensitivity/` | `--results-root`、`--boundary-config`、`--output-dir`、`--overwrite` | hash、标签或输入配对失败 | `python -m scripts.postprocessing.e1.analyze_roi_sensitivity --results-root results/articlev2` |
| `e2/` | 预留，暂无可执行入口 | 未来使用 P0/P1–P6 valid events | `postprocessing/E2/` | 待定义 | 尚未实现 | 无 |
| `e3/` | 预留，暂无可执行入口 | 未来使用匹配通道 valid events | `postprocessing/E3/` | 待定义 | 尚未实现 | 无 |
| `_archive/` | 不可执行的旧 schema 源码快照 | 历史 `events_clean/slit_id` | 不得生成正式结果 | 无受支持参数 | 禁止作为正式入口 | 无 |

E2/E3 实现前必须先定义基于 `slit_label` 的输入合同、验收指标和输出 manifest。
