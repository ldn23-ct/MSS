# Article V2 后处理规范

本目录是 E1–E3 分析执行合同的权威入口。理论边界见 source-response framework，实验比较关系见 simulation experiment design；具体数据选择、文件和验收以本目录为准。

| 实验 | 状态 | 正式产物 | 文档 |
|---|---|---|---|
| E1 | 已实现并通过完整验收 | 3 PNG、0 常规表 | [E1.md](E1.md) |
| E2 | 已实现；center 完整、grid 当前为 partial | 默认 4 PNG、2 CSV；显式多 case 时动态扩展 | [E2.md](E2.md) |
| E3 | 后续 source-truth imaging utility，待设计 | 无 | [E3.md](E3.md) |

统一规则：

- 所有事件输入均来自 `results/articlev2/events/valid/`；
- 使用 recorded `slit_label` 并在要求的统计中叠加固定 detector ROI；
- 正式图只输出 PNG，不新增 PDF；
- E2-F2/F3/F4 按显式 case/scatter-class 选择生成，文件名携带选择条件；
- `analysis_manifest.yaml`、`report.md` 和 `acceptance_summary.yaml` 为控制文件，不计入图表数量；
- E2 partial 结果必须显式标记，不得把 missing grid panels 当作零响应或完整论文证据。
