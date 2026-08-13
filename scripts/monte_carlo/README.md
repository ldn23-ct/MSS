# Monte Carlo 自动化脚本

本目录只负责生成 Geant4 输入配置和调度现有 `MSS` 可执行文件，不修改 Geant4 物理实现，也不执行数据清洗或论文分析。

| 脚本 | 职责 | 输入文件/schema | 输出目录/文件 | 主要参数 | 失败条件 | 示例命令 |
|---|---|---|---|---|---|---|
| `generate_source_response_experiment_configs.py` | 展开 articlev2 center/grid 单 pose 配置及 manifest | `article_base.yaml`、P0–P9 geometry、P001/P002 profile | `config/generated/<campaign>/`；结果路径为 `results/<campaign>/events/raw/` | `--campaign-id`、`--n-primary-per-pose`、`--threads`、`--base-seed`、`--overwrite` | geometry/profile 缺失、参数非法、目标非空且未允许覆盖 | `python -m scripts.monte_carlo.generate_source_response_experiment_configs` |
| `run_experiment_queue.py` | 串行执行 manifest，支持 dry-run、恢复、分片、范围和日志 | `source_response_simulation_campaign` manifest、`build/MSS` | raw event run、queue state/lock/log | `--dry-run`、`--state-file`、`--start-index`、`--end-index`、`--limit`、`--shard-*` | binary/manifest 缺失、live lock、输出不完整、large-run guard | `python -m scripts.monte_carlo.run_experiment_queue --manifest config/generated/articlev2/manifest.yaml --binary build/MSS --dry-run` |

常用命令：

```bash
python -m scripts.monte_carlo.generate_source_response_experiment_configs
python -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev2/manifest.yaml \
  --binary build/MSS \
  --dry-run
```

article v1 的配置生成、batch merge、raw cleanup 和实验编号过滤接口已移除。
