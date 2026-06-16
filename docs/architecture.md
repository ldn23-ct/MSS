# 第二版架构说明

## 1. 文档目的

本文档定义第二版车辆侧向背散射 ROI Geant4 仿真项目的代码组织方式、模块边界、核心数据结构、运行生命周期和数据流。

本文档服务于后续分阶段实现。它不重复 `spec.md` 中的全部物理参数和字段定义；若本文档与 `spec.md` 冲突，以 `spec.md` 为准。

文档优先级：

1. `spec.md`
2. `decisions.md`
3. `architecture.md`
4. `milestones.md`
5. `acceptance_checklist.md`

---

## 2. 架构目标

第二版程序的核心任务是：

```text
读取 YAML 配置
构建固定 VehicleROI
构建按 pose 平移的 ImagingHead
产生斜入射有限焦点 primary gamma
记录 detected gamma hit 的事件级统计量
输出 events.csv / events_debug.csv 与 metadata.yaml
本轮不实现 pose-level / scan-level 数据、summary、图表、统计指标或后处理脚本
```

架构设计应满足：

- 车辆 ROI 与成像头职责分离；
- 配置读取与 Geant4 构建分离；
- YAML 解析器固定采用已批准的 `yaml-cpp`；
- 事件状态与 step 判断分离；
- CSV 输出与后处理统计分离，本轮不实现后处理模块；
- 多线程输出不共享同一个输出流；
- 每个 pose 可作为独立静态几何状态运行；
- 所有非法配置和非法几何 fail fast。

---

## 3. 总体模块划分

| 关注点 | 主要模块 |
|---|---|
| YAML 读取与验证 | `SimulationConfigReader`, `VehicleROIConfigReader` |
| YAML / CLI 兼容入口 | `SimulationMessenger`，仅允许指定或切换入口 YAML 文件路径 |
| 配置对象 | `SimulationConfig`, `VehicleROIConfig`, `ScanPose`, `PoseList` |
| 材料管理 | `MaterialManager` |
| region 注册与查询 | `RegionRegistry`, `RegionResolver` |
| Geant4 几何总装 | `DetectorConstruction` 或 `GeometryAssembly` |
| 车辆 ROI 构建 | `VehicleROIConstruction` |
| 成像头构建 | `ImagingHeadConstruction` |
| 准直器 profile 读取 | `SlitCollimatorProfileReader` |
| 准直器几何构建 | `SlitCollimatorBuilder` |
| 虚拟探测器配置 | `VirtualDetectorPlane` |
| primary gamma 产生 | `PrimaryGeneratorAction`, `SourceModel`, `SpectrumSampler` |
| physics list | `PhysicsList` |
| event 状态 | `EventAction`, `EventRecord` |
| step 判断 | `SteppingAction` |
| pose 生成 | `ScanPoseManager` |
| run / pose 生命周期 | `PoseRunController`, `RunAction` |
| CSV 输出与合并 | `CsvWriter` |
| metadata 输出 | `MetadataWriter` |

### 3.1 现有代码迁移边界

当前仓库仍保留第一轮 PMMA 背散射实现。第二轮重构允许机制级复用，但不得语义级继承第一轮物理模型、入口和输出 schema。

| 现有模块 / 文件 | 第二轮处理方式 |
|---|---|
| `CollimatorProfileReader` | 可参考 CSV 解析、BOM 处理、顶点连续性和凸多边形检查；第二轮实现应迁移为 `SlitCollimatorProfileReader`，支持可变 jaw 和可选 `y_mm`。 |
| `CollimatorBuilder` | 可参考 `G4ExtrudedSolid` 构建方式；第二轮实现应迁移为 `SlitCollimatorBuilder`，移除固定三 jaw 和 mirror jaw，按 pose offset placement。 |
| 旧 `DetectorConstruction` | 不应继续承载 PMMA / air defect / mirror detector 语义；第二轮应拆分为 `GeometryAssembly` 或 `DetectorConstruction` 总装、`VehicleROIConstruction` 和 `ImagingHeadConstruction`。 |
| 旧 `SimulationConfig` | 不应继续扩展旧 macro 字段；第二轮应替换为 YAML-based `SimulationConfig`，字段与 `spec.md` 中 `simulation_config_v2.yaml` 对齐。 |
| `SpectrumSampler` | 可复用 spectrum CSV 读取、验证和 CDF sampling 机制。 |
| `CsvWriter` / `RunAction` | 可复用 worker 临时 CSV 与 master merge 机制；formal/debug header、run_id、目录结构和 metadata 必须按第二轮 schema 重写。 |
| `EventAction` / `SteppingAction` | 可复用 event reset、gamma track 过滤、detector crossing 插值和 first/last scatter 更新思路；散射统计范围、region 归因和 CSV 字段必须按第二轮规则重写。 |
| `README.md` / `macros/*.mac` | 当前属于第一轮 legacy 运行说明；第二轮实现时不得作为主入口依据，最终应改为 `--config config/base/simulation_config_v2.yaml` 样例。 |

