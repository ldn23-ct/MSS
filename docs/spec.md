# 第二版车辆侧向背散射 ROI 仿真项目规格书

## 0. 文档定位

本文档定义第二版车辆侧向背散射 ROI Geant4 仿真项目的正式需求规格。

第二版项目不是第一版项目的小修补。第一版文件、代码和文档仅作为历史参考，用于复用项目组织经验、CSV 输出链路经验和多线程输出经验；第二版的几何对象、扫描方式、事件字段和配置入口以本文档为准。

第二版项目同时服务两条需求线：

| 需求线 | 目标 |
|---|---|
| A 线：项目摸底 | 判断固定车辆 ROI + 移动成像头条件下，原始探测器二维响应是否包含可解释结构信息。 |
| B 线：论文数据 | 记录被探测 gamma hit 的来源、散射阶次、过程计数、first / last scatter 空间位置和区域归因，用于多重散射性质分析。 |

本文档不定义后处理绘图、不定义图像重建算法、不定义真实探测器响应模型。本轮项目固定为搭建 Geant4 仿真程序并输出事件级数据；位姿级 / 扫描级数据、summary、图像、统计指标和后处理模块留到下一轮项目迭代。

### 0.1 本轮修订范围

本修订版在原规格基础上做一致性补充，不改变第二版核心目标。修订重点为：

- 明确 `vehicle_roi_v03.yaml` 的实际 schema 和组件字段；
- 明确 `simulation_config_v2.yaml`、YAML 解析依赖和 CLI 主入口；
- 明确 World 尺寸策略、输出目录策略和随机数可复现策略；
- 明确 collimator profile 的 `y` 向零位姿与 placement 规则；
- 明确正式 CSV / debug CSV 的字段边界，避免与后处理输出、位姿级输出、扫描级输出混淆；
- 明确事件追踪模型从 primary-history 改为 detector-hit 模型，并对每条 gamma track 维护自身散射历史；
- 明确本轮 Geant4 程序只输出事件级文件，位姿级 / 扫描级数据、summary、图表、统计指标和后处理模块不在本轮实现。


---

## 1. 项目基本信息

| 项目 | 内容 |
|---|---|
| 项目名称 | MSS 第二版 |
| 仿真类型 | 车辆侧向背散射 gamma Geant4 仿真 |
| 主要对象 | 车辆侧向 ROI 模型 |
| 扫描方式 | 固定车辆 ROI，移动成像头组件 |
| 成像头组成 | 射线源 + 狭缝准直器 + 虚拟探测器平面 |
| 粒子 | gamma |
| 事件定义 | 1 event = 1 primary gamma |
| 输出格式 | `events.csv` + `metadata.yaml` |
| 主配置入口 | YAML |
| 车辆几何配置 | 由 `config/base/simulation_config_v2.yaml` 中的 `vehicle.geometry_file` 指定，样例为 `config/geometry/vehicle_roi_v04.yaml` |
| 运行配置 | 主入口 YAML，样例为 `config/base/simulation_config_v2.yaml` |
| C++ 标准 | C++17 |
| 构建系统 | CMake |

---

## 2. 第二版总体目标

第二版目标是建立一个可运行、可配置、可检查的车辆侧向背散射仿真程序。

核心仿真对象为：

```text
固定车辆 ROI 模型
+ 移动成像头组件
+ 斜入射有限焦点笔形束
+ 狭缝准直器
+ 单个虚拟探测平面
```

程序需要输出被探测 gamma hit 的事件级统计量。本轮项目不实现位姿级 / 扫描级数据生成，也不实现后处理模块；事件级 CSV 与 metadata 只需要为下一轮后处理迭代保留足够输入。

事件级输出应能支持后续迭代分析：

- 探测器二维响应图；
- normal / abnormal 差异图；
- 探测能量分布；
- 单散射 / 多重散射比例；
- Compton / Rayleigh 过程贡献；
- first / last scatter 空间分布；
- first / last scatter region 归因；
- 位姿级和扫描级响应图。

第二版本轮不要求在 Geant4 程序内完成图像重建、统计图生成或任何后处理脚本。

### 2.1 Geant4 程序输出边界

第二版 Geant4 程序的基础输出边界为：

```text
每个 pose 输出：
  events.csv 或 events_debug.csv
  metadata.yaml
```

其中：

- `events.csv` / `events_debug.csv` 是事件级输出；
- `metadata.yaml` 是该 pose run 的运行条件记录；
- 本轮不输出位姿级响应图、扫描级响应图、normal / abnormal 差异图、统计指标、论文图表、pose-level summary CSV 或 scan-level summary CSV；
- 后处理模块不在本轮实现，留到下一轮项目迭代。


---

## 3. 坐标系

第二版采用统一 global 坐标系。

| 坐标轴 | 含义 |
|---|---|
| `x` | 车辆长度方向 / 成像头横向扫描相关方向，`+x` 指向车尾，`-x` 指向车头。 |
| `y` | 车辆高度方向，同时也是狭缝准直器 jaw 拉伸方向。 |
| `z` | 侧向入射深度方向，`z = 0` 为近侧车辆外表面，`+z` 指向车内和远侧车体。 |

车辆 ROI 本地原点定义为：

```text
O = B 柱中心线在近侧车体外表面的投影点
O = (x = 0, y = 0, z = 0)
```

背散射关系为：

```text
source / detector side: z < 0
near-side vehicle surface: z = 0
vehicle interior / far side: z > 0
```

被探测 gamma 是从车辆 ROI 方向返回成像头侧，并沿 `-z` 方向穿越虚拟探测器平面的 gamma。真实探测器不区分 gamma 是否为 source primary；只要 gamma track 满足虚拟探测器 crossing 条件，即视为 detected gamma hit。

---

## 4. 配置文件体系

第二版使用主入口 YAML 描述运行配置，并由该主入口引用车辆 ROI YAML、准直器 profile CSV 和能谱 CSV。

主入口样例路径为：

```text
config/base/simulation_config_v2.yaml
```

车辆 ROI、准直器 profile 和能谱文件也放在 `config/` 目录下，但具体文件名不作为代码硬编码约束，应由 `config/base/simulation_config_v2.yaml` 中的字段明确指定。

### 4.1 车辆 ROI YAML

车辆 ROI YAML 文件由主入口中的 `vehicle.geometry_file` 指定。正式车辆 ROI 样例可使用 `config/geometry/vehicle_roi_v04.yaml`；同一 `components[]` schema 下的对照模型也可作为输入，例如 `config/geometry/pmma_box.yaml`。该文件负责描述 VehicleROI-compatible geometry：

- VehicleROI 总范围；
- 几何组件；
- host / daughter 关系；
- normal / abnormal insert；
- material；
- region_id；
- AABB；
- placement 信息；
- overlap 检查需要的元数据。

### 4.2 `config/base/simulation_config_v2.yaml`

该文件是第二版正式主入口，负责描述仿真运行条件，并引用车辆 ROI YAML、准直器 profile CSV 和能谱 CSV：

- run 参数；
- source 参数；
- collimator 参数；
- detector 参数；
- pose / scan 参数；
- physics 参数；
- output 参数；
- normal / abnormal 模型选择。

宏命令仅保留必要入口能力，例如指定或切换入口 YAML 文件路径。凡是 `config/base/simulation_config_v2.yaml` 可以表达的配置项，不应再新增对应宏命令。

### 4.3 YAML 解析依赖

第二版主配置入口为 YAML。C++ 实现需要显式选择 YAML 解析器。

基础实现批准采用：

```text
yaml-cpp
```

依赖边界：

- 已批准使用 `yaml-cpp`；若项目仓库当前未包含该依赖，应在 M0/M1 阶段完成 CMake 接入，并在依赖不可用时给出明确构建错误；
- 不允许在实现过程中临时改回 Geant4 macro 作为主配置入口；
- macro / `SimulationMessenger` 仅保留用于指定或切换入口 YAML 文件路径的最小能力；source、detector、collimator、pose、output、seed、thread、target 等可由 YAML 表达的参数不再通过宏命令实现。

### 4.4 CLI 入口

第二版正式 batch CLI 入口固定为：

```bash
./build/MSS --config config/base/simulation_config_v2.yaml
```

可选兼容形式：

```bash
./build/MSS config/base/simulation_config_v2.yaml
```

可视化入口通过 `--ui` 开启：

```bash
./build/MSS --config config/base/simulation_config_v2.yaml --ui
```

`--ui` 使用同一个 YAML 配置构建 VehicleROI、当前 pose 成像头、准直器和虚拟探测器。UI 模式仅用于几何与轨迹检查，默认只显示 pose list 的第一个 pose，执行 `macros/vis.mac` 中的少量事件显示命令，不写 `events.csv`、`events_debug.csv` 或 `metadata.yaml`。

若位置参数与 `--config` 同时出现，应以 `--config` 指定的路径为准；若未指定配置文件，应报错并打印用法说明。


---

## 5. `config/base/simulation_config_v2.yaml` 规格

