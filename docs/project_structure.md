# MSS 项目 v2 归档与交接导航

> 文档状态：项目级长期入口，当前用于项目 v2 归档与后续版本交接。
> 职责：说明 v2 已完成内容、归档文档、代码与配置文件职责，以及后续工作必须保持的兼容边界。
> 归档基线：`docs/archive/v2/`。
> 后续版本：尚未开始，版本号未定义。

## 1. 版本定位与阅读顺序

项目中的“版本”和实验名称必须分开理解。本文件只确认已经完成并归档的项目版本，不使用尚未正式启动的实验草案定义当前项目状态。

| 路径 | 定位 | 使用规则 |
|---|---|---|
| `docs/archive/v1/` | 第一轮历史资料 | 仅用于了解旧 PMMA、macro 和旧 CSV 实现，不作为当前代码依据。 |
| `docs/archive/v2/` | 项目 v2 正式归档基线 | 记录已完成 Geant4 核心及冻结 article v1 的规格、决策、架构、实施和验收。 |
| `docs/project_structure.md` | 跨版本导航与 v2 交接摘要 | 新任务和新接手人员的第一阅读入口。 |
| 根级其他预研文档及配套资产 | 未启动草案 | 不属于 v2，不代表已经实现、验证或进入当前主线，本文件不展开其方案内容。 |

建议阅读顺序：

1. 先读本文件，确认任务属于 v2 维护还是未来新版本。
2. 维护 Geant4 核心时，依次阅读 `archive/v2/spec.md`、`decisions.md`、`architecture.md`。
3. 复现 article v1 时，阅读 `archive/v2/article_design.md` 和 `article_experiment_automation.md`。
4. 需要核对实现过程或验收范围时，再读 `milestones.md` 和 `acceptance_checklist.md`。
5. 未来新版本必须先建立新的正式需求和设计文档，不得直接把预研草案或 v1 历史规则写回 v2 核心。

## 2. 项目 v2 总结

### 2.1 目标与总体链路

项目 v2 建立了以下稳定的数据生成基础：

```text
入口 YAML
   │
   ├── VehicleROI-compatible geometry YAML
   ├── collimator profile CSV
   └── source spectrum CSV（可选）
   │
   ▼
MSS / Geant4
   │
   ├── 每个 pose 独立 run 和 seed
   ├── events.csv 或 events_debug.csv
   └── metadata.yaml
   │
   ▼
显式 Python 实验队列、合并和 article v1 后处理
```

Geant4 核心只负责事件级 Monte Carlo 数据。位姿级统计、扫描级统计、batch 合并、图表和报告不由 `MSS` 自动生成。

### 2.2 已完成的 Geant4 核心能力

- 使用 YAML 作为 batch 主入口，支持 `--config` 和兼容的位置参数形式。
- World 中固定 VehicleROI-compatible 几何，通过移动 source、collimator 和虚拟探测器组成的成像头实现扫描。
- Pose 支持 list/grid，遵守“一次 run = 一个 pose + 一个实际 seed + 一组模型条件 + n_primary”。
- 支持有限焦点斜入射 gamma、mono/spectrum 能量和每 event 一个 primary gamma。
- 使用外部 CSV 定义可变 jaw 数量的凸多边形狭缝准直器，不默认构建镜像准直器。
- 使用单个理想虚拟探测平面，不模拟真实探测器材料响应或能量沉积 scoring。
- 对每条 gamma track 独立记录 Compton/Rayleigh scatter history、first/last scatter 和 detector crossing。
- Formal 输出语义为 `1 row = 1 detected gamma hit`；debug 输出语义为 `1 row = 1 gamma track summary`。
- 支持多线程临时 CSV、master 合并、run-level metadata、输出目录保护和几何可视化。

### 2.3 已完成并冻结的 article v1

Article v1 是 v2 内已经形成闭环的实验链路，当前只用于复现和兼容性维护：

- 生成 E0/E1/E3/E4 等 article campaign 的逐任务 YAML 和 manifest。
- 使用共享队列串行运行、检测完成状态、保存状态、分片和恢复。
- 对 article manifest 执行 batch 事件合并并建立 `by_condition/`。
- 将原始 detector hit 按固定 `det_x` 区间清洗并分配 S1/S2/S3。
- 汇总 total/k1/ms 散射计数。
- 生成 first/last scatter 条件级位置 histogram。
- 生成 grid response、控制模体差异矩阵和预览图。

### 2.4 v2 明确未完成的内容