不得从现有代码继承：PMMA 主模型、air defect、`PMMALogical` 散射过滤、mirror collimator、mirror detector、macro 主配置入口、`hits_profile_*` 文件名、compact/debug 旧 CSV header。

---

## 4. 推荐仓库结构

```text
MSS/
├── CMakeLists.txt
├── README.md
├── main.cc
├── docs/
│   ├── spec.md
│   ├── decisions.md
│   ├── architecture.md
│   ├── milestones.md
│   └── acceptance_checklist.md
├── include/
│   ├── SimulationConfig.hh
│   ├── SimulationConfigReader.hh
│   ├── SimulationMessenger.hh
│   ├── VehicleROIConfig.hh
│   ├── VehicleROIConfigReader.hh
│   ├── MaterialManager.hh
│   ├── RegionRegistry.hh
│   ├── RegionResolver.hh
│   ├── DetectorConstruction.hh
│   ├── VehicleROIConstruction.hh
│   ├── ImagingHeadConstruction.hh
│   ├── SourceModel.hh
│   ├── PrimaryGeneratorAction.hh
│   ├── SpectrumSampler.hh
│   ├── SlitCollimatorProfileReader.hh
│   ├── SlitCollimatorBuilder.hh
│   ├── VirtualDetectorPlane.hh
│   ├── PhysicsList.hh
│   ├── ActionInitialization.hh
│   ├── EventRecord.hh
│   ├── EventAction.hh
│   ├── SteppingAction.hh
│   ├── RunAction.hh
│   ├── ScanPoseManager.hh
│   ├── PoseRunController.hh
│   ├── CsvWriter.hh
│   └── MetadataWriter.hh
├── src/
│   ├── SimulationConfigReader.cc
│   ├── SimulationMessenger.cc
│   ├── VehicleROIConfigReader.cc
│   ├── MaterialManager.cc
│   ├── RegionRegistry.cc
│   ├── RegionResolver.cc
│   ├── DetectorConstruction.cc
│   ├── VehicleROIConstruction.cc
│   ├── ImagingHeadConstruction.cc
│   ├── SourceModel.cc
│   ├── PrimaryGeneratorAction.cc
│   ├── SpectrumSampler.cc
│   ├── SlitCollimatorProfileReader.cc
│   ├── SlitCollimatorBuilder.cc
│   ├── VirtualDetectorPlane.cc
│   ├── PhysicsList.cc
│   ├── ActionInitialization.cc
│   ├── EventAction.cc
│   ├── SteppingAction.cc
│   ├── RunAction.cc
│   ├── ScanPoseManager.cc
│   ├── PoseRunController.cc
│   ├── CsvWriter.cc
│   └── MetadataWriter.cc
├── config/
│   ├── base/
│   │   ├── simulation_config_v2.yaml
│   │   └── diagnostics_base.yaml
│   ├── geometry/
│   │   ├── vehicle_roi_v04.yaml
│   │   └── pmma_box.yaml
│   ├── collimator/
│   │   ├── collimator_profiles.csv
│   │   └── collimator_profiles1.csv
│   ├── source/
│   │   └── spectrum.csv
│   └── generated/
└── results/
    └── .gitkeep
```

允许按实现需要调整文件名，但模块边界不应漂移。

---

## 5. 核心配置结构

### 5.1 `SimulationConfig`

`SimulationConfig` 由 `simulation_config_v2.yaml` 读取生成。

建议结构：

