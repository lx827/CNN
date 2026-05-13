import numpy as np
import os, sys
sys.path.insert(0, '.')

data_dir = r'D:\code\wavelet_study\dataset\CW\down8192_CW'
data = np.load(os.path.join(data_dir, 'H-A-1.npy'))
fs = 8192

from app.services.diagnosis.bearing import envelope_analysis, fast_kurtogram
from app.services.diagnosis.engine import DiagnosisEngine
from app.services.diagnosis.order_tracking import _compute_order_spectrum_multi_frame
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum

bp = {'n': 9, 'd': 7.94, 'D': 38.52, 'alpha': 0}

# 1. Check the envelope spectrum shape
sig = data.astype(np.float64)
sig = sig - np.mean(sig)

# Get rot freq via multi-frame order tracking
oa, os_, rf, rsd = _compute_order_spectrum_multi_frame(sig, fs, samples_per_rev=1024, max_order=50)
print(f'Rot freq multi-frame: {rf:.2f} Hz, std={rsd:.3f}')

# 2. compute envelope via kurtogram
env = fast_kurtogram(sig, fs, max_level=5)
ofc = env['optimal_fc']
obw = env['optimal_bw']
mk = env['max_kurtosis']
ef0 = env['envelope_freq'][0]
ef1 = env['envelope_freq'][-1]
nel = len(env['envelope_freq'])
print(f'Kurtogram optimal: fc={ofc:.1f} Hz, bw={obw:.1f} Hz, max_kurt={mk:.3f}')
print(f'Envelope spectrum: freq range [{ef0:.1f}, {ef1:.1f}] Hz, {nel} points')

# 3. Compute theoretical bearing freqs  
bpfo = 3.57 * rf
bpfi = 5.43 * rf
bsf = 2.32 * rf
ftf = 0.40 * rf
print(f'\nTheoretical freqs @ {rf:.1f} Hz:')
print(f'  BPFO={bpfo:.1f} Hz ({bpfo/rf:.2f}fr)')
print(f'  BPFI={bpfi:.1f} Hz ({bpfi/rf:.2f}fr)')
print(f'  BSF={bsf:.1f} Hz ({bsf/rf:.2f}fr)')
print(f'  FTF={ftf:.1f} Hz ({ftf/rf:.2f}fr)')

# 4. Check the envelope spectrum energy distribution
freq_arr = np.array(env['envelope_freq'])
amp_arr = np.array(env['envelope_amp'])
background = float(np.median(amp_arr))
print(f'\nBackground median: {background:.6f}')

# 5. Look at actual envelope spectrum peak positions and SNRs
peak_amplitudes = sorted(amp_arr, reverse=True)
print(f'Top 10 envelope amplitudes: {peak_amplitudes[:10]}')
print(f'Top 10 envelope positions:')
top_indices = np.argsort(amp_arr)[::-1][:10]
for idx in top_indices:
    print(f'  f={freq_arr[idx]:.2f} Hz, amp={amp_arr[idx]:.6f}, SNR={amp_arr[idx]/background:.2f}')

# 6. Check around bearing freqs
for name, f_hz in [('BPFO', bpfo), ('BPFI', bpfi), ('BSF', bsf), ('FTF', ftf)]:
    tol = max(f_hz * 0.05, freq_arr[1]-freq_arr[0] if len(freq_arr)>1 else 1.0)
    mask = np.abs(freq_arr - f_hz) <= tol
    if np.any(mask):
        best_idx = np.argmax(amp_arr[mask])
        actual_idx = np.where(mask)[0][best_idx]
        print(f'\n{name} @ {f_hz:.1f} Hz +/- {tol:.1f}:')
        print(f'  detected at {freq_arr[actual_idx]:.2f} Hz, amp={amp_arr[actual_idx]:.6f}, SNR={amp_arr[actual_idx]/background:.2f}')
        ctx_start = max(0, actual_idx - 5)
        ctx_end = min(len(freq_arr), actual_idx + 6)
        for i in range(ctx_start, ctx_end):
            marker = ' <--' if i == actual_idx else ''
            print(f'    {freq_arr[i]:.1f} Hz: {amp_arr[i]:.6f}{marker}')
    else:
        print(f'\n{name} @ {f_hz:.1f} Hz: NO MATCH (no points in +/-{tol:.1f} Hz range)')

# 7. Time domain kurtosis
time_kurt = float(np.mean(sig ** 4) / (np.var(sig) ** 2 + 1e-12))
print(f'\nTime domain kurtosis: {time_kurt:.3f}')

# 8. Check engine background SNR
from scipy.signal import hilbert
analytic = hilbert(sig)
envelope_time = np.abs(analytic)
print(f'Time envelope RMS: {np.sqrt(np.mean(envelope_time**2)):.4f}')
print(f'Time envelope peak/mean ratio: {np.max(envelope_time)/np.mean(envelope_time):.2f}')
