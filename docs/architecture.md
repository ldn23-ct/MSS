# MSS 架构说明

## 1. 文档目的

本文档定义 `MSS` 的第一版实现架构，用于配合 Codex 进行分阶段代码生成。

文档关系如下：

| 文件 | 作用 |
|---|---|
| `docs/spec.md` | 定义仿真需求、物理参数、宏命令、CSV 输出和验收标准；是最高优先级依据。 |
| `docs/architecture.md` | 定义代码组织方式、模块边界、数据流和 Geant4 生命周期。 |
| `docs/decisions.md` | 记录已接受的设计决策，避免实现过程中发生设计漂移。 |
| `docs/milestones.md` | 定义分阶段实现顺序和每阶段验收点。 |

若本文档与 `spec.md` 冲突，以 `spec.md` 为准。本文档不重复所有物理参数，只规定实现结构和边界。

---

## 2. 架构原则

### 2.1 物理意图与软件流程分离

`MSS` 不是通用 Geant4 框架，而是面向 gamma 背散射多重散射统计的专用仿真程序。

代码中应保持以下职责分离：

| 关注点 | 主要负责模块 |
|---|---|
| 几何构建 | `DetectorConstruction`, `CollimatorBuilder` |
| 外部准直器 profile 读取 | `CollimatorProfileReader` |
| 物理过程注册 | `PhysicsList` |
| primary gamma 产生 | `PrimaryGeneratorAction`, `SpectrumSampler` |
| 单事件散射与探测状态 | `EventAction` |
| 单步过程判断与探测面穿越判断 | `SteppingAction` |
| CSV 写入与线程文件合并 | `CsvWriter`, `RunAction` |
| 运行级配置、命名与宏命令 | `SimulationConfig`, `SimulationMessenger`, `RunAction` |

禁止让某个类变成无边界的全局状态容器。

### 2.2 使用明确的数据结构传递跨模块信息

跨模块传递的信息应使用小型结构体，不应把互不相关的变量散落传递。

建议共享数据结构如下。

```cpp
struct DetectorPlaneConfig {
    double z_mm = -73.0;
    double x_min_mm = 53.0;
    double x_max_mm = 161.0;
    double y_min_mm = -50.0;
    double y_max_mm = 50.0;
};
```

```cpp
struct XZPoint {
    double x_mm;
    double z_mm;
};

struct PentagonJawProfile {
    std::string jaw_id;
    std::array<XZPoint, 5> vertices;
};

struct CollimatorProfile {
    std::string profile_id;
    PentagonJawProfile jaw0;
    PentagonJawProfile jaw1;
};
```

```cpp
struct ScatterSummary {
    int scatter_count_total = 0;
    int compton_count = 0;
    int rayleigh_count = 0;
    bool has_scatter = false;
    G4ThreeVector first_scatter_pos;
    G4ThreeVector last_scatter_pos;
};
```

```cpp
struct DetectorHitRecord {
    bool detected = false;
    double det_x = 0.0;
    double det_y = 0.0;
    double det_z = -73.0;
    double det_energy_keV = 0.0;
    G4ThreeVector det_dir;
};
```

```cpp
struct EventRecord {
    int event_id = -1;
    int track_id = 1;
    int parent_id = 0;
    double initial_energy_keV = 0.0;
    ScatterSummary scatter;
    DetectorHitRecord hit;
};
```

上述结构可集中放在 `include/SimulationData.hh` 或按职责拆入相应头文件。

---

## 3. 仓库结构

目标结构如下：