### 5.1 顶层结构

```yaml
schema_version: 2

run:
  random_seed: 12345
  number_of_threads: 8
  n_primary_per_pose: 10000
  debug: false

vehicle:
  geometry_file: config/geometry/vehicle_roi_v04.yaml
  model_type: normal
  selected_target_component: null
  abnormal_material: G4_POLYETHYLENE

pose:
  mode: list

  list:
    head_offset_x_mm: [0]
    head_offset_y_mm: [0]

  grid:
    x_offsets_mm: []
    y_offsets_mm: []

source:
  particle: gamma
  energy_mode: mono
  mono_energy_keV: 160.0
  spectrum_file: config/source/spectrum.csv

  source_pos_zero_mm: [0.0, 0.0, -185.0]
  incident_theta_deg: 45.0
  focal_spot_diameter_mm: 5.0

collimator:
  enable: true
  profile_file: config/collimator/collimator_profiles.csv
  profile_id: P001
  jaw_extrusion_length_y_mm: 120.0

detector:
  detector_z_zero_mm: -73.0
  detector_x_range_zero_mm: [53.0, 161.0]
  detector_y_range_zero_mm: [-50.0, 50.0]
  accept_direction: negative_z

physics:
  physics_list: G4EmLivermorePhysics
  production_cut_mm: 0.1

output:
  output_directory: results/simulations
  events_csv_name: events.csv
  metadata_yaml_name: metadata.yaml
  thread_tmp_directory: tmp
```

### 5.2 样例值说明

样例配置中的：

```yaml
source_pos_zero_mm: [0.0, 0.0, -185.0]
detector_z_zero_mm: -73.0
detector_x_range_zero_mm: [53.0, 161.0]
detector_y_range_zero_mm: [-50.0, 50.0]
```

来自第一版链路验证用数值。它们仅作为第二版程序构建、可视化和端到端输出测试的默认样例，不作为第二版最终成像头几何的不可修改物理常量。

### 5.3 字段约束

`config/base/simulation_config_v2.yaml` 的字段约束如下：

| 路径 | 约束 |
|---|---|
| `schema_version` | 必须为 `2`。 |
| `run.random_seed` | 非负整数。 |
| `run.number_of_threads` | 整数，且 `>= 1`。 |
| `run.n_primary_per_pose` | 整数，且 `> 0`。 |
| `run.debug` | bool。 |
| `vehicle.geometry_file` | 可读 VehicleROI-compatible YAML 文件路径；可指向车辆 ROI 或同 schema 对照模型。 |
| `vehicle.model_type` | `normal` 或 `abnormal`。 |
| `vehicle.selected_target_component` | `normal` 时可为 `null`；`abnormal` 时必须是当前 geometry YAML 中 `is_insert=true` 的 component name。若该 YAML 声明非空 recommended target list，还必须属于该 list。 |
| `vehicle.abnormal_material` | 已知 NIST 材料或项目自定义材料。 |
| `pose.mode` | `list` 或 `grid`。 |
| `pose.list.head_offset_x_mm/y_mm` | list mode 下必须长度相同；元素必须为整数 mm。 |
| `pose.grid.x_offsets_mm/y_offsets_mm` | grid mode 下元素必须为整数 mm。 |
| `source.particle` | 第一阶段仅支持 `gamma`。 |
| `source.energy_mode` | `mono` 或 `spectrum`。 |
| `source.mono_energy_keV` | mono 模式下必须为正且有限。 |
| `source.spectrum_file` | spectrum 模式下必须可读。 |
| `source.source_pos_zero_mm` | 长度为 3 的有限数值数组。 |
| `source.incident_theta_deg` | `0 < theta <= 90`。 |
| `source.focal_spot_diameter_mm` | 正数。 |
| `collimator.enable` | bool。 |
| `collimator.profile_file` | collimator 启用时必须可读。 |
| `collimator.profile_id` | collimator 启用时必须存在于 profile CSV。 |
| `collimator.jaw_extrusion_length_y_mm` | 正数。 |
| `detector.detector_z_zero_mm` | 有限数值。 |
| `detector.detector_x_range_zero_mm` | `[min,max]`，且 `min < max`。 |
| `detector.detector_y_range_zero_mm` | `[min,max]`，且 `min < max`。 |
| `detector.accept_direction` | 第一阶段仅支持 `negative_z`。 |
| `physics.production_cut_mm` | 正数。 |
| `output.output_directory` | 不存在时应创建；存在时按 17.3 策略处理。 |

### 5.4 样例配置文件的作用

仓库中的 `config/base/simulation_config_v2.yaml` 是最小可运行样例。它的职责是：

- 支持 M1/M2 读取配置；
- 支持零位姿端到端测试；
- 支持 source / collimator / detector / output 链路验证。

该样例中的第一版继承数值不应写死进 C++ 源码。


---

## 6. 车辆 ROI 模型

### 6.1 总体范围

第二版车辆 ROI 模型由 `vehicle.geometry_file` 指定的 VehicleROI-compatible YAML 描述。车辆 ROI 样例保持以下默认 ROI 范围；PMMA box 等 control geometry 可复用同一范围作为对照：

```text
x ∈ [-900, 1300] mm
y ∈ [0, 1250] mm
z ∈ [0, 1450] mm
```

对应 VehicleROI box：

```text
center = [200, 625, 725] mm
size   = [2200, 1250, 1450] mm
material = G4_AIR
region_id = vehicle_background_air
```

### 6.2 建模原则

车辆 ROI 模型采用基本 Geant4 几何体，不追求 CAD 级还原。

要求：

- 车辆 ROI 在所有 scan pose 中保持固定；
- 所有实体 volume 不允许 overlap；
- 相邻材料层允许贴边；
- insert 必须完全位于唯一宿主 volume 内；
- normal / abnormal 几何完全一致，只替换指定 insert 的 material 和 region_id；
- 未被具体结构占据的车辆 ROI 空隙由 VehicleROI 空气母体承载，region_id 为 `vehicle_background_air`。

### 6.3 主要结构

车辆 ROI 至少包含：

- 近侧车门；
- 远侧车门；
- 近侧 / 远侧车窗；
- 近侧 / 远侧 B 柱；
- 近侧 / 远侧 C 柱；
- 乘员舱空气；
- 前排 / 后排座椅；
- 后备箱空气；
- 可选 abnormal insert。

### 6.4 normal / abnormal 规则

`vehicle.model_type` 支持：

```text
normal
abnormal
```

normal 运行：

```text
insert material = host material
insert region_id = host region_id
```

abnormal 运行：

```text
selected_target_component 对应 insert:
  material = abnormal_material
  region_id = target

其他 insert:
  material = host material
  region_id = host region_id
```

第一阶段每个 abnormal run 只启用一个 selected target component。

若：

```yaml
vehicle:
  model_type: abnormal
  selected_target_component: null
```

则配置读取阶段应报错停止。

若：

```yaml
vehicle:
  model_type: normal
  selected_target_component: null
```

则按 normal baseline 运行。

### 6.5 材料

默认材料表：

| 语义 | Geant4 材料 |
|---|---|
| 空气 | `G4_AIR` |
| 钢 / 高强钢代理 | `G4_Fe` |
| 车窗玻璃 | `G4_GLASS_PLATE` |
| 门内饰 / PP 类塑料 | `G4_POLYPROPYLENE` |
| 低密度座椅泡沫 | `Vehicle_PU_Foam` |
| 默认 abnormal target | `G4_POLYETHYLENE` |
| 可选高 Z target | `G4_W` |

`Vehicle_PU_Foam` 为自定义材料：

```cpp
auto* foam = new G4Material("Vehicle_PU_Foam", 0.055*g/cm3, 4);
foam->AddElement(nist->FindOrBuildElement("C"), 0.60);
foam->AddElement(nist->FindOrBuildElement("H"), 0.08);
foam->AddElement(nist->FindOrBuildElement("O"), 0.28);
foam->AddElement(nist->FindOrBuildElement("N"), 0.04);
```

### 6.6 region_id

几何构建时必须为每个 logical volume 或 placement 建立 region_id 映射。

常用 region_id 包括：

```text
vehicle_background_air
near_door_outer_metal
near_door_cavity_air
near_door_reinforcement
near_door_inner_metal
near_door_trim
far_door_trim
far_door_inner_metal
far_door_cavity_air
far_door_reinforcement
far_door_outer_metal
near_window_glass
far_window_glass
near_b_pillar_metal
near_c_pillar_metal
far_b_pillar_metal
far_c_pillar_metal
cabin_air
seat_foam
seat_frame_metal
rear_trunk_air
target
other
none
```

### 6.7 `vehicle_roi_v03.yaml` 实际 schema

`vehicle_roi_v03.yaml` 当前采用以下顶层结构：

