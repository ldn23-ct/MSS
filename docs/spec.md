# 第二版车辆侧向背散射 ROI 仿真项目规格书

## 0. 文档定位

本文档定义第二版车辆侧向背散射 ROI Geant4 仿真项目的正式需求规格。

第二版项目不是第一版项目的小修补。第一版文件、代码和文档仅作为历史参考，用于复用项目组织经验、CSV 输出链路经验和多线程输出经验；第二版的几何对象、扫描方式、事件字段和配置入口以本文档为准。

第二版项目同时服务两条需求线：

| 需求线 | 目标 |
|---|---|
| A 线：项目摸底 | 判断固定车辆 ROI + 移动成像头条件下，原始探测器二维响应是否包含可解释结构信息。 |
| B 线：论文数据 | 记录被探测 primary gamma 的散射阶次、过程计数、first / last scatter 空间位置和区域归因，用于多重散射性质分析。 |

本文档不定义后处理绘图、不定义图像重建算法、不定义真实探测器响应模型。

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
| 车辆几何配置 | `vehicle_roi_v03.yaml` |
| 运行配置 | `simulation_config_v2.yaml` |
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

程序需要输出被探测 primary gamma 的事件级统计量，用于后处理生成：

- 探测器二维响应图；
- normal / abnormal 差异图；
- 探测能量分布；
- 单散射 / 多重散射比例；
- Compton / Rayleigh 过程贡献；
- first / last scatter 空间分布；
- first / last scatter region 归因；
- 位姿级和扫描级响应图。

第二版不要求在 Geant4 程序内完成图像重建或统计图生成。

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

被探测 primary gamma 是从车辆 ROI 方向返回成像头侧，并沿 `-z` 方向穿越虚拟探测器平面的 gamma。

---

## 4. 配置文件体系

第二版使用两个 YAML 文件作为主配置入口。

```text
vehicle_roi_v03.yaml
simulation_config_v2.yaml
```

### 4.1 `vehicle_roi_v03.yaml`

该文件负责描述车辆 ROI：

- VehicleROI 总范围；
- 几何组件；
- host / daughter 关系；
- normal / abnormal insert；
- material；
- region_id；
- AABB；
- placement 信息；
- overlap 检查需要的元数据。

### 4.2 `simulation_config_v2.yaml`

该文件负责描述仿真运行条件：

- run 参数；
- source 参数；
- collimator 参数；
- detector 参数；
- pose / scan 参数；
- physics 参数；
- output 参数；
- normal / abnormal 模型选择。

宏命令可作为调试接口，但第二版正式配置不以 Geant4 macro 为主入口。

---

## 5. `simulation_config_v2.yaml` 规格

### 5.1 顶层结构

```yaml
schema_version: 2

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

  grid:
    x_offsets_mm: []
    y_offsets_mm: []

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

### 5.2 样例值说明

样例配置中的：

```yaml
source_pos_zero_mm: [0.0, 0.0, -185.0]
detector_z_zero_mm: -73.0
detector_x_range_zero_mm: [53.0, 161.0]
detector_y_range_zero_mm: [-50.0, 50.0]
```

来自第一版链路验证用数值。它们仅作为第二版程序构建、可视化和端到端输出测试的默认样例，不作为第二版最终成像头几何的不可修改物理常量。

---

## 6. 车辆 ROI 模型

### 6.1 总体范围

第二版车辆 ROI 模型使用 `vehicle_roi_v03.yaml` 描述。默认 ROI 范围为：

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
  spectrum_file: data/spectrum.csv
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

准直器 profile 文件沿用第一版表头：

```csv
profile_id,jaw_id,vertex_id,x_mm,z_mm
```

字段含义：

| 字段 | 含义 |
|---|---|
| `profile_id` | profile ID。 |
| `jaw_id` | jaw 编号，格式为 `jaw_0 ... jaw_{M-1}`。 |
| `vertex_id` | 同一 jaw 内顶点编号。 |
| `x_mm` | 零位姿 global x 坐标，单位 mm。 |
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
track_id == 1
parent_id == 0
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

同一 event 中，第一次有效探测命中被记录。后续穿越不再产生额外正式 CSV 行。

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

### 13.1 追踪对象

只记录 primary gamma：

```text
particle_name == gamma
track_id == 1
parent_id == 0
```

secondary gamma、电子、正电子等不进入事件级散射摘要。

### 13.2 detected 与 undetected

正式 `events.csv`：

```text
只记录 detected primary gamma
```

Debug CSV：

```text
记录 detected 和 undetected primary gamma
```

Debug CSV 使用字段：

```text
detected
```

区分事件是否被探测。

### 13.3 散射记录原则

对于 primary gamma，记录其 Compton / Rayleigh 散射历史。

事件是否进入正式 CSV 只由是否被探测器探测到决定，不由散射发生在哪个 volume 决定。

统计过程：

| 过程 | 是否计入 |
|---|---|
| Compton scattering，process name `compt` | 是 |
| Rayleigh scattering，process name `Rayl` | 是 |
| Photoelectric effect | 否 |
| secondary particle interactions | 否 |

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

### 13.4 记录变量

每个 event 维护：

```text
event_id
detected
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

