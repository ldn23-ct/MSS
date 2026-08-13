# 旧 schema 后处理源码快照

本目录保存整改前尚未迁移的 v2 scatter count、scatter histogram、grid response 和 E2–E6 单体分析代码，仅用于查阅算法思路。

| 源码快照 | 历史职责 | 输入文件/schema | 允许输出 | 主要参数 | 失败条件 | 示例命令 |
|---|---|---|---|---|---|---|
| `analysis_pipeline.py`、`run_analysis.py` | 旧 E2–E6 单体分析 | 历史 `events_clean.csv/slit_id` | 无正式输出 | 不受支持 | schema 已废弃 | 禁止执行 |
| `summarize_scatter_counts.py` | 旧 scatter count | 历史 raw/clean events | 无正式输出 | 不受支持 | schema 已废弃 | 禁止执行 |
| `plot_scatter_position_histogram.py` | 旧位置 histogram | 历史 scatter summary | 无正式输出 | 不受支持 | schema 已废弃 | 禁止执行 |
| `plot_grid_response.py` | 旧 grid response | 历史 grid summary | 无正式输出 | 不受支持 | schema 已废弃 | 禁止执行 |

本目录不属于 Python package，不维护回归测试，也不得生成或覆盖正式 E1–E3 结果。新实现应在对应 `e2/`、`e3/` 包中基于 `slit_label` 重写。
