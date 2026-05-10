# MSS M10 验收清单

本清单用于验收第一版宏文件、示例数据、README 和输出链路。所有命令默认从仓库根目录运行。

## 1. 构建

```bash
cmake -S . -B build
cmake --build build -j
```

验收点：

- CMake 配置成功。
- 编译成功。
- 生成 `build/MSS`。

## 2. 单线程 debug 输出

```bash
./build/MSS macros/run.mac
```

验收点：

- 程序正常结束。
- 生成 `results/hits_profile_P001_mono_160keV_seed12345_debug.csv`。
- CSV header 等于：

```csv
event_id,track_id,parent_id,det_z,det_dir_x,det_dir_y,det_dir_z,initial_energy,initial_dir_x,initial_dir_y,initial_dir_z,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

- `initial_energy` 在 mono 160 keV 运行中为 `160`。
- CSV 包含 `initial_dir_x`、`initial_dir_y`、`initial_dir_z`，三者表示发射时单位方向。

## 3. 多线程 compact 输出

```bash
./build/MSS macros/run_mt.mac
```

验收点：

- 程序正常结束。
- 生成 `results/hits_profile_P001_mono_160keV_seed12345.csv`。
- 最终 CSV 只有一个 header。
- CSV header 等于：

```csv
initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

- compact 合并成功后，`results/tmp/` 中对应本次运行的 thread 临时 CSV 已删除。

## 4. 可视化检查

```bash
./build/MSS macros/vis.mac
```

验收点：

- PMMA 模体可见，位置对应 `z=[0,65] mm`。
- 空气缺陷启用时可见。
- 外部 CSV 指定的 3 块原始凸多边形钨准直器 jaw 可见。
- 关于 `x=0` 镜像的 3 块钨准直器 jaw 可见。
- 原始探测面辅助体位于 `z=-73 mm`，范围为 `x=[53,161] mm`、`y=[-50,50] mm`。
- 镜像探测面辅助体位于 `z=-73 mm`，范围为 `x=[-161,-53] mm`、`y=[-50,50] mm`。
- 少量 gamma 轨迹可用于检查源位置和锥束方向。

## 5. Spectrum 示例

使用 spectrum 模式时，应设置：

```text
/source/energyMode spectrum
/source/spectrumFile data/spectrum.csv
```

验收点：

- `data/spectrum.csv` 的 header 为 `energy_keV,weight`。
- 文件可被程序读取。
- energy 为正、weight 非负且总 weight 大于 0。

## 6. 非法 profile

使用临时非法 profile 或不存在的 profile ID 运行。

验收点：

- 找不到 profile ID 时停止。
- jaw 少于 3 个顶点时停止。
- `vertex_id` 重复时停止。
- `vertex_id` 不连续时停止。
- 多边形非凸或含连续共线点时停止。
- 坐标非数值时停止。

非法 profile 测试不应修改仓库内的有效 `data/collimator_profiles.csv`。

## 7. 关闭准直器

使用临时宏文件或临时命令设置：

```text
/geometry/enableCollimator false
```

验收点：

- 即使 `/geometry/collimatorProfileFile` 指向不存在的文件，程序也不读取 profile。
- 不构建原始或镜像 tungsten jaw。
- World、PMMA、空气缺陷和探测面辅助体仍按配置构建。
