# `sensitive_selector.py` — 敏感分量选择

**对应源码**：`cloud/app/services/diagnosis/sensitive_selector.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `score_components` | `score_components(components, original, fs, target_freq, weights) -> List[float]` | 综合评分 |
| `select_top_components` | `select_top_components(...) -> List[Tuple]` | 选择 Top-K 敏感分量 |
| `select_wp_sensitive_nodes` | `select_wp_sensitive_nodes(signal, fs, level=3) -> List[int]` | 选择小波包敏感节点 |
| `select_emd_sensitive_imfs` | `select_emd_sensitive_imfs(imfs, original, fs) -> List[int]` | 选择 EMD 敏感 IMF |
| `select_vmd_sensitive_modes` | `select_vmd_sensitive_modes(modes, original, fs) -> List[int]` | 选择 VMD 敏感模态 |