```text
MSS/
├── .gitignore
├── AGENTS.md
├── CMakeLists.txt
├── README.md
├── main.cc
├── docs/
│   ├── architecture.md
│   ├── decisions.md
│   ├── milestones.md
│   └── spec.md
├── include/
│   ├── DetectorConstruction.hh
│   ├── PhysicsList.hh
│   ├── PrimaryGeneratorAction.hh
│   ├── RunAction.hh
│   ├── EventAction.hh
│   ├── SteppingAction.hh
│   ├── CollimatorProfileReader.hh
│   ├── CollimatorBuilder.hh
│   ├── SpectrumSampler.hh
│   ├── CsvWriter.hh
│   ├── SimulationConfig.hh
│   ├── SimulationMessenger.hh
│   └── SimulationData.hh
├── src/
│   ├── DetectorConstruction.cc
│   ├── PhysicsList.cc
│   ├── PrimaryGeneratorAction.cc
│   ├── RunAction.cc
│   ├── EventAction.cc
│   ├── SteppingAction.cc
│   ├── CollimatorProfileReader.cc
│   ├── CollimatorBuilder.cc
│   ├── SpectrumSampler.cc
│   ├── CsvWriter.cc
│   ├── SimulationConfig.cc
│   └── SimulationMessenger.cc
├── macros/
│   ├── vis.mac
│   ├── run.mac
│   └── run_mt.mac
├── data/
│   ├── collimator_profiles.csv
│   └── spectrum.csv
└── results/
    └── .gitkeep
```

允许按 Geant4 标准模式增加：

```text
include/ActionInitialization.hh
src/ActionInitialization.cc
```

`.gitignore` 建议忽略：

```gitignore
build/
results/*.csv
results/tmp/
*.root
*.log
```

但应保留：

```gitignore
!results/.gitkeep
```

---

## 4. 运行生命周期

### 4.1 程序启动

预期流程：

```text
main()
  ├── 使用 G4RunManagerFactory 创建 run manager
  ├── 创建共享 SimulationConfig
  ├── 注册 DetectorConstruction
  ├── 注册 PhysicsList
  ├── 注册 ActionInitialization 或各个 user action
  ├── 创建 SimulationMessenger
  ├── 若传入 argv[1]，执行宏文件
  └── 若无宏文件，可进入交互模式
```

必须使用 Geant4 run manager factory，不应写死单线程 run manager。

### 4.2 宏命令配置

第一版必须支持：

```text
/geometry/collimatorProfileFile data/collimator_profiles.csv
/geometry/collimatorProfileId P001
/geometry/enableAirDefect true

/source/energyMode mono
/source/monoEnergy 160 keV
/source/spectrumFile data/spectrum.csv

/run/randomSeed 12345
/run/numberOfThreads 8

/output/directory results
/output/debug false
```

实现要求：

- 宏命令值进入明确的配置字段。
- 几何相关命令必须在 `/run/initialize` 前生效。
- 源与输出配置必须在 `/run/beamOn` 前有效。
- 非法值应尽早报错，不应静默回退。

建议配置结构：

```cpp
struct GeometryConfig {
    std::string collimator_profile_file = "data/collimator_profiles.csv";
    std::string collimator_profile_id = "P001";
    bool enable_air_defect = true;
};

struct SourceConfig {
    std::string energy_mode = "mono";
    double mono_energy_keV = 160.0;
    std::string spectrum_file = "data/spectrum.csv";
};

struct OutputConfig {
    std::string output_directory = "results";

    // 重要：debug 是否显式设置，应与 debug 值分开。
    // 若未显式设置，则单线程默认 debug，多线程默认 compact。
    std::optional<bool> debug_override = std::nullopt;
};

struct RunConfig {
    long random_seed = 12345;
    int number_of_threads = 1;
};
```

也可以合并为一个 `SimulationConfig`。关键点是 `/output/debug` 的“是否显式设置”需要被保存，否则无法同时满足“单线程默认 debug、多线程默认 compact”的规则。

### 4.3 `/run/initialize`

初始化阶段应完成：

1. `DetectorConstruction` 构建 World、PMMA、可选空气缺陷、准直器和探测面可视化辅助体。
2. `CollimatorProfileReader` 读取并验证指定 profile。
3. `CollimatorBuilder` 将 profile 转换为 Geant4 钨准直器几何。
4. `PhysicsList` 注册 `G4EmLivermorePhysics` 并设置 production cut。
5. 源、输出与线程配置处于有效状态。

