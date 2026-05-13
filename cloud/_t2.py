import numpy as np, os, sys
sys.path.insert(0, '.')
data_dir = r'D:\code\wavelet_study\dataset\CW\down8192_CW'
fs = 8192
from app.services.diagnosis.engine import DiagnosisEngine

files = sorted(os.listdir(data_dir))
samples = {}
for f in files:
    cls, ver, _ = f.split('-')
    if cls not in samples: samples[cls] = {}
    if ver not in samples[cls]: samples[cls][ver] = f

results = []
for cls in ['H', 'I', 'O']:
    for ver in ['B', 'C', 'D']:
        if ver not in samples.get(cls, {}): continue
        fname = samples[cls][ver]
        data = np.load(os.path.join(data_dir, fname))
        engine = DiagnosisEngine(
            strategy='advanced', bearing_method='kurtogram',
            gear_method='standard', denoise_method='none',
            bearing_params={'n': 9, 'd': 7.94, 'D': 38.52, 'alpha': 0},
            gear_teeth=None,
        )
        r = engine.analyze_comprehensive(data.astype(np.float64), fs)
        ind = r['bearing']['fault_indicators']
        sig = ','.join(k for k,v in ind.items() if isinstance(v,dict) and v.get('significant')) or 'NONE'
        bpfo = ind.get('BPFO',{}).get('snr',0)
        bpfi = ind.get('BPFI',{}).get('snr',0)
        bsf = ind.get('BSF',{}).get('snr',0)
        rf = round(r['bearing'].get('rot_freq_hz',0),1)
        h_score = r['health_score']
        status = r['status']
        hp = ind.get('BPFO',{}).get('harmonic_snrs',[])
        hi = ind.get('BPFI',{}).get('harmonic_snrs',[])
        hb = ind.get('BSF',{}).get('harmonic_snrs',[])
        results.append((cls,ver,rf,h_score,status,bpfo,bpfi,bsf,sig,hp,hi,hb))

print(f"{' ':8} {'RF':>6} {'Score':>6} {'BPFO':>6} {'BPFI':>6} {'BSF':>6} {'Sig':>16} {'HPFO':>12} {'HPFI':>12} {'HBSF':>12}")
print('-'*100)
for cls,ver,rf,sc,st,bpfo,bpfi,bsf,sig,hp,hi,hb in results:
    hp_str = '[' + ','.join(f'{x:.1f}' for x in hp[-3:]) + ']' if hp else '[]'
    hi_str = '[' + ','.join(f'{x:.1f}' for x in hi[-3:]) + ']' if hi else '[]'
    hb_str = '[' + ','.join(f'{x:.1f}' for x in hb[-3:]) + ']' if hb else '[]'
    print(f'{cls}-{ver:<4} {rf:>6.1f} {sc:>6} {bpfo:>6.1f} {bpfi:>6.1f} {bsf:>6.1f} {sig:>16} {hp_str:>12} {hi_str:>12} {hb_str:>12}')

h_ok = sum(1 for r in results if r[0]=='H' and r[8]=='NONE')
i_ok = sum(1 for r in results if r[0]=='I' and r[8]!='NONE')
o_ok = sum(1 for r in results if r[0]=='O' and r[8]!='NONE')
print(f'\nH correctly identified as healthy: {h_ok}/{sum(1 for r in results if r[0]=="H")}')
print(f'I correctly flagged as fault: {i_ok}/{sum(1 for r in results if r[0]=="I")}')
print(f'O correctly flagged as fault: {o_ok}/{sum(1 for r in results if r[0]=="O")}')
