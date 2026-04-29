# CNN 项目概览

## 项目概述

这是一个基于 PyTorch 的 **MNIST 手写数字识别 CNN 训练项目**，属于深度学习练习/学习项目。包含两个版本的训练脚本：

- **`train_mnist_v1.py`**：基础版 CNN 模型（2个卷积层，1个全连接层）
- **`train_mnist_v2.py`**：优化版 CNN 模型（3个卷积块，更深的网络结构，增加数据增强、学习率调度器、早停机制等）

## 技术栈

- **深度学习框架**：PyTorch + torchvision
- **数据处理**：MNIST 数据集（自动下载）
- **评估指标**：scikit-learn（混淆矩阵、分类报告、Precision/Recall/F1、ROC曲线）
- **可视化**：matplotlib + seaborn
- **数值计算**：numpy

## 模型架构

### v1 基础模型 (MNISTCNN)
```
Conv(1→32) → BN → ReLU → MaxPool → Conv(32→64) → BN → ReLU → MaxPool → Flatten → Linear(3136→128) → ReLU → Dropout(0.5) → Linear(128→10)
```

### v2 优化模型 (MNISTCNNImproved)
```
[Conv(1→32) → BN → ReLU → Conv(32→32) → BN → ReLU → MaxPool → Dropout] →
[Conv(32→64) → BN → ReLU → Conv(64→64) → BN → ReLU → MaxPool → Dropout] →
[Conv(64→128) → BN → ReLU] →
Flatten → Linear(6272→256) → ReLU → Dropout → Linear(256→10)
```

## 运行方式

```bash
# 运行基础版
python train_mnist_v1.py

# 运行优化版
python train_mnist_v2.py
```

### 关键超参数（可在脚本 main() 中修改）

| 参数 | v1 默认值 | v2 默认值 |
|------|-----------|-----------|
| epochs | 50 | 40 |
| learning_rate | 0.001 | 0.001 |
| batch_size | 64 | 64 |
| dropout | 0.5 | 0.3 |
| weight_decay | - | 1e-4 |
| 数据增强 | ❌ | ✅ (RandomAffine) |
| 学习率调度器 | ❌ | ✅ (StepLR, step=8, gamma=0.5) |
| 早停机制 | ❌ | ✅ (patience=8) |

## 输出结果

运行后会自动生成结果目录（`results_mnist_enhanced/` 或 `results_mnist_optimized/`），包含：

### 文本结果
- `test_metrics.txt` — 测试集综合指标
- `classification_report.csv` — 每个类别的详细报告
- `training_log.csv` — 每个 epoch 的训练/验证日志
- `confusion_matrix.csv` — 混淆矩阵原始数据

### 可视化图片
- `loss_curve.png` / `accuracy_curve.png` — 训练/验证损失和准确率曲线
- `f1_curve.png` — 验证集 F1 分数曲线
- `confusion_matrix.png` — 混淆矩阵热力图
- `roc_curves.png` — 各类别 ROC 曲线
- `overall_metrics_bar.png` — 综合指标柱状图
- `per_class_f1.png` — 每个类别的 F1 分数
- `error_distribution.png` — 误分类样本分布
- `confidence_distribution.png` — 预测置信度分布
- `misclassified_samples.png` — 误分类样本展示
- `correct_samples.png` — 正确分类样本展示

### 模型权重
- `best_mnist_cnn.pth` (v1) 或 `best_mnist_cnn_optimized.pth` (v2) — 最佳模型权重

## 依赖安装

```bash
pip install torch torchvision numpy scikit-learn matplotlib seaborn
```

## 项目结构

```
e:\A-codehub\CNN\
├── train_mnist_v1.py          # 基础版训练脚本
├── train_mnist_v2.py          # 优化版训练脚本（推荐）
├── README.md                  # 项目说明（简短）
├── QWEN.md                    # 项目上下文文档
├── Data_mnist/                # MNIST 数据下载目录（自动创建）
├── results_mnist_enhanced/    # v1 输出目录（运行后生成）
├── results_mnist_optimized/   # v2 输出目录（运行后生成）
└── *.pth                      # 模型权重文件（运行后生成）
```

## 代码约定

- 所有输出使用非交互式后端（`matplotlib.use("Agg")`），适合服务器/无头环境运行
- 随机种子固定为 42，保证可复现性
- 自动检测并使用 GPU（如可用）
- 数据划分：55000 训练 / 5000 验证 / 10000 测试
- 归一化参数：mean=0.1307, std=0.3081（MNIST 标准值）
