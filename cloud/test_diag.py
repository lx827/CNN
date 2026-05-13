import numpy as np, os, sys
sys.path.insert(0, '.')
data_dir = r'D:\code\wavelet_study\dataset\CW\down8192_CW'
fs = 8192

from app.services.diagnosis.engine import DiagnosisEngine

for cls, fname in [('H', 'H-A-1.npy'), ('I', 'I-A-1.npy'), ('O', 'O-A-1.npy')]:
    data = np.load(os.path.join(data_dir, fname))
    
    engine = DiagnosisEngine(
        strategy="advanced", bearing_method="kurtogram",
        gear_method="standard", denoise_method="none",
        bearing_params={"n": 9, "d": 7.94, "D": 38.52, "alpha": 0},
        gear_teeth=None,
    )
    result = engine.analyze_comprehensive(data.astype(np.float64), fs)
    
    print(f"\n=== {fname} ({cls}) ===")
    print(f"  Score={result['health_score']} Status={result['status']}")
    ind = result['bearing']['fault_indicators']
    for name, info in ind.items():
        if isinstance(info, dict):
            sig = "*** SIGNIFICANT ***" if info.get('significant') else ""
            h = info.get('harmonic_snrs', [])
            sb = info.get('sideband_snrs')
            sb_str = f" sidebands={sb}" if sb else ""
            print(f"  {name}: SNR={info.get('snr',0):.1f}, harmonics={h}{sb_str} {sig}")

print("\nDone!")