无散射时：

```text
first_scatter_x/y/z = NaN
last_scatter_x/y/z = NaN
first_scatter_region_id = none
last_scatter_region_id = none
scatter_count_total = 0
compton_count = 0
rayleigh_count = 0
```

---

## 14. 正式事件级 CSV

### 14.1 输出对象

正式 `events.csv` 只输出 detected primary gamma。

```text
1 row = 1 detected primary gamma
```

未探测 event 不进入正式 `events.csv`。

### 14.2 Header

正式 `events.csv` header 为：

```csv
event_id,det_x,det_y,det_z,det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,first_scatter_region_id,last_scatter_region_id
```

### 14.3 字段含义

| 字段 | 含义 |
|---|---|
| `event_id` | Geant4 event 编号。 |
| `det_x` | 探测平面命中点 x 坐标，单位 mm。 |
| `det_y` | 探测平面命中点 y 坐标，单位 mm。 |
| `det_z` | 探测平面命中点 z 坐标，单位 mm。 |
| `det_energy` | 到达探测平面时 primary gamma 能量，单位 keV。 |
| `scatter_count_total` | primary gamma 的 Compton + Rayleigh 总次数。 |
| `compton_count` | Compton 次数。 |
| `rayleigh_count` | Rayleigh 次数。 |
| `first_scatter_x/y/z` | 第一次有效散射位置，单位 mm。 |
| `last_scatter_x/y/z` | 最后一次有效散射位置，单位 mm。 |
| `first_scatter_region_id` | 第一次有效散射对应的 region_id。 |
| `last_scatter_region_id` | 最后一次有效散射对应的 region_id。 |

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
detected primary gamma
undetected primary gamma
```

### 15.2 Header

Debug CSV header 为：

```csv
event_id,detected,det_x,det_y,det_z,det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,first_scatter_region_id,last_scatter_region_id
```

### 15.3 未探测事件填写规则

若 `detected = 0`：

```text
det_x = NaN
det_y = NaN
det_z = NaN
det_energy = NaN
```

散射字段按 event 已发生的追踪结果填写。

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

Debug CSV 不包含其他可选字段。

---

## 16. metadata.yaml

每个 pose 输出一个 `metadata.yaml`，记录 run-level 条件。

示例：

```yaml
run_id: pose_x0_y0_normal_seed12345
output_csv: events.csv

model_type: normal
vehicle_model_id: vehicle_roi_v03
vehicle_geometry_file: data/vehicle_roi_v03.yaml
selected_target_component: null
abnormal_target_type: none
abnormal_target_region: none

pose_id: pose_x0_y0
head_offset_x_mm: 0
head_offset_y_mm: 0

n_primary: 10000
random_seed: 12345
number_of_threads: 8

debug: false

source:
  particle: gamma
  energy_mode: mono
  mono_energy_keV: 160.0
  spectrum_file: data/spectrum.csv
  incident_theta_deg: 45.0
  focal_spot_diameter_mm: 5.0
  source_pos_zero_mm: [0.0, 0.0, -185.0]

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

notes: sample config for pipeline validation
```

metadata 不重复写入每一行 CSV。

---

## 17. 输出文件组织

### 17.1 每个位姿独立输出

每个 pose 独立运行一组 Monte Carlo 统计。

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

---

## 21. 后处理边界

Geant4 程序只负责输出事件级数据和 metadata。

以下内容由后处理完成：

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

Geant4 不直接输出 detector region ID 或 depth region ID。

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
15. 正式 `events.csv` 只输出 detected primary gamma；
16. debug CSV 输出 detected + undetected，并使用 `detected` 字段区分；
17. 正式 CSV header 与本文档一致；
18. debug CSV header 与本文档一致；
19. `metadata.yaml` 使用 `head_offset_x_mm` 和 `head_offset_y_mm`，不使用 `vehicle_shift_x/y`；
20. 多线程输出不共享同一个输出流；
21. master 合并后最终 CSV 只保留一个 header。

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
