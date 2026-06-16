# 第二版里程碑实施计划

## 1. 文档目的

本文档定义第二版车辆侧向背散射 ROI Geant4 仿真项目的分阶段实现顺序。

本文档不是科研计划，也不是后处理分析计划。它只约束第二版基础程序的代码生成顺序、每阶段交付物和验收点。

使用优先级：

1. `spec.md`：需求、配置格式、字段、物理约定和输出规格。
2. `decisions.md`：已接受设计决策。
3. `architecture.md`：模块边界、数据流和生命周期。
4. `milestones.md`：阶段实现顺序。
5. `acceptance_checklist.md`：阶段后验收检查。

若本文档与 `spec.md` 冲突，以 `spec.md` 为准。

---

## 2. 与 Codex 配合方式

第二版仍采用小步实现方式。每次只实现一个里程碑。

推荐流程：

1. 让 Codex 读取 `docs/spec.md`、`docs/decisions.md`、`docs/architecture.md`、`docs/milestones.md`。
2. 明确指定要实现的里程碑编号。
3. 明确要求不得实现后续里程碑。
4. 检查修改过的文件。
5. 运行该里程碑对应检查。
6. 通过后再进入下一里程碑。

推荐 prompt 模板：

```text
Read docs/spec.md, docs/decisions.md, docs/architecture.md, and docs/milestones.md.
Implement Milestone N only.
Do not implement Milestone N+1 or later.
After implementation, summarize:
- changed files
- what was implemented
- how to test it
- what was intentionally left for later
```

---

## 3. 全局实现规则

### 3.1 必须遵守

- 以 `config/base/simulation_config_v2.yaml` 或 `--config` 指定的等价 YAML 作为第二版主配置入口。
- `--ui` 是第二版可视化入口；它仍使用 YAML 配置，不得通过 legacy macro 设置 source、detector、collimator、pose、output、seed、thread 或 target。
- 主入口 YAML 位于 `config/`，车辆 ROI、collimator profile 和 spectrum 文件也位于 `config/`，具体文件名由主入口 YAML 指定。
- 车辆 ROI 固定，成像头移动。
- 使用 `head_offset_x_mm` / `head_offset_y_mm`，不得使用 `vehicle_shift_x/y`。
- `pose_id` 由 offset 自动生成，不由用户手写。
- 第一阶段 offset 只支持整数 mm。
- 正整数 pose 编码不加前缀，负整数使用 `m` 前缀。
- Source、collimator、detector 共享同一个 pose offset。
- source 使用斜入射有限焦点笔形束。
- collimator reader 支持可变 jaw 数量。
- 不构建镜像准直器。
- 不构建镜像探测器。
- detector 为单个理想虚拟平面。
- 正式 CSV 输出所有 detected gamma hit。
- debug CSV 输出 gamma track summary，并使用 `detected` 字段区分该 track 是否有效穿越探测平面。
- 同一 event 可输出 0 行、1 行或多行 detected gamma hit。
- 同一 gamma track 只记录第一次有效 detector crossing。
- 每条 gamma track 维护自身 Compton / Rayleigh 散射历史，secondary gamma 不继承 parent track 的散射阶次。
- 事件是否进入正式输出只由 detected gamma hit 决定。
- 散射坐标使用 postStep position。
- 散射 region 归属使用 preStep volume。
- 输出采用 `events.csv` / `events_debug.csv` + `metadata.yaml`。
- 本轮不实现 pose-level summary、scan-level summary、图表、统计指标或后处理脚本。
- World 使用中心 `[0,0,0]`、边长 `4000 mm` 的固定 `G4_AIR` box，并检查所有 pose 下组件均在 World 内。
- 一个 run 对应一个 pose 和一个实际 seed；一个 run 可以使用多线程执行。
- 多线程输出使用线程临时 CSV + master 合并。
- 所有非法配置、非法几何、非法 profile 和输出错误必须 fail fast。

### 3.2 禁止行为

- 不得把第一版 `spec.md` 作为第二版硬规格。
- 不得重新引入 PMMA 模体作为第二版主模型。
- 不得使用 `vehicle_shift_x/y` 表示扫描。
- 不得让用户直接手写 `pose_id`。
- 不得支持小数 offset，除非后续规格更新。
- 不得把正 offset 写成 `p10` 这类形式。
- 不得构建镜像准直器。
- 不得构建镜像探测器。
- 不得加入真实探测器材料响应。
- 不得加入 sensitive detector 能量沉积 scoring。
- 不得在 Geant4 程序中生成统计图、差异图或 CNR。
- 不得在本轮实现 pose_summary.csv、scan_summary.csv 或后处理脚本。
- 不得让多个 worker 共享同一个 `std::ofstream`。
- 不得在正式 CSV 中加入 `detected`、`pose_id`、`model_type` 或 `head_offset_x/y`。
- 不得在 debug CSV 中加入 `termination_process`、`termination_volume`、`termination_region_id`。
- 不得静默修复非法 YAML、非法 profile 或非法几何。

### 3.3 现有代码迁移规则

当前仓库不是空骨架，而是第一轮 PMMA 背散射实现。后续里程碑应在现有代码上建立第二轮结构，同时隔离第一轮语义。

可机制级复用：