```yaml
schema:
  name: vehicle_roi_model
  version: v03_materials_yaml_1
  format: yaml
metadata: {...}
units: {...}
coordinate_system: {...}
roi: {...}
geant4_placement_rules: {...}
materials: {...}
model_modes: {...}
regions: {...}
components:
  - name: VehicleROI
    host: World
    shape: box
    center_mm: [200.0, 625.0, 725.0]
    size_mm: [2200.0, 1250.0, 1450.0]
    material: G4_AIR
    region_id: vehicle_background_air
    is_insert: false
    role: roi_air_mother
    half_size_mm: [1100.0, 625.0, 725.0]
    aabb_mm:
      x: [-900.0, 1300.0]
      y: [0.0, 1250.0]
      z: [0.0, 1450.0]
    placement_center_in_host_mm: [0.0, 0.0, 0.0]
validation: {...}
```

实现应按该 schema 读取，而不是另行假设 `vehicle_roi:` 顶层字段。

### 6.8 component 字段规范

每个 `components[]` 条目使用以下字段：

| 字段 | 类型 | 必须 | 说明 |
|---|---|---|---|
| `name` | string | 是 | component 唯一名称。 |
| `host` | string | 是 | 宿主 volume 名称；根 ROI 的 host 为 `World`。 |
| `shape` | string | 是 | 第一阶段仅支持 `box`。 |
| `center_mm` | array[3] | 是 | component 在 VehicleROI 坐标系中的 global center。 |
| `size_mm` | array[3] | 是 | box 全尺寸，不是 half length。 |
| `material` | string 或 object | 是 | 普通 component 为 string；insert 可为 `normal/abnormal` object。 |
| `region_id` | string 或 object | 是 | 普通 component 为 string；insert 可为 `normal/abnormal` object。 |
| `is_insert` | bool | 是 | 是否是 abnormal 可替换 insert。 |
| `role` | string | 是 | 语义角色，用于检查和后处理分组。 |
| `half_size_mm` | array[3] | 是 | `size_mm * 0.5`，用于构建检查。 |
| `aabb_mm` | object | 是 | x/y/z 三轴 `[min,max]`，用于 overlap 和 containment 检查。 |
| `placement_center_in_host_mm` | array[3] | 是 | 在 host 坐标系下的 placement center。 |

材料和 region 的读取规则：

```text
普通 component:
  material: string
  region_id: string

insert component:
  material.normal: normal 模式材料
  material.abnormal: abnormal 模式材料默认值
  region_id.normal: normal 模式 region_id
  region_id.abnormal: abnormal 模式 region_id，通常为 target
```

### 6.9 VehicleROI 组件清单

当前 `vehicle_roi_v03.yaml` 包含 45 个 components，其中 `VehicleROI` 为 ROI 空气母体，其余 44 个为车辆结构或 insert。基础实现应至少能读取并构建下表全部 component。

| name | host | role | center_mm | size_mm | material | region_id | is_insert |
|---|---|---|---|---|---|---|---|
| `near_front_door_outer_skin` | `VehicleROI` | `door` | `[-430.0, 425.0, 0.5]` | `[740.0, 550.0, 1.0]` | `G4_Fe` | `near_door_outer_metal` | `false` |
| `near_front_door_cavity_air` | `VehicleROI` | `door` | `[-430.0, 425.0, 33.0]` | `[740.0, 550.0, 64.0]` | `G4_AIR` | `near_door_cavity_air` | `false` |
| `near_front_door_beam` | `near_front_door_cavity_air` | `door` | `[-430.0, 480.0, 40.0]` | `[600.0, 80.0, 20.0]` | `G4_Fe` | `near_door_reinforcement` | `false` |
| `near_front_door_insert` | `near_front_door_cavity_air` | `door_insert` | `[-430.0, 320.0, 35.0]` | `[250.0, 180.0, 35.0]` | `normal=G4_AIR; abnormal=G4_POLYETHYLENE` | `normal=near_door_cavity_air; abnormal=target` | `true` |
| `near_front_door_inner_metal` | `VehicleROI` | `door` | `[-430.0, 425.0, 65.6]` | `[740.0, 550.0, 1.2]` | `G4_Fe` | `near_door_inner_metal` | `false` |
| `near_front_door_trim` | `VehicleROI` | `door` | `[-430.0, 425.0, 78.1]` | `[740.0, 550.0, 23.8]` | `G4_POLYPROPYLENE` | `near_door_trim` | `false` |
| `near_rear_door_outer_skin` | `VehicleROI` | `door` | `[430.0, 425.0, 0.5]` | `[740.0, 550.0, 1.0]` | `G4_Fe` | `near_door_outer_metal` | `false` |
| `near_rear_door_cavity_air` | `VehicleROI` | `door` | `[430.0, 425.0, 33.0]` | `[740.0, 550.0, 64.0]` | `G4_AIR` | `near_door_cavity_air` | `false` |
| `near_rear_door_beam` | `near_rear_door_cavity_air` | `door` | `[430.0, 480.0, 40.0]` | `[600.0, 80.0, 20.0]` | `G4_Fe` | `near_door_reinforcement` | `false` |
| `near_rear_door_insert` | `near_rear_door_cavity_air` | `door_insert` | `[430.0, 320.0, 35.0]` | `[250.0, 180.0, 35.0]` | `normal=G4_AIR; abnormal=G4_POLYETHYLENE` | `normal=near_door_cavity_air; abnormal=target` | `true` |
| `near_rear_door_inner_metal` | `VehicleROI` | `door` | `[430.0, 425.0, 65.6]` | `[740.0, 550.0, 1.2]` | `G4_Fe` | `near_door_inner_metal` | `false` |
| `near_rear_door_trim` | `VehicleROI` | `door` | `[430.0, 425.0, 78.1]` | `[740.0, 550.0, 23.8]` | `G4_POLYPROPYLENE` | `near_door_trim` | `false` |
| `far_front_door_trim` | `VehicleROI` | `door` | `[-430.0, 425.0, 1371.9]` | `[740.0, 550.0, 23.8]` | `G4_POLYPROPYLENE` | `far_door_trim` | `false` |
| `far_front_door_inner_metal` | `VehicleROI` | `door` | `[-430.0, 425.0, 1384.4]` | `[740.0, 550.0, 1.2]` | `G4_Fe` | `far_door_inner_metal` | `false` |
| `far_front_door_cavity_air` | `VehicleROI` | `door` | `[-430.0, 425.0, 1417.0]` | `[740.0, 550.0, 64.0]` | `G4_AIR` | `far_door_cavity_air` | `false` |
| `far_front_door_beam` | `far_front_door_cavity_air` | `door` | `[-430.0, 480.0, 1410.0]` | `[600.0, 80.0, 20.0]` | `G4_Fe` | `far_door_reinforcement` | `false` |
| `far_front_door_insert` | `far_front_door_cavity_air` | `door_insert` | `[-430.0, 320.0, 1415.0]` | `[250.0, 180.0, 35.0]` | `normal=G4_AIR; abnormal=G4_POLYETHYLENE` | `normal=far_door_cavity_air; abnormal=target` | `true` |
| `far_front_door_outer_skin` | `VehicleROI` | `door` | `[-430.0, 425.0, 1449.5]` | `[740.0, 550.0, 1.0]` | `G4_Fe` | `far_door_outer_metal` | `false` |
| `far_rear_door_trim` | `VehicleROI` | `door` | `[430.0, 425.0, 1371.9]` | `[740.0, 550.0, 23.8]` | `G4_POLYPROPYLENE` | `far_door_trim` | `false` |
| `far_rear_door_inner_metal` | `VehicleROI` | `door` | `[430.0, 425.0, 1384.4]` | `[740.0, 550.0, 1.2]` | `G4_Fe` | `far_door_inner_metal` | `false` |
| `far_rear_door_cavity_air` | `VehicleROI` | `door` | `[430.0, 425.0, 1417.0]` | `[740.0, 550.0, 64.0]` | `G4_AIR` | `far_door_cavity_air` | `false` |
| `far_rear_door_beam` | `far_rear_door_cavity_air` | `door` | `[430.0, 480.0, 1410.0]` | `[600.0, 80.0, 20.0]` | `G4_Fe` | `far_door_reinforcement` | `false` |
| `far_rear_door_insert` | `far_rear_door_cavity_air` | `door_insert` | `[430.0, 320.0, 1415.0]` | `[250.0, 180.0, 35.0]` | `normal=G4_AIR; abnormal=G4_POLYETHYLENE` | `normal=far_door_cavity_air; abnormal=target` | `true` |
| `far_rear_door_outer_skin` | `VehicleROI` | `door` | `[430.0, 425.0, 1449.5]` | `[740.0, 550.0, 1.0]` | `G4_Fe` | `far_door_outer_metal` | `false` |
| `near_front_window_glass` | `VehicleROI` | `window_glass` | `[-430.0, 925.0, 2.0]` | `[650.0, 400.0, 4.0]` | `G4_GLASS_PLATE` | `near_window_glass` | `false` |
| `near_rear_window_glass` | `VehicleROI` | `window_glass` | `[430.0, 925.0, 2.0]` | `[650.0, 400.0, 4.0]` | `G4_GLASS_PLATE` | `near_window_glass` | `false` |
| `far_front_window_glass` | `VehicleROI` | `window_glass` | `[-430.0, 925.0, 1448.0]` | `[650.0, 400.0, 4.0]` | `G4_GLASS_PLATE` | `far_window_glass` | `false` |
| `far_rear_window_glass` | `VehicleROI` | `window_glass` | `[430.0, 925.0, 1448.0]` | `[650.0, 400.0, 4.0]` | `G4_GLASS_PLATE` | `far_window_glass` | `false` |
| `near_b_pillar` | `VehicleROI` | `pillar` | `[0.0, 650.0, 45.0]` | `[100.0, 1000.0, 90.0]` | `G4_Fe` | `near_b_pillar_metal` | `false` |
| `near_c_pillar` | `VehicleROI` | `pillar` | `[900.0, 650.0, 45.0]` | `[120.0, 1000.0, 90.0]` | `G4_Fe` | `near_c_pillar_metal` | `false` |
| `far_b_pillar` | `VehicleROI` | `pillar` | `[0.0, 650.0, 1405.0]` | `[100.0, 1000.0, 90.0]` | `G4_Fe` | `far_b_pillar_metal` | `false` |
| `far_c_pillar` | `VehicleROI` | `pillar` | `[900.0, 650.0, 1405.0]` | `[120.0, 1000.0, 90.0]` | `G4_Fe` | `far_c_pillar_metal` | `false` |
| `cabin_air` | `VehicleROI` | `cabin_air_host` | `[45.0, 625.0, 725.0]` | `[1590.0, 1050.0, 1250.0]` | `G4_AIR` | `cabin_air` | `false` |
| `front_seat_base_foam` | `cabin_air` | `seat` | `[-430.0, 250.0, 600.0]` | `[450.0, 140.0, 420.0]` | `Vehicle_PU_Foam` | `seat_foam` | `false` |
| `front_seat_back_foam` | `cabin_air` | `seat` | `[-430.0, 625.0, 820.0]` | `[450.0, 610.0, 120.0]` | `Vehicle_PU_Foam` | `seat_foam` | `false` |
| `front_seat_frame` | `cabin_air` | `seat` | `[-430.0, 160.0, 600.0]` | `[420.0, 30.0, 340.0]` | `G4_Fe` | `seat_frame_metal` | `false` |
| `front_seat_insert` | `front_seat_back_foam` | `seat_insert` | `[-430.0, 520.0, 820.0]` | `[250.0, 200.0, 60.0]` | `normal=Vehicle_PU_Foam; abnormal=G4_POLYETHYLENE` | `normal=seat_foam; abnormal=target` | `true` |
| `rear_seat_base_foam` | `cabin_air` | `seat` | `[430.0, 250.0, 600.0]` | `[550.0, 140.0, 420.0]` | `Vehicle_PU_Foam` | `seat_foam` | `false` |
| `rear_seat_back_foam` | `cabin_air` | `seat` | `[430.0, 625.0, 850.0]` | `[550.0, 610.0, 120.0]` | `Vehicle_PU_Foam` | `seat_foam` | `false` |
| `rear_seat_frame` | `cabin_air` | `seat` | `[430.0, 160.0, 600.0]` | `[500.0, 30.0, 340.0]` | `G4_Fe` | `seat_frame_metal` | `false` |
| `rear_seat_insert` | `rear_seat_back_foam` | `seat_insert` | `[430.0, 520.0, 850.0]` | `[300.0, 200.0, 60.0]` | `normal=Vehicle_PU_Foam; abnormal=G4_POLYETHYLENE` | `normal=seat_foam; abnormal=target` | `true` |
| `cabin_air_package_insert` | `cabin_air` | `cabin_package_insert` | `[0.0, 420.0, 650.0]` | `[220.0, 220.0, 220.0]` | `normal=G4_AIR; abnormal=G4_POLYETHYLENE` | `normal=cabin_air; abnormal=target` | `true` |
| `rear_trunk_air` | `VehicleROI` | `trunk_air_host` | `[1130.0, 500.0, 725.0]` | `[340.0, 700.0, 1250.0]` | `G4_AIR` | `rear_trunk_air` | `false` |
| `rear_trunk_package_insert` | `rear_trunk_air` | `trunk_package_insert` | `[1125.0, 350.0, 700.0]` | `[250.0, 250.0, 250.0]` | `normal=G4_AIR; abnormal=G4_POLYETHYLENE` | `normal=rear_trunk_air; abnormal=target` | `true` |

