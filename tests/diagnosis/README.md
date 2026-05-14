# tests/diagnosis — 诊断算法回归与有效性测试

> 所有测试脚本需在 cloud venv 中运行，并添加 cloud 模块路径。

## 运行方式

```bash
cd D:\code\CNN\cloud
. venv/Scripts/activate
python ../tests/diagnosis/test_none_params.py
python ../tests/diagnosis/test_cpw_robustness.py
python ../tests/diagnosis/test_varying_speed_order.py
python ../tests/diagnosis/test_effectiveness.py
```

服务器端：
```bash
cd /opt/CNN/cloud
source venv/bin/activate
python ../tests/diagnosis/test_none_params.py
```

## 测试文件说明

### 回归测试（核心，每次部署前必须通过）

| 文件 | 用途 |
|------|------|
| `test_none_params.py` | 验证 bearing_params/gear_teeth 为 None 时算法不崩溃 |
| `test_cpw_robustness.py` | 验证 CPW 对 rot_freq=None/0/负值/空频组合的鲁棒性 |
| `test_varying_speed_order.py` | 验证变速阶次跟踪算法的正确性 |

### 有效性测试（评估检出率和误诊率）

| 文件 | 用途 | 数据集 |
|------|------|--------|
| `test_effectiveness.py` | **主测试**：CW轴承+WTgearbox全面有效性评估 | CW + WTgearbox |
| `test_gear_detail.py` | 齿轮诊断明细：fault_indicators/votes/时域特征 | WTgearbox |
| `test_gear_values.py` | 齿轮指标值对比：健康 vs 故障 | WTgearbox |
| `test_time_features.py` | 各工况时域特征明细（kurt/crest/rms） | WTgearbox |
| `test_fm4.py` | FM4/M6A/M8A 对行星齿轮箱的区分力测试 | WTgearbox |
| `test_c2_features.py` | c1/c2 通道特征对比 | WTgearbox |

### 当前有效性基线（2026-05-15）

**CW 轴承数据集（仅轴承参数）**：
- 健康(H)：0% 误诊 ✅
- 内圈(I)：75% 检出（I-A升速工况漏检）
- 外圈(O)：100% 检出 ✅

**WTgearbox 行星齿轮箱（仅齿轮参数）**：
- 健康(He)：12.5% 误诊（N1_45/55 kurt>12 已知局限）
- 缺齿(Mi)：75% 检出 ✅
- 断齿(Br)：12.5% 检出（kurt与健康重叠，已知局限）
- 磨损(We)：12.5% 检出（同上）
- 裂纹(Rc)：0% 检出（时域特征与健康无异，已知局限）

> **根本原因**：行星齿轮箱的频域指标(SER/CAR/sideband/FM4/M6A/M8A)对健康/故障无区分力，
> 时域峭度与健康N1子集重叠(kurt=8~22)。这是行星齿轮箱诊断的公认难题。