- `SpectrumSampler` 的 spectrum CSV 验证和 CDF sampling；
- `CsvWriter` / `RunAction` 中 worker 临时 CSV 与 master merge 的基本思路；
- `SteppingAction` 中 gamma track 过滤和 detector plane crossing 插值；
- `CollimatorProfileReader` 中 CSV 基础解析和凸多边形检查；
- `CollimatorBuilder` 中 `G4ExtrudedSolid` 构建经验；
- `PhysicsList` 中 `G4EmLivermorePhysics` 和 `0.1 mm` production cut。

必须隔离或替换：

- PMMA / air defect 几何；
- mirror collimator 和 mirror detector；
- macro 主配置入口和旧 `/geometry/*`、`/source/*`、`/output/*` 参数；
- `PMMALogical` 内散射过滤；
- `hits_profile_*` 输出文件名；
- compact/debug 第一轮 CSV header；
- 固定三块 jaw 数据结构。

---

## 4. 里程碑总览

| 里程碑 | 名称 | 主要交付物 |
|---:|---|---|
| M0 | 第二版仓库骨架与 legacy 隔离 | 可编译最小项目、核心占位类、基础 CLI、第一轮语义隔离 |
| M1 | `simulation_config_v2.yaml` 读取 | `SimulationConfigReader`、配置结构、基础验证 |
| M2 | `vehicle_roi_v03.yaml` 读取 | `VehicleROIConfigReader`、组件配置、host/insert 校验 |
| M3 | 材料与 region 基础设施 | `MaterialManager`、`RegionRegistry`、`RegionResolver` |
| M4 | VehicleROI 几何构建 | World、VehicleROI、车辆组件、normal/abnormal insert |
| M5 | ScanPoseManager | list/grid pose 生成、pose_id 自动编码 |
| M6 | 成像头配置与虚拟探测器辅助体 | `ImagingHeadConstruction`、`VirtualDetectorPlane` |
| M7 | 斜入射有限焦点源 | `SourceModel`、`PrimaryGeneratorAction`、mono/spectrum |
| M8 | 第二版准直器 profile reader | 可变 jaw 数量 CSV reader 与 validator |
| M9 | 无镜像狭缝准直器几何 | `SlitCollimatorBuilder`、offset 应用、钨 jaw 构建 |
| M10 | EventRecord 与 EventAction | event 状态、detected/debug 写出接口占位 |
| M11 | Stepping 散射追踪 | gamma track 过滤、per-track Compton/Rayleigh 计数、region 归属 |
| M12 | Detector crossing | negative_z crossing、detector hit 记录 |
| M13 | 正式与 debug CSV 输出 | 精确 header、detected/undetected 规则 |
| M14 | metadata.yaml 输出 | 每 pose run-level metadata |
| M15 | 多线程输出合并 | worker 临时 CSV、master 合并、临时文件处理 |
| M16 | 多 pose 运行控制与样例文件 | `PoseRunController`、sample configs、README 对齐 |

---

# M0：第二版仓库骨架与 legacy 隔离

## 目标

在现有第一轮代码基础上建立第二版最小可编译骨架，并隔离 legacy PMMA / macro / mirror / old CSV 语义。该阶段只建立 CMake、入口文件和核心占位类的第二轮边界，不实现真实车辆几何、源、准直器、探测器或 CSV 输出。

## 创建或修改文件

创建或调整：

- `CMakeLists.txt`
- `main.cc`
- `include/SimulationConfig.hh`
- `include/SimulationConfigReader.hh`
- `include/VehicleROIConfig.hh`
- `include/VehicleROIConfigReader.hh`
- `include/MaterialManager.hh`
- `include/RegionRegistry.hh`
- `include/RegionResolver.hh`
- `include/VehicleROIConstruction.hh`
- `include/ImagingHeadConstruction.hh`
- `include/SourceModel.hh`
- `include/PrimaryGeneratorAction.hh`
- `include/SpectrumSampler.hh`
- `include/SlitCollimatorProfileReader.hh`
- `include/SlitCollimatorBuilder.hh`
- `include/VirtualDetectorPlane.hh`
- `include/PhysicsList.hh`
- `include/ActionInitialization.hh`
- `include/EventRecord.hh`
- `include/EventAction.hh`
- `include/SteppingAction.hh`
- `include/RunAction.hh`
- `include/PoseRunController.hh`
- `include/CsvWriter.hh`
- `include/MetadataWriter.hh`
- 对应 `src/*.cc`
- `config/.gitkeep`
- `results/.gitkeep`

## 任务

### M0.1 CMake

要求：

- project 名称为 `MSS`。
- executable target 为 `MSS`。
- C++ 标准为 C++17。
- 查找 Geant4。
- 接入已批准的 `yaml-cpp`；若依赖不可用，应给出明确构建错误。

### M0.2 main 入口

`main.cc` 应接受一个 YAML 配置路径，例如：

```bash
./build/MSS config/base/simulation_config_v2.yaml
```

或实现明确的等价方式：

```bash
./build/MSS --config config/base/simulation_config_v2.yaml
```

`--config` 为推荐主入口；若同时支持位置参数形式，应以 `--config` 指定路径为准。README 和验收文档必须与实际入口一致。

### M0.3 占位类

所有核心类应能编译，但仅实现最小行为。

### M0.4 legacy 隔离

要求：

- 旧 macro 运行链路不得作为第二轮默认主路径；如保留 `SimulationMessenger`，只能用于指定或切换入口 YAML 文件路径。
- 旧 PMMA / air defect / mirror collimator / mirror detector / compact CSV 文件名逻辑不得继续作为默认行为。
- 若保留旧类文件名作为临时过渡，必须保证其对外语义已经改为第二轮职责，或在后续里程碑中明确重命名 / 替换。
- README 与宏文件可暂时保留，但不得作为第二轮 M0/M1 验收入口。