```cpp
struct RunConfig {
    long random_seed = 12345;
    int number_of_threads = 1;
    long n_primary_per_pose = 10000;
    bool debug = false;
};

struct VehicleRunConfig {
    std::string geometry_file;
    std::string model_type;  // normal | abnormal
    std::optional<std::string> selected_target_component;
    std::string abnormal_material = "G4_POLYETHYLENE";
};

struct SourceConfig {
    std::string particle = "gamma";
    std::string energy_mode = "mono";  // mono | spectrum
    double mono_energy_keV = 160.0;
    std::string spectrum_file;
    std::array<double, 3> source_pos_zero_mm;
    double incident_theta_deg = 45.0;
    double focal_spot_diameter_mm = 5.0;
};

struct CollimatorConfig {
    bool enable = true;
    std::string profile_file;
    std::string profile_id;
    double jaw_extrusion_length_y_mm = 120.0;
};

struct DetectorConfig {
    double detector_z_zero_mm;
    double detector_x_min_zero_mm;
    double detector_x_max_zero_mm;
    double detector_y_min_zero_mm;
    double detector_y_max_zero_mm;
    std::string accept_direction = "negative_z";
};

struct PhysicsConfig {
    std::string physics_list = "G4EmLivermorePhysics";
    double production_cut_mm = 0.1;
};

struct OutputConfig {
    std::string output_directory = "results/simulations";
    std::string events_csv_name = "events.csv";
    std::string metadata_yaml_name = "metadata.yaml";
    std::string thread_tmp_directory = "tmp";
    std::string existing_run_policy = "fail";
};

struct WorldConfig {
    std::array<double, 3> center_mm = {0.0, 0.0, 0.0};
    std::array<double, 3> size_mm = {4000.0, 4000.0, 4000.0};
    std::string material = "G4_AIR";
};

struct SimulationConfig {
    int schema_version = 2;
    RunConfig run;
    VehicleRunConfig vehicle;
    SourceConfig source;
    CollimatorConfig collimator;
    DetectorConfig detector;
    PhysicsConfig physics;
    OutputConfig output;
    WorldConfig world;
    PoseList poses;
};
```

### 5.2 `ScanPose`

```cpp
struct ScanPose {
    int pose_index = 0;
    int head_offset_x_mm = 0;
    int head_offset_y_mm = 0;
    long random_seed = 0;
    std::string pose_id;
};
```

第一阶段 offset 只支持整数 mm。每个 pose run 使用一个实际 `random_seed`，默认可按 `base_random_seed + pose_index` 生成。

`pose_id` 自动生成：

```text
pose_x{encoded_x}_y{encoded_y}
```

编码规则：

```text
0      -> 0
正整数 -> 原始十进制数字
负整数 -> m + 绝对值
```

### 5.3 `DetectorPlaneActual`

每个 pose 下计算实际探测器范围：

```cpp
struct DetectorPlaneActual {
    double z_mm;
    double x_min_mm;
    double x_max_mm;
    double y_min_mm;
    double y_max_mm;
};
```

计算规则：

```text
x_min = x_min_zero + head_offset_x
x_max = x_max_zero + head_offset_x
y_min = y_min_zero + head_offset_y
y_max = y_max_zero + head_offset_y
z     = detector_z_zero
```

---

## 6. 车辆 ROI 配置结构

### 6.1 `VehicleROIConfig`

`VehicleROIConfig` 由 `vehicle.geometry_file` 指定的 VehicleROI-compatible YAML 读取生成，例如车辆 ROI YAML 或同 schema 的 PMMA control geometry。

建议包含：

```cpp
struct Aabb {
    std::array<double, 2> x;
    std::array<double, 2> y;
    std::array<double, 2> z;
};

struct BoxComponentConfig {
    std::string name;
    std::string host;
    std::string shape;
    std::string role;
    std::array<double, 3> center_mm;
    std::array<double, 3> size_mm;
    std::array<double, 3> half_size_mm;
    std::array<double, 3> placement_center_in_host_mm;
    Aabb aabb_mm;
    std::string material;
    std::string region_id;

    bool is_insert = false;
    std::optional<std::string> normal_material;
    std::optional<std::string> abnormal_material;
    std::optional<std::string> normal_region_id;
    std::optional<std::string> abnormal_region_id;
};

struct VehicleROIConfig {
    std::string vehicle_model_id;
    BoxComponentConfig root_roi;
    std::vector<BoxComponentConfig> components;
};
```