### 6.10 推荐 abnormal target component

第一阶段 abnormal run 每次只启用一个 insert。推荐 target component 为：

- `near_front_door_insert`
- `near_rear_door_insert`
- `far_front_door_insert`
- `far_rear_door_insert`
- `front_seat_insert`
- `rear_seat_insert`
- `cabin_air_package_insert`
- `rear_trunk_package_insert`

对车辆 ROI 样例，若 `selected_target_component` 不在上述列表中，配置读取阶段应报错。对 `recommended_single_target_components: []` 的 control geometry，不支持 abnormal target 选择；例如 `pmma_box.yaml` 应使用 `model_type: normal` 与 `selected_target_component: null`。

### 6.11 AABB / placement / overlap 规则

`vehicle_roi_v03.yaml` 中的 AABB 和 placement 信息用于实现期检查，不是替代 Geant4 几何构建的独立几何系统。

规则：

```text
G4Box half length = size_mm * 0.5
component global center = center_mm
component placement in host = placement_center_in_host_mm
positive-volume overlap among sibling components = forbidden
touching surfaces = allowed
optional engineering gap = 0.01 mm, only if implementation needs to avoid numerical boundary ambiguity
```

必须检查：

- host 名称存在；
- component 完全位于 host 内；
- 同一 host 下非嵌套 component 不存在正体积 overlap；
- insert 完全位于唯一 host 内；
- `aabb_mm` 与 `center_mm/size_mm` 一致；
- `half_size_mm` 与 `size_mm` 一致。

### 6.12 World 几何

World 不由 `vehicle_roi_v03.yaml` 显式描述，但 Geant4 实现必须构建。

第二版基础实现使用固定 World：

```text
World shape = box
World material = G4_AIR
World center_mm = [0.0, 0.0, 0.0]
World size_mm = [4000.0, 4000.0, 4000.0]
```

World 必须包含：

```text
VehicleROI
Source zero/actual position
Collimator jaw 全部 pose 下的包围盒
VirtualDetectorPlane 全部 pose 下的包围盒
```

配置读取或几何构建阶段必须检查所有 pose 下的 VehicleROI 和成像头组件均位于固定 World 内。若任一 pose 下 source、detector plane 或 collimator jaw 超出 World，程序必须 fail fast。

`metadata.yaml` 应记录固定 World 的 shape、center、size 和 material。


---

## 7. 成像头模型

### 7.1 总体定义

第二版成像头是刚性组件组：

```text
ImagingHead = Source + SlitCollimator + VirtualDetectorPlane
```

成像头整体在 `x-y` 平面内离散平移。

车辆 ROI 不随 pose 移动。

成像头内 source、collimator、detector 共享同一个 offset：

```text
head_offset = (head_offset_x, head_offset_y, 0)
```

### 7.2 零位姿 global 坐标 + offset

所有成像头组件首先以零位姿 global 坐标给出。

实际坐标为：

```text
x_actual = x_zero + head_offset_x
y_actual = y_zero + head_offset_y
z_actual = z_zero
```

第二版暂不支持：

- 成像头旋转；
- 成像头 z 方向移动；
- 连续运动；
- 运动模糊；
- 时间相关积分。

---

## 8. 扫描 pose

### 8.1 pose 字段

每个扫描状态由以下量定义：

```text
pose_id
head_offset_x_mm
head_offset_y_mm
```

`pose_id` 不由用户直接写入，而是由 offset 自动生成。

### 8.2 offset 取值限制

第一阶段仅支持整数 mm offset。

暂不支持小数 offset。

### 8.3 pose_id 编码规则

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

| `head_offset_x_mm` | `head_offset_y_mm` | `pose_id` |
|---:|---:|---|
| `0` | `0` | `pose_x0_y0` |
| `2` | `1` | `pose_x2_y1` |
| `-2` | `1` | `pose_xm2_y1` |
| `2` | `-1` | `pose_x2_ym1` |
| `-10` | `-4` | `pose_xm10_ym4` |
| `1111` | `0` | `pose_x1111_y0` |

### 8.4 list mode

list mode 用于显式输入若干成对偏置。

```yaml
pose:
  mode: list
  list:
    head_offset_x_mm: [0, 2, 3, 10]
    head_offset_y_mm: [0, 1, 4, 2]
```

规则：

```text
第 i 个 x offset 与第 i 个 y offset 配对。
两个数组长度必须相同。
```

若长度不同，配置读取阶段报错停止。

### 8.5 grid mode

grid mode 用于从 x offset 和 y offset 的笛卡尔积自动生成 pose。

