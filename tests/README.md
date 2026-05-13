# Tests — 回归测试套件

> 本文档说明 `tests/` 目录下的回归测试，用于验证诊断算法的关键功能和鲁棒性。

---

## 1. 测试概述

回归测试覆盖诊断算法库的以下方面：

- **None 参数安全**：确保所有诊断函数在 `bearing_params`/`gear_teeth` 为 `None` 时不崩溃
- **CPW 鲁棒性**：验证倒频谱预白化在边界条件下的稳定性
- **变速阶次跟踪**：验证多帧平均和变速跟踪算法的正确性

---

## 2. 测试文件

### 2.1 `test_none_params.py` — None 参数安全测试

验证当设备未配置轴承/齿轮参数时，诊断引擎不会崩溃，而是回退到统计诊断模式。

**测试场景：**
- `bearing_params` 中 `alpha=None`
- `bearing_params` 完全为 `None`
- `gear_teeth` 为 `None`
- `DiagnosisEngine` 各种组合下的 `None` 参数

**运行方式：**
```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/test_none_params.py
```

---

### 2.2 `test_cpw_robustness.py` — CPW 鲁棒性测试

验证 CPW（倒频谱预白化）算法在边界条件下的稳定性。

**测试场景：**
- `rot_freq=None`（自动估计转频）
- `rot_freq=-5`（非法负值）
- `rot_freq=0`（零值）
- `comb_frequencies` 为空列表
- `comb_frequencies` 包含 `None`

**运行方式：**
```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/test_cpw_robustness.py
```

---

### 2.3 `test_varying_speed_order.py` — 变速阶次跟踪测试

验证变速工况下的阶次跟踪算法正确性。

**测试场景：**
- 使用真实变速数据（`0.5X_B_VS_0_40_0Hz-X.npy`）
- 验证转频估计准确性
- 比较多帧平均 vs 单帧分析的阶次谱差异
- 生成对比可视化图表

**输出：**
- 控制台输出转频估计值、峰值差异等量化指标
- `tests/diagnosis/output/order_tracking_comparison.png` — 对比图

**运行方式：**
```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/test_varying_speed_order.py
```

---

## 3. 运行全部测试

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate

python ../tests/diagnosis/test_none_params.py
python ../tests/diagnosis/test_cpw_robustness.py
python ../tests/diagnosis/test_varying_speed_order.py
```

---

## 4. 添加新测试

当修改诊断算法库时，建议添加对应的回归测试：

1. 在 `tests/diagnosis/` 下创建新测试文件
2. 使用 `assert` 验证关键输出
3. 在 `tests/README.md` 中记录测试目的和运行方式
4. 确保测试在修改前后都能通过

---

## 5. 测试环境要求

- Python 3.10+
- 激活 `cloud/venv/` 虚拟环境
- 真实数据测试需要 `D:\code\wavelet_study\dataset\HUSTbear\down8192` 目录存在