- 真实探测器材料响应和能量沉积 scoring。
- Pose-level/scan-level summary 作为 Geant4 自动输出。
- 连续运动、运动模糊、成像头旋转或 z 向扫描。
- 图像重建、完整车辆 CAD 和论文指标自动闭环。
- 任何属于下一版本的新实验设计、配置矩阵或正式分析链路。

## 3. 仓库分层与职责

| 层次 | 路径 | 职责 |
|---|---|---|
| 构建与入口 | `CMakeLists.txt`, `main.cc` | 构建 `MSS`，读取配置并进入 batch 或可视化控制流程。 |
| Geant4 核心 | `include/`, `src/` | 配置、几何、source、tracking、输出和 run 生命周期。 |
| 手工维护配置 | `config/base/`, `config/geometry/`, `config/collimator/`, `config/source/` | 提供基础运行和实验输入。 |
| 生成配置 | `config/generated/` | 由实验生成器产生，不作为手工规格源，通常不提交。 |
| 实验自动化 | `scripts/` | Article v1 配置生成和共享队列。 |
| Article v1 后处理 | `scripts/article/` | 清洗、计数、位置 histogram 和 grid response。 |
| 测试 | `tests/` | 核心实验契约、队列和 article v1 Python 回归。 |
| 运行产物 | `results/` | 原始 run、合并数据、队列状态、日志和分析输出，不属于源码。 |
| 文档 | `docs/` | 跨版本导航、历史归档和未启动预研草案。 |

## 4. 根级关键文件

| 文件 | 含义与功能 |
|---|---|
| `CMakeLists.txt` | 定义 `MSS` C++17 可执行文件、Geant4/yaml-cpp 依赖和 CTest 注册。CMake source 列表也是判断当前实际编译模块的直接依据。 |
| `main.cc` | 程序入口；解析 `--config`/位置参数和 `--ui`，读取配置与几何，并交给 batch pose controller 或 visualization controller。 |
| `README.md` | 面向使用者的构建、基础运行和项目导航入口。 |
| `AGENTS.md` | 面向 Codex 的修改规则、文档优先级和 v2 兼容约束。 |
| `.gitignore` | 排除 build、generated config、results、Python cache 和图表等生成产物。 |
| `.env.example` | 环境变量示例，不保存本地密钥或机器专属值。 |

## 5. C++ 模块导航

除单独注明外，下表中的模块由同名 `include/*.hh` 与 `src/*.cc` 组成。

### 5.1 配置、位姿与标识

| 模块 | 职责 |
|---|---|
| `SimulationConfig` | 保存 run、vehicle、pose、source、collimator、detector、physics、output 和 world 配置。 |
| `SimulationConfigReader` | 读取并验证入口 YAML，解析相对路径和必需字段。 |
| `SimulationMessenger` | 保留必要的 Geant4 UI/配置入口兼容能力，不是主配置系统。 |
| `VehicleROIConfig` | 定义 VehicleROI-compatible YAML 的 AABB、box component、material 和 region 数据结构。 |
| `VehicleROIConfigReader` | 读取并验证车辆或模体 geometry YAML。 |
| `ScanPoseManager` | 将 list/grid 原始配置展开为有序 pose，并生成 pose ID、offset 和实际 seed。 |
| `RunIdBuilder` | 根据 pose、collimator、model、energy 和 seed 生成可追踪 run ID。 |

### 5.2 几何与材料

| 模块 | 职责 |
|---|---|
| `DetectorConstruction` | 构建 World，协调 VehicleROI、成像头、region registry 和 World 边界检查。 |
| `VehicleROIConstruction` | 按 geometry YAML 构建车辆 ROI、PMMA/分层模体及可替换 target component。 |
| `ImagingHeadConstruction` | 将 source 参考位置、slit collimator 和 detector plane 作为同一成像头按 pose 平移。 |
| `SlitCollimatorProfileReader` | 读取并严格验证外部 profile CSV、jaw 编号和凸多边形顶点。 |
| `SlitCollimatorBuilder` | 使用 `G4ExtrudedSolid` 构建当前 profile 的 tungsten jaw。 |
| `VirtualDetectorPlane` | 保存零位姿和实际 detector bounds，并构建理想虚拟探测平面。 |
| `MaterialManager` | 解析 Geant4 内置材料和 geometry YAML 中使用的自定义材料。 |
| `RegionRegistry` | 建立 physical volume 到稳定 region ID 的注册关系。 |
| `RegionResolver` | 在 tracking 时从 volume 解析 region ID。 |

### 5.3 Source 与 physics