profile 或几何输入无效时，必须在事件产生前停止。

### 4.4 run 开始

`BeginOfRunAction` 负责：

1. 应用或确认随机种子。
2. 根据线程数和 `/output/debug` 显式设置解析最终输出模式。
3. 构造最终输出文件名与线程临时文件名。
4. 创建输出目录与 `tmp/` 目录。
5. 初始化当前线程对应的 CSV writer。

默认输出模式：

| 条件 | 默认模式 |
|---|---|
| 单线程且未显式设置 `/output/debug` | debug |
| 多线程且未显式设置 `/output/debug` | compact |
| 显式设置 `/output/debug true/false` | 使用显式值 |

### 4.5 event 生命周期

```text
BeginOfEventAction
  ├── 重置 EventRecord
  ├── 重置 ScatterSummary
  └── 重置 DetectorHitRecord

GeneratePrimaries
  ├── 采样 primary gamma 初始能量
  ├── 在 z = 0 圆形束斑上采样目标点
  ├── 从源位置发射 primary gamma
  └── 将初始能量写入 EventAction

SteppingAction
  ├── 忽略非 primary gamma
  ├── 统计 PMMA 内 Compton/Rayleigh 散射
  ├── 判断是否穿越探测面
  └── 若穿越点在探测器边界内，记录 hit

EndOfEventAction
  ├── 若 hit.detected == true，写出一行 CSV
  └── 否则不写出
```

不变量：

```text
1 event = 1 primary gamma
1 CSV row = 1 detected primary gamma
```

未到达探测面的事件不写入 CSV。

### 4.6 run 结束

`EndOfRunAction` 负责：

1. 关闭线程本地 CSV 文件。
2. 由 master 合并 worker 临时 CSV。
3. 合并时只保留一个 header。
4. compact 模式合并成功后删除对应临时文件。
5. debug 模式合并成功后保留对应临时文件。
6. 合并失败时保留所有临时文件并报错。

---

## 5. 组件设计

### 5.1 `DetectorConstruction`

职责：

- 构建 World。
- 构建 PMMA 模体。
- 根据 `enable_air_defect` 构建或省略空气缺陷。
- 调用 `CollimatorProfileReader` 与 `CollimatorBuilder` 构建准直器。
- 构建探测面的可视化辅助几何。
- 暴露探测器边界配置，供 `SteppingAction` 使用。

稳定 volume 名称建议：

```text
WorldLogical
PMMALogical
AirDefectLogical
CollimatorJaw0Logical
CollimatorJaw1Logical
DetectorPlaneVisLogical
```

`SteppingAction` 不应依赖可视化属性或 placement 顺序判断物理含义。

探测面辅助几何只用于可视化，不应作为 sensitive detector，也不应用于能量沉积统计。

### 5.2 `CollimatorProfileReader`

职责：读取、筛选、验证并返回一个 `CollimatorProfile`。

输入 CSV：

```csv
profile_id,jaw_id,vertex_id,x_mm,z_mm
```

必须报错停止的情况：

- 文件无法打开。
- 指定 `profile_id` 不存在。
- 缺少必要列。
- 指定 profile 中不是两块 jaw。
- jaw ID 不是 `jaw_0` 与 `jaw_1`。
- 某块 jaw 不是五个顶点。
- `vertex_id` 缺失、重复或超出 `0..4`。
- 坐标为空、非数值、NaN 或 Inf。
- 多边形面积为 0。
- 五边形非凸。

该类只验证数据，不创建 Geant4 solid。

### 5.3 `CollimatorBuilder`

职责：将已验证的 `CollimatorProfile` 转换为 Geant4 钨几何。

要求：

- 使用 `G4ExtrudedSolid`。
- 输入 `x_mm` 和 `z_mm` 是全局坐标。
- 映射关系为：global x → local x，global z → local y。
- local z 为拉伸方向，半长 `60 mm`。
- 旋转使拉伸方向对应全局 y 方向。
- 不额外叠加 `collimator_center_z`。