```yaml
pose:
  mode: grid
  grid:
    x_offsets_mm: [-10, 0, 10]
    y_offsets_mm: [0, 5]
```

生成：

```text
(-10, 0)
(-10, 5)
(0, 0)
(0, 5)
(10, 0)
(10, 5)
```

---

## 9. 射线源

### 9.1 粒子与 event 定义

每个 event 产生一个 primary gamma：

```text
1 event = 1 primary gamma
```

### 9.2 源位置

源位置由 YAML 给出零位姿坐标：

```yaml
source:
  source_pos_zero_mm: [0.0, 0.0, -185.0]
```

实际位置为：

```text
source_pos_actual = source_pos_zero + (head_offset_x, head_offset_y, 0)
```

### 9.3 入射方向

第二版源模型为斜入射有限焦点笔形束，不再使用第一版目标平面采样锥束。

入射方向位于 global `x-z` 平面内，与 `+x` 轴正方向成 `theta` 角：

```text
incident_dir = (cos(theta), 0, sin(theta))
```

合法范围：

```text
0° < theta <= 90°
```

默认样例值：

```yaml
incident_theta_deg: 45.0
```

### 9.4 焦点面

焦点面为过 `source_pos_actual` 的圆形平面，该平面垂直于 `incident_dir`。

圆形焦点面内均匀采样 gamma 起点。

默认样例焦点直径：

```yaml
focal_spot_diameter_mm: 5.0
```

焦点面采样基为：

```text
u = (0, 1, 0)
v = (-sin(theta), 0, cos(theta))
```

采样：

```text
r = R * sqrt(xi_1)
phi = 2π * xi_2
R = focal_spot_diameter_mm / 2
```

起点：

```text
gamma_start = source_pos_actual
            + r * cos(phi) * u
            + r * sin(phi) * v
```

方向：

```text
gamma_dir = incident_dir
```

### 9.5 能量模式

第二版保留第一版的能量模式：

```text
mono
spectrum
```

mono 模式：

```yaml
source:
  energy_mode: mono
  mono_energy_keV: 160.0
```

spectrum 模式：

```yaml
source:
  energy_mode: spectrum
  spectrum_file: config/source/spectrum.csv
```

spectrum CSV 格式：

```csv
energy_keV,weight
40,0.01
45,0.03
50,0.06
```

验证规则：

- `energy_keV` 必须为正且有限；
- `weight` 必须非负且有限；
- 文件至少包含一行有效数据；
- 权重总和必须大于 0；
- 程序内部归一化并构建 CDF。

---

## 10. 狭缝准直器

### 10.1 总体原则

第二版准直器为成像头组件之一。

准直器位于车辆 ROI 与虚拟探测器平面之间。

准直器由外部 CSV profile 定义。

第二版不构建镜像准直器。

### 10.2 CSV 表头

准直器 profile 文件基础必需列为：

```csv
profile_id,jaw_id,vertex_id,x_mm,z_mm
```

当前样例文件中包含额外的 `y_mm` 列：

```csv
profile_id,jaw_id,vertex_id,x_mm,y_mm,z_mm
```

解析规则：

- `profile_id`、`jaw_id`、`vertex_id`、`x_mm`、`z_mm` 为必需列；
- `y_mm` 为可选列；
- 若存在 `y_mm`，它定义该顶点所在 jaw 的零位姿 global y 坐标；
- 若不存在 `y_mm`，默认 `y_zero_mm = 0`；
- 同一 jaw 内所有顶点的 `y_mm` 必须相同；
- UTF-8 BOM 应被容忍并去除。

字段含义：

| 字段 | 含义 |
|---|---|
| `profile_id` | profile ID。 |
| `jaw_id` | jaw 编号，格式为 `jaw_0 ... jaw_{M-1}`。 |
| `vertex_id` | 同一 jaw 内顶点编号。 |
| `x_mm` | 零位姿 global x 坐标，单位 mm。 |
| `y_mm` | 可选。零位姿 global y 坐标，单位 mm。 |
| `z_mm` | 零位姿 global z 坐标，单位 mm。 |

### 10.3 jaw 规则

每个 profile 包含可变数量的 jaw。

若某个 profile 包含 `M` 块 jaw，则：

```text
M >= 1
jaw_id = jaw_0, jaw_1, ..., jaw_{M-1}
```

每块 jaw：

```text
N >= 3
vertex_id = 0, 1, ..., N-1
```

必须拒绝：

- 文件无法打开；
- 找不到指定 profile；
- 缺少必要列；
- 必要字段为空；
- jaw 编号不连续；
- jaw 编号重复；
- vertex_id 缺失、重复或不连续；
- 坐标非数值、NaN 或 Inf；
- 多边形面积为 0；
- 多边形非凸；
- 连续共线点。

### 10.4 Geant4 构建

每块 jaw 使用：

```text
G4ExtrudedSolid
```

输入点为零位姿 global `x-z` 坐标：

```text
(x_mm, z_mm)
```

映射：

| 输入物理量 | `G4ExtrudedSolid` local 坐标 |
|---|---|
| global x | local x |
| global z | local y |
| global y | local z 拉伸方向 |

jaw 沿 global `y` 方向拉伸。

默认样例拉伸长度：

```yaml
jaw_extrusion_length_y_mm: 120.0
```

扫描 pose 下：

```text
x_actual = x_zero + head_offset_x
z_actual = z_zero
y_actual = y_zero + head_offset_y
```

### 10.5 占位 profile

第二版样例配置可以暂用第一版 `P001` 作为占位 slit profile，用于构建、可视化和输出链路测试。

该占位 profile 不代表第二版最终成像头准直器几何。

### 10.6 y 向 placement 约定

准直器 jaw 的 `x-z` 多边形由 CSV 中的 `x_mm/z_mm` 描述，jaw 沿 global `y` 方向拉伸。

零位姿下：

```text
jaw_center_y_zero = y_mm, if CSV contains y_mm
jaw_center_y_zero = 0,    otherwise
```

pose 下：

```text
jaw_center_y_actual = jaw_center_y_zero + head_offset_y
jaw_x_actual = jaw_x_zero + head_offset_x
jaw_z_actual = jaw_z_zero
```

`jaw_extrusion_length_y_mm` 表示沿 global y 方向的全长，而不是 half length。

若使用 `G4ExtrudedSolid`，其 local z 为拉伸轴。实现可采用以下等价方式之一：

1. 将 CSV 的 `x/z` 多边形映射到 `G4ExtrudedSolid` local `x/y`，local `z` 作为拉伸轴，然后通过 rotation/placement 使 local z 对齐 global y；
2. 构建时在局部坐标中完成 `global x -> local x`、`global z -> local y`、`global y -> local z` 的轴映射。

无论采用哪种实现，最终 global 几何必须满足：

```text
profile 多边形位于 global x-z 平面
jaw 厚度/拉伸方向为 global y
head_offset_x 只影响 global x
head_offset_y 只影响 global y
z 不随 pose 改变
```


---

## 11. 虚拟探测器平面

### 11.1 探测器类型

第二版探测器为单个理想虚拟探测平面。

不模拟真实探测器材料响应。

不设置真实 sensitive detector。

探测记录来自 step 穿越判定。

第二版不构建镜像探测器。

### 11.2 几何关系

背散射结构中：

```text
VehicleROI
→ SlitCollimator
→ VirtualDetectorPlane
```

准直器夹在车辆 ROI 与虚拟探测平面之间。

### 11.3 探测器零位姿

探测器平面平行于 global `x-y` 平面。

样例配置：

```yaml
detector:
  detector_z_zero_mm: -73.0
  detector_x_range_zero_mm: [53.0, 161.0]
  detector_y_range_zero_mm: [-50.0, 50.0]
  accept_direction: negative_z
```

### 11.4 pose 下的实际接收范围

```text
det_x_min_actual = det_x_min_zero + head_offset_x
det_x_max_actual = det_x_max_zero + head_offset_x

det_y_min_actual = det_y_min_zero + head_offset_y
det_y_max_actual = det_y_max_zero + head_offset_y

det_z_actual = detector_z_zero
```

### 11.5 探测面穿越条件

当：

```yaml
accept_direction: negative_z
```

探测判定为：

```text
particle == gamma
preStep.z > detector_z
postStep.z <= detector_z
direction.z < 0
crossing point inside detector x-y bounds
```

穿越点线性插值：

```text
t = (detector_z - pre_z) / (post_z - pre_z)

det_x = pre_x + t * (post_x - pre_x)
det_y = pre_y + t * (post_y - pre_y)
det_z = detector_z
```

同一 gamma track 中，第一次有效 detector crossing 被记录。该 gamma track 后续再次穿越探测面时不再产生额外正式 CSV 行。

同一 event 内不同 gamma track 均可记录为不同 hit。因此同一 event 可输出 0 行、1 行或多行 detected gamma hit。

---

## 12. 物理过程

### 12.1 Physics List

第二版默认使用：

```text
G4EmLivermorePhysics
```

### 12.2 Production cut

默认：

```text
0.1 mm
```