| 模块 | 职责 |
|---|---|
| `SpectrumSampler` | 读取 `energy_keV,weight` CSV，验证并构建能量采样 CDF。 |
| `SourceModel` | 计算当前 pose 的有限焦点 primary 位置、方向和能量。 |
| `PrimaryGeneratorAction` | 每个 event 产生一个 primary gamma。 |
| `PhysicsList` | 注册项目 v2 使用的 Geant4 EM physics 和 production cut。 |

### 5.4 事件追踪与输出

| 模块 | 职责 |
|---|---|
| `EventRecord.hh` | 定义 scatter summary、detector hit、gamma track summary 和 event record 数据结构。 |
| `EventAction` | 在 event 内维护 per-gamma-track 状态、hit 顺序，并在 event end 交给 writer。 |
| `SteppingAction` | 识别 `compt`/`Rayl`、记录 first/last scatter，并判断第一次有效 detector crossing。 |
| `CsvWriter` | 写 formal/debug CSV，管理 thread-local 文件和 master merge。 |
| `MetadataWriter` | 输出 run-level `metadata.yaml`，保存配置、geometry、pose、seed 和 provenance。 |
| `RunAction` | 管理单个 run 的输出目录、writer 生命周期、线程文件和 run-end merge。 |

### 5.5 执行与可视化

| 模块 | 职责 |
|---|---|
| `ActionInitialization` | 为 master/worker 注册 primary、run、event 和 stepping actions。 |
| `PoseRunController` | 按 pose 顺序创建并执行独立 Geant4 run。 |
| `VisualizationController` | 在 `--ui` 模式构建第一个 pose，执行 `macros/vis.mac`，且不写正式结果。 |

### 5.6 Legacy-isolated 文件

`include/CollimatorBuilder.hh`、`src/CollimatorBuilder.cc`、`include/CollimatorProfileReader.hh` 和 `src/CollimatorProfileReader.cc` 是早期隔离占位实现，未列入当前 CMake target。项目 v2 的正式路径是 `SlitCollimatorBuilder` 和 `SlitCollimatorProfileReader`，后续不得误用旧类。

## 6. 配置与数据文件导航

| 路径或文件 | 含义与功能 |
|---|---|
| `config/base/simulation_config_v2.yaml` | 车辆 ROI 核心的可运行入口样例，展示多 pose、source、collimator、detector 和输出配置。 |
| `config/base/article_base.yaml` | Article 实验生成器使用的基础 YAML；具体物理条件由生成器覆盖，归档行为以 article v1 automation 文档为准。 |
| `config/geometry/vehicle_roi_v04.yaml` | 车辆侧向 ROI 几何、材料、region 和可替换 target component。 |
| `config/geometry/pmma_box.yaml` | 使用同一 VehicleROI-compatible schema 的均匀 PMMA control geometry。 |
| `config/geometry/phantom_yaml_files/` | Article v1 使用的 P0–P3/P5 PMMA 缺陷模体和 M0–M3 简化金属层模体。 |
| `config/collimator/collimator_profiles.csv` | 早期/对照准直器 profile 数据。 |
| `config/collimator/collimator_profiles1.csv` | `simulation_config_v2.yaml` 当前样例使用的车辆 ROI profile。 |
| `config/collimator/article_collimator_profiles.csv` | Article v1 三通道实验使用的 profile。 |
| `config/source/spectrum.csv` | Spectrum energy mode 的示例能谱。 |
| `config/generated/` | 生成器输出的 manifest 和逐 case YAML；可重新生成，不是正式规格。 |
| `results/` | 仿真、合并、队列和分析产物；不得作为源码或配置基线。 |

工作区中可能存在为未来研究准备的额外 geometry、profile 或 generated config。除非未来正式文档明确纳入，它们不属于项目 v2 交付物。

## 7. Python 脚本导航

### 7.1 V2 共享基础设施与 article v1

| 脚本 | 职责 |
|---|---|
| `scripts/generate_article_experiment_configs.py` | 从 `article_base.yaml` 和 v1 phantom 展开 article v1 campaign、batch、seed、pose 和 manifest。 |
| `scripts/run_experiment_queue.py` | 按 manifest 串行执行 `MSS --config`，检测完成状态、保存 state/lock/log、支持过滤和分片，并对 article v1 执行 batch merge。 |

共享队列的最小 manifest 契约为：

```yaml
cases:
  - config_file: path/to/config.yaml
```

只有 manifest 顶层为 `experiment: article_simulation_campaign` 时，队列才执行 article v1 batch 合并。