实现必须按 VehicleROI-compatible YAML 的实际顶层结构读取：

```text
schema / metadata / units / coordinate_system / roi / geant4_placement_rules / materials / model_modes / regions / components / validation
```

不得假设存在 `vehicle_roi:` 顶层字段。`components[]` 中的 `shape` 第一阶段仅支持 `box`，`half_size_mm` 与 `aabb_mm` 用于读取阶段一致性检查。

### 6.2 host / daughter 坐标转换

若 component 是 `VehicleROI` 的直接 daughter：

```text
placement = component_center - VehicleROI_center
```

若 component 是其他 host 的 daughter：

```text
placement = component_center - host_center
```

YAML 中的 `size` 表示全长。构建 `G4Box` 时使用 half length。

### 6.3 normal / abnormal 材料选择

`VehicleROIConstruction` 根据 `VehicleRunConfig` 选择 insert 材料和 region。

normal：

```text
insert material = normal_material
insert region_id = normal_region_id
```

abnormal：

```text
selected_target_component:
  material = abnormal_material
  region_id = target

其他 insert:
  material = normal_material
  region_id = normal_region_id
```

---

## 6.4 DetectorConstruction / GeometryAssembly

### 6.4.1 职责

`DetectorConstruction` 或等价 `GeometryAssembly` 负责在 Geant4 生命周期中总装几何。

职责包括：

- 构建固定 World；
- 调用 `VehicleROIConstruction` 构建固定车辆 ROI；
- 调用 `ImagingHeadConstruction` 构建当前 pose 下的 source 辅助体、collimator jaw 和 virtual detector plane；
- 检查 VehicleROI 与所有 pose 下成像头组件均位于固定 World 内；
- 支持 pose 间重新初始化或重建几何。

不负责：

- 产生 primary gamma；
- 记录 event；
- 写 CSV；
- 生成后处理 summary 或图表。

### 6.4.2 固定 World

本轮 World 固定为：

```text
shape = box
center_mm = [0.0, 0.0, 0.0]
size_mm = [4000.0, 4000.0, 4000.0]
material = G4_AIR
```

不实现按 pose 自动扩展 World。若 VehicleROI、source、collimator jaw 或 detector plane 在任一 pose 下超出固定 World，应在事件产生前 fail fast。

---

## 7. MaterialManager

### 7.1 职责

`MaterialManager` 负责统一创建和查询 Geant4 材料。

必须支持：

| 材料 | 来源 |
|---|---|
| `G4_AIR` | NIST |
| `G4_Fe` | NIST |
| `G4_GLASS_PLATE` | NIST |
| `G4_POLYPROPYLENE` | NIST |
| `G4_POLYETHYLENE` | NIST |
| `G4_W` | NIST |
| `Vehicle_PU_Foam` | 自定义 |

### 7.2 `Vehicle_PU_Foam`

```cpp
auto* foam = new G4Material("Vehicle_PU_Foam", 0.055*g/cm3, 4);
foam->AddElement(nist->FindOrBuildElement("C"), 0.60);
foam->AddElement(nist->FindOrBuildElement("H"), 0.08);
foam->AddElement(nist->FindOrBuildElement("O"), 0.28);
foam->AddElement(nist->FindOrBuildElement("N"), 0.04);
```

材料创建应幂等，避免重复创建同名 material。

---

## 8. RegionRegistry 与 RegionResolver

### 8.1 `RegionRegistry`

`RegionRegistry` 负责建立 volume / placement 到 `region_id` 的映射。

建议接口：

```cpp
class RegionRegistry {
public:
    void Register(const G4VPhysicalVolume* volume, std::string region_id);
    std::string FindRegionId(const G4VPhysicalVolume* volume) const;
};
```

### 8.2 `RegionResolver`

`RegionResolver` 在 `SteppingAction` 中使用。

散射 region 归属规则：

```text
使用 preStep volume 对应的 region_id
```

返回规则：