配置：

```yaml
physics:
  physics_list: G4EmLivermorePhysics
  production_cut_mm: 0.1
```

---

## 13. 事件追踪逻辑

### 13.1 基本模型

第二版事件追踪模型采用：

```text
detector-hit 模型 + per-gamma-track scatter history
```

基本定义：

```text
1 event = 1 source primary gamma
1 row in events.csv = 1 detected gamma hit
```

一次 event 中允许产生多个 gamma track，也允许产生多个 detected gamma hit。每个 detected gamma hit 由以下二元组唯一标识：

```text
event_id + hit_id
```

`hit_id` 在同一 `event_id` 内从 `0` 开始，按有效 detector crossing 被记录的顺序递增。

### 13.2 追踪对象

探测器记录对象为所有 gamma track：

```text
particle_name == gamma
```

电子、正电子和其他非 gamma track 不进入事件级输出。非 gamma track 的过程也不计入 gamma track 的散射历史。

### 13.3 detected 与 undetected

正式 `events.csv`：

```text
只记录 detected gamma hit
```

Debug CSV：

```text
1 row = 1 gamma track summary
```

其中：

- `detected = 1` 表示该 gamma track 至少一次有效穿越探测平面；
- `detected = 0` 表示该 gamma track 未有效穿越探测平面。

Debug CSV 会明显增大，因为所有 gamma track 都可能被记录。

### 13.4 gamma 来源定义

每条 gamma track 必须记录来源字段：

```text
gamma_source_type
gamma_source_process
gamma_source_x
gamma_source_y
gamma_source_z
gamma_source_region_id
```

primary gamma：

```text
gamma_source_type = primary
gamma_source_process = primary_generator
gamma_source_x/y/z = 该 primary gamma 的实际起点 gamma_start
gamma_source_region_id = source
```

其中 `gamma_start` 是焦点面随机采样后的实际 primary gamma 起点，不能简化为 YAML 中的 `source_pos_actual`。

secondary gamma：

```text
gamma_source_type = secondary
gamma_source_process = track->GetCreatorProcess()->GetProcessName()
gamma_source_x/y/z = track->GetVertexPosition()
gamma_source_region_id = vertex 所在 volume 对应的 region_id
```

若 secondary gamma vertex 不在已注册 region 内：

```text
gamma_source_region_id = other
```

若无法判定 vertex region：

```text
gamma_source_region_id = none
```

### 13.5 散射记录原则

对每条 gamma track，记录其自身的 Compton / Rayleigh 散射历史。

每条 gamma track 的散射阶次从该 track 产生时开始计数，初始值为 `0`。

primary gamma：

```text
初始散射阶次 = 0
后续该 primary gamma 自身发生 compt / Rayl 时计数 +1
```

secondary gamma：

```text
初始散射阶次 = 0
不继承 parent track 的散射阶次
后续该 secondary gamma 自身发生 compt / Rayl 时计数 +1
```

示例：

```text
primary gamma 先经历 2 次 Compton 后产生 secondary gamma；
secondary gamma 自身又经历 1 次 Compton 后被探测；
该 detected secondary gamma 的 scatter_count_total = 1，而不是 3。
```

gamma track 是否进入正式 CSV 只由是否形成 detected gamma hit 决定，不由散射发生在哪个 volume 决定。

统计过程：

| 过程 | 是否计入 |
|---|---|
| Compton scattering，process name `compt` | 是 |
| Rayleigh scattering，process name `Rayl` | 是 |
| Photoelectric effect | 否 |
| 非 gamma track 的过程 | 否 |

散射位置使用：

```text
step->GetPostStepPoint()->GetPosition()
```

region 归属使用：

```text
preStep volume 对应的 region_id
```

即：

| 情况 | region 归属 |
|---|---|
| step 起点位于子 volume | 子 volume 的 region_id |
| step 起点位于 VehicleROI 空气母体 | `vehicle_background_air` |
| step 起点位于未注册区域 | `other` |
| 无有效散射 | `none` |

贴边界面事件按 preStep volume 归属。

### 13.6 first / last scatter 定义

`first_scatter_*` / `last_scatter_*` 描述当前 detected gamma track 自身的 first / last Compton 或 Rayleigh 散射位置。

定义：

```text
first_scatter_x/y/z = 该 gamma track 产生后第一次有效散射位置
last_scatter_x/y/z = 该 gamma track 产生后最后一次有效散射位置
```

如果该 gamma track 从产生到探测之间没有发生 Compton / Rayleigh：

```text
scatter_count_total = 0
compton_count = 0
rayleigh_count = 0
first_scatter_x/y/z = NaN
last_scatter_x/y/z = NaN
first_scatter_region_id = none
last_scatter_region_id = none
```

### 13.7 记录变量

每个 event 至少维护：

```text
event_id
next_hit_id
per-track gamma summary map
```

每条 gamma track summary 至少维护：

```text
track_id
parent_id
is_primary_gamma
gamma_source_type
gamma_source_process
gamma_source_x/y/z
gamma_source_region_id
detected
hit_id
scatter_count_total
compton_count
rayleigh_count
first_scatter_x/y/z
last_scatter_x/y/z
first_scatter_region_id
last_scatter_region_id
det_x/det_y/det_z
det_energy
```

`is_primary_gamma` 由以下条件定义：

```text
track_id == 1 && parent_id == 0
```

### 13.8 散射统计空间范围

`scatter_count_total`、`compton_count`、`rayleigh_count` 统计的是当前 gamma track 在整个 Geant4 world 中发生的指定散射过程，而不是只统计 VehicleROI 内散射。

因此：

- VehicleROI 内散射计入；
- collimator / tungsten jaw 内 gamma track 的 `compt` / `Rayl` 也计入；
- world air 中 gamma track 的 `compt` / `Rayl` 也计入；
- 未注册 region 的散射 region_id 记为 `other`；
- 无散射 gamma track 的 first/last region_id 记为 `none`。

gamma track 是否进入正式 CSV 只由是否形成 detected gamma hit 决定，不由散射发生位置决定。

### 13.9 不进入事件级 CSV 的变量

为保持第二版基础程序输出稳定，以下变量不写入正式 `events.csv` 或 `events_debug.csv`：

- `pose_id`；
- `head_offset_x_mm` / `head_offset_y_mm`；
- primary 初始方向 `dir_x/y/z`；
- primary 初始能量；
- `target_interaction` boolean；
- per-region scatter counts；
- detector region ID；
- depth region ID。

处理方式：

- pose 信息写入该 pose 的 `metadata.yaml`；
- primary gamma 的实际起点通过 detected hit 或 debug track summary 中的 `gamma_source_x/y/z` 写出；
- primary 初始方向和初始能量由 `metadata.yaml` 中 source 参数与随机种子复现；
- detector region、depth region、per-region 统计和 target interaction 由后处理根据事件级 first/last scatter 信息或后续扩展 debug 输出生成；
- 若后续论文数据需要完整 per-region trajectory，应另开扩展 CSV schema，不修改本节定义的基础正式 CSV header。


---

## 14. 正式事件级 CSV

### 14.1 输出对象

正式 `events.csv` 输出所有 detected gamma hit。

```text
1 row = 1 detected gamma hit
```

未探测 gamma track 不进入正式 `events.csv`。同一 event 可输出 0 行、1 行或多行。

### 14.2 Header

正式 `events.csv` header 为：

```csv
event_id,hit_id,track_id,parent_id,is_primary_gamma,gamma_source_type,gamma_source_process,gamma_source_x,gamma_source_y,gamma_source_z,gamma_source_region_id,det_x,det_y,det_z,det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,first_scatter_region_id,last_scatter_region_id
```

### 14.3 字段含义

| 字段 | 含义 |
|---|---|
| `event_id` | Geant4 event 编号。 |
| `hit_id` | 同一 event 内 detected gamma hit 的递增编号，从 `0` 开始。 |
| `track_id` | detected gamma 的 Geant4 track id。 |
| `parent_id` | detected gamma 的 Geant4 parent id。 |
| `is_primary_gamma` | 当 `track_id == 1 && parent_id == 0` 时为 `1`，否则为 `0`。 |
| `gamma_source_type` | `primary` 或 `secondary`。 |
| `gamma_source_process` | primary gamma 为 `primary_generator`；secondary gamma 为 creator process name。 |
| `gamma_source_x/y/z` | primary gamma 为实际 `gamma_start`；secondary gamma 为 track vertex position。 |
| `gamma_source_region_id` | primary gamma 为 `source`；secondary gamma 为 vertex 所在 region_id，未注册时为 `other`，无法判定时为 `none`。 |
| `det_x` | 探测平面命中点 x 坐标，单位 mm。 |
| `det_y` | 探测平面命中点 y 坐标，单位 mm。 |
| `det_z` | 探测平面命中点 z 坐标，单位 mm。 |
| `det_energy` | crossing 时该 gamma track 的能量，单位 keV。 |
| `scatter_count_total` | 当前 detected gamma track 自身的 Compton + Rayleigh 总次数。 |
| `compton_count` | 当前 detected gamma track 自身的 Compton 次数。 |
| `rayleigh_count` | 当前 detected gamma track 自身的 Rayleigh 次数。 |
| `first_scatter_x/y/z` | 当前 detected gamma track 自身第一次 Compton / Rayleigh 散射位置，单位 mm。 |
| `last_scatter_x/y/z` | 当前 detected gamma track 自身最后一次 Compton / Rayleigh 散射位置，单位 mm。 |
| `first_scatter_region_id` | 当前 detected gamma track 自身第一次有效散射的 region_id。 |
| `last_scatter_region_id` | 当前 detected gamma track 自身最后一次有效散射的 region_id。 |

