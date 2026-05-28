# 第二版验收清单

## 1. 文档目的

本文档定义第二版车辆侧向背散射 ROI Geant4 仿真项目的验收检查项。

验收目标不是证明物理结果已经正确解释，而是确认第二版基础程序满足以下条件：

```text
YAML 配置可读取
VehicleROI 几何可构建且可检查
ImagingHead 可按 pose 平移
primary gamma 源、准直器、虚拟探测器链路可运行
事件级 CSV 与 metadata 输出符合规格
多线程输出策略正确
错误输入能够 fail fast
```

本文档以 `spec.md` 为最高依据，并与 `decisions.md` 和 `architecture.md` 保持一致。

---

## 2. 通用验收约定

### 2.1 默认运行入口

推荐从仓库根目录运行：

```bash
cmake -S . -B build
cmake --build build -j
./build/MSS --config data/simulation_config_v2.yaml
```

可视化检查入口为：

```bash
./build/MSS --config data/simulation_config_v2.yaml --ui
```

推荐主入口使用 `--config`。若实现同时支持位置参数形式，应以 `--config` 指定路径为准。README、样例命令和本文档应同步更新，不能保留互相矛盾的入口。

### 2.2 默认样例配置

样例 `simulation_config_v2.yaml` 使用：

```yaml
run:
  random_seed: 12345
  number_of_threads: 8
  n_primary_per_pose: 10000
  debug: false

vehicle:
  geometry_file: data/vehicle_roi_v03.yaml
  model_type: normal
  selected_target_component: null
  abnormal_material: G4_POLYETHYLENE

pose:
  mode: list
  list:
    head_offset_x_mm: [0]
    head_offset_y_mm: [0]

source:
  particle: gamma
  energy_mode: mono
  mono_energy_keV: 160.0
  spectrum_file: data/spectrum.csv
  source_pos_zero_mm: [0.0, 0.0, -185.0]
  incident_theta_deg: 45.0
  focal_spot_diameter_mm: 5.0

collimator:
  enable: true
  profile_file: data/collimator_profiles.csv
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
  output_directory: results
  events_csv_name: events.csv
  metadata_yaml_name: metadata.yaml
  thread_tmp_directory: tmp
```

这些源与探测器位置来自第一版链路验证值，只用于第二版程序构建、可视化和端到端输出测试，不是第二版最终成像头几何的不可修改物理常量。

### 2.3 输出目录约定

默认单 pose normal 运行的推荐输出目录为：

```text
results/pose_x0_y0_normal_seed12345/
```

正式模式应包含：

```text
events.csv
metadata.yaml
```

debug 模式应包含：

```text
events_debug.csv
metadata.yaml
```

多线程临时文件位于：

```text
results/{run_id}/tmp/
```

---

## 3. 构建验收

### 3.1 命令

```bash
cmake -S . -B build
cmake --build build -j
```

### 3.2 验收点

- CMake 配置成功。
- 编译成功。
- 生成可执行文件 `build/MSS`。
- executable、CMake project 和 README 中的项目名一致，不使用旧项目名。
- C++ 标准为 C++17。
- Geant4 run manager 不写死为单线程专用实现。

### 3.3 legacy 隔离验收

当前仓库曾包含第一轮 PMMA 实现。第二轮基础实现必须满足：

- 构建和默认运行路径不依赖 PMMA、air defect、mirror detector、mirror collimator、`hits_profile_*` 文件名或旧 compact/debug header。
- `./build/MSS --config data/simulation_config_v2.yaml` 是主入口；位置参数形式若存在，也必须表示 YAML 配置路径，而不是 macro 文件。
- 旧 macro 不能设置 source、detector、collimator、pose、output、seed、thread、target 等 YAML 已覆盖参数。
- 源码中不存在固定三 jaw 假设作为第二轮 profile 结构。
- 不构建 `Mirror` jaw 或 mirror detector。
- `SteppingAction` 不按 `PMMALogical` 过滤散射。
- 正式 CSV header 精确等于 `spec.md`，不包含旧 `initial_energy`、`initial_dir_*` 或 `is_multiple_scatter` 字段。

---

## 4. YAML 配置读取验收