## 完成标准

- `cmake -S . -B build` 成功。
- `cmake --build build -j` 成功。
- 生成 `build/MSS`。
- 运行无配置或配置路径错误时给出清晰错误，不崩溃。
- 未实现真实仿真行为。
- 默认入口不再依赖第一轮 macro 文件。
- CMake 已接入 `yaml-cpp` 或在依赖不可用时明确失败。

## 不做

- 不读取 YAML 内容。
- 不运行第一轮 PMMA / air defect / mirror 几何作为第二轮默认行为。
- 不构建 VehicleROI。
- 不构建成像头。
- 不产生 gamma。
- 不写 CSV。
- 不实现多线程合并。

---

# M1：`simulation_config_v2.yaml` 读取

## 目标

实现运行配置 YAML 的读取、结构化保存和基础验证。

## 修改文件

- `include/SimulationConfig.hh`
- `src/SimulationConfig.cc`，如需要
- `include/SimulationConfigReader.hh`
- `src/SimulationConfigReader.cc`
- `main.cc`
- `CMakeLists.txt`

## 任务

### M1.1 定义配置结构

实现：

- `RunConfig`
- `VehicleRunConfig`
- `SourceConfig`
- `CollimatorConfig`
- `DetectorConfig`
- `PhysicsConfig`
- `OutputConfig`
- `SimulationConfig`

字段应与 `spec.md` 中 `simulation_config_v2.yaml` 保持一致。不得把旧 `SimulationConfig` 中的 `enableAirDefect`、`collimatorProfileFile`、`debugOutputOverride` 等 macro-era 字段作为第二轮 schema。

### M1.2 读取 YAML

读取顶层字段：

```yaml
schema_version
run
vehicle
pose
source
collimator
detector
physics
output
```

M1 阶段可以先读取 pose 原始数组，但 pose 生成可留到 M5。

### M1.3 基础验证

必须验证：

- `schema_version == 2`。
- 必要字段存在。
- 字段类型正确。
- `number_of_threads >= 1`。
- `n_primary_per_pose > 0`。
- `model_type` 为 `normal` 或 `abnormal`。
- abnormal 模式下 `selected_target_component` 不为 null。
- `energy_mode` 为 `mono` 或 `spectrum`。
- `mono_energy_keV > 0`。
- `incident_theta_deg` 满足 `(0, 90]`。
- `focal_spot_diameter_mm > 0`。
- detector range 合法。
- output directory 非空。

## 完成标准

- 有效 `config/base/simulation_config_v2.yaml` 可读取。
- 已批准的 `yaml-cpp` 已实际用于读取配置。
- 配置对象可打印或日志输出关键字段。
- 非法字段能 fail fast。
- 未读取或构建 `vehicle_roi_v03.yaml`。
- 不再通过旧 macro 字段驱动 source、detector、collimator、pose、output、seed 或 thread。
- 提供 `config/base/simulation_config_v2.yaml` 最小可读样例。

## 不做

- 不生成 pose_id。
- 不构建 Geant4 几何。
- 不读取 collimator profile。
- 不写输出文件。

---

# M2：`vehicle_roi_v03.yaml` 读取

## 目标

实现车辆 ROI YAML 的读取和结构验证，不构建 Geant4 几何。该阶段不得复用 PMMA / air defect 几何字段作为 VehicleROI schema。

## 修改文件

- `include/VehicleROIConfig.hh`
- `src/VehicleROIConfig.cc`，如需要
- `include/VehicleROIConfigReader.hh`
- `src/VehicleROIConfigReader.cc`
- `main.cc` 或测试入口

## 任务

### M2.1 定义数据结构

实现：

- `BoxComponentConfig`
- `VehicleROIConfig`
- insert 配置字段；
- host / daughter 关系字段；
- material 与 region_id 字段。

### M2.2 读取 YAML

按 `vehicle_roi_v03.yaml` 实际 schema 读取，不得假设存在 `vehicle_roi:` 顶层字段。

读取：

- `schema`、`metadata`、`units`、`coordinate_system`、`roi`、`geant4_placement_rules`、`materials`、`model_modes`、`regions`、`components`、`validation`；
- VehicleROI 根 volume；
- 所有 component；
- center；
- size；
- host；
- shape；
- role；
- half_size_mm；
- aabb_mm；
- placement_center_in_host_mm；
- material；
- region_id；
- normal / abnormal insert 字段。

### M2.3 配置验证

必须验证：

- root VehicleROI 存在。
- component name 唯一。
- host 存在。
- size 三个分量均为正。
- center 三个分量均为有限数值。
- material 字段存在。
- region_id 字段存在。
- insert 有 normal / abnormal material 与 region 信息。
- abnormal target component 若在 simulation config 中指定，则存在且是 insert。
- `shape` 第一阶段必须为 `box`。
- `half_size_mm` 与 `size_mm` 一致。
- `aabb_mm` 与 `center_mm/size_mm` 一致。
- `placement_center_in_host_mm` 与 host placement 规则一致。
- recommended target component 列表合法。

### M2.4 AABB 检查

基于 YAML 进行不依赖 Geant4 的 AABB 检查：

- daughter 在 host 内；
- 同级实体不 overlap；
- 贴边允许；
- insert 位于唯一宿主内。

## 完成标准

