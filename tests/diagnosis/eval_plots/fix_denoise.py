# -*- coding: utf-8 -*-
"""补跑去噪 + 鲁棒性评估"""
import sys, json, time
from pathlib import Path
import numpy as np

sys.path.insert(0, r'd:\code\CNN\cloud')
from app.services.diagnosis.engine import DiagnosisEngine, BearingMethod, DenoiseMethod
from app.services.diagnosis.ensemble import run_research_ensemble

HUST = Path(r'D:\code\wavelet_study\dataset\HUSTbear\down8192')
FS = 8192
MAX_PTS = FS * 5
BP = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
OUT = Path(r'D:\code\CNN\tests\output\eval_plots')


def ld(d, f):
    return np.load(d / f).astype(np.float64)[:MAX_PTS]


def fc(f):
    s = f.replace('.npy', '').rsplit('-', 1)[0]
    for p in s.split('_'):
        if p in 'HNBIOCh':
            return {'H': 'H', 'N': 'H', 'B': 'B', 'I': 'I', 'O': 'O', 'C': 'C'}.get(p)


# === 去噪 ===
print('=== 去噪效果 ===')
r = {"methods": {}}
for label, fcode in [('外圈故障', 'O'), ('健康', 'H')]:
    files = sorted(f for f in HUST.glob('*-X.npy') if fc(f.name) == fcode)
    if not files:
        continue
    print(f'[{label}] {files[0].name}')
    sig_c = ld(HUST, files[0].name)
    np.random.seed(42)
    sig_n = sig_c + np.random.randn(len(sig_c)) * np.std(sig_c)
    bp = np.var(sig_c)
    for dn, dl in [('none', '无去噪'), ('wavelet', '小波去噪'), ('vmd', 'VMD去噪'),
                    ('savgol', 'Savitzky-Golay'), ('wavelet_vmd', '小波+VMD级联')]:
        engine = DiagnosisEngine()
        engine.denoise_method = DenoiseMethod(dn)
        try:
            proc = engine.preprocess(sig_n)
            rp = np.var(sig_c - proc[:len(sig_c)])
        except Exception:
            rp = bp
        dsnr = 10 * np.log10(max(bp, 1e-12) / max(rp, 1e-12))
        r['methods'].setdefault(dl, {})[label] = round(dsnr, 2)
        print(f'  {dl}: DSNR={dsnr:+.1f}dB')
(OUT / '47_denoise.json').write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
print('-> 47_denoise.json')

# === 鲁棒性 ===
print('\n=== 鲁棒性 ===')
or_files = sorted(f for f in HUST.glob('*-X.npy') if fc(f.name) == 'O')
sig_c = ld(HUST, or_files[0].name)
np.random.seed(42)
snrs = [20, 10, 5, 0, -5]
r2 = {"snr_levels": snrs, "methods": {}}
for name, method in [('包络', BearingMethod.ENVELOPE), ('Kurtogram', BearingMethod.KURTOGRAM),
                      ('MED', BearingMethod.MED), ('MCKD', BearingMethod.MCKD)]:
    curve = []
    print(f'[{name}]')
    for s_db in snrs:
        sp = np.var(sig_c.astype(np.float64))
        noise = np.sqrt(sp / (10 ** (s_db / 10))) * np.random.randn(len(sig_c))
        try:
            engine = DiagnosisEngine(bearing_method=method, bearing_params=BP,
                                     denoise_method=DenoiseMethod.NONE)
            res = engine.analyze_bearing(sig_c + noise, FS)
            inds = res.get('fault_indicators', {})
            det = any(v.get('significant') for k, v in inds.items()
                      if isinstance(v, dict) and not k.endswith('_stat'))
            curve.append({'snr_db': s_db, 'detected': det})
            print(f'  SNR={s_db}dB: {"V" if det else "X"}')
        except Exception:
            curve.append({'snr_db': s_db, 'detected': False})
    r2['methods'][name] = curve

# Ensemble
curve = []
print('[Ensemble]')
for s_db in snrs:
    sp = np.var(sig_c.astype(np.float64))
    noise = np.sqrt(sp / (10 ** (s_db / 10))) * np.random.randn(len(sig_c))
    try:
        res = run_research_ensemble(sig_c + noise, FS, bearing_params=BP, max_seconds=5.0)
        det = res.get('status', 'normal') != 'normal' or res.get('health_score', 100) < 70
        curve.append({'snr_db': s_db, 'detected': det})
        print(f'  SNR={s_db}dB: {"V" if det else "X"}')
    except Exception:
        curve.append({'snr_db': s_db, 'detected': False})
r2['methods']['Ensemble'] = curve
(OUT / '46_robustness.json').write_text(json.dumps(r2, ensure_ascii=False, indent=2), encoding='utf-8')
print('-> 46_robustness.json')
print('\nDONE')
