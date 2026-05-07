# MSS

`MSS` 是一个 Geant4 gamma 背散射 Monte Carlo 仿真项目。第一版目标是生成事件级 CSV，用于统计到达理想探测平面的 primary gamma 在 PMMA 内的 Compton / Rayleigh 散射历史。

第一版不实现图像重建、真实探测器响应、探测器能量沉积 scoring、profile 批处理或 Python 后处理分析。

## 环境

| 项目 | 要求 |
|---|---|
| Geant4 | 11.2.0 |
| 操作系统 | Ubuntu 24.04 |
| 编译器 | Ubuntu 24.04 系统默认 GCC |
| 构建系统 | CMake |
| C++ 标准 | C++17 |
| 可执行文件 | `MSS` |

## 构建

从仓库根目录运行：

```bash
cmake -S . -B build
cmake --build build -j
```

当前 CMake 不复制 `macros/` 或 `data/` 到 `build/`。下面的运行命令都假设当前工作目录是仓库根目录。

## 运行

单线程 debug 最小测试：

```bash
./build/MSS macros/run.mac
```

预期输出：

```text
results/hits_profile_P001_mono_160keV_seed12345_debug.csv
```

多线程 compact 测试：

```bash
./build/MSS macros/run_mt.mac
```

预期输出：

```text
results/hits_profile_P001_mono_160keV_seed12345.csv
```

几何与轨迹可视化：

```bash
./build/MSS macros/vis.mac
```

`vis.mac` 用于检查 PMMA、空气缺陷、两块钨准直器 jaw、探测面辅助体和少量 gamma 轨迹。需要可用的 Geant4 可视化驱动和图形环境。

## 宏命令

第一版支持以下宏命令：

| 命令 | 说明 |
|---|---|
| `/geometry/collimatorProfileFile data/collimator_profiles.csv` | 准直器 profile CSV |
| `/geometry/collimatorProfileId P001` | 本次运行使用的 profile ID |
| `/geometry/enableAirDefect true` | 是否构建 PMMA 内空气缺陷 |
| `/source/energyMode mono` | 能量模式，`mono` 或 `spectrum` |
| `/source/monoEnergy 160 keV` | 单能模式 primary gamma 能量 |
| `/source/spectrumFile data/spectrum.csv` | spectrum 模式 CSV |
| `/run/randomSeed 12345` | 随机种子 |
| `/run/numberOfThreads 8` | Geant4 worker 线程数 |
| `/output/directory results` | 输出目录 |
| `/output/debug false` | 显式选择 debug 或 compact 输出 |

若未显式设置 `/output/debug`，单线程默认 debug，多线程默认 compact。

## 输入 CSV

准直器 profile CSV 格式：

```csv
profile_id,jaw_id,vertex_id,x_mm,z_mm
P001,jaw_0,0,21,-20
```

约束：

- 每个 profile 必须包含 `jaw_0` 和 `jaw_1`。
- 每个 jaw 必须有 `vertex_id` 为 `0..4` 的 5 个顶点，不能缺失或重复。
- `x_mm` 和 `z_mm` 是全局坐标，单位 mm。
- 非法 profile 会 fail fast。

当前 `data/collimator_profiles.csv` 中的 `P001` 用于运行、可视化和输出链路检查。除非另有确认，不应把它当作真实准直器几何。

spectrum CSV 格式：

```csv
energy_keV,weight
40,0.01
```

`data/spectrum.csv` 是合法示例输入。程序会检查能量为正、权重非负且总权重大于 0，并按权重构造 CDF 采样。真实能谱应在后续替换该文件。

## 输出 CSV

只输出到达探测平面边界内的 primary gamma。未到达探测面的 event 不输出。

compact header：

```csv
initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

debug header：

```csv
event_id,track_id,parent_id,det_z,det_dir_x,det_dir_y,det_dir_z,initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

单位约定：

| 类型 | CSV 单位 |
|---|---|
| 长度 | mm |
| 能量 | keV |

`is_multiple_scatter` 的定义是 `scatter_count_total >= 2`。无 PMMA 内散射时，first / last scatter 坐标输出为 `NaN`。

## Debug 与 Compact

debug 模式包含 event、track、parent、探测面 z 和探测方向字段，适合单线程调试。

compact 模式只包含后处理统计所需字段，适合多线程正式运行。

多线程运行时，每个 worker 写入 `results/tmp/` 下的临时 CSV，run 结束后由 master 合并。compact 模式合并成功后删除对应临时 CSV；debug 模式合并成功后保留临时 CSV。

## 第一版限制

第一版不包含：

- 图像重建；
- 真实探测器材料响应；
- 探测器能量沉积 scoring；
- source collimator；
- 自动遍历所有 collimator profile；
- 全散射轨迹输出；
- Python 后处理分析脚本；
- 源位置、探测器边界、PMMA 尺寸或空气缺陷尺寸宏命令。

## 验收

详细验收步骤见 `docs/acceptance_checklist.md`。
