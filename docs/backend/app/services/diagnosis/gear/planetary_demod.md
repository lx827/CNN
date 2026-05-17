# `planetary_demod.py` — 行星齿轮解调

**对应源码**：`cloud/app/services/diagnosis/gear/planetary_demod.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `planetary_envelope_order_analysis` | `planetary_envelope_order_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | 窄带包络阶次分析（Level 2a） |
| `planetary_fullband_envelope_order_analysis` | `planetary_fullband_envelope_order_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | 全频带包络阶次分析（Level 2b） |
| `planetary_tsa_envelope_analysis` | `planetary_tsa_envelope_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | TSA 残差包络阶次分析（Level 2c，区分力=3.31） |
| `planetary_hp_envelope_order_analysis` | `planetary_hp_envelope_order_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | 高通滤波包络阶次分析（Level 2d） |
| `planetary_vmd_demod_analysis` | `planetary_vmd_demod_analysis(signal, fs, rot_freq, gear_teeth, max_K=5) -> dict` | VMD 幅频联合解调（Level 3，慢方法） |
| `planetary_sc_scoh_analysis` | `planetary_sc_scoh_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | 谱相关/谱相干解调（Level 4，慢方法） |
| `planetary_msb_analysis` | `planetary_msb_analysis(signal, fs, rot_freq, gear_teeth) -> dict` | MSB 残余边频带分析（Level 5，慢方法） |
| `evaluate_planetary_demod_results` | `evaluate_planetary_demod_results(narrowband_result, vmd_result) -> dict` | 行星箱结果评估统一入口 |
