# P1/P2/P3/P5/P6 前层 slab：远端 grid 仿真运行手册

本批次只生成独立 raw 仿真数据。所有命令从仓库根目录执行；构建、生成配置和启动 worker 分开进行。

## 1. 冻结参数与环境

| 模体 | Geometry | Profile / matched slit | Seed |
|---|---|---|---|
| P1 | `P1_front_slab_10mm.yaml` | P002 / S1 | 12000–12080 |
| P2 | `P2_front_slab_25mm.yaml` | P001 / S2 | 12081–12161 |
| P3 | `P3_front_slab_40mm.yaml` | P002 / S3 | 12162–12242 |
| P5 | `P5_front_slab_70mm.yaml` | P002 / S5 | 12243–12323 |
| P6 | `P6_front_slab_85mm.yaml` | P001 / S6 | 12324–12404 |

五份 geometry 位于 `config/geometry/article_files/`，均为 1000×1000 mm 横向尺寸的均匀 `G4_PLEXIGLASS`，z 从 0 延伸至对应缺陷前缘，只有一个根组件，无缺陷或 insert。

共同参数：

- 560 keV mono gamma；x/y = −10:2.5:10 mm；每组 9×9 = 81 pose。
- 每 pose 100,000,000 primary；每组 8,100,000,000，五组共 40,500,000,000。
- 每组一个独立 worker，每个 MSS 进程使用 7 个 Geant4 线程，五组同时运行请求 35 个计算线程。Geant4 主线程和队列进程另有少量开销。
- 基准为 `config/base/front_slab_grid_base.yaml`：源位置 [0,0,−20] mm，准直器 y 长度 1300 mm，保持已有 P4 slab 的探测器和物理设置。P002 的探测器 x 范围为 [11,101] mm，P001 为 [20,127] mm。
- 远端应已安装支持多线程的 Geant4（含当前 CMake 要求的 UI/vis 组件）、yaml-cpp、CMake、C++17 编译器，以及 Python 3/PyYAML；当前 shell 已配置 Geant4 环境和物理数据集。

`git pull` 同步 geometry、独立基准、脚本及本手册；`build/`、`config/generated/` 和仿真结果在远端本地生成，不通过 Git 同步。

## 2. 同步与单独构建

本次代码提交并推送到远端分支后执行：

```bash
git pull
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j 24
```

构建使用 24 个并行编译任务；仿真线程数来自后续生成的 YAML，两者独立。

## 3. 一次生成五组配置

```bash
python3 -m scripts.monte_carlo.generate_front_slab_grid_campaigns
```

应汇报五个 campaign，每组 81 tasks、7 threads，以及表中的独立 seed 范围；总计 405 tasks、40,500,000,000 primary。此命令不启动 MSS。

每组目录为：

```text
config/generated/articlev3_p<编号>_front_slab_<厚度>mm_100m/
├── configs/grid/<model>_<profile>/<81 pose YAML>
├── manifest.yaml
└── reference_manifest.yaml
```

生成器在开始写入前检查全部五组几何和目标目录。非空目标目录会拒绝覆盖；恢复仿真时直接复用已有配置。需要完整重建配置时，先确认五组队列均已停止，再显式使用：

```bash
python3 -m scripts.monte_carlo.generate_front_slab_grid_campaigns --overwrite
```

`--overwrite` 只替换 generated 配置，不改写结果。正常恢复不需要这个参数。

## 4. 五组 dry-run

依次复制执行：

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_p1_front_slab_10mm_100m/manifest.yaml \
  --binary build/MSS \
  --dry-run
```

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_p2_front_slab_25mm_100m/manifest.yaml \
  --binary build/MSS \
  --dry-run
```

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_p3_front_slab_40mm_100m/manifest.yaml \
  --binary build/MSS \
  --dry-run
```

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_p5_front_slab_70mm_100m/manifest.yaml \
  --binary build/MSS \
  --dry-run
```

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_p6_front_slab_85mm_100m/manifest.yaml \
  --binary build/MSS \
  --dry-run