- `vehicle_roi_v03.yaml` 可读取。
- 能列出组件数量、host 关系和 region_id。
- AABB 检查通过。
- 构造一个临时 overlap YAML 时能报错。
- 提供 `config/geometry/vehicle_roi_v04.yaml` 当前完整 VehicleROI 样例。

## 不做

- 不创建 G4Box。
- 不创建材料。
- 不注册 region 到 Geant4 volume。
- 不处理 pose offset。

---

# M3：材料与 region 基础设施

## 目标

实现材料管理和 region 映射基础设施。

## 修改文件

- `include/MaterialManager.hh`
- `src/MaterialManager.cc`
- `include/RegionRegistry.hh`
- `src/RegionRegistry.cc`
- `include/RegionResolver.hh`
- `src/RegionResolver.cc`

## 任务

### M3.1 MaterialManager

支持：

- `G4_AIR`
- `G4_Fe`
- `G4_GLASS_PLATE`
- `G4_POLYPROPYLENE`
- `G4_POLYETHYLENE`
- `G4_W`
- `Vehicle_PU_Foam`

`Vehicle_PU_Foam`：

```text
density = 0.055 g/cm3
C = 0.60
H = 0.08
O = 0.28
N = 0.04
```

材料创建应幂等。

### M3.2 RegionRegistry

实现 volume 到 region_id 的注册表。

### M3.3 RegionResolver

实现基于 preStep volume 的 region 查询逻辑。

返回规则：

| 情况 | 返回 |
|---|---|
| 已注册 volume | 注册 region_id |
| VehicleROI 空气母体 | `vehicle_background_air` |
| 未注册 volume | `other` |
| 无有效散射 | `none` |

## 完成标准

- 材料均可创建或查询。
- 重复请求 `Vehicle_PU_Foam` 不重复创建。
- region 注册和查询可通过最小测试验证。

## 不做

- 不构建完整车辆 ROI。
- 不实现散射记录。
- 不写 CSV。

---

# M4：VehicleROI 几何构建

## 目标

使用 `vehicle_roi_v03.yaml` 构建固定 World、VehicleROI 和全部车辆 ROI 组件。

## 修改文件

- `include/VehicleROIConstruction.hh`
- `src/VehicleROIConstruction.cc`
- `include/DetectorConstruction.hh`，若使用统一 DetectorConstruction
- `src/DetectorConstruction.cc`
- `include/ActionInitialization.hh`，如需要

## 任务

### M4.1 World 与 VehicleROI

World 固定为：

```text
center = [0, 0, 0] mm
size = [4000, 4000, 4000] mm
material = G4_AIR
```

构建：

```text
World
└── VehicleROI
```

VehicleROI：

```text
center = [200, 625, 725] mm
size = [2200, 1250, 1450] mm
material = G4_AIR
region_id = vehicle_background_air
```

### M4.2 车辆组件

根据 YAML 构建所有 component。

要求：

- `size` 按全长读取，G4Box 使用 half length。
- placement 使用 `component_center - host_center`。
- host / daughter 层级与 YAML 一致。
- normal / abnormal insert 材料和 region 按配置选择。

### M4.3 region 注册

每个 physical volume 创建后注册 region_id。

### M4.4 可视化属性

给主要材料区设置可区分可视化属性，便于检查。

## 完成标准

- 可视化可见 VehicleROI 和主要车辆结构。
- normal 模型无 target region。
- abnormal 模型只有 selected insert 为 target region。
- Geant4 overlap 检查通过。
- VehicleROI 位于固定 World 内。
- 若任一几何组件超出固定 World，fail fast。

## 不做

- 不构建成像头。
- 不实现 source。
- 不实现 detector crossing。
- 不写 CSV。

---

# M5：ScanPoseManager

## 目标

实现 list / grid pose 生成和 `pose_id` 自动编码。

## 修改文件

- `include/ScanPose.hh` 或 `include/SimulationConfig.hh`
- `include/ScanPoseManager.hh`
- `src/ScanPoseManager.cc`
- `src/SimulationConfigReader.cc`

## 任务

### M5.1 list mode

规则：

```text
第 i 个 x offset 与第 i 个 y offset 配对。
```

x/y 数组长度不同必须报错。

### M5.2 grid mode

规则：

```text
x_offsets × y_offsets 笛卡尔积。
```

### M5.3 pose_id 自动生成

编码规则：

```text
0      -> 0
正整数 -> 原始十进制数字
负整数 -> m + 绝对值
```

格式：

```text
pose_x{encoded_x}_y{encoded_y}
```

示例：

```text
(0, 0) -> pose_x0_y0
(1111, 0) -> pose_x1111_y0
(-10, -4) -> pose_xm10_ym4
```

### M5.4 offset 限制

第一阶段只支持整数 mm offset。小数必须报错。

## 完成标准

- list mode 生成正确 pose 顺序。
- grid mode 生成正确笛卡尔积。
- pose_id 正确。
- 非法 offset fail fast。
- 每个 pose 带有稳定的 `pose_index`，供 run seed 与 metadata 使用。
- `ScanPoseManager` 生成的 `PoseList` 作为 `PoseRunController` 执行 pose runs 的输入。

## 不做

- 不执行 Geant4 run。
- 不创建 pose 输出目录。
- 不移动几何。

---

# M6：成像头配置与虚拟探测器辅助体

## 目标

实现成像头的统一 offset 计算，并构建虚拟探测器可视化辅助体。

## 修改文件

