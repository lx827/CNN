# 诊断方法评估框架 — 使用说明

## 文件结构

```
tests/diagnosis/method_eval/
├── __init__.py              # 包初始化
├── config.py                # 全局配置（数据集/方法/参数/输出目录）
├── label_mapper.py          # 预测标签推断（D-S融合/fault_indicators）
├── visualizer.py            # 可视化模块（混淆矩阵/柱状图/热力图/雷达图）
├── plot_generator.py        # 数据保存工具（JSON格式）
├── replot.py                # 独立绘图脚本（从JSON重新生成图表）
├── test_bearing_hustbear.py # 测试1：HUSTbear 恒速轴承评估
├── test_bearing_cw.py       # 测试2：CW 变速轴承评估
├── test_gear_wtgearbox.py   # 测试3：WTgearbox 齿轮评估
├── test_binary_all.py       # 测试4：二分类全数据集汇总
└── main.py                  # 主入口（一键运行全部4个测试）
```

## 运行测试

### 单个测试

```bash
cd /d/code/CNN/cloud
venv\Scripts\python.exe tests\diagnosis\method_eval\test_bearing_hustbear.py
venv\Scripts\python.exe tests\diagnosis\method_eval\test_bearing_cw.py
venv\Scripts\python.exe tests\diagnosis\method_eval\test_gear_wtgearbox.py
venv\Scripts\python.exe tests\diagnosis\method_eval\test_binary_all.py
```

### 一键运行全部

```bash
cd /d/code/CNN/cloud
venv\Scripts\python.exe tests\diagnosis\method_eval\main.py
```

## 独立绘图（从JSON数据重新生成图表）

测试运行时会保存数据到 `results_*.json` 文件。修改绘图代码后，可以从 JSON 重新生成图表，无需重跑数据。

```bash
# 从测试1的数据重新生成
venv\Scripts\python.exe tests\diagnosis\method_eval\replot.py bearing_hustbear

# 从测试3的数据重新生成
venv\Scripts\python.exe tests\diagnosis\method_eval\replot.py gear_wtgearbox

# 从所有数据重新生成
venv\Scripts\python.exe tests\diagnosis\method_eval\replot.py --all
```

## 输出目录

| 测试 | 输出目录 | 图表 |
|------|---------|------|
| 测试1 | `bearing_hustbear/` | 混淆矩阵、Accuracy柱状图、ROC/PR曲线、报告 |
| 测试2 | `bearing_cw/` | 混淆矩阵、Accuracy柱状图、ROC/PR曲线、报告 |
| 测试3 | `gear_wtgearbox/` | 混淆矩阵、Accuracy柱状图、ROC/PR曲线、报告 |
| 测试4 | `binary_all/` | 3张数据集对比柱状图 + 雷达图(Top5) + 报告 |

## 快速/全量模式切换

每个测试文件都有快速模式和全量模式，通过注释切换：

```python
# 快速验证模式（3个方法）
BEARING_METHODS_ACTIVE = [
    ("标准包络", "envelope"),
    ("DWT", "dwt"),
    ("EMD", "emd_envelope"),
]

# 全量模式（11个方法）— 取消注释下面一行
# BEARING_METHODS_ACTIVE = [(n, v) for n, v in BEARING_METHODS if v not in SKIP_METHODS]
```

## 数据保存格式

测试运行时会保存以下 JSON 文件：

- `results_ensemble_confusion.json` — 混淆矩阵数据
- `results_accuracy_bar.json` — 准确率柱状图数据

独立绘图脚本会读取这些 JSON 文件，重新生成 SVG 图表。