### 4.1 有效配置

使用默认 `data/simulation_config_v2.yaml` 运行。

验收点：

- 程序能读取 `data/simulation_config_v2.yaml`。
- 程序能读取其中指定的 `data/vehicle_roi_v03.yaml`。
- `schema_version = 2` 被识别。
- `run`、`vehicle`、`pose`、`source`、`collimator`、`detector`、`physics`、`output` 顶层字段均被解析。
- 不依赖 Geant4 macro 作为主配置入口。
- 旧 macro 文件不能作为默认运行入口；`SimulationMessenger` 如保留，只能指定或切换入口 YAML 文件路径。
- 程序实际使用已批准的 `yaml-cpp` 读取配置，而不是退回 macro。
- 若 `yaml-cpp` 依赖不可用，CMake 或程序启动阶段给出明确错误。
- YAML 语法错误应 fail fast，并指出文件路径。

### 4.2 无效配置 fail fast

分别构造临时错误配置，不修改有效样例文件。

必须报错停止：

- YAML 文件不存在。
- `schema_version` 缺失或不是 `2`。
- 必要字段缺失。
- 字段类型错误。
- `number_of_threads < 1`。
- `n_primary_per_pose <= 0`。
- `model_type` 不是 `normal` 或 `abnormal`。
- `incident_theta_deg <= 0` 或 `incident_theta_deg > 90`。
- `focal_spot_diameter_mm <= 0`。
- detector range 中 `min >= max`。
- output directory 为空或无法创建。

错误信息应指出具体文件、字段或配置节名称。

---

## 5. pose 生成验收

### 5.1 list mode

配置：

```yaml
pose:
  mode: list
  list:
    head_offset_x_mm: [0, 2, 3, 10]
    head_offset_y_mm: [0, 1, 4, 2]
```

验收点：

| 序号 | offset | pose_id |
|---:|---|---|
| 0 | `(0, 0)` | `pose_x0_y0` |
| 1 | `(2, 1)` | `pose_x2_y1` |
| 2 | `(3, 4)` | `pose_x3_y4` |
| 3 | `(10, 2)` | `pose_x10_y2` |

要求：

- `pose_id` 由程序自动生成。
- 用户不需要、也不应在 YAML 中手写 `pose_id`。
- x/y 数组按索引配对，不做笛卡尔积。

### 5.2 list mode 负 offset

配置：

```yaml
pose:
  mode: list
  list:
    head_offset_x_mm: [-10, 1111]
    head_offset_y_mm: [-4, 0]
```

验收点：

| offset | pose_id |
|---|---|
| `(-10, -4)` | `pose_xm10_ym4` |
| `(1111, 0)` | `pose_x1111_y0` |

要求：

- 正整数不加 `p` 前缀。
- 负整数使用 `m` + 绝对值。
- 整数位数不限制为三位。
- 第一阶段不支持小数 offset。

### 5.3 grid mode

配置：

```yaml
pose:
  mode: grid
  grid:
    x_offsets_mm: [-10, 0, 10]
    y_offsets_mm: [0, 5]
```

验收点：

程序生成 6 个 pose：

```text
(-10, 0)
(-10, 5)
(0, 0)
(0, 5)
(10, 0)
(10, 5)
```

对应 pose_id：

```text
pose_xm10_y0
pose_xm10_y5
pose_x0_y0
pose_x0_y5
pose_x10_y0
pose_x10_y5
```

### 5.4 pose 错误输入

必须报错停止：

- `pose.mode` 不是 `list` 或 `grid`。
- list mode 中 x/y 数组长度不同。
- offset 是小数。
- offset 是字符串或非法类型。
- grid mode 中 x 或 y offset 列表为空。

---

## 6. VehicleROI 几何验收

### 6.1 `vehicle_roi_v03.yaml` schema 验收

验收点：