- `include/ImagingHeadConstruction.hh`
- `src/ImagingHeadConstruction.cc`
- `include/VirtualDetectorPlane.hh`
- `src/VirtualDetectorPlane.cc`

## 任务

### M6.1 成像头 actual 坐标计算

计算：

```text
source_pos_actual = source_pos_zero + (head_offset_x, head_offset_y, 0)
```

Detector actual bounds：

```text
x_min = x_min_zero + head_offset_x
x_max = x_max_zero + head_offset_x
y_min = y_min_zero + head_offset_y
y_max = y_max_zero + head_offset_y
z = detector_z_zero
```

### M6.2 探测器辅助体

构建单个虚拟探测器平面辅助体：

- 平行 global `x-y`；
- 位于 `detector_z_actual`；
- 覆盖当前 pose 的 detector bounds；
- 不作为 sensitive detector；
- 不模拟真实材料响应。

### M6.3 禁止镜像探测器

不得构建镜像探测器。

## 完成标准

- 在 `pose_x0_y0` 下探测器范围等于 zero config。
- 在 `pose_x10_y5` 下探测器范围随 x/y 平移。
- VehicleROI 不移动。
- 可视化中只出现一个探测器辅助平面。

## 不做

- 不实现 detector crossing。
- 不构建准直器。
- 不产生 gamma。
- 不写 CSV。

---

# M7：斜入射有限焦点源

## 目标

实现第二版 primary gamma 源模型。

## 修改文件

- `include/SourceModel.hh`
- `src/SourceModel.cc`
- `include/PrimaryGeneratorAction.hh`
- `src/PrimaryGeneratorAction.cc`
- `include/SpectrumSampler.hh`
- `src/SpectrumSampler.cc`

## 任务

### M7.1 事件定义

每个 event 产生一个 primary gamma。

### M7.2 incident direction

```text
incident_dir = (cos(theta), 0, sin(theta))
```

theta 从 YAML 读取，合法范围 `(0°, 90°]`。

### M7.3 焦点面采样

焦点面过 `source_pos_actual`，垂直于 incident direction。

使用：

```text
u = (0, 1, 0)
v = (-sin(theta), 0, cos(theta))
```

在圆盘内均匀采样起点。

### M7.4 能量模式

支持：

- mono；
- spectrum。

spectrum CSV header：

```csv
energy_keV,weight
```

严格验证 energy 和 weight。

## 完成标准

- mono 模式生成固定能量 primary gamma。
- spectrum 模式可读取合法 spectrum 并采样。
- `theta = 45°` 时方向约为 `(0.7071, 0, 0.7071)`。
- `theta = 90°` 时方向约为 `(0, 0, 1)`。
- gamma 起点落在有限焦点圆盘内。
- 不使用第一版目标平面锥束采样。
- 提供 `config/source/spectrum.csv` 最小合法样例。

## 不做

- 不实现 detector crossing。
- 不统计散射。
- 不写 CSV。

---

# M8：第二版准直器 profile reader

## 目标

实现第二版狭缝准直器 CSV profile 读取和验证。可参考旧 `CollimatorProfileReader` 的 CSV 解析和凸多边形检查，但必须迁移为 `SlitCollimatorProfileReader` 语义。

## 修改文件

- `include/SlitCollimatorProfileReader.hh`
- `src/SlitCollimatorProfileReader.cc`
- 必要时添加 profile 数据结构头文件

## 任务

### M8.1 数据结构

```cpp
struct XZPoint {
    double x_mm;
    double z_mm;
};

struct SlitJawProfile {
    std::string jaw_id;
    double y_zero_mm = 0.0;
    std::vector<XZPoint> vertices;
};

struct SlitCollimatorProfile {
    std::string profile_id;
    std::vector<SlitJawProfile> jaws;
};
```

### M8.2 CSV 读取

必需列：

```csv
profile_id,jaw_id,vertex_id,x_mm,z_mm
```

可选列：

```csv
y_mm
```

只读取指定 `profile_id`。若存在 `y_mm`，同一 jaw 内所有顶点的 `y_mm` 必须相同，并作为 jaw 的 `y_zero_mm`；若不存在，`y_zero_mm = 0`。Reader 应容忍并去除 UTF-8 BOM。

### M8.3 验证规则

必须验证：

- 文件可打开；
- 指定 profile 存在；
- 必要列存在；
- `M >= 1`；
- jaw ID 连续为 `jaw_0 ... jaw_{M-1}`；
- 每块 jaw `N >= 3`；
- `vertex_id = 0 ... N-1` 连续；
- 坐标有限；
- 同一 jaw 内 `y_mm` 不一致时 fail fast；
- 多边形面积非零；
- 多边形凸；
- 不含连续共线点。

## 完成标准

- 可读取样例 `P001`。
- 不写死三块 jaw。
- 不复用旧 `std::array<..., 3>` profile 结构。
- 不构建镜像。
- 各类非法 profile 可报错停止。
- 提供 `config/collimator/collimator_profiles.csv` 或主入口 YAML 指定的等价样例 profile 文件。

## 不做

- 不创建 `G4ExtrudedSolid`。
- 不构建 tungsten jaw。
- 不自动批量扫描 profile。

---

# M9：无镜像狭缝准直器几何

## 目标

使用 M8 输出的 profile 构建第二版钨准直器几何。可参考旧 `CollimatorBuilder` 的 `G4ExtrudedSolid` 经验，但必须迁移为 `SlitCollimatorBuilder` 语义。

