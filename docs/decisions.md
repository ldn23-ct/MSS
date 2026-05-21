# 第二版设计决策记录

## 1. 文档目的

本文档记录第二版车辆侧向背散射 ROI 仿真项目中已经接受的关键设计决策，用于约束后续规格、架构、里程碑、验收清单和代码实现，避免在实现过程中发生设计漂移。

本文档不替代 `spec.md`。功能需求、字段定义、配置格式、物理参数、验收条件仍以 `spec.md` 为最高依据。

文档优先级：

1. `spec.md`
2. `decisions.md`
3. `architecture.md`
4. `milestones.md`
5. `acceptance_checklist.md`
6. 现有代码，但前提是不与上述文档冲突

若必须修改 Accepted 决策，应先更新本文档，再同步更新规格和实现。

---

## 2. 决策状态

| 状态 | 含义 |
|---|---|
| Accepted | 已接受，当前实现必须遵守。 |
| Proposed | 提案中，尚未成为实现约束。 |
| Superseded | 已被后续决策取代。 |
| Deferred | 有价值，但明确推迟。 |

---

## 3. 决策索引

| ID | 决策 | 状态 |
|---|---|---|
| D001 | 第二版是围绕车辆侧向 ROI 的重构项目，不直接继承第一版硬规格 | Accepted |
| D002 | 主配置入口采用两个 YAML 文件 | Accepted |
| D003 | 固定车辆 ROI，移动成像头组件 | Accepted |
| D004 | 使用 `head_offset_x/y`，废弃 `vehicle_shift_x/y` | Accepted |
| D005 | pose 支持 list / grid 两种生成模式，`pose_id` 自动生成 | Accepted |
| D006 | 成像头由 Source、SlitCollimator 和 VirtualDetectorPlane 组成 | Accepted |
| D007 | 射线源采用斜入射有限焦点笔形束 | Accepted |
| D008 | 能量模式保留 mono / spectrum | Accepted |
| D009 | 狭缝准直器沿用 CSV 表头，但 jaw 数量可变且不构建镜像 | Accepted |
| D010 | 探测器为单个理想虚拟平面，不模拟真实探测器响应 | Accepted |
| D011 | 探测器位于准直器之后，采用 `negative_z` 有效穿越方向 | Accepted |
| D012 | 正式 CSV 只记录 detected primary gamma，debug CSV 记录 detected 与 undetected | Accepted |
| D013 | 正式事件级 CSV 同时服务项目摸底线和论文数据线 | Accepted |
| D014 | 输出组织采用 `events.csv` + `metadata.yaml` | Accepted |
| D015 | 事件是否进入正式输出只由 detector hit 决定，不由散射发生位置决定 | Accepted |
| D016 | 散射 region 归属使用 preStep volume | Accepted |
| D017 | 车辆 ROI 几何由 YAML 构建，normal / abnormal 只替换 insert 材料和 region | Accepted |
| D018 | 使用 `G4EmLivermorePhysics`，默认 production cut 为 `0.1 mm` | Accepted |
| D019 | 多线程输出继承线程临时 CSV + master 合并策略 | Accepted |
| D020 | Geant4 程序只输出事件级数据和 metadata，统计图与指标后处理完成 | Accepted |
| D021 | 样例源和探测器位置可使用第一版数值，但只作为链路验证默认值 | Accepted |
| D022 | 模块职责保持窄边界 | Accepted |
| D023 | 无效配置、非法几何、非法 profile 和输出错误必须 fail fast | Accepted |
| D024 | 第二版基础构建不包含真实探测器响应、图像重建和连续运动扫描 | Accepted |

---

## D001：第二版是围绕车辆侧向 ROI 的重构项目，不直接继承第一版硬规格

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第一版项目完成了基础背散射 Geant4 链路验证，包括源、准直器、简单模体、探测面、事件级 CSV 和多线程输出。第二版研究对象已经转为车辆侧向 ROI 成像摸底和多重散射统计分析。

### 决策

第二版不是第一版的小修补。第一版文件、代码和文档只作为历史参考。

第二版的几何对象、扫描方式、源模型、准直器规则、探测器定义、事件字段、输出组织和配置入口均以第二版文档为准。

### 影响

- 不默认继承第一版 PMMA 模体。
- 不默认继承第一版 CSV schema。
- 不默认继承第一版镜像准直器或镜像探测器。
- 可复用第一版的项目组织经验、线程输出经验和部分样例数值。

