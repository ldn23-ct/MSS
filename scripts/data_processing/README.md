# 基础数据清洗与筛选

本目录建立 articlev2 的权威有效事件层。标准顺序是：必要时校准 slit 边界 → 清洗并冻结标签 → 数据资格审计。

| 脚本 | 职责 | 输入文件/schema | 输出目录/文件 | 主要参数 | 失败条件 | 示例命令 |
|---|---|---|---|---|---|---|
| `common.py` | metadata、profile/slit、acceptance ROI 与路径共享契约 | run-level `metadata.yaml` | Python 数据结构 | 无 CLI | metadata/schema/数值非法 | `from scripts.data_processing.common import load_run_metadata` |
| `experiment_contract.py` | 冻结 P0–P9、E1–E6 数据资格条件 | 无文件输入 | 审计与 E1 使用的常量 | 无 CLI | 合同自检失败 | `from scripts.data_processing.experiment_contract import EXPERIMENT_REQUIREMENTS` |
| `slit_channels.py` | 三峰/谷边界估计、稳定性检查和标签分配 | raw detector 坐标、metadata | 边界估计对象、`slit_label` | 无独立 CLI | 峰谷数量、稳定性或 profile 非法 | `from scripts.data_processing.slit_channels import slit_label_for_x` |
| `estimate_slit_boundaries.py` | 独立校准 P001/P002 零位姿边界 | `events/raw/center/P0/{P001,P002}` | `data_processing/slit_channels/` 下 JSON、CSV、PNG | `--results-root`、`--output-dir`、`--overwrite` | baseline 不唯一或边界校验失败 | `python -m scripts.data_processing.estimate_slit_boundaries --results-root results/articlev2` |
| `clean_events.py` | 过滤无效深度、删除 legacy 字段、追加 `slit_group/slit_label` | raw `events.csv` + metadata + boundary JSON | `events/valid/` 下 CSV、summary、manifest | `--results-root`、`--input-root`、`--output-root`、`--overwrite` | raw schema、边界、metadata 或覆盖策略非法 | `python -m scripts.data_processing.clean_events --results-root results/articlev2` |
| `audit_experiment_data.py` | 校验配对、行守恒、标签、seed、条件完整性和 boundary hash | raw/valid events、metadata、boundary、生成 manifest | `data_processing/audit/` 下 YAML、CSV、Markdown | `--results-root`、`--output-dir`、`--generated-manifest`、`--overwrite` | 必需条件缺失或数据合同错误 | `python -m scripts.data_processing.audit_experiment_data --results-root results/articlev2` |

```bash
python -m scripts.data_processing.clean_events --results-root results/articlev2
python -m scripts.data_processing.audit_experiment_data \
  --results-root results/articlev2 \
  --overwrite
```

所有会替换完整输出层的命令默认拒绝覆盖；确认重建时显式传 `--overwrite`。
