# E1：均匀模体多狭缝深度响应基线

| 脚本 | 职责 | 输入文件/schema | 输出目录/文件 | 主要参数 | 失败条件 | 示例命令 |
|---|---|---|---|---|---|---|
| `run.py` | 生成 S1–S6 detector-plane 分布、2/4 mm first-scatter 深度响应、计数与验收报告 | `events/valid` + `data_processing/audit` | `postprocessing/E1/{figures,tables}`、manifest、report、acceptance | `--results-root`、`--audit-dir`、`--output-dir`、`--overwrite` | 审计非 pass、P0 center 缺失、标签/ROI/schema 非法、输出已存在 | `python -m scripts.postprocessing.e1.run --results-root results/articlev2` |
| `analyze_roi_sensitivity.py` | 分析固定 slit channel 内 detector ROI 扩张的纯度/捕获率权衡 | valid events manifest + boundary JSON | `postprocessing/E1/roi_sensitivity/` | `--results-root`、`--boundary-config`、`--output-dir`、`--overwrite` | manifest/hash/标签不一致或输出已存在 | `python -m scripts.postprocessing.e1.analyze_roi_sensitivity --results-root results/articlev2` |

```bash
python -m scripts.postprocessing.e1.run --results-root results/articlev2
python -m scripts.postprocessing.e1.analyze_roi_sensitivity \
  --results-root results/articlev2
```

`run.py --overwrite` 会替换 E1 正式 figures/tables，但保留同级 `roi_sensitivity/` 和 `archive/`。