## 修改文件

- `include/SlitCollimatorBuilder.hh`
- `src/SlitCollimatorBuilder.cc`
- `include/ImagingHeadConstruction.hh`
- `src/ImagingHeadConstruction.cc`

## 任务

### M9.1 G4ExtrudedSolid

每块 jaw 使用 `G4ExtrudedSolid`。

映射：

| 输入 | local 坐标 |
|---|---|
| global x | local x |
| global z | local y |
| global y | local z 拉伸方向 |

沿 global y 方向拉伸。

### M9.2 offset 应用

`y_zero` 来自 profile CSV 可选 `y_mm`；若 CSV 不含 `y_mm`，则 `y_zero = 0`。`jaw_extrusion_length_y_mm` 表示 global y 方向全长，不是 half length。

当前 pose 下：

```text
x_actual = x_zero + head_offset_x
z_actual = z_zero
y_actual = y_zero + head_offset_y
```

### M9.3 材料与镜像

- 材料使用 `G4_W`。
- 不构建镜像 jaw。
- 若 `collimator.enable = false`，不读取 profile，不构建 tungsten jaw。

## 完成标准

- 合法 profile 构建出全部原始 jaw。
- jaw 数量等于 profile 中 jaw 数量。
- pose offset 改变时 jaw 同步平移。
- 可视化中没有镜像 jaw。
- 不出现旧 `Mirror` jaw 命名或关于 `x=0` 的镜像 placement。
- `enable=false` 时不读取不存在的 profile 文件。

## 不做

- 不实现 detector crossing。
- 不写 CSV。
- 不自动扫描 profile。

---

# M10：EventRecord 与 EventAction

## 目标

实现事件级状态模型，但不实现 step 判断。

## 修改文件

- `include/EventRecord.hh`
- `include/EventAction.hh`
- `src/EventAction.cc`

## 任务

### M10.1 EventRecord

保存：

- `event_id`；
- `next_hit_id`；
- per-track gamma summary map；
- 每条 gamma track 的 `track_id`、`parent_id`、`is_primary_gamma`；
- 每条 gamma track 的 `gamma_source_type/process/x/y/z/region_id`；
- 每条 gamma track 的 detector hit；
- 每条 gamma track 的 scatter counts；
- 每条 gamma track 的 first / last scatter position；
- 每条 gamma track 的 first / last scatter region。

### M10.2 reset 规则

每个 event 开始时：

```text
next_hit_id = 0
per-track gamma summary map cleared
```

每条 gamma track summary 创建时：

```text
detected = false
hit_id = -1
scatter_count_total = 0
compton_count = 0
rayleigh_count = 0
first / last scatter position = NaN
first / last scatter region = none
det fields = NaN
gamma_source_* 按 track 类型填写
```

### M10.3 更新接口

提供：

```cpp
EnsureGammaTrackSummary(track)
RecordComptonScatter(track_id, pos, region_id)
RecordRayleighScatter(track_id, pos, region_id)
RecordDetectorHit(track_id, hit)
HasDetectorHit(track_id)
GetRecord()
```

## 完成标准

- event begin 正确重置。
- gamma track summary 创建时正确设置 `gamma_source_*`。
- scatter 更新接口按 track 正确维护 first / last。
- 同一 gamma track 只能记录一次有效 hit。
- 同一 event 内不同 gamma track 可分别记录 hit。
- 未写 CSV 或仅使用占位 writer。

## 不做

- 不判断 process name。
- 不判断 detector crossing。
- 不实现 CSV header。

---

# M11：Stepping 散射追踪

## 目标

实现所有 gamma track 的 Compton / Rayleigh 散射记录。

## 修改文件

- `include/SteppingAction.hh`
- `src/SteppingAction.cc`
- 必要时调整 `EventAction`
- 必要时接入 `RegionResolver`

## 任务

### M11.1 gamma track 过滤

处理所有：

```text
particle_name == gamma
```

### M11.2 process 过滤

计入：

```text
compt
Rayl
```

不计入：

- photoelectric effect；
- 非 gamma 粒子过程。

secondary gamma 的散射阶次从自身产生时从 `0` 开始，不继承 parent track 的散射阶次。

### M11.3 坐标与 region

- 散射位置使用 postStep position。
- region 归属使用 preStep volume。

### M11.4 事件保留边界

gamma track 是否进入正式 CSV 不在 M11 决定，由 detected gamma hit 决定。

## 完成标准

- 每条 gamma track 的 Compton / Rayleigh 计数正确。
- `scatter_count_total = compton_count + rayleigh_count`。
- first / last scatter 按 gamma track 更新正确。
- secondary gamma 不继承 parent track 的散射阶次。
- region 归属使用 preStep volume。

## 不做

- 不实现 detector crossing。
- 不写 CSV。

---

# M12：Detector crossing

## 目标

实现虚拟探测器平面穿越判定和 detector hit 记录。

## 修改文件

- `include/SteppingAction.hh`
- `src/SteppingAction.cc`
- `include/VirtualDetectorPlane.hh`
- `src/VirtualDetectorPlane.cc`
- 必要时调整 `EventAction`

## 任务

### M12.1 negative_z 判定

当 `accept_direction = negative_z`：

```text
preStep.z > detector_z
postStep.z <= detector_z
direction.z < 0
```

还必须满足：

```text
particle == gamma
```

### M12.2 线性插值