- 能识别顶层 `schema`、`metadata`、`units`、`coordinate_system`、`roi`、`geant4_placement_rules`、`materials`、`model_modes`、`regions`、`components`、`validation`。
- 不假设存在 `vehicle_roi:` 顶层字段。
- 能读取 `components[]` 中每个 component 的 `name`、`host`、`shape`、`center_mm`、`size_mm`、`material`、`region_id`、`is_insert`、`role`、`half_size_mm`、`aabb_mm`、`placement_center_in_host_mm`。
- `shape` 第一阶段仅支持 `box`。
- `half_size_mm == size_mm * 0.5`。
- `aabb_mm` 与 `center_mm / size_mm` 一致。

### 6.2 读取 `vehicle_roi_v03.yaml`

验收点：

- 识别 VehicleROI 根 volume。
- VehicleROI 范围为：

```text
x = [-900, 1300] mm
y = [0, 1250] mm
z = [0, 1450] mm
```

- VehicleROI 材料为 `G4_AIR`。
- VehicleROI region 为 `vehicle_background_air`。
- YAML 中 `size` 被按全长读取，构建 `G4Box` 时使用 half length。

### 6.3 坐标转换

验收点：

- VehicleROI 直接 daughter 的 placement 为：

```text
component_center - VehicleROI_center
```

- 非 VehicleROI 直接 daughter 的 placement 为：

```text
component_center - host_center
```

- 组件的 global AABB 与 YAML 中定义一致。

### 6.4 主要组件可视化

使用第二版可视化入口检查：

```bash
./build/MSS --config data/simulation_config_v2.yaml --ui
```

验收点：

- 程序通过 YAML 构建几何，而不是通过 legacy `/geometry/*` 或 `/source/*` macro 命令配置。
- UI 模式只显示第一个 pose，并在终端打印该 pose。
- `macros/vis.mac` 自动执行少量事件用于轨迹显示。
- UI 模式不写 `events.csv`、`events_debug.csv` 或 `metadata.yaml`。

可视化中应能识别：

- VehicleROI 空气母体。
- 近侧前门、近侧后门。
- 远侧前门、远侧后门。
- 近侧 / 远侧车窗。
- 近侧 / 远侧 B 柱。
- 近侧 / 远侧 C 柱。
- cabin_air。
- front / rear seat foam 与 frame。
- rear_trunk_air。
- insert 体积。

### 6.5 overlap 与 host 检查

必须无 overlap：

- door beam 与 door insert。
- cabin_air 与 rear_trunk_air。
- cabin_air_package_insert 与座椅。
- seat base / seat back / seat frame。
- far door inner metal 与 far door cavity。
- near / far windows 与 pillars。
- near / far doors 与 pillars。

必须满足 host 包含关系：

- door insert 位于对应 door cavity air 内。
- seat insert 位于对应 seat back foam 内。
- cabin package insert 位于 cabin_air 内。
- trunk package insert 位于 rear_trunk_air 内。

若任一检查失败，程序应在事件产生前停止。

---


## 7. World 几何验收

验收点：

- World 为 `G4_AIR` box。
- World center 为 `[0, 0, 0] mm`。
- World size 为 `[4000, 4000, 4000] mm`。
- VehicleROI 位于 World 内。
- 所有 pose 下的 source、collimator jaw 和 virtual detector plane 均位于 World 内。
- 若任一组件超出固定 World，程序必须在事件产生前 fail fast。
- `metadata.yaml` 记录 World 的 shape、center、size 和 material。

## 8. 材料与 region 验收

### 8.1 材料

必须可创建或读取：

| 材料 | 要求 |
|---|---|
| `G4_AIR` | NIST |
| `G4_Fe` | NIST |
| `G4_GLASS_PLATE` | NIST |
| `G4_POLYPROPYLENE` | NIST |
| `G4_POLYETHYLENE` | NIST |
| `G4_W` | NIST |
| `Vehicle_PU_Foam` | 自定义 |

`Vehicle_PU_Foam`：

```text
density = 0.055 g/cm3
C = 0.60
H = 0.08
O = 0.28
N = 0.04
```

材料创建应幂等，不重复创建同名 material。

### 8.2 region_id 注册

验收点：

- 每个可发生散射归因的 physical volume 都能查询到 region_id。
- VehicleROI 空气母体返回 `vehicle_background_air`。
- 未注册但被查询到的 volume 返回 `other`。
- 无有效散射时 region 为 `none`。
- `metadata.yaml` 不需要列出每个 region，但 CSV 中 region 字符串必须与注册值一致。

