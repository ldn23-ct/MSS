# Article V2 后处理规范

本目录是 E1–E3 分析执行合同的权威入口。理论边界见 source-response framework，实验比较关系见 simulation experiment design；具体数据选择、文件和验收以本目录为准。

| 实验 | 状态 | 正式产物 | 文档 |
|---|---|---|---|
| E1 | 已实现并通过完整验收 | 3 PNG、0 常规表 | [E1.md](E1.md) |
| E2 | 合并 grid 完整并通过严格验收 | 本次正式结果为 7 PNG、3 CSV | [E2.md](E2.md) |
| E3 | 主网格与严格 slab 比较均通过完整验收 | 6 PNG、4 CSV | [E3.md](E3.md) |

55 mm PMMA 前层参考的冻结 geometry、100M/pose 批次参数和远端 8×6 并发命令见 [E3_slab_remote_run.md](E3_slab_remote_run.md)。81 个 raw run 已导入、清洗并通过严格 E3 预检，Report 已纳入 E3-F6/E3-T4 实测结果。

统一规则：

- 当前正式结果统一来自 `results/articlev3_merged/events/valid/`；三个原始 campaign 保持不变；
- 使用 recorded `slit_label` 并在要求的统计中叠加固定 detector ROI；
- 正式图只输出 PNG，不新增 PDF；
- E2-F2/F3 按显式 case/scatter-class 选择生成，文件名携带选择条件；E2-5/E2-6 只输出定量表；
- `analysis_manifest.yaml`、`report.md` 和 `acceptance_summary.yaml` 为控制文件，不计入图表数量；
- E2 单位姿表正式使用合并 grid `(0,0)`；旧 `center` 选择仅为向后兼容；
- E2/E3 的核心定量指标采用 5000 次 Poisson 重采样，报告 95% 区间和有效抽样数；
- E3 正式结果要求 P0/P1–P6 matched grid 与独立 P4 55 mm slab 各自 81 位姿全部通过预检，固定发布 6 PNG、4 CSV；`run_core.py` 只保留为无 slab 数据时的 5 PNG、3 CSV 兼容入口。
