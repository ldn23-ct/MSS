# E1：均匀模体系统响应基线与散射空间特征

| 脚本 | 职责 | 输入 | 输出 | 主要参数 |
|---|---|---|---|---|
| `run.py` | 生成 acquisition-group detector ROI、total depth response、按 P002/P001 分行的 2×2 first/last spatial overlay | 审计通过的 P0 center valid events | `postprocessing/E1/` 下 3 PNG、manifest、report、acceptance | `--results-root`、`--spatial-view-quantile`、`--spatial-{x,y,z}lim`、`--overwrite` |
| `analyze_roi_sensitivity.py` | 独立分析固定 slit channel 内 ROI 扩张的纯度/捕获率权衡 | valid manifest + boundary JSON | `postprocessing/E1/roi_sensitivity/` | `--boundary-config`、`--overwrite` |

```bash
conda run -n data python -m scripts.postprocessing.e1.run \
  --results-root results/articlev2 \
  --overwrite
```

`run.py` 的正式合同只包含三张 PNG，不生成 E1 常规结果表或 PDF。`--overwrite` 会替换 E1 正式 figures/control files，删除旧正式 tables，同时保留同级 `roi_sensitivity/` 和 `archive/`。

E1-F3 分别用 P002 S1/S3/S5 和 P001 S2/S4/S6 的 first/last pooled 坐标计算中心 99% 视窗，形成两行 x-z/y-z panels；视窗外点数写入 console、report 和 manifest，手动 x/y/z limits 只改变显示，不删除事件。
