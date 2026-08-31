# E3 55 mm PMMA 前层参考：远端仿真运行手册

本手册只在远端 Linux 主机生成 slab raw 数据。主分析数据 `articlev3_merged` 不需要复制到远端；清洗、严格 E3 和 Report 补全在 raw 数据带回当前项目后执行。

> 当前状态（2026-08-31）：本批次 81 个 raw pose 已导入当前项目，清洗与严格 E3 六图四表均已完成。本手册继续作为该 campaign 的复现、分片运行和中断恢复记录。

## 1. 冻结批次参数

| 项目 | 值 |
|---|---|
| Campaign | `articlev3_p4_front_slab_55mm_100m` |
| Geometry | `config/geometry/article_files/P4_front_slab_55mm.yaml` |
| 模体 | 1000×1000×55 mm³ 均匀 `G4_PLEXIGLASS`，z=[0,55] mm |
| 能量 | 560 keV mono gamma |
| Profile / matched slit | P001 / S4 |
| 网格 | x/y = −10:2.5:10 mm，9×9，共 81 pose |
| Primary | 100,000,000 / pose |
| Seed | 11000–11080 |
| 并发 | 8 worker × 6 Geant4 threads = 48 logical threads |

所有命令均从仓库根目录执行。正式运行前确认远端仓库包含本 geometry 和生成器，并确认没有同名 campaign 正在运行。

## 2. 构建与生成配置

```bash
cmake --build build -j 24

python3 -m scripts.monte_carlo.generate_front_slab_reference_configs \
  --campaign-id articlev3_p4_front_slab_55mm_100m \
  --n-primary-per-pose 100000000 \
  --threads 6 \
  --base-seed 11000
```

生成器必须汇报 81 个 task、总计 8,100,000,000 primary、seed `11000..11080`，并生成：

```text
config/generated/articlev3_p4_front_slab_55mm_100m/
├── configs/grid/P4_front_slab_55mm_P001/*.yaml
├── manifest.yaml
└── reference_manifest.yaml
```

若配置目录已存在，先确认它属于同一批次。只有确实需要完整重建配置时才在生成命令末尾添加 `--overwrite`；该参数不覆盖 `results/`。

## 3. Dry-run

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_p4_front_slab_55mm_100m/manifest.yaml \
  --binary build/MSS \
  --dry-run
```

首次运行应打印 81 行 `run`。若出现 `skip-complete`，说明同名 raw run 已存在；先确认它确实属于本批次，不要使用 `--rerun-completed` 覆盖。

## 4. 八个并行 worker

打开八个独立终端。每个终端只修改第一行的 `slab_shard`，依次使用 0、1、2、3、4、5、6、7，然后执行同一命令：

```bash
slab_shard=0

python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_p4_front_slab_55mm_100m/manifest.yaml \
  --binary build/MSS \
  --shard-count 8 \
  --shard-index "${slab_shard}" \
  --state-file "results/queues/articlev3_p4_front_slab_55mm_100m/shard_${slab_shard}_state.json" \
  --log-dir "results/queues/articlev3_p4_front_slab_55mm_100m/logs/shard_${slab_shard}" \
  --allow-large-run
```

shard 0 包含 11 个 pose，其余 shard 各包含 10 个 pose。八个 worker 同时运行时共请求 48 个 Geant4 worker threads。

中断后，在对应终端原样重新执行相同命令。必须保持 manifest、`--shard-count`、`--shard-index` 和 state file 不变，也不要添加 `--rerun-completed`。若某个 pose 留下非空但不完整的 run 目录，先根据 state/log 确认精确目录，将该单个目录移到独立隔离位置后再恢复；不要删除其他完整 run。

## 5. 完成检查

八个 worker 都退出成功后，再执行一次第 3 节 dry-run。验收结果必须为 81 行 `skip-complete`、0 行 `run`。

raw 数据应位于：

```text
results/articlev3_p4_front_slab_55mm_100m/events/raw/grid/
└── P4_front_slab_55mm/P001/<81 run directories>/
```

每个 run 必须同时包含非空 `events.csv` 和 `metadata.yaml`，metadata 中应为 100M primary、560 keV、P001、相应 pose、geometry `P4_front_slab_55mm.yaml` 和唯一 seed。

## 6. 打包回传

```bash
tar -czf articlev3_p4_front_slab_55mm_100m.tar.gz \
  results/articlev3_p4_front_slab_55mm_100m/events/raw \
  config/generated/articlev3_p4_front_slab_55mm_100m/manifest.yaml \
  config/generated/articlev3_p4_front_slab_55mm_100m/reference_manifest.yaml

sha256sum articlev3_p4_front_slab_55mm_100m.tar.gz
```

回传压缩包及 SHA-256 后，当前项目中的后续固定流程为 slit 标签冻结、深度清洗、81-pose provenance 审计、严格 E3 六图四表和 Report 重建。本批次已经完成该全流程；远端阶段仍以 raw 数据回传为边界。
