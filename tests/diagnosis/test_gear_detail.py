"""齿轮诊断明细测试：查看 fault_indicators 的具体内容"""
import os, sys, glob, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'cloud'))

from app.services.diagnosis.ensemble import run_research_ensemble

WTGEAR_GEAR_TEETH = {"sun": 28, "ring": 100, "planet": 36, "planet_count": 4, "input": 28}
FS = 8192

WTGEAR_DATA_DIR = r"D:\code\wavelet_study\dataset\WTgearbox\down8192"

def load_npy_files(data_dir):
    groups = {}
    for fpath in sorted(glob.glob(os.path.join(data_dir, "*.npy"))):
        fname = os.path.basename(fpath)
        name_no_ext = fname.replace(".npy", "")
        parts = name_no_ext.split("-")
        ch = parts[-1]
        prefix = "-".join(parts[:-1])
        groups.setdefault(prefix, {})[ch] = fpath
    return groups

groups = load_npy_files(WTGEAR_DATA_DIR)

# 测试几个关键工况
test_cases = [
    ("He_N1_40", "健康N1@40Hz"),
    ("He_N2_40", "健康N2@40Hz"),
    ("Br_B1_40", "断齿B1@40Hz"),
    ("Mi_M1_40", "缺齿M1@40Hz"),
    ("Rc_R1_40", "裂纹R1@40Hz"),
    ("We_W1_40", "磨损W1@40Hz"),
]

for prefix, desc in test_cases:
    if prefix not in groups:
        print(f"{desc}: 无数据")
        continue
    # 取第一个通道
    first_ch = sorted(groups[prefix].keys())[0]
    signal = np.load(groups[prefix][first_ch])
    signal = signal[:FS*5]

    result = run_research_ensemble(signal, FS, bearing_params=None, gear_teeth=WTGEAR_GEAR_TEETH, profile="runtime")

    print(f"\n{'='*60}")
    print(f"{desc} ({prefix}): hs={result['health_score']}, status={result['status']}")
    print(f"  gear_confidence={result['ensemble']['gear_confidence']}")
    print(f"  gear_vote_fraction={result['ensemble']['gear_vote_fraction']}")
    print(f"  skip_bearing={result['ensemble']['skip_bearing']}, skip_gear={result['ensemble']['skip_gear']}")

    # 齿轮指标明细
    gear_indicators = result.get("gear", {}).get("fault_indicators", {})
    print(f"  齿轮 fault_indicators:")
    for k, v in gear_indicators.items():
        if isinstance(v, dict):
            print(f"    {k}: value={v.get('value', v.get('ratio', v.get('score', '?')))}, "
                  f"warning={v.get('warning', '?')}, critical={v.get('critical', '?')}")
        else:
            print(f"    {k}: {v}")

    # 各齿轮方法的投票
    gear_votes = result["ensemble"]["gear_votes"]
    print(f"  齿轮投票明细:")
    for key, vote in gear_votes.items():
        print(f"    {key}: conf={vote.get('confidence', '?')}, abnormal={vote.get('abnormal', '?')}, "
              f"hits={vote.get('hits', '?')}, warning_hits={vote.get('warning_hits', '?')}, "
              f"critical_hits={vote.get('critical_hits', '?')}")

    # 时域特征
    tf = result.get("time_features", {})
    print(f"  时域特征: kurtosis={tf.get('kurtosis', '?')}, crest_factor={tf.get('crest_factor', '?')}")