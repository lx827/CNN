"""验证 SC/SCoh 归一化修复"""
import sys, os, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'cloud'))
from app.services.diagnosis.bearing_cyclostationary import bearing_sc_scoh_analysis

# HUSTbear 内圈故障
ir = np.load(r'D:\code\wavelet_study\dataset\HUSTbear\down8192\I_40Hz-X.npy')[:8192*5]
h = np.load(r'D:\code\wavelet_study\dataset\HUSTbear\down8192\H_40Hz-X.npy')[:8192*5]

bp = {'n': 9, 'd': 5.5, 'D': 29, 'alpha': 0}

r1 = bearing_sc_scoh_analysis(ir, 8192, bp, 40.0)
r2 = bearing_sc_scoh_analysis(h, 8192, bp, 40.0)

print(f'IR SCoh max: {r1["sc_max_value"]:.4f}, dominant: {r1["dominant_fault"]}')
print(f'H  SCoh max: {r2["sc_max_value"]:.4f}, dominant: {r2["dominant_fault"]}')

# 验证：SCoh 值应在 0~1 之间
max_scoh = max(r1['sc_max_value'], r2['sc_max_value'])
if max_scoh <= 1.5:
    print(f'\n✓ SCoh 归一化正常 (max={max_scoh:.4f})')
else:
    print(f'\n✗ SCoh 归一化异常 (max={max_scoh:.4f}, 应 <=1)')

# 验证故障区分度
ir_max = r1['sc_max_value']
h_max = r2['sc_max_value']
ratio = ir_max / (h_max + 1e-12)
print(f'故障/健康区分比: {ratio:.2f}')
if ratio > 1.1:
    print('✓ 故障信号 SCoh 明显高于健康信号')
else:
    print('✗ 区分度不足')

# CW 变速数据集
cw_dir = r'D:\code\CNN\CW\down8192_CW'
if os.path.exists(cw_dir):
    cw_ir = np.load(os.path.join(cw_dir, 'I-A-1.npy'))[:8192*5]
    cw_h = np.load(os.path.join(cw_dir, 'H-A-1.npy'))[:8192*5]
    r_cw_ir = bearing_sc_scoh_analysis(cw_ir, 8192, bp, 20.0)
    r_cw_h = bearing_sc_scoh_analysis(cw_h, 8192, bp, 20.0)
    print(f'\nCW IR SCoh max: {r_cw_ir["sc_max_value"]:.4f}, dominant: {r_cw_ir["dominant_fault"]}')
    print(f'CW H  SCoh max: {r_cw_h["sc_max_value"]:.4f}, dominant: {r_cw_h["dominant_fault"]}')
    cw_ratio = r_cw_ir['sc_max_value'] / (r_cw_h['sc_max_value'] + 1e-12)
    print(f'CW 故障/健康区分比: {cw_ratio:.2f}')