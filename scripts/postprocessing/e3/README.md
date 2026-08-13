# E3：缺陷诱导 source-response redistribution（待实现）

本目录仅保留接口位置，当前没有可执行脚本。未来实现必须读取 `events/valid/**/events_valid.csv` 和审计 inventory，使用匹配通道及左闭右开的 first-scatter source region，输出到 `postprocessing/E3/{figures,tables}`，并生成 manifest、report 与 acceptance summary。

| 脚本 | 职责 | 输入文件/schema | 输出目录/文件 | 主要参数 | 失败条件 | 示例命令 |
|---|---|---|---|---|---|---|
| 暂无 | 预留 E3 实现位置 | 未来为匹配通道 valid events + inventory + `slit_label` | `postprocessing/E3/{figures,tables}`、manifest、report、acceptance | 待定义 | 接口和统计合同尚未实现 | 无 |

不得直接启用 `_archive/` 中依赖 `events_clean/slit_id` 的历史实现。