---

## D002：主配置入口采用两个 YAML 文件

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版参数数量明显增加，包括车辆 ROI 几何、normal / abnormal 模型、成像头位置、扫描 pose、源、准直器、探测器、线程和输出。仅用 Geant4 macro 不利于表达嵌套结构和批量 pose。

### 决策

第二版主配置入口采用两个 YAML 文件：

```text
vehicle_roi_v03.yaml
simulation_config_v2.yaml
```

其中：

| 文件 | 职责 |
|---|---|
| `vehicle_roi_v03.yaml` | 车辆 ROI 几何、材料、host / daughter、insert、region_id。 |
| `simulation_config_v2.yaml` | run、pose、source、collimator、detector、physics、output、model_type。 |

Geant4 macro 可作为调试接口，但不是第二版正式配置入口。

### 影响

- 需要实现 YAML 配置读取和严格验证。
- 配置错误应在 Geant4 run 前报错停止。
- 输出 metadata 应记录实际使用的 YAML 配置条件。

---

## D003：固定车辆 ROI，移动成像头组件

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版关注车辆侧向 ROI 场景下成像头位姿变化引起的探测响应。若平移车辆 ROI，会破坏车辆结构在全局坐标中的解释稳定性。

### 决策

扫描组织方式为：

```text
固定车辆 ROI
+ 移动成像头组件
+ 每个 pose 独立 Monte Carlo 统计
```

车辆 ROI 在所有 pose 中保持固定。成像头组件整体按 `head_offset_x/y` 平移。

### 影响

- `VehicleROIConstruction` 不负责扫描平移。
- `ImagingHeadConstruction` 统一接收当前 pose offset。
- first / last scatter 坐标始终位于稳定的全局车辆坐标系中。

---

## D004：使用 `head_offset_x/y`，废弃 `vehicle_shift_x/y`

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

早期统计文档中出现过 `vehicle_shift_x/y`，但第二版扫描原则已经明确为车辆 ROI 固定、成像头移动。

### 决策

第二版统一使用：

```text
head_offset_x_mm
head_offset_y_mm
```

废弃：

```text
vehicle_shift_x
vehicle_shift_y
```

### 影响

- `metadata.yaml` 必须使用 `head_offset_x_mm` 和 `head_offset_y_mm`。
- CSV 中不写入 `vehicle_shift_x/y`。
- 架构、里程碑和验收文档不得再使用车辆平移语义描述扫描。

---

## D005：pose 支持 list / grid 两种生成模式，`pose_id` 自动生成

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版需要支持手动指定若干离散偏置，也需要支持规则扫描网格。`pose_id` 若手写，容易与 offset 不一致。

### 决策

`simulation_config_v2.yaml` 中 pose 支持两种模式：

```text
list
grid
```

list mode：

```text
第 i 个 head_offset_x 与第 i 个 head_offset_y 配对。
```

grid mode：

```text
x_offsets 与 y_offsets 取笛卡尔积。
```

`pose_id` 不由用户直接设置，而是由整数 mm offset 自动生成。

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

| offset | pose_id |
|---|---|
| `(0, 0)` | `pose_x0_y0` |
| `(2, 1)` | `pose_x2_y1` |
| `(-2, 1)` | `pose_xm2_y1` |
| `(1111, 0)` | `pose_x1111_y0` |

### 影响

- 第一阶段 offset 只支持整数 mm。
- 不支持小数 offset。
- list mode 中 x/y 数组长度不同必须报错。

---

## D006：成像头由 Source、SlitCollimator 和 VirtualDetectorPlane 组成

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版成像系统需要表达源、准直器和探测器的相对位置，并在扫描时保持相对位置不变。

### 决策

成像头为刚性组件组：

```text
ImagingHead = Source + SlitCollimator + VirtualDetectorPlane
```

成像头整体在 `x-y` 平面内平移，不旋转，不沿 `z` 方向运动。

### 影响

- source、collimator、detector 共享同一个 `head_offset`。
- 成像头内部相对位置在同一 pose 中保持不变。
- 成像头旋转、连续运动和运动模糊不属于基础构建。

---

## D007：射线源采用斜入射有限焦点笔形束

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版成像头不再采用第一版的点源锥束目标平面采样，而需要表达斜入射笔形束。

### 决策

每个 event 产生一个 primary gamma。源模型为：

```text
斜入射有限焦点笔形束
```

入射方向：