该类不解析 CSV，也不决定使用哪个 profile。

### 5.4 `PhysicsList`

职责：定义 Geant4 物理过程。

要求：

- 注册 `G4EmLivermorePhysics`。
- 设置全局 production cut 为 `0.1 mm`。

不得包含几何、源、输出或事件记录逻辑。

### 5.5 `PrimaryGeneratorAction`

职责：每个 event 产生一个 primary gamma。

要求：

- 粒子类型：gamma。
- 源位置：`(0, 0, -185 mm)`。
- 束型：通过 z = 0 平面圆形目标点采样生成锥束。
- 束斑半径：`1.5 mm`。
- 能量模式：`mono` 或 `spectrum`。

采样初始能量后，应将 `initial_energy_keV` 写入事件状态。

不得写 CSV，也不得判断探测面穿越。

### 5.6 `SpectrumSampler`

职责：读取能谱 CSV 并按权重采样 gamma 能量。

输入 CSV：

```csv
energy_keV,weight
```

要求：

- 能量为正且有限。
- 权重非负且有限。
- 文件非空。
- 总权重大于 0。
- 内部归一化并构建 CDF。
- 每个 event 采样一个能量。

该类不应依赖 Geant4 event、几何或输出文件。

### 5.7 `EventAction`

职责：持有当前 event 的记录。

event 开始时：

- 重置散射计数。
- first/last scatter 位置置为 NaN。
- 重置 detector hit 标记。
- 准备接收初始能量。

event 过程中提供接口，例如：

```cpp
void SetInitialEnergy(double energy_keV);
void RecordComptonScatter(const G4ThreeVector& pos);
void RecordRayleighScatter(const G4ThreeVector& pos);
void RecordDetectorHit(const DetectorHitRecord& hit);
bool HasDetectorHit() const;
const EventRecord& GetRecord() const;
```

event 结束时：

- 若已探测，写一行 CSV。
- 若未探测，不写。

`EventAction` 不负责判断某个 step 是否为 Compton/Rayleigh，也不负责探测面穿越计算。

### 5.8 `SteppingAction`

职责：检查每个 step 并更新事件状态。

只处理：

```text
particle == gamma
track_id == 1
parent_id == 0
```

PMMA 内散射计数条件：

```text
processName == "compt" || processName == "Rayl"
```

并且相互作用点位于 PMMA 材料或 `PMMALogical` 对应区域内。空气缺陷、钨准直器、World 中的相互作用不计入 PMMA 散射。

散射位置使用：

```cpp
step->GetPostStepPoint()->GetPosition()
```

探测面穿越条件：

```text
preStep.z > detector_z
postStep.z <= detector_z
direction.z < 0
```

穿越点线性插值：

```text
t = (detector_z - pre_z) / (post_z - pre_z)
det_x = pre_x + t * (post_x - pre_x)
det_y = pre_y + t * (post_y - pre_y)
```

hit 接受范围：

```text
53 mm <= det_x <= 161 mm
-50 mm <= det_y <= 50 mm
```

同一 event 一旦记录有效 detector hit，后续穿越不应再产生额外 CSV 行。实现上可以记录后忽略重复 hit，也可以在记录后停止该 primary track；若停止 track，需确保不影响已记录数据。

### 5.9 `CsvWriter`

职责：安全写出 CSV。

要求：

- 根据 debug/compact 模式生成精确 header。
- 每个 worker 线程写独立临时 CSV。
- 不共享同一个 `std::ofstream`。
- 写出前统一转换为 mm 与 keV。
- 无散射位置写为 `NaN`。
- run 结束后由 master 合并。
- 最终文件只保留一个 header。

compact header：

```csv
initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

debug header：

```csv
event_id,track_id,parent_id,det_z,det_dir_x,det_dir_y,det_dir_z,initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