```text
t = (detector_z - pre_z) / (post_z - pre_z)
det_x = pre_x + t * (post_x - pre_x)
det_y = pre_y + t * (post_y - pre_y)
```

### M12.3 bounds 检查

使用当前 pose 下的 detector actual bounds。

### M12.4 hit 记录规则

同一 gamma track 只记录第一次有效 detector crossing。同一 event 内不同 gamma track 可分别记录 hit。

## 完成标准

- 探测面穿越点插值正确。
- pose offset 改变时 detector bounds 随之改变。
- 每条 gamma track 的第一有效 hit 被记录。
- 同一 event 可输出 0 行、1 行或多行 detected gamma hit。
- 未命中 gamma track 保持 `detected=false`。

## 不做

- 不模拟真实探测器响应。
- 不记录能量沉积。
- 不构建镜像探测器。

---

# M13：正式与 debug CSV 输出

## 目标

实现事件级 CSV 输出，包括正式模式和 debug 模式。旧 `CsvWriter` 只能复用打开文件、格式化和合并机制，header 与 row schema 必须按 `spec.md` 重写。

## 修改文件

- `include/CsvWriter.hh`
- `src/CsvWriter.cc`
- `include/EventAction.hh`
- `src/EventAction.cc`
- `include/RunAction.hh`
- `src/RunAction.cc`

## 任务

### M13.1 正式 CSV header

必须精确为：

```csv
event_id,hit_id,track_id,parent_id,is_primary_gamma,gamma_source_type,gamma_source_process,gamma_source_x,gamma_source_y,gamma_source_z,gamma_source_region_id,det_x,det_y,det_z,det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,first_scatter_region_id,last_scatter_region_id
```

### M13.2 Debug CSV header

必须精确为：

```csv
event_id,track_id,parent_id,is_primary_gamma,gamma_source_type,gamma_source_process,gamma_source_x,gamma_source_y,gamma_source_z,gamma_source_region_id,detected,hit_id,det_x,det_y,det_z,det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,first_scatter_region_id,last_scatter_region_id
```

### M13.3 写出规则

正式模式：

```text
写所有 detected gamma hit
```

Debug 模式：

```text
写所有 gamma track summary
```

未探测 gamma track 的 `hit_id = -1`，det 字段为 `NaN`。

## 完成标准

- 正式 CSV 不包含 `detected` 字段。
- Debug CSV 包含 `detected` 字段，并采用 gamma track summary schema。
- 不输出 termination 字段。
- 无散射字段按 NaN / none 写出。
- 正式 CSV 包含 `hit_id`、`track_id`、`parent_id`、`is_primary_gamma` 和 `gamma_source_*` 字段。
- `hit_id` 在同一 event 内从 `0` 开始递增。
- 单线程运行可生成最终 CSV。
- 不再输出旧 compact/debug header、`initial_energy`、`initial_dir_*` 或 `is_multiple_scatter` 字段。

## 不做

- 不实现多线程合并。
- 不写 metadata。
- 不生成统计图。

---

# M14：metadata.yaml 输出

## 目标

为每个 pose 写出 run-level metadata。旧 `RunAction` 的 `hits_profile_*` 文件名逻辑不得继续作为第二轮 metadata 或 run_id 来源。

## 修改文件

- `include/MetadataWriter.hh`
- `src/MetadataWriter.cc`
- `include/RunAction.hh`
- `src/RunAction.cc`
- `include/PoseRunController.hh`，如需要

## 任务

### M14.1 必要字段

写出：

```yaml
run_id: ...
output_csv: ...
model_type: ...
vehicle_model_id: ...
vehicle_geometry_file: ...
selected_target_component: ...
abnormal_target_type: ...
abnormal_target_region: ...
pose_id: ...
head_offset_x_mm: ...
head_offset_y_mm: ...
n_primary: ...
base_random_seed: ...
random_seed: ...
number_of_threads: ...
debug: ...
source: ...
collimator: ...
detector: ...
physics: ...
world:
  shape: box
  center_mm: [0.0, 0.0, 0.0]
  size_mm: [4000.0, 4000.0, 4000.0]
  material: G4_AIR
output_policy:
  existing_run_policy: fail
pose_index: ...
notes: ...
```

`random_seed` 只写一次，取值为该 pose run 最终实际执行时使用的 seed；`base_random_seed` 记录入口 YAML 中的基础 seed。

### M14.2 禁止字段

不得写出：

```text
vehicle_shift_x
vehicle_shift_y
```

### M14.3 run_id

推荐：

```text
run_id = {pose_id}_{model_type}_seed{random_seed}
```

## 完成标准

- 每个 pose 输出一个 `metadata.yaml`。
- metadata 与实际 CSV 文件名一致。
- metadata 中记录 source、detector、collimator、physics 配置。
- 不在事件 CSV 中重复写入 metadata 字段。
- metadata 记录每个 pose run 实际使用的 `random_seed`。
- 创建 `results/{run_id}` 时，若目录已存在且非空，必须 fail fast。

## 不做

- 不生成后处理结果。
- 不写 detector region mapping 或 depth region mapping 结果。

---

# M15：多线程输出合并

## 目标

实现多线程安全输出和 master 合并。旧 `RunAction` / `CsvWriter` 的线程临时文件机制可复用，但输出目录必须改为每个 `results/{run_id}/tmp/`。

## 修改文件

- `include/CsvWriter.hh`
- `src/CsvWriter.cc`
- `include/RunAction.hh`
- `src/RunAction.cc`
- 必要时调整 `PoseRunController`