### 14.4 单位

| 类型 | 单位 |
|---|---|
| 长度 | mm |
| 能量 | keV |
| 计数 | 无量纲整数 |
| region | 字符串 |

---

## 15. Debug CSV

### 15.1 输出对象

Debug CSV 输出：

```text
1 row = 1 gamma track summary
```

Debug CSV 记录 detected 与 undetected gamma track。由于所有 gamma track 都可能被记录，debug CSV 文件会明显大于正式 `events.csv`。

### 15.2 Header

Debug CSV header 为：

```csv
event_id,track_id,parent_id,is_primary_gamma,gamma_source_type,gamma_source_process,gamma_source_x,gamma_source_y,gamma_source_z,gamma_source_region_id,detected,hit_id,det_x,det_y,det_z,det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,first_scatter_region_id,last_scatter_region_id
```

### 15.3 字段与填写规则

Debug CSV 使用与正式 `events.csv` 相同的 gamma track 来源、探测和散射字段，并额外包含 `detected` 字段。

若 `detected = 1`：

```text
hit_id = 同一 event 内 detected gamma hit 的递增编号，从 0 开始
det_x/det_y/det_z = 该 gamma track 第一次有效 detector crossing 点
det_energy = crossing 时该 gamma track 的能量，单位 keV
```

若 `detected = 0`：

```text
hit_id = -1
det_x = NaN
det_y = NaN
det_z = NaN
det_energy = NaN
```

散射字段按该 gamma track 自身已发生的追踪结果填写。

若无有效散射：

```text
scatter_count_total = 0
compton_count = 0
rayleigh_count = 0
first_scatter_x/y/z = NaN
last_scatter_x/y/z = NaN
first_scatter_region_id = none
last_scatter_region_id = none
```

Debug CSV 不包含 `termination_process`、`termination_volume`、`termination_region_id` 或其他可选字段。

---

## 16. metadata.yaml

每个 pose run 输出一个 `metadata.yaml`，记录 run-level 条件。第二版中一个 run 对应一个 pose 和一个实际使用的 seed；多线程只是该 run 内部的执行方式。

示例：

```yaml
run_id: pose_x0_y0_normal_seed12345
output_csv: events.csv

model_type: normal
vehicle_model_id: vehicle_roi_v03
vehicle_geometry_file: config/geometry/vehicle_roi_v04.yaml
selected_target_component: null
abnormal_target_type: none
abnormal_target_region: none

pose_id: pose_x0_y0
pose_index: 0
head_offset_x_mm: 0
head_offset_y_mm: 0

n_primary: 10000
base_random_seed: 12345
random_seed: 12345
number_of_threads: 8

debug: false

source:
  particle: gamma
  energy_mode: mono
  mono_energy_keV: 160.0
  spectrum_file: config/source/spectrum.csv
  incident_theta_deg: 45.0
  focal_spot_diameter_mm: 5.0
  source_pos_zero_mm: [0.0, 0.0, -185.0]

collimator:
  enable: true
  profile_file: config/collimator/collimator_profiles.csv
  profile_id: P001
  jaw_extrusion_length_y_mm: 120.0

detector:
  detector_z_zero_mm: -73.0
  detector_x_range_zero_mm: [53.0, 161.0]
  detector_y_range_zero_mm: [-50.0, 50.0]
  accept_direction: negative_z

physics:
  physics_list: G4EmLivermorePhysics
  production_cut_mm: 0.1

world:
  shape: box
  center_mm: [0.0, 0.0, 0.0]
  size_mm: [4000.0, 4000.0, 4000.0]
  material: G4_AIR

output_policy:
  existing_run_policy: fail

notes: sample config for pipeline validation
```

metadata 不重复写入每一行 CSV。

### 16.1 metadata 必含字段

`metadata.yaml` 至少应包含以下字段：

```yaml
run_id: string
output_csv: string
model_type: normal | abnormal
vehicle_model_id: string
vehicle_geometry_file: string
selected_target_component: string | null
abnormal_target_type: string | none
abnormal_target_region: target | none
pose_id: string
pose_index: int
head_offset_x_mm: int
head_offset_y_mm: int
n_primary: int
base_random_seed: int
random_seed: int
number_of_threads: int
debug: bool
source: {...}
collimator: {...}
detector: {...}
physics: {...}
world: {...}
output_policy: {...}
```

其中 `world` 至少记录固定 World 配置：

```yaml
world:
  shape: box
  center_mm: [0.0, 0.0, 0.0]
  size_mm: [4000.0, 4000.0, 4000.0]
  material: G4_AIR
```

其中 `output_policy` 至少记录输出目录已存在时的策略：

```yaml
output_policy:
  existing_run_policy: fail
```

### 16.2 随机数与 run 关系

第二版中，一个 run 对应一个 pose 和一个实际使用的 seed。该 run 可以使用多线程运行；线程数不改变 run 的定义。

多 pose 程序执行时，每个 pose run 必须使用不同 seed，并在该 pose 的 `metadata.yaml` 中记录实际使用的 `random_seed`。

推荐默认规则：

```text
base_random_seed = run.random_seed
pose_seed = base_random_seed + pose_index
```

约束：

- 每个 pose run 使用一个明确 seed；
- 每个 pose run 的 metadata 必须记录 `base_random_seed`、`pose_index` 和实际 `random_seed`；
- 同一配置、同一 Geant4 版本、同一线程数下应尽量保持可复现；
- 改变 `number_of_threads` 时，基础实现不强制逐事件 bitwise identical；
- 不要求实现复杂 hash 派生策略或跨线程数严格复现策略。


---

## 17. 输出文件组织

### 17.1 每个位姿独立输出

每个 pose 独立运行一组 Monte Carlo 统计。第二版定义中，一个 run 对应一个 pose 和一个 seed；若一次程序执行包含多个 pose，则程序内部顺序执行多个 pose run。

建议输出目录结构：

```text
results/
└── {run_id}/
    ├── events.csv
    ├── metadata.yaml
    └── tmp/
        ├── events_thread0.csv
        ├── events_thread1.csv
        └── ...
```

若 debug 为 true：

```text
results/{run_id}/events_debug.csv
results/{run_id}/metadata.yaml
```

### 17.2 run_id 生成

建议：

```text
run_id = {pose_id}_{model_type}_seed{random_seed}
```

示例：

```text
pose_x0_y0_normal_seed12345
pose_x1111_y0_abnormal_seed12345
pose_xm10_y4_normal_seed12345
```

### 17.3 输出目录已存在时的策略

默认策略为 fail fast：

```text
若 results/{run_id}/ 已存在且非空：
  程序报错停止
```

理由：

- 避免不同配置或不同运行结果混写；
- 避免旧 CSV 被误认为新结果；
- 保持 metadata 与 CSV 一一对应。

后续可选扩展：

```yaml
output:
  existing_run_policy: fail | overwrite | append_forbidden | new_run_id
```

第二版基础实现仅要求支持 `fail`。若实现 `overwrite` 或 `new_run_id`，必须在 metadata 中记录实际策略。


---

## 18. 多线程输出策略

第二版继承第一版多线程输出策略。

规则：

1. 每个 worker 线程写独立临时 CSV；
2. 不允许多个 worker 共享同一个 `std::ofstream`；
3. run 结束后由 master 合并临时 CSV；
4. 最终 CSV 只保留一个 header；
5. 正式模式合并成功后删除对应临时 CSV；
6. debug 模式合并成功后保留对应临时 CSV；
7. 合并失败时保留所有临时 CSV 并报错。

---

## 19. Run / pose 生命周期

### 19.1 程序启动

```text
main()
  ├── 读取 simulation_config_v2.yaml
  ├── 读取 vehicle_roi_v03.yaml
  ├── 生成 pose 列表
  ├── 创建 Geant4 run manager
  ├── 注册 geometry / physics / actions
  └── 按 pose 执行 run
```

### 19.2 每个 pose 的运行流程

```text
For each pose:
  ├── 生成 pose_id
  ├── 应用 head_offset
  ├── 构建或更新 ImagingHead geometry
  ├── VehicleROI 保持固定
  ├── /run/initialize
  ├── beamOn n_primary_per_pose
  ├── 写 events.csv 或 events_debug.csv
  ├── 写 metadata.yaml
  └── 多线程合并
```