```text
incident_dir = (cos(theta), 0, sin(theta))
0° < theta <= 90°
```

焦点面为垂直于 `incident_dir` 的圆形平面，primary gamma 起点在该圆形焦点面内均匀采样，方向固定为 `incident_dir`。

### 影响

- 第一版锥束目标面采样不再使用。
- `source_pos_zero_mm`、`incident_theta_deg`、`focal_spot_diameter_mm` 从 YAML 读取。
- 样例值可为 `theta = 45°`、`focal_spot_diameter = 5 mm`。

---

## D008：能量模式保留 mono / spectrum

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

mono 模式适合链路验证和可重复调试，spectrum 模式用于后续接入真实能谱。

### 决策

第二版继续支持：

```text
mono
spectrum
```

mono 模式使用 `mono_energy_keV`。spectrum 模式读取 `energy_keV,weight` CSV 并按权重采样。

### 影响

- 需要保留 `SpectrumSampler` 或等价模块。
- spectrum CSV 需严格验证能量和权重。
- 能量模式信息写入 `metadata.yaml`。

---

## D009：狭缝准直器沿用 CSV 表头，但 jaw 数量可变且不构建镜像

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版仍希望复用第一版外部 profile 文件组织方式，但斜入射破坏了第一版关于 `x=0` 的左右对称假设。

### 决策

准直器 profile 表头沿用：

```csv
profile_id,jaw_id,vertex_id,x_mm,z_mm
```

第二版规则：

```text
jaw 数量可变，M >= 1
jaw_id 必须连续为 jaw_0 ... jaw_{M-1}
每块 jaw 为凸多边形，N >= 3
不构建镜像准直器
```

CSV 中的 `x_mm,z_mm` 表示零位姿 global `x-z` 坐标。

### 影响

- 第一版固定三块 jaw 的读取逻辑需要改写。
- 第一版镜像 jaw 构建逻辑不得进入第二版。
- 可暂用第一版 `P001` 作为链路验证占位 profile。

---

## D010：探测器为单个理想虚拟平面，不模拟真实探测器响应

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

当前阶段只需要采集事件级统计量，不需要真实探测器材料响应或能量沉积 scoring。

### 决策

第二版探测器为单个理想虚拟探测平面。

不包含：

- 真实探测器材料；
- sensitive detector；
- 能量沉积 scoring；
- 镜像探测器。

探测记录来自几何穿越判定。

### 影响

- `det_energy` 表示 primary gamma 穿越虚拟探测平面时的能量。
- detector region mapping 和 depth mapping 由后处理完成。

---

## D011：探测器位于准直器之后，采用 `negative_z` 有效穿越方向

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版仍为背散射结构。探测器和准直器的相对位置按第一版链路验证关系组织：准直器夹在车辆 ROI 与探测平面之间。

### 决策

几何关系：

```text
VehicleROI
→ SlitCollimator
→ VirtualDetectorPlane
```

探测器有效穿越方向采用：

```yaml
accept_direction: negative_z
```

对应判定：

```text
preStep.z > detector_z
postStep.z <= detector_z
direction.z < 0
```

### 影响

- 探测器位置和接收范围仍由 YAML 配置。
- 样例配置可使用第一版链路验证数值。
- 同一 event 只记录第一次有效 detector hit。

---

## D012：正式 CSV 只记录 detected primary gamma，debug CSV 记录 detected 与 undetected

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

正式统计文件应聚焦探测器可见事件，避免未探测事件显著增加文件体积。调试阶段需要检查未探测 event 的散射记录和事件生命周期。

### 决策

正式 `events.csv`：

```text
只记录 detected primary gamma
```

Debug CSV：

```text
记录 detected primary gamma 和 undetected primary gamma
```

Debug CSV 只比正式 CSV 增加一个字段：

```csv
detected
```

不增加其他 termination 类可选字段。

### 影响

- 正式 CSV 无 `detected` 字段。
- Debug CSV 中未探测 event 的 det 字段填 `NaN`。
- debug 模式不输出 `termination_process`、`termination_volume` 或 `termination_region_id`。

---

## D013：正式事件级 CSV 同时服务项目摸底线和论文数据线

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

项目摸底需要探测面二维响应、能量和 first / last scatter 来源。论文数据需要散射阶次和过程计数。

### 决策

正式 `events.csv` 采用统一 schema，同时包含：

- 探测位置；
- 探测能量；
- scatter_count_total；
- compton_count；
- rayleigh_count；
- first / last scatter 坐标；
- first / last scatter region_id。

