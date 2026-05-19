---
name: test-writing
description: "On-demand workflow for writing correctness tests for diagnosis algorithms in the CNN project. Use when: adding a new test, reviewing existing tests, or adding a new diagnostic algorithm that needs verification."
user-invocable: true
---

# 诊断算法测试编写规范

基于本项目实际测试编写经验提炼。核心原则：**测云端、用合成、存 JSON、图分离、标清楚**。

---

## 1. 核心铁律

| 规则 | 说明 |
|------|------|
| **测云端模块** | 测试只能 `import` 和调用 `cloud/app/` 下的现有函数，**禁止在测试文件中重写算法逻辑**（如自己写 FFT、自己写峰值检测） |
| **合成 + 真实** | 每个算法用合成信号（已知 ground truth）验证计算正确性，再用真实数据集验证实际效果 |
| **结果存 JSON** | 测试结果写入 `output/*.json`，含 `summary`（total/passed/failed） |
| **绘图脚本独立** | `plot_results.py` 只读 JSON，不重跑分析 |
| **图表能自解释** | 标注阈值线、通过/失败标记、轴含义，让非领域专家也能看懂 |

---

## 2. 测试文件结构

```
tests/diagnosis/foundation/
├── synthetic_signals.py          # 合成信号生成器（含 ground truth）
├── test_<算法>_correctness.py    # 正确性测试（每个算法一个）
├── plot_results.py               # 独立绘图脚本（只读 JSON）
└── output/                       # JSON + PNG（已加入 .gitignore）
```

### 2.1 合成信号生成器

每种信号必须有明确的 ground truth：

```python
def bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=3.0):
    """返回值: (signal, fs, {"bpfo": 90.0, "rot_freq": 25.0, "type": "bearing_outer_race"})"""
```

### 2.2 正确性测试模板

```python
def test_xxx():
    results = []
    # 合成信号验证
    sig, fs, gt = synthetic_func()
    output = cloud_module.algorithm(sig, fs)
    passed = check(output, gt)
    results.append({"test": "synthetic_case", "expected": ..., "actual": ..., "passed": passed})
    return results

def test_real():
    results = []
    for fname, desc, expect_fault in test_files:
        snr = measure(...)
        if expect_fault == "BPFO":
            passed = snr > 3.0
        elif expect_fault == "none":
            passed = snr < 3.0  # 健康数据不应误报
        results.append({"file": fname, "passed": passed, ...})
    return results

def main():
    all_results = {"synthetic": test_synthetic(), "real_data": test_real()}
    # ⚠️ summary 统计必须用 get("passed", False)，默认 False！
    passed = sum(1 for v in all_results.values() for item in v if item.get("passed", False))
```

### 2.3 绘图脚本

```python
def plot_xxx():
    data = load_json("xxx_correctness.json")  # 只读 JSON
    if not data: return
    # 用 matplotlib 绘图
    fig.savefig(...)
```

---

## 3. 避免的陷阱

| 陷阱 | 错误做法 | 正确做法 |
|------|---------|---------|
| **本地重写算法** | `def _compute_cepstrum_simple(): N=len; fft=...` | `from app.api.data_view import _compute_cepstrum` |
| **参数不一致** | 测试用 D=39.04，云端用 D=38.52 | 统一从 AGENTS.md 数据集参数表取值 |
| **图表空/看不懂** | 误差 1e-7 画柱状图 | 改为理论值vs计算值并排对比，加阈值标注 |
| **output 提交到 git** | 无 .gitignore | `tests/diagnosis/foundation/output/` 加入 .gitignore |
| **不用虚拟环境** | `python test.py` | `d:\code\CNN\cloud\venv\Scripts\python.exe test.py` |
| **重复测试** | 3 个框架都测轴承分类 | 删除被新测试覆盖的旧文件 |
| **`passed` 默认值** | `item.get("passed", True)` → 漏设字段永远通过 | `item.get("passed", False)` — 每个 item 必须显式设置 `"passed": True/False` |
| **硬 assert 阻止后续** | `assert total-passed == 0` → 一个失败全部崩溃 | 改为 `if failed: print("WARNING: ...")`，让所有测试跑完 |

---

## 4. 测试覆盖检查清单

每个诊断算法至少覆盖：

- [ ] 合成信号正确性（已知 ground truth，验证计算误差）
- [ ] 真实数据集效果（至少 1 个健康 + 1 个故障样本）
- [ ] 边界条件（空信号、极短信号、None 参数）
- [ ] 每个测试 item 显式设置 `"passed": True/False`
- [ ] JSON 输出含 `summary.total/passed/failed`，统计用 `get("passed", False)`
- [ ] 绘图脚本能独立运行（不重跑分析）
- [ ] 图表标注清晰（阈值线、通过/失败、轴含义）

---

## 5. 运行测试

```bash
cd /d/code/CNN
# 激活虚拟环境
d:\code\CNN\cloud\venv\Scripts\activate

# 运行测试 → 生成 JSON
python tests/diagnosis/foundation/test_bearing_fault_freqs.py
python tests/diagnosis/foundation/test_envelope_correctness.py

# 独立绘图（不重跑分析）
python tests/diagnosis/foundation/plot_results.py
```

---

## 6. 何时删除旧测试

当新测试完全覆盖旧测试的功能时，删除旧文件并同步更新 `docs/tests/INDEX.md`。