第一阶段允许每个 pose 作为独立静态几何状态运行。

不要求模拟连续运动或在一个 event loop 内动态移动成像头。

---

## 20. 错误处理

以下情况必须 fail fast：

### 20.1 YAML 配置错误

- YAML 文件不存在；
- 必要字段缺失；
- 数值类型错误；
- `schema_version` 不支持；
- `pose.mode` 不是 `list` 或 `grid`；
- list mode 中 x/y offset 数组长度不同；
- offset 不是整数；
- `n_primary_per_pose <= 0`；
- `number_of_threads < 1`；
- `model_type` 不是 `normal` 或 `abnormal`；
- abnormal 模式下未指定 `selected_target_component`；
- 指定 target component 不存在或不是 insert；
- `incident_theta_deg <= 0` 或 `incident_theta_deg > 90`；
- `focal_spot_diameter_mm <= 0`；
- detector range 非法；
- output directory 无法创建。

### 20.2 Vehicle ROI 错误

- material 不存在且无法创建；
- host 不存在；
- daughter 不在 host 内；
- 同级实体 overlap；
- insert 不在唯一宿主内；
- region_id 缺失。

### 20.3 Collimator profile 错误

- profile 文件无法打开；
- 找不到 profile_id；
- jaw 编号不连续；
- vertex_id 不连续；
- 坐标非法；
- 多边形非法。

### 20.4 输出错误

- CSV 无法创建；
- metadata 无法写出；
- 线程临时文件无法创建；
- 合并失败；
- 合并后 header 不唯一。

### 20.5 CLI / dependency 错误

- 未提供配置文件路径；
- `--config` 后缺少参数；
- 同时提供多个互相冲突的配置文件路径；
- YAML parser 依赖不可用；
- YAML 文件语法错误。

### 20.6 World / pose 错误

- 任一 pose 下 source 不在 World 内；
- 任一 pose 下 detector plane 不在 World 内；
- 任一 pose 下 collimator jaw 不在 World 内；
- 固定 World 尺寸不足以覆盖 VehicleROI 或任一 pose 下成像头组件。

### 20.7 随机数策略错误

- random seed 非整数；
- 多 pose 模式下无法为每个 pose run 确定独立 seed；
- metadata 未记录该 pose run 实际使用的 random_seed。


---

## 21. 后处理边界

本轮 Geant4 程序只负责输出事件级数据和 metadata。

以下内容不在本轮实现，留到下一轮后处理项目迭代：

- 探测器二维 histogram；
- normal / abnormal 差异图；
- 相对变化图；
- CNR；
- detector region mapping；
- depth region mapping；
- `M_RJ`；
- `purity_R`；
- `crosstalk_R`；
- `H_k`；
- `H_ms`；
- `F_ms`；
- `D_JS`；
- effective rank；
- SVD explained variance。

Geant4 不直接输出 detector region ID 或 depth region ID。本轮也不提供后处理脚本。

### 21.1 与位姿级 / 扫描级输出的一致性

项目文档中若出现“事件级 / 位姿级 / 扫描级输出”表述，应按以下边界解释：

| 层级 | 本轮是否实现 | 说明 |
|---|---|---|
| 事件级 | 是 | `events.csv` 中的 detected gamma hit、`events_debug.csv` 中的 gamma track summary，以及 `metadata.yaml` |
| 位姿级 | 否 | 下一轮后处理项目迭代实现 |
| 扫描级 | 否 | 下一轮后处理项目迭代实现 |

因此，`StatisticsAccumulator`、`ScanSummaryWriter`、pose-level summary、scan-level summary、二维响应图和统计指标不属于本轮强制模块。若文档或代码中保留相关名称，应标注为下一轮后处理或 deferred。


---

## 22. 验收标准摘要

第二版基础实现至少应满足：

1. 能读取 `simulation_config_v2.yaml`；
2. 能读取 `vehicle_roi_v03.yaml`；
3. VehicleROI 几何可视化正确，且无 overlap；
4. normal / abnormal insert 替换逻辑正确；
5. 成像头 source、collimator、detector 随同一个 head_offset 平移；
6. 车辆 ROI 在不同 pose 中保持固定；
7. pose_id 按 offset 自动生成；
8. list mode 和 grid mode 均可生成 pose；
9. 斜入射有限焦点笔形束方向满足 `incident_dir = (cos(theta), 0, sin(theta))`；
10. 焦点起点位于垂直 incident_dir 的圆形焦点面内；
11. 准直器按第二版可变 jaw 规则读取 profile；
12. 不构建镜像准直器；
13. 不构建镜像探测器；
14. 探测面 crossing 使用 YAML 中的 detector 配置；
15. 正式 `events.csv` 输出所有 detected gamma hit，且同一 event 可输出多行；
16. debug CSV 输出 gamma track summary，并使用 `detected` 字段区分该 track 是否有效穿越探测平面；
17. 正式 CSV header 与本文档一致；
18. debug CSV header 与本文档一致；
19. `metadata.yaml` 使用 `head_offset_x_mm` 和 `head_offset_y_mm`，不使用 `vehicle_shift_x/y`；
20. 多线程输出不共享同一个输出流；
21. master 合并后最终 CSV 只保留一个 header。

22. 能按 `vehicle_roi_v03.yaml` 实际 schema 读取 `schema/metadata/units/roi/materials/model_modes/regions/components/validation`；
23. 能构建当前样例中全部 VehicleROI components；
24. 能识别全部 `is_insert=true` 的 recommended target component；
25. abnormal 模式下非 selected insert 保持 normal material 和 normal region_id；
26. 固定 World 为中心 `[0,0,0]`、边长 `4000 mm` 的 `G4_AIR` box，并能覆盖全部 VehicleROI 和全部 pose 下的成像头组件；
27. collimator CSV 可读取必需列，并兼容可选 `y_mm` 列和 UTF-8 BOM；
28. collimator jaw 的 global y placement 满足 `y_actual = y_zero + head_offset_y`；
29. formal CSV 不包含 pose_id、primary 初始方向、primary 初始能量、target interaction boolean、per-region scatter counts；这些字段由 metadata、`gamma_source_*` 字段或后处理处理；
30. metadata 记录 pose、pose_index、head_offset、base_random_seed、该 pose run 实际使用的 random_seed、thread 数、source/collimator/detector/physics/world/output_policy；
31. 输出目录已存在且非空时按默认 fail fast 策略处理；
32. 多 pose 运行时每个 pose run 使用不同 seed，并在对应 metadata 中记录实际 seed；
33. 位姿级和扫描级 summary、图表、统计指标和后处理脚本不作为本轮验收项，留到下一轮项目迭代。


---

## 23. 第二版当前非目标

第二版基础构建不包含：

- 整车 CAD 复现；
- 完整车辆扫描；
- 底盘、发动机舱、轮胎、悬挂详细建模；
- 曲面真实车身；
- 真实探测器材料响应；
- sensitive detector 能量沉积建模；
- 工程级图像重建；
- 连续运动扫描；
- 运动模糊；
- 时间相关探测器积分；
- 成像头旋转；
- 成像头 z 方向运动；
- 镜像准直器；
- 镜像探测器；
- 在 Geant4 内直接生成统计图。

---

## 24. 规格闭合状态

当前第二版规格已闭合到可以指导基础代码实现。

已闭合项：

- 第二版目标和边界；
- 固定车辆 ROI + 移动成像头；
- 两个 YAML 配置文件；
- list / grid pose 规则；
- pose_id 自动生成规则；
- 斜入射有限焦点源；
- mono / spectrum 能量模式；
- 可变 jaw 数量准直器 reader；
- 不构建镜像准直器；
- 单个虚拟探测平面；
- negative_z 探测方向；
- detector-hit 事件追踪模型；
- per-gamma-track scatter history；
- `gamma_source_*` 来源字段；
- 正式 CSV 与 debug CSV schema；
- metadata.yaml；
- 多线程临时 CSV + master merge。

仍可通过 YAML 调整的参数：

- 源零位姿；
- 探测器零位姿；
- 探测器接收范围；
- 入射角；
- 焦点直径；
- 准直器 profile；
- head_offset 列表或 grid；
- 每个位姿入射粒子数；
- normal / abnormal target 位置；
- 随机种子与线程数。

这些参数是运行配置，不再阻塞第二版基础实现。

本修订版新增闭合项：

- `vehicle_roi_v03.yaml` 实际 schema；
- component 字段规范；
- 当前 VehicleROI 组件清单；
- abnormal target component 列表；
- AABB / placement / overlap 检查规则；
- 固定 World 尺寸策略；
- YAML parser 依赖边界；
- CLI 主入口；
- collimator 可选 `y_mm` 与 y placement；
- 散射统计空间范围；
- 不进入基础事件级 CSV 的字段边界；
- metadata 必含字段；
- 每个 pose run 的随机 seed 记录策略；
- 输出目录已存在时的默认 fail fast 策略；
- 位姿级 / 扫描级输出与后处理模块留到下一轮项目迭代的边界。