### 8.3 normal / abnormal insert

normal 配置：

```yaml
vehicle:
  model_type: normal
  selected_target_component: null
```

验收点：

- 所有 insert 使用 normal material。
- 所有 insert 使用 normal region_id。
- 无 insert region 为 `target`。

abnormal 配置示例：

```yaml
vehicle:
  model_type: abnormal
  selected_target_component: front_seat_insert
  abnormal_material: G4_POLYETHYLENE
```

验收点：

- `front_seat_insert` 材料为 `G4_POLYETHYLENE`。
- `front_seat_insert` region_id 为 `target`。
- 其他 insert 保持 normal material 与 normal region_id。
- normal / abnormal 几何尺寸完全一致。

非法情况必须报错：

- abnormal 模式下 target 为 null。
- target component 不存在。
- target component 不是 insert。
- `selected_target_component` 不属于 spec.md 推荐 abnormal target component 列表。

---

## 9. 成像头 pose offset 验收

### 9.1 VehicleROI 固定

使用两个不同 pose，例如：

```text
pose_x0_y0
pose_x10_y5
```

验收点：

- VehicleROI 中所有车辆组件 global 坐标不变。
- first / last scatter 坐标仍在同一车辆 global 坐标系中解释。

### 9.2 source 同步平移

验收点：

```text
source_pos_actual = source_pos_zero + (head_offset_x, head_offset_y, 0)
```

例如 source zero 为 `[0, 0, -185]`：

| pose | source actual |
|---|---|
| `pose_x0_y0` | `[0, 0, -185]` |
| `pose_x10_y5` | `[10, 5, -185]` |
| `pose_xm10_ym4` | `[-10, -4, -185]` |

### 9.3 collimator 同步平移

验收点：

- jaw 顶点 x 坐标随 `head_offset_x` 平移。
- jaw y 向 placement 随 `head_offset_y` 平移。
- jaw z 坐标不随 pose 改变。
- 不构建镜像 jaw。

### 9.4 detector 同步平移

验收点：

```text
det_x_min_actual = det_x_min_zero + head_offset_x
det_x_max_actual = det_x_max_zero + head_offset_x
det_y_min_actual = det_y_min_zero + head_offset_y
det_y_max_actual = det_y_max_zero + head_offset_y
det_z_actual = detector_z_zero
```

例如 zero detector 为：

```text
x=[53,161], y=[-50,50], z=-73
```

在 `pose_x10_y5` 下应为：

```text
x=[63,171], y=[-45,55], z=-73
```

---

## 10. 射线源验收

### 10.1 基本事件定义

验收点：

- `1 event = 1 primary gamma`。
- primary particle 为 gamma。
- 不在一个 event 内产生多个 primary gamma。

### 10.2 入射方向

当：

```yaml
incident_theta_deg: 45.0
```

应满足：

```text
incident_dir ≈ (0.7071, 0, 0.7071)
```

当：

```yaml
incident_theta_deg: 90.0
```

应满足：

```text
incident_dir ≈ (0, 0, 1)
```

非法 theta 必须报错：

```text
theta <= 0
theta > 90
```

### 10.3 焦点面采样

验收点：

- gamma 起点位于过 `source_pos_actual` 的圆形焦点面内。
- 焦点面垂直于 `incident_dir`。
- 起点到 source actual 的距离不超过 `focal_spot_diameter_mm / 2`。
- gamma 方向固定为 `incident_dir`，不使用第一版目标平面锥束采样。

### 10.4 能量模式

mono 模式：

```yaml
energy_mode: mono
mono_energy_keV: 160.0
```

验收点：

- primary gamma 初始能量为 `160 keV`。

spectrum 模式：

```yaml
energy_mode: spectrum
spectrum_file: data/spectrum.csv
```

验收点：

- spectrum CSV header 为 `energy_keV,weight`。
- energy 为正且有限。
- weight 非负且有限。
- 权重总和大于 0。
- 非法 spectrum 文件报错停止。

---

## 11. 狭缝准直器验收

### 11.1 合法 profile

使用样例：

