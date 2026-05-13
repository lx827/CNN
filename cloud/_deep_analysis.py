import numpy as np, os, sys
sys.path.insert(0, '.')

data_dir = r'D:\code\wavelet_study\dataset\CW\down8192_CW'

for fname, label in [('I-A-1.npy', 'INNER RACE'), ('O-A-1.npy', 'OUTER RACE')]:
    data = np.load(os.path.join(data_dir, fname))
    fs = 8192
    sig = data.astype(np.float64) - np.mean(data.astype(np.float64))
    
    from app.services.diagnosis.order_tracking import _compute_order_spectrum_multi_frame
    oa, os_, rf, rsd = _compute_order_spectrum_multi_frame(sig, fs, samples_per_rev=1024, max_order=50)
    
    print(f"\n{'='*60}")
    print(f"=== {fname} ({label}) ===")
    print(f"Rot freq: {rf:.2f} Hz, std: {rsd:.3f}")
    
    # Compute theoretical bearing frequencies
    bpfo = 3.57 * rf
    bpfi = 5.43 * rf
    bsf = 2.32 * rf
    ftf = 0.40 * rf
    print(f"Theoretical: BPFO={bpfo:.1f}Hz, BPFI={bpfi:.1f}Hz, BSF={bsf:.1f}Hz, FTF={ftf:.1f}Hz")
    
    # Time domain stats
    from scipy import stats
    print(f"Time kurtosis: {stats.kurtosis(sig, fisher=False):.3f}")
    print(f"Time RMS: {np.sqrt(np.mean(sig**2)):.4f}")
    
    # Envelope via kurtogram  
    from app.services.diagnosis.bearing import fast_kurtogram
    env = fast_kurtogram(sig, fs, max_level=5)
    print(f"Kurtogram: fc={env['optimal_fc']:.1f}Hz, bw={env['optimal_bw']:.1f}Hz, kurt={env['max_kurtosis']:.3f}")
    
    # Check envelope spectrum peaks at bearing frequencies
    freq_arr = np.array(env['envelope_freq'])
    amp_arr = np.array(env['envelope_amp'])
    bg = float(np.median(amp_arr))
    
    for name, fhz in [("BPFO", bpfo), ("BPFI", bpfi), ("BSF", bsf), ("FTF", ftf)]:
        tol = max(fhz * 0.03, 1.0)
        mask = np.abs(freq_arr - fhz) <= tol
        if np.any(mask):
            best_idx = int(np.argmax(amp_arr[mask]))
            actual_idx = int(np.where(mask)[0][best_idx])
            snr = amp_arr[actual_idx] / bg if bg > 0 else 0
            # Check 2x harmonic
            h2_f = fhz * 2
            h2_mask = np.abs(freq_arr - h2_f) <= max(h2_f * 0.03, 1.0)
            h2_snr = float(np.max(amp_arr[h2_mask])) / bg if np.any(h2_mask) and bg > 0 else 0
            print(f"  {name}: {fhz:.1f}Hz -> detected {freq_arr[actual_idx]:.1f}Hz, SNR={snr:.1f}, 2xSNR={h2_snr:.1f}")
        else:
            print(f"  {name}: {fhz:.1f}Hz -> NO MATCH")
    
    # Top envelope peaks
    top_idx = np.argsort(amp_arr)[::-1][:8]
    print(f"Top envelope peaks:")
    for i in top_idx:
        print(f"  {freq_arr[i]:.1f} Hz: SNR={amp_arr[i]/bg:.1f}")
    
    # Now compute the order spectrum to check
    max_o = 10
    mask_o = oa <= max_o
    top_order_idx = np.argsort(os_[mask_o])[::-1][:5]
    print(f"Top order peaks (<={max_o}x):")
    oa_masked = oa[mask_o]
    for i in top_order_idx:
        print(f"  order {oa_masked[i]:.2f}: {os_[mask_o][i]:.4f}")

print("\nDone.")