### 7.2 Article v1 后处理

| 脚本 | 职责 |
|---|---|
| `scripts/article/clean_events.py` | 递归读取 `events.csv`，按固定 detector-x 区间分配 S1/S2/S3 并写 `events_clean.csv`。 |
| `scripts/article/summarize_scatter_counts.py` | 对 cleaned events 汇总 S1/S2/S3/ALL 的 total、k1 和 ms。 |
| `scripts/article/plot_scatter_position_histogram.py` | 按物理条件汇总 first/last scatter 在 x/y/z 的位置 histogram。 |
| `scripts/article/plot_grid_response.py` | 生成 article v1 grid response、control delta、可选 first-scatter 深度筛选和预览图。 |

## 8. 测试与宏文件导航

| 文件 | 覆盖内容 |
|---|---|
| `tests/test_core_experiment_contract.py` | `abnormal_material`、自定义材料、run ID 和输出覆盖策略等共享 C++ 契约。 |
| `tests/test_experiment_queue.py` | 队列执行、恢复、分片、完成检测、v1 state 兼容和 article batch merge。 |
| `tests/test_article_experiment_configs.py` | Article v1 配置矩阵、batch、seed 和 manifest。 |
| `tests/test_article_clean_events.py` | Detector channel 清洗和输入验证。 |
| `tests/test_article_scatter_counts.py` | Total/k1/ms 计数语义。 |
| `tests/test_article_scatter_position_histogram.py` | 条件级 scatter 位置分箱、provenance 和输出。 |
| `tests/test_article_grid_response.py` | Grid response、control delta 和深度筛选。 |
| `macros/vis.mac` | 当前 `--ui` 可视化命令。 |
| `macros/run.mac`, `macros/run_mt.mac` | 第一轮 legacy macro 参考，不是 v2 batch 主入口。 |

未启动预研资产可能带有独立测试，但这些测试的存在不表示相应功能已经进入 v2 或下一版本正式范围。

## 9. V2 归档文档地图

| 文档 | 职责 | 归档状态 |
|---|---|---|
| `docs/archive/v2/change.md` | 解释 v1 到 v2 的车辆 ROI 重构背景。 | 历史背景基线 |
| `docs/archive/v2/spec.md` | 定义 v2 配置、几何、事件追踪、CSV 和 metadata 的最高优先级契约。 | 稳定规格基线 |
| `docs/archive/v2/decisions.md` | 固化 v2 已接受、取代或推迟的设计决策。 | 稳定决策基线 |
| `docs/archive/v2/architecture.md` | 描述 C++ 模块边界、数据流和 run/pose 生命周期。 | 稳定架构基线 |
| `docs/archive/v2/milestones.md` | 记录 v2 核心的实施顺序和已完成里程碑。 | 实施历史 |
| `docs/archive/v2/acceptance_checklist.md` | 记录构建、几何、事件输出、多线程和错误处理验收。 | 回归基线 |
| `docs/archive/v2/article_design.md` | Article v1 的 E0–E5 实验分类、条件和论文逻辑。 | 冻结实验设计 |
| `docs/archive/v2/article_experiment_automation.md` | Article v1 配置、队列、batch 合并和后处理操作说明。 | 冻结复现说明 |

V2 核心维护时的文档优先级为：

```text
docs/archive/v2/spec.md
  > docs/archive/v2/decisions.md
  > docs/archive/v2/architecture.md
  > docs/archive/v2/milestones.md
  > docs/archive/v2/acceptance_checklist.md
  > existing code
```

未来新版本的正式用户需求和新规格可以修改 v2 行为，但必须显式说明兼容性影响，不能静默把预研假设当作既有契约。

## 10. 稳定接口与交接边界

后续工作默认必须保护以下 v2 接口：

- Formal/debug CSV header、字段单位和事件行语义。
- `metadata.yaml` 的 run-level provenance。
- 一个 run 与 pose、实际 seed、model condition、n_primary 的对应关系。
- Pose ID、run ID 和输出目录的可复现性。
- `cases[].config_file` manifest 基础契约。
- VehicleROI-compatible geometry YAML、collimator CSV 和 spectrum CSV 的输入边界。
- Geant4 核心只输出事件级数据，统计与绘图属于显式 Python 层。

工作区中出现设计稿、配置草案、生成器或测试，只能证明存在预研资产，不能证明下一版本已经立项或完成。启动下一版本前，应先创建新的正式需求、设计、自动化和验收文档，并在本导航中登记其状态。