| 情况 | 返回 |
|---|---|
| preStep volume 已注册 | 对应 region_id |
| preStep volume 是 VehicleROI 空气母体 | `vehicle_background_air` |
| preStep volume 未注册 | `other` |
| 无有效散射 | `none` |

注意：散射位置坐标仍使用 postStep position；region 归属使用 preStep volume。

---

## 9. 成像头架构

### 9.1 `ImagingHeadConstruction`

职责：

- 接收当前 `ScanPose`；
- 计算成像头组件实际坐标；
- 构建或更新准直器几何；
- 构建虚拟探测器可视化辅助体；
- 暴露当前 pose 下的 detector plane actual config。

不负责：

- 构建车辆 ROI；
- 产生 primary gamma；
- 判断 detector crossing；
- 写 CSV。

### 9.2 source 坐标

```text
source_pos_actual = source_pos_zero + (head_offset_x, head_offset_y, 0)
```

### 9.3 collimator 坐标

对 CSV profile 中每个 jaw 顶点：

```text
x_actual = x_zero + head_offset_x
z_actual = z_zero
```

jaw 沿 y 拉伸时：

```text
y_actual = y_zero + head_offset_y
```

其中 `y_zero` 来自 profile CSV 的可选 `y_mm`；若 CSV 不含 `y_mm`，则 `y_zero = 0`。`jaw_extrusion_length_y_mm` 表示 global y 方向全长，不是 half length。

### 9.4 detector 坐标

```text
detector_z_actual = detector_z_zero
x/y range 随 head_offset_x/y 平移
```

---

## 10. SlitCollimatorProfileReader

### 10.1 职责

读取第二版狭缝准直器 CSV profile。

输入必需列：

```csv
profile_id,jaw_id,vertex_id,x_mm,z_mm
```

可选列：

```csv
y_mm
```

若存在 `y_mm`，同一 jaw 内所有顶点的 `y_mm` 必须相同，并作为该 jaw 的 `y_zero_mm`。若不存在 `y_mm`，`y_zero_mm = 0`。Reader 应容忍并去除 UTF-8 BOM。

### 10.2 数据结构

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

### 10.3 验证规则

必须验证：

- 文件可打开；
- 指定 `profile_id` 存在；
- 必要列存在；
- 可选 `y_mm` 若存在，同一 jaw 内取值一致；
- `M >= 1`；
- jaw ID 连续为 `jaw_0 ... jaw_{M-1}`；
- 每块 jaw 顶点数 `N >= 3`；
- `vertex_id = 0 ... N-1` 连续；
- 坐标有限；
- 多边形面积非零；
- 多边形凸；
- 不含连续共线点。

该类不创建 Geant4 solid。

---

## 11. SlitCollimatorBuilder

### 11.1 职责

将已验证的 `SlitCollimatorProfile` 构建为 Geant4 钨几何。

### 11.2 几何规则

每块 jaw 使用：

```text
G4ExtrudedSolid
```

二维截面映射：

| 输入物理量 | `G4ExtrudedSolid` local 坐标 |
|---|---|
| global x | local x |
| global z | local y |
| global y | local z 拉伸方向 |

沿 global `y` 方向拉伸。

第二版不构建镜像 jaw。

### 11.3 offset 应用

`SlitCollimatorBuilder` 应接收当前 `ScanPose` 或已计算的实际坐标。

不得在 builder 内私自读取全局配置。

---

## 12. SourceModel 与 PrimaryGeneratorAction

### 12.1 `SourceModel`

职责：

- 计算 incident direction；
- 在焦点面内采样起点；
- 按 mono / spectrum 采样能量。

### 12.2 incident direction

```text
incident_dir = (cos(theta), 0, sin(theta))
```

`theta` 来自 YAML，合法范围：

```text
0° < theta <= 90°
```

### 12.3 焦点面采样

基向量：

```text
u = (0, 1, 0)
v = (-sin(theta), 0, cos(theta))
```

采样：