## 任务

### M15.1 临时文件

每个 pose 输出目录下创建：

```text
tmp/
```

每个 worker 写独立临时 CSV。

### M15.2 合并

master run end 时合并：

- 最终 CSV 只保留一个 header；
- 保留全部数据行；
- 任一临时文件无法读取时报错；
- 最终文件无法写入时报错。

### M15.3 临时文件处理

正式模式：

```text
合并成功后删除临时 CSV
```

debug 模式：

```text
合并成功后保留临时 CSV
```

合并失败：

```text
保留所有临时 CSV 并报错
```

## 完成标准

- 多线程正式模式最终 `events.csv` header 唯一。
- 多线程 debug 模式最终 `events_debug.csv` header 唯一。
- 不再使用全局 `results/tmp/` 或 `hits_profile_*_threadN.csv` 命名。
- worker 不共享输出流。
- 正式模式合并成功后 tmp 中对应临时 CSV 被删除。
- debug 模式合并成功后 tmp 中对应临时 CSV 被保留。

## 不做

- 不让 worker 直接写最终 CSV。
- 不在内存中累积所有 event 后统一写出。

---

# M16：多 pose 运行控制与样例文件

## 目标

完成第二版基础链路：多个 pose 独立运行、独立输出，并补齐样例配置、README 和 legacy macros 清理。

## 修改文件

- `include/PoseRunController.hh`
- `src/PoseRunController.cc`
- `config/base/simulation_config_v2.yaml`
- `config/geometry/vehicle_roi_v04.yaml`
- `config/collimator/collimator_profiles.csv`
- `config/source/spectrum.csv`
- `README.md`
- `macros/*.mac`，如保留兼容示例
- `docs/acceptance_checklist.md`，如需要同步

## 任务

### M16.1 PoseRunController

按 PoseList 逐个执行：

```text
For each pose:
  generate pose_id
  generate run_id
  apply head_offset
  initialize geometry
  beamOn n_primary_per_pose
  write CSV
  write metadata
```

对外语义：

```text
每个 pose 是独立静态几何 Monte Carlo 统计。
```

### M16.2 样例配置

检查并整理可运行样例。样例文件应位于 `config/`，其中入口 YAML 为：

```text
config/base/simulation_config_v2.yaml
```

车辆 ROI、collimator profile 和 spectrum 文件的实际文件名由入口 YAML 指定。

样例源和探测器位置使用第一版链路验证值，但 README 和文档必须说明其样例性质。

### M16.3 README

README 至少说明，并移除第一轮 PMMA 主叙述作为默认运行方式：

- 项目目标；
- 依赖环境；
- 构建命令；
- batch 与 `--ui` 可视化运行命令；
- 入口 YAML 与被引用数据文件职责；
- pose list / grid 规则；
- pose_id 编码规则；
- formal / debug CSV 区别；
- metadata 作用；
- 第一阶段非目标。
- 本轮不实现位姿级 / 扫描级后处理。

## 完成标准

- 默认样例配置可端到端运行。
- 生成 `results/pose_x0_y0_normal_seed12345/events.csv`。
- 生成 `results/pose_x0_y0_normal_seed12345/metadata.yaml`。
- list mode 多 pose 可生成多个独立目录。
- grid mode 可生成笛卡尔积 pose。
- README 命令与实际程序入口一致。
- `macros/vis.mac` 可作为 `--ui` 的第二版可视化宏，但不得覆盖 YAML 主入口或设置 YAML 已覆盖的运行参数。
- `macros/run.mac` 和 `macros/run_mt.mac` 若保留，只能作为 legacy 示例。
- 多 pose 运行中每个 pose run 使用不同 seed，并在 metadata 中记录。
- `--ui` 多 pose 配置只显示第一个 pose，自动运行少量事件用于轨迹检查，且不写 CSV 或 metadata。

## 不做

- 不添加后处理绘图脚本。
- 不添加 pose-level summary。
- 不添加 scan-level summary。
- 不添加图像重建。
- 不添加真实探测器响应。
- 不添加连续运动扫描。

---

## 5. Deferred work

以下内容不属于第二版基础构建，除非后续规格明确更新：

- 整车 CAD 复现；
- 曲面真实车身；
- 真实探测器材料响应；
- sensitive detector 能量沉积 scoring；
- 图像重建；
- 后处理绘图脚本；
- pose-level summary；
- scan-level summary；
- 连续运动扫描；
- 运动模糊；
- 时间相关积分；
- 成像头旋转；
- 成像头 z 方向运动；
- 镜像准直器；
- 镜像探测器；
- 小数 offset；
- 自动大规模 campaign 管理系统。

---

## 6. 总体 Codex 工作流

建议先进行只读检查：

```text
Read docs/spec.md, docs/decisions.md, docs/architecture.md, and docs/milestones.md.
Do not write code yet.
Summarize the implementation order and identify ambiguities that block Milestone 0.
```

然后逐阶段推进：

```text
Read docs/spec.md, docs/decisions.md, docs/architecture.md, and docs/milestones.md.
Implement Milestone 0 only.
Do not implement Milestone 1 or later.
After implementation, summarize changed files, how to build, and deferred work.
```

每个里程碑完成后：

```text
Review the implementation against docs/milestones.md and docs/acceptance_checklist.md.
Check whether it implemented anything beyond the requested milestone.
If yes, identify the extra changes and suggest whether to revert them.
Do not write new code unless asked.
```
