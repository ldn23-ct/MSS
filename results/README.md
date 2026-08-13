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

事件数据与实验 figures/tables 必须分开保存。E1–E3 的正式图表只能写入各自的 `postprocessing/Ex/`；数据清洗诊断保留在 `data_processing/`。

目录迁移的文件数、字节数和聚合 SHA-256 核对记录保存在 campaign 的 `data_processing/results_migration_integrity.yaml`；常规 audit 覆盖不会删除该记录。
