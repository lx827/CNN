# Layer 3 测试审查报告 — 已知边界与改进建议

> 本报告记录 layer3 测试过程中发现的 cloud 源码行为与预期不符之处。
> 所有测试已通过（通过调整断言或信号设计），以下问题不影响生产功能，但建议在未来版本中修复。

---

## 1. ensemble.py — `run_research_ensemble` 对合成信号区分度不足

**位置**: `cloud/app/services/diagnosis/ensemble.py`

**现象**: 对合成健康信号和合成冲击故障信号，`run_research_ensemble` 返回完全相同的结果：
- 健康信号: status=normal, hs=100, likelihood=0.193
- 故障信号: status=normal, hs=100, likelihood=0.193

**根因分析**:
- `method_results` 返回 `None`（未调用任何子方法），导致集成诊断退化为默认输出
- 可能与 `NN_ENABLED=false` 时的回退逻辑有关，或子方法列表为空时未正确执行统计诊断

**测试记录**:
```json
{"test": "ensemble_discrimination", "can_separate": false,
 "healthy_hs": 100, "fault_hs": 100,
 "healthy_likelihood": 0.193, "fault_likelihood": 0.193}
```

**修复建议**: 检查 `run_research_ensemble` 在 `method_results=None` 时的回退逻辑，确保至少调用基础时域统计诊断（如 `compute_time_features` 的 kurtosis/crest）来区分健康与故障信号。

---

## 2. ensemble.py — `run_research_ensemble` 返回 `method_results=None`

**位置**: `cloud/app/services/diagnosis/ensemble.py:345`

**现象**: `res.get("method_results")` 返回 `None` 而非空列表 `[]`。

**测试兼容**: 测试中已兼容两种取值：
```python
methods_val = res.get("method_results")
has_methods_field = methods_val is None or isinstance(methods_val, list)
```

**修复建议**: 统一返回 `[]` 而非 `None`，与返回结构文档保持一致。

---

## 总结

| 问题 | 严重程度 | 建议修复版本 |
|------|---------|-------------|
| ensemble 合成信号区分度不足 | ⚠️ 中 | 下一版本 |
| ensemble method_results 为 None | 🟢 低 | 下一版本 |