```

首次运行每条命令应打印 81 行 `run`；已有完整结果会打印 `skip-complete`。dry-run 不启动 MSS，不创建 state、lock 或日志。

## 5. 五个终端同时启动

在五个独立终端分别复制以下命令。每个 worker 只执行自己的 81 个单 pose 配置，一个 pose 完成后再执行下一个；无需分片或切换 campaign。

### 终端 1：P1，10 mm，P002/S1

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_p1_front_slab_10mm_100m/manifest.yaml \
  --binary build/MSS \
  --state-file results/queues/articlev3_p1_front_slab_10mm_100m/state.json \
  --log-dir results/queues/articlev3_p1_front_slab_10mm_100m/logs \
  --allow-large-run
```

### 终端 2：P2，25 mm，P001/S2

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_p2_front_slab_25mm_100m/manifest.yaml \
  --binary build/MSS \
  --state-file results/queues/articlev3_p2_front_slab_25mm_100m/state.json \
  --log-dir results/queues/articlev3_p2_front_slab_25mm_100m/logs \
  --allow-large-run
```

### 终端 3：P3，40 mm，P002/S3

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_p3_front_slab_40mm_100m/manifest.yaml \
  --binary build/MSS \
  --state-file results/queues/articlev3_p3_front_slab_40mm_100m/state.json \
  --log-dir results/queues/articlev3_p3_front_slab_40mm_100m/logs \
  --allow-large-run
```

### 终端 4：P5，70 mm，P002/S5

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_p5_front_slab_70mm_100m/manifest.yaml \
  --binary build/MSS \
  --state-file results/queues/articlev3_p5_front_slab_70mm_100m/state.json \
  --log-dir results/queues/articlev3_p5_front_slab_70mm_100m/logs \
  --allow-large-run
```

### 终端 5：P6，85 mm，P001/S6

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_p6_front_slab_85mm_100m/manifest.yaml \
  --binary build/MSS \
  --state-file results/queues/articlev3_p6_front_slab_85mm_100m/state.json \
  --log-dir results/queues/articlev3_p6_front_slab_85mm_100m/logs \
  --allow-large-run
```

终端显示队列的 run/done/skip 进度，单 pose 的 MSS stdout/stderr 写入各自日志目录；对应 state 记录精确的 `expected_run_dir` 和 `log_path`。五组结果位于：

```text
results/articlev3_p1_front_slab_10mm_100m/events/raw/grid/P1_front_slab_10mm/P002/
results/articlev3_p2_front_slab_25mm_100m/events/raw/grid/P2_front_slab_25mm/P001/
results/articlev3_p3_front_slab_40mm_100m/events/raw/grid/P3_front_slab_40mm/P002/
results/articlev3_p5_front_slab_70mm_100m/events/raw/grid/P5_front_slab_70mm/P002/
results/articlev3_p6_front_slab_85mm_100m/events/raw/grid/P6_front_slab_85mm/P001/
```

## 6. 中断恢复与完成验收

哪个 worker 中断，就在该终端原样重新执行对应命令，保持 manifest 和 state file 相同。完整 pose 会跳过；恢复粒度为整 pose，不能续接部分 histories。

若失败的 pose 留下非空但不完整的 run 目录，配置的 `existing_run_policy: fail` 会拒绝覆盖。先根据该 worker 的 state/log 确认精确目录，将这个 run 移到独立隔离目录，再复用原命令；不要移动其他完整 pose。活动队列锁会拒绝重复启动相同 worker，正常中断后的失效锁由队列检查处理。

五个 worker 全部成功后，重新执行第 4 节的五条 dry-run 命令。每条必须为 81 行 `skip-complete`、0 行 `run`；合计 405 个完整 pose。

各 run 应包含 `events.csv` 和 `metadata.yaml`，metadata 对应 100M primary、560 keV、正确的 slab model/profile/pose/seed，并记录 7 threads。回传 raw 数据时同时保留每组 generated 目录下的 `manifest.yaml`、`reference_manifest.yaml`，供后续来源核验。本批次不执行清洗或论文后处理。

