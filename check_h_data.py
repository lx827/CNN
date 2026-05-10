import numpy as np
from scipy import stats
import glob, os

_FEATURE_BASELINES = {
    'rms': {'baseline': 0.008, 'warning': 0.015, 'critical': 0.030},
    'peak': {'baseline': 0.050, 'warning': 0.080, 'critical': 0.150},
    'kurtosis': {'baseline': 3.50, 'warning': 5.00, 'critical': 7.00},
    'crest_factor': {'baseline': 7.00, 'warning': 8.50, 'critical': 10.50},
    'skewness': {'baseline': 0.00, 'warning': 0.20, 'critical': 0.50},
    'impulse_factor': {'baseline': 9.50, 'warning': 11.00, 'critical': 13.00},
}

def _feature_severity(value, metric):
    cfg = _FEATURE_BASELINES.get(metric)
    if not cfg:
        return 0.0
    baseline = cfg['baseline']
    critical = cfg['critical']
    if value <= baseline or critical <= baseline:
        return 0.0
    return max(0.0, min(1.0, (abs(value) - baseline) / (critical - baseline)))

def compute_features(signal):
    arr = signal - np.mean(signal)
    peak = float(np.max(np.abs(arr)))
    rms = float(np.sqrt(np.mean(arr ** 2)))
    mean_abs = float(np.mean(np.abs(arr)))
    kurtosis = float(stats.kurtosis(arr, fisher=False))
    skewness = float(stats.skew(arr))
    crest_factor = peak / rms if rms > 1e-12 else 0.0
    impulse_factor = peak / mean_abs if mean_abs > 1e-12 else 0.0
    return {
        'peak': peak, 'rms': rms, 'kurtosis': kurtosis,
        'crest_factor': crest_factor, 'skewness': skewness,
        'impulse_factor': impulse_factor
    }

def diagnose(avg_features):
    sev = {
        'rms': _feature_severity(avg_features['rms'], 'rms'),
        'peak': _feature_severity(avg_features['peak'], 'peak'),
        'kurtosis': _feature_severity(avg_features['kurtosis'], 'kurtosis'),
        'crest_factor': _feature_severity(avg_features['crest_factor'], 'crest_factor'),
        'skewness': _feature_severity(abs(avg_features['skewness']), 'skewness'),
        'impulse_factor': _feature_severity(avg_features['impulse_factor'], 'impulse_factor'),
    }
    fault_scores = {
        '正常运行': 1.0,
        '齿轮磨损': sev['rms'] * 0.40 + sev['peak'] * 0.30 + sev['crest_factor'] * 0.15 + sev['kurtosis'] * 0.15,
        '轴承内圈故障': sev['kurtosis'] * 0.40 + sev['crest_factor'] * 0.25 + sev['impulse_factor'] * 0.25 + sev['peak'] * 0.10,
        '轴承外圈故障': sev['kurtosis'] * 0.30 + sev['crest_factor'] * 0.25 + sev['rms'] * 0.25 + sev['impulse_factor'] * 0.20,
        '滚动体故障': sev['kurtosis'] * 0.30 + sev['peak'] * 0.30 + sev['impulse_factor'] * 0.25 + sev['crest_factor'] * 0.15,
        '轴不对中': sev['rms'] * 0.40 + sev['skewness'] * 0.30 + sev['peak'] * 0.20 + sev['kurtosis'] * 0.10,
        '基础松动': sev['peak'] * 0.35 + sev['rms'] * 0.25 + sev['crest_factor'] * 0.25 + sev['skewness'] * 0.15,
    }
    normal_decay = 1.0
    normal_decay *= max(0.0, 1.0 - sev['rms'] * 0.35)
    normal_decay *= max(0.0, 1.0 - sev['kurtosis'] * 0.50)
    normal_decay *= max(0.0, 1.0 - sev['crest_factor'] * 0.35)
    normal_decay *= max(0.0, 1.0 - sev['peak'] * 0.20)
    normal_decay *= max(0.0, 1.0 - sev['skewness'] * 0.25)
    normal_decay *= max(0.0, 1.0 - sev['impulse_factor'] * 0.30)
    fault_scores['正常运行'] = normal_decay
    total = sum(fault_scores.values())
    fault_probabilities = {k: round(v / total, 4) for k, v in fault_scores.items()}
    max_fault_sev = max(v for k, v in fault_scores.items() if k != '正常运行')
    health_score = int(max(0, min(100, fault_probabilities.get('正常运行', 0) * 100 - max_fault_sev * 30)))
    status = 'normal' if health_score >= 80 else 'warning' if health_score >= 60 else 'fault'
    return health_score, status, fault_probabilities, sev

data_dir = r'D:\code\wavelet_study\dataset\CW\down8192_CW'
files = sorted(glob.glob(os.path.join(data_dir, '*.npy')))

print('=== H组数据逐个诊断 ===')
for prefix in ['H-A', 'H-B', 'H-C', 'H-D']:
    prefix_files = {os.path.basename(f).replace('.npy', '').split('-')[-1]: f 
                    for f in files if os.path.basename(f).startswith(prefix)}
    channels_data = {}
    for ch_num, fpath in sorted(prefix_files.items()):
        data = np.load(fpath)
        channels_data[f'ch{ch_num}'] = data
    
    all_features = [compute_features(channels_data[k]) for k in sorted(channels_data.keys())]
    avg_features = {}
    for key in ['rms', 'peak', 'kurtosis', 'crest_factor', 'skewness', 'impulse_factor']:
        values = [f.get(key, 0) for f in all_features]
        avg_features[key] = np.mean(values)
    
    health, status, probs, sev = diagnose(avg_features)
    print(f'{prefix}: health={health} ({status}) | Peak={avg_features["peak"]:.4f} RMS={avg_features["rms"]:.4f} Kurt={avg_features["kurtosis"]:.2f} Crest={avg_features["crest_factor"]:.2f} Impulse={avg_features["impulse_factor"]:.2f}')
    print(f'  severity: Peak={sev["peak"]:.2f} RMS={sev["rms"]:.2f} Kurt={sev["kurtosis"]:.2f} Crest={sev["crest_factor"]:.2f} Impulse={sev["impulse_factor"]:.2f}')
    top3 = sorted([(k, v) for k, v in probs.items() if k != '正常运行'], key=lambda x: x[1], reverse=True)[:3]
    print(f'  top3: ' + ' | '.join([f'{k}={v:.1%}' for k, v in top3]))
    print()