### 影响

- 不再拆分“摸底版 CSV”和“论文版 CSV”。
- 后处理可从同一个 `events.csv` 计算 A 线和 B 线指标。

---

## D014：输出组织采用 `events.csv` + `metadata.yaml`

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

run-level 条件不应重复写入每个事件行，否则 CSV 冗余且不利于保持事件字段稳定。

### 决策

每个 pose 输出：

```text
events.csv 或 events_debug.csv
metadata.yaml
```

`metadata.yaml` 记录：

- run_id；
- model_type；
- pose_id；
- head_offset_x/y；
- n_primary；
- random_seed；
- source；
- collimator；
- detector；
- physics；
- vehicle geometry file。

### 影响

- CSV 中不重复写入 `pose_id`、`model_type`、`head_offset_x/y`。
- 后处理通过 metadata 建立 run 条件与事件文件的关系。

---

## D015：事件是否进入正式输出只由 detector hit 决定，不由散射发生位置决定

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

事件保留条件应反映探测器是否观察到该 primary gamma，而不是预先根据散射发生在哪种材料或 region 过滤事件。

### 决策

正式事件输出条件为：

```text
detected == true
```

对于 detected primary gamma，记录其 Compton / Rayleigh 散射历史。散射发生在哪个 region 只用于归因解释，不用于决定事件是否输出。

### 影响

- 不使用“只统计实体车辆材料区”作为事件保留条件。
- region_id 是解释字段，不是事件筛选字段。
- `vehicle_background_air`、`cabin_air` 等 region 可以作为散射归属结果出现，若 primary gamma 在相应区域发生有效 Compton / Rayleigh。

---

## D016：散射 region 归属使用 preStep volume

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

Geant4 step 的 post point 可能位于边界或进入下一 volume。若用 postStep volume 做 region 归属，贴边事件容易归入下一个体积。

### 决策

散射坐标使用：

```text
postStep position
```

散射 region 归属使用：

```text
preStep volume 对应的 region_id
```

规则：

| 情况 | region 归属 |
|---|---|
| step 起点位于子 volume | 子 volume 的 region_id |
| step 起点位于 VehicleROI 空气母体 | `vehicle_background_air` |
| step 起点位于未注册区域 | `other` |
| 无有效散射 | `none` |

### 影响

- `SteppingAction` 需要同时取 postStep position 和 preStep volume。
- `RegionResolver` 必须支持 volume 到 region_id 的映射。

---

## D017：车辆 ROI 几何由 YAML 构建，normal / abnormal 只替换 insert 材料和 region

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版车辆 ROI 需要表达 normal / abnormal 配对，但不希望 normal 与 abnormal 几何尺寸不同，否则差异图难以解释。

### 决策

车辆 ROI 几何由 `vehicle_roi_v03.yaml` 构建。

normal / abnormal 规则：

```text
normal:
  insert material = host material
  insert region_id = host region_id

abnormal:
  selected_target_component:
    material = abnormal_material
    region_id = target
  other inserts:
    material = host material
    region_id = host region_id
```

第一阶段每个 abnormal run 只启用一个 selected target component。

### 影响

- abnormal 模式下 `selected_target_component` 不能为空。
- 指定 target component 必须存在且必须是 insert。
- normal / abnormal 几何形状完全一致。

---

## D018：使用 `G4EmLivermorePhysics`，默认 production cut 为 `0.1 mm`

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版关注低能 gamma 背散射和 Compton / Rayleigh 过程统计。第一版中该物理列表已作为可用基础。

### 决策

默认使用：

```text
G4EmLivermorePhysics
```

默认 production cut：

```text
0.1 mm
```

### 影响

- `PhysicsList` 不应包含几何、输出或事件记录逻辑。
- 后续若更换 physics list，应先更新本文档和 `spec.md`。

---

## D019：多线程输出继承线程临时 CSV + master 合并策略

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

Geant4 多线程中多个 worker 共享同一个输出流容易产生竞争和文件损坏。第一版已经验证线程临时 CSV + master 合并策略可行。

### 决策

第二版继承该策略：

1. 每个 worker 写独立临时 CSV；
2. worker 之间不共享 `std::ofstream`；
3. master 在 run end 合并临时 CSV；
4. 最终 CSV 只保留一个 header；
5. 正式模式合并成功后删除临时文件；
6. debug 模式合并成功后保留临时文件；
7. 合并失败时保留所有临时文件并报错。

