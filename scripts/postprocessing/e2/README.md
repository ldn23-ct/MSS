# E2：缺陷深度–slit 通道匹配（待实现）

本目录仅保留接口位置，当前没有可执行脚本。未来实现必须读取 `events/valid/**/events_valid.csv` 和审计 inventory，使用既有 `slit_label`，输出到 `postprocessing/E2/{figures,tables}`，并生成 manifest、report 与 acceptance summary。

| 脚本 | 职责 | 输入文件/schema | 输出目录/文件 | 主要参数 | 失败条件 | 示例命令 |
|---|---|---|---|---|---|---|
| 暂无 | 预留 E2 实现位置 | 未来为 P0/P1–P6 valid events + inventory + `slit_label` | `postprocessing/E2/{figures,tables}`、manifest、report、acceptance | 待定义 | 接口和统计合同尚未实现 | 无 |

预期目标是比较 P1–P6 相对 P0 的 total/k1/MS 深度×通道响应；具体统计合同以 `docs/articlev2_analysis/E2.md` 为准。
