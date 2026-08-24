# Article V2 后处理规范

本目录是 E1–E3 分析执行合同的权威入口。理论边界见 source-response framework，实验比较关系见 simulation experiment design；具体数据选择、文件和验收以本目录为准。

| 实验 | 状态 | 正式产物 | 文档 |
|---|---|---|---|
| E1 | 已实现并通过完整验收 | 3 PNG、0 常规表 | [E1.md](E1.md) |
| E2 | 合并 grid 完整并通过严格验收 | 本次正式结果为 7 PNG、3 CSV | [E2.md](E2.md) |
| E3 | 主网格 core 已完成；严格 slab 比较待数据 | core 为 5 PNG、3 CSV；完整入口目标为 6 PNG、4 CSV | [E3.md](E3.md) |

55 mm PMMA 前层参考的冻结 geometry、100M/pose 批次参数和远端 8×6 并发命令见 [E3_slab_remote_run.md](E3_slab_remote_run.md)。在 81 个 raw run 导回前，Report 和 E3 完成状态保持不变。

统一规则：

- 当前正式结果统一来自 `results/articlev3_merged/events/valid/`；三个原始 campaign 保持不变；
- 使用 recorded `slit_label` 并在要求的统计中叠加固定 detector ROI；
- 正式图只输出 PNG，不新增 PDF；
- E2-F2/F3 按显式 case/scatter-class 选择生成，文件名携带选择条件；E2-5/E2-6 只输出定量表；
- `analysis_manifest.yaml`、`report.md` 和 `acceptance_summary.yaml` 为控制文件，不计入图表数量；
- E2 单位姿表正式使用合并 grid `(0,0)`；旧 `center` 选择仅为向后兼容；
- E2/E3 的核心定量指标采用 5000 次 Poisson 重采样，报告 95% 区间和有效抽样数；
- E3 core 要求 P0/P1–P6 matched grid 全部通过预检并固定发布 5 PNG、3 CSV；完整严格入口仍要求额外的 P4 55 mm slab 81 位姿，届时发布 6 PNG、4 CSV。