### 影响

- `CsvWriter` 必须线程本地化。
- `RunAction` 或 `PoseRunController` 负责触发合并。
- 不允许 worker 直接写最终 CSV。

---

## D020：Geant4 程序只输出事件级数据和 metadata，统计图与指标后处理完成

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版同时服务项目摸底和论文分析，但 Geant4 程序不应承担后处理绘图和统计分析职责。

### 决策

Geant4 程序只输出：

```text
events.csv / events_debug.csv
metadata.yaml
```

以下内容由后处理完成：

- 二维响应图；
- normal / abnormal 差异图；
- CNR；
- detector region mapping；
- depth region mapping；
- `M_RJ`；
- `H_k`；
- `H_ms`；
- `F_ms`；
- `D_JS`；
- SVD / effective rank。

### 影响

- Geant4 不输出 detector region ID。
- Geant4 不输出 depth region ID。
- 后处理通过 metadata 组织 run 条件。

---

## D021：样例源和探测器位置可使用第一版数值，但只作为链路验证默认值

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版成像头真实几何仍可通过 YAML 调整。为了尽快完成链路验证，需要提供可运行默认值。

### 决策

样例配置可使用：

```yaml
source_pos_zero_mm: [0.0, 0.0, -185.0]
detector_z_zero_mm: -73.0
detector_x_range_zero_mm: [53.0, 161.0]
detector_y_range_zero_mm: [-50.0, 50.0]
```

这些值只作为第二版程序构建、可视化和端到端输出测试的默认样例，不是第二版最终成像头几何的不可修改物理常量。

### 影响

- 文档中必须标注这些值的样例性质。
- 后续可以只修改 YAML，不改代码。

---

## D022：模块职责保持窄边界

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版模块更多，若职责不清，后续用 Codex 分阶段实现时容易出现跨模块污染。

### 决策

模块边界应保持明确：

| 模块 | 职责 |
|---|---|
| YAML reader | 读取和验证配置。 |
| Vehicle ROI construction | 构建车辆 ROI，不处理 pose offset。 |
| Imaging head construction | 构建 source 辅助体、准直器和探测器辅助体，统一应用 pose offset。 |
| Source model | 生成 primary gamma。 |
| Stepping action | 记录 primary gamma 散射和探测穿越。 |
| Event action | 维护单 event 状态，控制 event 写出。 |
| Csv writer | 写线程本地 CSV 并合并。 |
| Metadata writer | 写 run-level metadata。 |

### 影响

- CSV 写入不放在 `SteppingAction`。
- 准直器 CSV 解析不散落在几何构建代码中。
- 后处理指标不进入 Geant4 主程序。

---

## D023：无效配置、非法几何、非法 profile 和输出错误必须 fail fast

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

车辆 ROI、pose、source、detector、collimator 和输出路径中任一错误都可能生成看似合理但实际不可解释的数据。

### 决策

以下错误必须在事件产生前或出错点立即报错停止：

- YAML 字段缺失或类型错误；
- 非法 pose；
- detector range 非法；
- abnormal target 无效；
- host / daughter 不合法；
- overlap；
- 非法 collimator profile；
- spectrum 文件非法；
- 输出目录或 CSV 无法创建；
- 多线程合并失败。

### 影响

- 不做静默 fallback。
- 不自动修复非法 profile 或几何。
- 错误信息应指出字段、文件或组件名。

---

## D024：第二版基础构建不包含真实探测器响应、图像重建和连续运动扫描

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版当前目标是搭建车辆侧向 ROI 背散射事件级数据生成链路，而不是完整工程成像系统。

### 决策

第二版基础构建不包含：

- 整车 CAD 复现；
- 真实探测器材料响应；
- sensitive detector 能量沉积；
- 图像重建；
- 后处理绘图；
- 连续运动扫描；
- 运动模糊；
- 时间相关积分；
- 成像头旋转；
- 成像头 z 方向运动；
- 镜像准直器；
- 镜像探测器。

### 影响

- 所有这些内容进入 deferred work。
- Codex 不得在基础构建中主动实现这些功能。

---

## 4. 变更控制

修改 Accepted 决策时应：

1. 将旧决策标记为 `Superseded`；
2. 新增决策 ID；
3. 说明变化内容和原因；
4. 同步更新 `spec.md`、`architecture.md`、`milestones.md` 和 `acceptance_checklist.md` 中受影响的内容。