```yaml
collimator:
  enable: true
  profile_file: data/collimator_profiles.csv
  profile_id: P001
```

验收点：

- 能读取 profile `P001`。
- 能读取必需列 `profile_id,jaw_id,vertex_id,x_mm,z_mm`。
- 若存在可选 `y_mm`，同一 jaw 内所有 `y_mm` 必须相同。
- 若不存在 `y_mm`，`jaw_center_y_zero = 0`。
- UTF-8 BOM 不应导致表头识别失败。
- 支持可变数量 jaw，不能写死三块 jaw。
- jaw ID 连续为 `jaw_0 ... jaw_{M-1}`。
- 每块 jaw 使用 `G4ExtrudedSolid`。
- jaw 沿 global y 方向拉伸。
- 拉伸长度来自 `jaw_extrusion_length_y_mm`，且该值表示 global y 方向全长，不是 half length。
- 不构建镜像准直器。

### 11.2 非法 profile

使用临时非法文件测试，不修改有效样例文件。

必须报错停止：

- 文件无法打开。
- 找不到指定 profile_id。
- 缺少必要列。
- jaw ID 不连续。
- jaw ID 重复。
- 某 jaw 少于 3 个顶点。
- vertex_id 缺失、重复或不连续。
- 坐标为空、非数值、NaN 或 Inf。
- 多边形面积为 0。
- 多边形非凸。
- 含连续共线点。
- 同一 jaw 内 `y_mm` 不一致。

### 11.3 关闭准直器

配置：

```yaml
collimator:
  enable: false
  profile_file: data/not_exist.csv
```

验收点：

- 程序不读取 profile 文件。
- 不构建 tungsten jaw。
- source、VehicleROI、detector 仍按配置构建。

---

## 12. 虚拟探测器验收

### 12.1 几何关系

验收点：

- 探测器为单个虚拟平面。
- 平面平行于 global `x-y`。
- 不构建真实探测器材料。
- 不设置 sensitive detector。
- 不构建镜像探测器。
- 准直器位于 VehicleROI 与虚拟探测平面之间。

### 12.2 negative_z crossing

当：

```yaml
accept_direction: negative_z
```

探测判定必须使用：

```text
particle == gamma
preStep.z > detector_z
postStep.z <= detector_z
direction.z < 0
crossing point inside detector x-y bounds
```

穿越点使用线性插值：

```text
t = (detector_z - pre_z) / (post_z - pre_z)
det_x = pre_x + t * (post_x - pre_x)
det_y = pre_y + t * (post_y - pre_y)
```

同一 gamma track 只记录第一次有效 detector crossing。同一 event 内不同 gamma track 可分别记录为 detected gamma hit。

---

## 13. event 追踪验收

### 13.1 gamma track 过滤

处理所有：

```text
particle_name == gamma
```

不处理：

- electron；
- positron；
- 其他非 gamma 粒子。

### 13.2 散射计数

计入：

```text
processName == compt
processName == Rayl
```

不计入：

- photoelectric effect；
- 非 gamma 粒子过程。

验收点：

- 每条 gamma track 独立维护 `scatter_count_total`、`compton_count` 和 `rayleigh_count`。
- `scatter_count_total = compton_count + rayleigh_count`。
- secondary gamma 的散射阶次从自身产生时从 `0` 开始，不继承 parent track 的散射阶次。
- first scatter 为当前 gamma track 自身第一次有效 Compton / Rayleigh。
- last scatter 为当前 gamma track 自身最后一次有效 Compton / Rayleigh。
- 无有效散射时 first / last scatter 坐标为 `NaN`，region 为 `none`。

### 13.3 region 归属

验收点：

- 散射位置坐标使用 postStep position。
- 散射 region 使用 preStep volume。
- step 起点位于子 volume 时返回子 volume 的 region_id。
- step 起点位于 VehicleROI 空气母体时返回 `vehicle_background_air`。
- step 起点位于未注册区域时返回 `other`。
- 贴边界面事件按 preStep volume 归属。

### 13.4 散射统计空间范围

验收点：