### 5.10 `RunAction`

职责：管理 run 级初始化与结束。

要求：

- 初始化随机种子。
- 解析最终输出模式。
- 构造最终文件名和线程临时文件名。
- run 开始时初始化 CSV writer。
- run 结束时触发 master 合并。

不得执行 per-step 物理判断，也不得解析准直器多边形。

---

## 6. 数据流

配置数据流：

```text
Macro commands
  └── SimulationConfig
        ├── DetectorConstruction
        │     ├── CollimatorProfileReader
        │     └── CollimatorBuilder
        ├── PrimaryGeneratorAction
        │     └── SpectrumSampler
        ├── RunAction
        │     └── CsvWriter
        └── SteppingAction
              └── DetectorPlaneConfig
```

单 event 数据流：

```text
PrimaryGeneratorAction
  └── initial energy
        ↓
EventAction::EventRecord
        ↑
SteppingAction
  ├── PMMA scatter updates
  └── detector crossing update
        ↓
EndOfEventAction
  └── CsvWriter::WriteRow(EventRecord)
```

---

## 7. 多线程模型

多线程模式下：

- worker 线程处理 events。
- 每个 worker 写自己的临时 CSV。
- master 在 run 结束后合并文件。

允许共享只读状态：

- 几何常量。
- 探测面边界。
- 冻结后的配置值。

禁止共享可变状态：

- 多线程共享一个 `std::ofstream`。
- 多线程更新同一个 `EventRecord`。
- 将全部 event record 累积到内存后统一写出。

---

## 8. 错误处理策略

无效输入或不可能几何应 fail fast。

初始化阶段 fatal：

- 缺少准直器 profile 文件。
- 找不到指定 profile ID。
- jaw 或 vertex 数量错误。
- 多边形非法。
- spectrum 模式下能谱文件非法。
- 输出目录无法创建。

运行阶段 fatal：

- CSV 文件无法打开。
- CSV 合并失败。

设计上非 fatal：

- event 未到达探测器。
- event 无 PMMA 散射但到达探测器。
- event 在探测前发生光电吸收。

---

## 9. 单位与输出约定

Geant4 内部可使用 Geant4 单位系统。

CSV 输出统一约定：

| 量 | CSV 单位 |
|---|---|
| 长度 | mm |
| 能量 | keV |

除非 `spec.md` 更新，不应给 CSV 字段名增加单位后缀。

---

## 10. Codex 实现边界

Codex 应按里程碑逐步实现。

推荐任务格式：

```text
Read docs/spec.md, docs/architecture.md, and docs/milestones.md.
Implement Milestone 2 only: Collimator profile reader.
Do not modify unrelated modules except CMakeLists.txt if required.
After implementation, summarize changed files and validation commands.
```

不推荐任务：

```text
Build the whole project.
Make it work.
Implement everything from the spec.
```

这类任务范围过大，不利于检查错误。

---

## 11. 第一版非目标

第一版不得扩展到以下功能，除非 `spec.md` 明确更新：

- 图像重建。
- 真实探测器材料响应。
- 探测器能量沉积 scoring。
- 自动遍历全部 collimator profile。
- 全部散射轨迹输出。
- 源位置宏命令。
- 探测器边界宏命令。
- 真实准直器 profile 生成逻辑。

---

## 12. 架构验收清单

实现满足本文档的条件：

- `spec.md` 是物理参数和输出规格的唯一最高依据。
- 几何构建、profile 读取、事件跟踪和 CSV 输出位于不同模块。
- 只记录 primary gamma。
- PMMA 内 Compton/Rayleigh 散射计数绑定到当前 event。
- 探测面穿越使用线性插值。
- 一个被探测 primary gamma 只产生一行 CSV。
- 多线程输出不共享一个输出流。
- compact 模式只在合并成功后删除临时 CSV。
- debug 模式合并成功后保留临时 CSV。
- 非法 profile 在事件生成前报错停止。
