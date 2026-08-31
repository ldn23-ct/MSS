# Results 目录合同

`results/` 只保存可再生成或本地保留的运行产物；除本说明和 `.gitkeep` 外均不提交 Git。

```text
results/<campaign>/
├── events/
│   ├── raw/                   # Geant4 events.csv + metadata.yaml
│   └── valid/                 # events_valid.csv + metadata.yaml
├── data_processing/
│   ├── slit_channels/         # 边界 JSON、统计 CSV、诊断 PNG
│   └── audit/                 # 数据资格 YAML、CSV、Markdown
└── postprocessing/
    ├── E1/
    ├── E2/
    └── E3/
```

本次统一分析使用 `results/articlev3_merged/`。其中 `events/raw/` 是指向 `articlev2`、`articlev3_grid_p001_add80m` 和 `articlev3_grid_p002_100m` 原始层的相对符号链接索引；`events/valid/` 是清洗后按 phantom/profile/pose 实际合并的数据；`data_processing/merge/` 与 `data_processing/audit/` 保存来源、seed、历史数和行数守恒记录。三个原 campaign 均保持不变。

E3 的独立 55 mm 均匀 PMMA 前层参考保存在 `results/articlev3_p4_front_slab_55mm_100m/`：`events/raw/` 保留 81 个原始 pose，`events/valid/` 保存按主数据同一冻结边界和深度规则得到的 81 个有效事件文件，目录根的 `reference_manifest.yaml` 固定其 geometry、历史数、seed 和网格 provenance。该 campaign 不并入 `articlev3_merged/events/valid/`，而由严格 E3 入口独立读取。

事件数据与实验 figures/tables 必须分开保存。E1–E3 的正式图表只能写入各自的 `postprocessing/Ex/`；数据清洗诊断保留在 `data_processing/`。

目录迁移的文件数、字节数和聚合 SHA-256 核对记录保存在 campaign 的 `data_processing/results_migration_integrity.yaml`；常规 audit 覆盖不会删除该记录。