- `scatter_count_total`、`compton_count`、`rayleigh_count` 不限于 VehicleROI 内。
- gamma track 在 VehicleROI、collimator、World air 或其他 registered / unregistered volume 中发生的 `compt` / `Rayl` 均计入。
- 未注册 region 返回 `other`。
- gamma track 是否进入正式 CSV 只由 detected gamma hit 决定。

---

## 14. 正式 CSV 验收

### 14.1 输出文件

正式模式：

```yaml
run:
  debug: false
```

期望输出：

```text
results/{run_id}/events.csv
results/{run_id}/metadata.yaml
```

### 14.2 Header

`events.csv` header 必须精确等于：

```csv
event_id,hit_id,track_id,parent_id,is_primary_gamma,gamma_source_type,gamma_source_process,gamma_source_x,gamma_source_y,gamma_source_z,gamma_source_region_id,det_x,det_y,det_z,det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,first_scatter_region_id,last_scatter_region_id
```

### 14.3 行语义

验收点：

- `1 row = 1 detected gamma hit`。
- 同一 event 可输出 0 行、1 行或多行。
- 未探测 gamma track 不写入正式 CSV。
- CSV 不包含 `detected` 字段。
- CSV 不包含 `pose_id`、`model_type`、`head_offset_x/y`，这些信息写入 metadata。
- CSV 包含 `hit_id`、`track_id`、`parent_id`、`is_primary_gamma` 和 `gamma_source_*` 字段。
- `hit_id` 在同一 event 内从 `0` 开始递增。
- primary gamma 的 `gamma_source_x/y/z` 为焦点面随机采样后的实际 `gamma_start`。
- secondary gamma 的 `gamma_source_x/y/z` 为 track vertex position。
- CSV 不包含 `source_dir_x/y/z`、`source_energy_keV`、`target_interaction`、per-region scatter counts、detector region ID 或 depth region ID。
- 长度单位为 mm。
- 能量单位为 keV。
- 无散射 gamma track 的 first / last scatter 坐标为 `NaN`，region 为 `none`。

---

## 15. Debug CSV 验收

### 15.1 输出文件

Debug 模式：

```yaml
run:
  debug: true
```

期望输出：

```text
results/{run_id}/events_debug.csv
results/{run_id}/metadata.yaml
```

### 15.2 Header

`events_debug.csv` header 必须精确等于：

```csv
event_id,track_id,parent_id,is_primary_gamma,gamma_source_type,gamma_source_process,gamma_source_x,gamma_source_y,gamma_source_z,gamma_source_region_id,detected,hit_id,det_x,det_y,det_z,det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,first_scatter_region_id,last_scatter_region_id
```

### 15.3 行语义

验收点：

- `1 row = 1 gamma track summary`。
- detected gamma track 与 undetected gamma track 均写入。
- `detected` 只允许为 `0` 或 `1`。
- `detected = 1` 时，`hit_id` 为同一 event 内 detected gamma hit 的递增编号，从 `0` 开始。
- `detected = 0` 时：

```text
hit_id = -1
det_x = NaN
det_y = NaN
det_z = NaN
det_energy = NaN
```

- scatter 字段按该 gamma track 自身已发生的追踪结果填写。
- Debug CSV 会明显大于正式 CSV，因为所有 gamma track 都可能被记录。
- Debug CSV 不包含 `termination_process`、`termination_volume`、`termination_region_id` 或其他额外字段。
- Debug CSV 不包含 `source_dir_x/y/z`、`source_energy_keV`、`target_interaction`、per-region scatter counts、detector region ID 或 depth region ID。

---

## 16. metadata.yaml 验收

每个 pose 必须写出 `metadata.yaml`。

必须包含：

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

验收点：

- metadata 中使用 `head_offset_x_mm` 和 `head_offset_y_mm`。
- metadata 中不得出现 `vehicle_shift_x` 或 `vehicle_shift_y`。
- `output_csv` 与实际 CSV 文件名一致。
- `n_primary` 等于该 pose 的入射 primary gamma 数。
- metadata 记录 `base_random_seed`、`pose_index` 和该 pose run 实际使用的 `random_seed`。
- `run_id` 推荐格式为：

```text
{pose_id}_{model_type}_seed{random_seed}
```