```text
r = R * sqrt(xi_1)
phi = 2π * xi_2
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

### 12.4 `PrimaryGeneratorAction`

每个 event 只产生一个 primary gamma。

不负责：

- 写 CSV；
- 判断探测器命中；
- 统计散射。

---

## 13. VirtualDetectorPlane

### 13.1 职责

`VirtualDetectorPlane` 是配置与几何辅助模块，不是真实 sensitive detector。

职责：

- 保存 detector zero config；
- 根据 pose 计算 detector actual bounds；
- 可构建可视化辅助体；
- 向 `SteppingAction` 提供当前 detector crossing 所需配置。

### 13.2 detector crossing 配置

第一阶段支持：

```yaml
accept_direction: negative_z
```

对应：

```text
preStep.z > detector_z
postStep.z <= detector_z
direction.z < 0
```

---

## 14. EventRecord

### 14.1 数据结构

```cpp
struct ScatterSummary {
    int scatter_count_total = 0;
    int compton_count = 0;
    int rayleigh_count = 0;

    G4ThreeVector first_scatter_pos;
    G4ThreeVector last_scatter_pos;

    std::string first_scatter_region_id = "none";
    std::string last_scatter_region_id = "none";
};

struct DetectorHitRecord {
    bool detected = false;
    int hit_id = -1;
    double det_x_mm = std::numeric_limits<double>::quiet_NaN();
    double det_y_mm = std::numeric_limits<double>::quiet_NaN();
    double det_z_mm = std::numeric_limits<double>::quiet_NaN();
    double det_energy_keV = std::numeric_limits<double>::quiet_NaN();
};

struct GammaTrackSummary {
    int track_id = -1;
    int parent_id = -1;
    bool is_primary_gamma = false;

    std::string gamma_source_type;      // primary | secondary
    std::string gamma_source_process;   // primary_generator or creator process
    G4ThreeVector gamma_source_pos;
    std::string gamma_source_region_id = "none";

    ScatterSummary scatter;
    DetectorHitRecord hit;
};

struct EventRecord {
    int event_id = -1;
    int next_hit_id = 0;
    std::unordered_map<int, GammaTrackSummary> gamma_tracks;
};
```

### 14.2 reset 规则

每个 event 开始时：

```text
next_hit_id = 0
gamma_tracks cleared
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

---

## 15. EventAction

### 15.1 职责

`EventAction` 持有当前 event 的 `EventRecord`，并按 track_id 管理每条 gamma track 的 summary。

提供接口：

```cpp
void BeginOfEventAction(const G4Event*) override;
void EndOfEventAction(const G4Event*) override;

void EnsureGammaTrackSummary(const G4Track* track);
void RecordComptonScatter(int track_id, const G4ThreeVector& pos, const std::string& region_id);
void RecordRayleighScatter(int track_id, const G4ThreeVector& pos, const std::string& region_id);
void RecordDetectorHit(int track_id, const DetectorHitRecord& hit);

const EventRecord& GetRecord() const;
bool HasDetectorHit(int track_id) const;
```

### 15.2 写出规则

End of event：

| 模式 | 行为 |
|---|---|
| 正式模式 | 对每个 detected gamma hit 写一行。 |
| debug 模式 | 对每条 gamma track summary 写一行，并写 `detected` 字段。 |

`EventAction` 不负责判断 step 是否为散射，也不负责 detector crossing 插值。

---

## 16. SteppingAction

### 16.1 过滤对象

处理所有 gamma track：

```text
particle_name == gamma
```

### 16.2 散射统计

计入：

```text
processName == "compt"
processName == "Rayl"
```

不计入：

- photoelectric effect；
- 非 gamma 粒子。

每条 gamma track 独立维护自身散射历史。secondary gamma 的散射阶次从自身产生时从 `0` 开始，不继承 parent track 的散射阶次。gamma track 是否进入正式 CSV 不由散射发生位置决定。

散射位置：

```text
postStep position
```

region 归属：

```text
preStep volume -> RegionResolver
```

### 16.3 detector crossing

当 detector accept direction 为 `negative_z` 时：

```text
preStep.z > detector_z
postStep.z <= detector_z
direction.z < 0
```

穿越点：

```text
t = (detector_z - pre_z) / (post_z - pre_z)
det_x = pre_x + t * (post_x - pre_x)
det_y = pre_y + t * (post_y - pre_y)
det_z = detector_z
```

若穿越点落在当前 pose 的 detector bounds 内，则记录 detector hit。

同一 gamma track 只记录第一次有效 detector crossing。同一 event 内不同 gamma track 可分别形成 detected gamma hit。

---