---

## 17. 多线程输出验收

### 17.1 多线程正式模式

配置：

```yaml
run:
  number_of_threads: 8
  debug: false
```

验收点：

- 每个 worker 写独立临时 CSV。
- worker 不共享同一个 `std::ofstream`。
- master 在 run end 合并临时 CSV。
- 最终 `events.csv` 只有一个 header。
- 正式模式合并成功后删除对应临时 CSV。
- 合并失败时保留所有临时 CSV 并报错。

### 17.2 多线程 debug 模式

配置：

```yaml
run:
  number_of_threads: 8
  debug: true
```

验收点：

- 最终 `events_debug.csv` 只有一个 header。
- debug 模式合并成功后保留线程临时 CSV。
- 临时 CSV header 与 debug header 一致。

### 17.3 多线程与 seed

验收点：

- 一个 run 对应一个 pose 和一个实际 seed。
- 一个 run 可以使用多个 worker thread。
- 多线程不改变 run 与 pose / seed 的对应关系。
- metadata 记录该 pose run 实际使用的 `random_seed` 和 `number_of_threads`。

---

## 18. 多 pose 输出验收

使用 list mode 多 pose 配置：

```yaml
pose:
  mode: list
  list:
    head_offset_x_mm: [0, 10, -10]
    head_offset_y_mm: [0, 5, -4]
```

验收点：

- 程序生成三个独立 pose。
- 每个 pose 独立运行 `n_primary_per_pose` 个 primary gamma。
- 每个 pose 独立输出目录：

```text
results/pose_x0_y0_normal_seed12345/
results/pose_x10_y5_normal_seed12346/
results/pose_xm10_ym4_normal_seed12347/
```

- 每个目录有独立 `events.csv` 或 `events_debug.csv`。
- 每个目录有独立 `metadata.yaml`。
- metadata 中的 `run_id` 与目录名一致，`pose_id` 与对应 offset 一致。

---

## 19. 后处理边界验收

本轮不得输出或实现：

- detector region ID；
- depth region ID；
- 二维响应图；
- normal / abnormal 差异图；
- CNR；
- `M_RJ`；
- `H_k`；
- `H_ms`；
- `F_ms`；
- `D_JS`；
- SVD 或 effective rank；
- pose_summary.csv；
- scan_summary.csv；
- 后处理脚本。

这些留到下一轮后处理项目迭代。

---

## 20. 非目标检查

第二版基础构建不得主动加入或继续继承第一轮实现中的：

- 整车 CAD 复现；
- 真实探测器材料响应；
- sensitive detector 能量沉积；
- 图像重建；
- 连续运动扫描；
- 运动模糊；
- 时间相关积分；
- 成像头旋转；
- 成像头 z 方向运动；
- 镜像准直器；
- 镜像探测器；
- PMMA 主模型；
- air defect；
- `PMMALogical` 散射过滤；
- `hits_profile_*` 输出命名；
- 第一轮 compact/debug CSV header；
- 在 Geant4 内生成统计图；
- pose-level summary；
- scan-level summary；
- 后处理脚本。

---

## 21. 最小端到端验收

使用默认样例配置运行：

```bash
./build/MSS --config data/simulation_config_v2.yaml
```

或 README 中定义的等价命令。

验收点：

- 程序正常结束。
- 读取 `data/simulation_config_v2.yaml`。
- 读取 `vehicle_roi_v03.yaml`。
- 构建 VehicleROI。
- 构建 source、slit collimator、virtual detector plane。
- 运行 `10000` 个 primary gamma。
- 生成：

```text
results/pose_x0_y0_normal_seed12345/events.csv
results/pose_x0_y0_normal_seed12345/metadata.yaml
```

- `events.csv` header 正确。
- `metadata.yaml` 中 `pose_id = pose_x0_y0`。
- `metadata.yaml` 中 `head_offset_x_mm = 0`，`head_offset_y_mm = 0`。
- metadata 中不出现 `vehicle_shift_x/y`。
- metadata 中记录固定 World 与该 pose run 实际 random_seed。
- 若没有 detected event，正式 CSV 可以只有 header，但程序仍应正常结束。