## 17. CsvWriter

### 17.1 职责

`CsvWriter` 负责：

- 生成正式 CSV header；
- 生成 debug CSV header；
- 每个 worker 写线程本地临时 CSV；
- master 合并临时 CSV；
- 合并时只保留一个 header；
- 正式模式合并成功后删除临时文件；
- debug 模式合并成功后保留临时文件。

### 17.2 正式 CSV header

```csv
event_id,hit_id,track_id,parent_id,is_primary_gamma,gamma_source_type,gamma_source_process,gamma_source_x,gamma_source_y,gamma_source_z,gamma_source_region_id,det_x,det_y,det_z,det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,first_scatter_region_id,last_scatter_region_id
```

### 17.3 Debug CSV header

```csv
event_id,track_id,parent_id,is_primary_gamma,gamma_source_type,gamma_source_process,gamma_source_x,gamma_source_y,gamma_source_z,gamma_source_region_id,detected,hit_id,det_x,det_y,det_z,det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,first_scatter_region_id,last_scatter_region_id
```

### 17.4 线程文件组织

每个 pose 输出目录：

```text
results/{run_id}/
├── events.csv 或 events_debug.csv
├── metadata.yaml
└── tmp/
    ├── events_thread0.csv
    ├── events_thread1.csv
    └── ...
```

worker 不得直接写最终 CSV。

---

## 18. MetadataWriter

### 18.1 职责

`MetadataWriter` 负责为每个 pose 写出 `metadata.yaml`。

metadata 记录 run-level 条件，不重复写入每个事件行。

### 18.2 必须包含的字段

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

`random_seed` 只写一次，取值为该 pose run 最终实际执行时使用的 seed；`base_random_seed` 仅记录入口 YAML 中的基础 seed。

禁止使用：

```text
vehicle_shift_x
vehicle_shift_y
```

---

## 19. Run / pose 生命周期

### 19.1 程序启动

```text
main()
  ├── 读取 config/base/simulation_config_v2.yaml 或 --config 指定的入口 YAML
  ├── 读取 vehicle_roi_v03.yaml
  ├── 验证所有配置
  ├── 生成 PoseList
  ├── 创建 Geant4 run manager
  ├── 注册 PhysicsList
  ├── 注册 ActionInitialization
  └── 交给 PoseRunController 执行 pose runs
```

### 19.2 每个 pose 的运行流程

```text
For each ScanPose:
  ├── 生成 pose_id
  ├── 计算该 pose run 的 random_seed
  ├── 生成 run_id
  ├── 计算 head_offset
  ├── 构建或刷新当前 pose 的 ImagingHead
  ├── VehicleROI 保持固定
  ├── 初始化 / 重新初始化 Geant4 geometry
  ├── BeginOfRunAction
  │     ├── 创建 results/{run_id}/
  │     ├── 创建 tmp/
  │     └── 打开线程本地 CSV
  ├── BeamOn n_primary_per_pose
  ├── EndOfRunAction
  │     ├── 关闭线程本地 CSV
  │     ├── master 合并
  │     └── 处理临时文件
  └── MetadataWriter 写 metadata.yaml
```

实现可以选择：

- 每个 pose 重新创建 run manager；或
- 使用同一个 run manager 并在 pose 间重新初始化几何。

但对外语义必须保持：

```text
每个 pose 是一组独立静态几何 Monte Carlo 统计。
```

---

## 20. 多线程模型

多线程模式下：

- worker 处理 events；
- 每个 worker 写自己的临时 CSV；
- master 合并临时 CSV；
- 不共享 `std::ofstream`；
- 不把全部 event records 累积到内存后再统一写出。

允许共享只读状态：

- 已冻结配置；
- 车辆 ROI 几何常量；
- 当前 pose 配置；
- detector actual bounds；
- region registry 只读映射；
- collimator profile 数据。

禁止共享可变状态：

- 当前 event record；
- 输出流；
- worker 本地 CSV writer；
- mutable random sampling state。

本轮随机数语义为：一个 run 对应一个 pose 和一个实际 seed。一个 run 可以使用多线程执行。多 pose 程序执行时，默认可使用 `pose_seed = base_random_seed + pose_index`，并在每个 pose 的 `metadata.yaml` 中记录 `base_random_seed`、`pose_index` 和实际 `random_seed`。不要求跨线程数逐事件 bitwise identical。

---

## 21. 数据流

### 21.1 配置数据流

```text
simulation_config_v2.yaml
  └── SimulationConfigReader
        └── SimulationConfig
              ├── PoseList
              ├── SourceConfig
              ├── CollimatorConfig
              ├── DetectorConfig
              ├── OutputConfig
              └── PhysicsConfig

vehicle_roi_v03.yaml
  └── VehicleROIConfigReader
        └── VehicleROIConfig
              └── VehicleROIConstruction
```

### 21.2 几何数据流

```text
VehicleROIConfig
  └── VehicleROIConstruction
        ├── MaterialManager
        └── RegionRegistry

ScanPose + ImagingHeadConfig
  └── ImagingHeadConstruction
        ├── SlitCollimatorProfileReader
        ├── SlitCollimatorBuilder
        └── VirtualDetectorPlane
```

### 21.3 event 数据流

```text
PrimaryGeneratorAction
  └── Generate primary gamma

SteppingAction
  ├── filter gamma tracks
  ├── record per-gamma-track Compton / Rayleigh scatter
  ├── resolve region from preStep volume
  └── detect virtual detector crossing

EventAction
  ├── hold EventRecord
  └── write row according to output mode

CsvWriter
  ├── write thread-local CSV
  └── master merge
```

---

## 22. 错误处理策略

### 22.1 配置阶段 fatal

- YAML 文件不存在；
- `schema_version` 不支持；
- 必要字段缺失；
- 字段类型错误；
- list pose 数组长度不一致；
- offset 非整数；
- `n_primary_per_pose <= 0`；
- `number_of_threads < 1`；
- `model_type` 非法；
- abnormal 模式未指定 target；
- detector range 非法；
- theta 非法；
- focal spot diameter 非法。

### 22.2 几何阶段 fatal

- material 无法解析；
- host 不存在；
- daughter 不在 host 内；
- 同级实体 overlap；
- insert 不在唯一宿主内；
- region_id 缺失；
- collimator profile 非法。

### 22.3 运行 / 输出阶段 fatal

- CSV 无法创建；
- metadata 无法写出；
- results/{run_id} 已存在且非空；
- 线程临时文件无法创建；
- 合并失败；
- 合并后 header 不唯一。

原则：

```text
不静默回退
不自动修复非法输入
错误信息应包含文件、字段或组件名
```

---

## 23. 后处理边界

Geant4 程序不负责：

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
- SVD / effective rank。

这些全部留到下一轮后处理项目迭代。本轮不实现后处理脚本、pose_summary.csv 或 scan_summary.csv。

---

## 24. 第一阶段非目标

第一阶段不实现：

- 整车 CAD；
- 曲面真实车身；
- 真实探测器响应；
- sensitive detector 能量沉积；
- 图像重建；
- 连续运动扫描；
- 运动模糊；
- 时间相关积分；
- 成像头旋转；
- 成像头 z 方向运动；
- 镜像准直器；
- 镜像探测器；
- 在 Geant4 内生成统计图；
- pose-level summary；
- scan-level summary；
- 后处理脚本。

---

## 25. 架构验收要点

实现满足本文档的条件：

- 以 YAML 为主配置入口；
- 车辆 ROI 固定，成像头移动；
- `head_offset_x/y` 统一作用于 source、collimator、detector；
- `pose_id` 自动生成，不手写；
- source 使用斜入射有限焦点笔形束；
- collimator reader 支持可变 jaw 数量；
- 不构建镜像准直器；
- 不构建镜像探测器；
- detector crossing 由当前 pose detector bounds 决定；
- 散射位置用 postStep position；
- region 归属用 preStep volume；
- 正式 CSV 输出所有 detected gamma hit；
- debug CSV 输出 gamma track summary，并使用 `detected` 字段区分该 track 是否有效穿越探测平面；
- metadata 使用 `head_offset_x/y`，不使用 `vehicle_shift_x/y`；
- metadata 记录固定 World、output policy、pose_index、base_random_seed 和该 pose run 最终实际使用的 random_seed；
- 多线程输出不共享输出流；
- master 合并后最终 CSV 只有一个 header。
