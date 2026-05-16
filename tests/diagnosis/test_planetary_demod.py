r"""
行星齿轮箱解调算法全数据集评估

对 WTgearbox 160 个 .npy 文件运行所有解调方法，
输出各方法对健康/故障的区分力统计，并记录计算时间。

方法列表：
  - narrowband:  窄带包络阶次分析 (Level 2)
  - fullband:    全频段包络阶次分析 (Level 2b)
  - tsa_envelope: TSA包络阶次分析 (Level 2c)
  - hp_envelope: 高通包络阶次分析 (Level 2d)
  - vmd_demod:   VMD幅频联合解调 (Level 3) — ⚠️ 较慢
  - sc_scoh:     谱相关/谱相干解调 (Level 4)
  - msb:         调制信号双谱 (Level 5)

用法：
  cd /d D:\code\CNN\cloud
  . venv\Scripts\activate
  PYTHONPATH=D:\code\CNN\cloud python ..\tests\diagnosis\test_planetary_demod.py
  PYTHONPATH=D:\code\CNN\cloud python ..\tests\diagnosis\test_planetary_demod.py --skip-vmd
"""
import sys
import os
import time
import numpy as np
import json
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cloud"))

from app.services.diagnosis.gear.planetary_demod import (
    planetary_envelope_order_analysis,
    planetary_fullband_envelope_order_analysis,
    planetary_vmd_demod_analysis,
    planetary_tsa_envelope_analysis,
    planetary_hp_envelope_order_analysis,
    planetary_sc_scoh_analysis,
    planetary_msb_analysis,
)

DATA_DIR = Path(r"D:\code\wavelet_study\dataset\WTgearbox\down8192")
FS = 8192

GEAR_TEETH = {
    "sun": 28, "ring": 100, "planet": 36,
    "planet_count": 4,
}

# 故障类型映射
FAULT_MAP = {
    "He": "健康", "Br": "断齿", "Mi": "缺齿", "We": "磨损", "Rc": "裂纹",
}

# 转速列表
SPEEDS = [20, 25, 30, 35, 40, 45, 50, 55]

# 慢算法标记
SLOW_METHODS = {
    "vmd_demod": "⚠️ VMD O(N²) 较慢(avg 0.7~1.3s)，2G服务器需严格控制K≤5",
}


def load_file(filename):
    """加载 .npy 文件"""
    path = DATA_DIR / filename
    if not path.exists():
        return None
    return np.load(str(path))


def get_rot_freq_from_filename(filename):
    """从文件名提取转速"""
    parts = filename.replace(".npy", "").split("-")
    speed_part = parts[0].split("_")[-1]
    try:
        return float(speed_part)
    except ValueError:
        return 35.0


# === 各方法的关键指标提取 ===

# 通用指标字段（narrowband/fullband/tsa/hp/vmd 共有）
COMMON_SNR_KEYS = [
    ("sun_fault_snr", "sun"),
    ("planet_fault_snr", "planet"),
    ("carrier_snr", "carrier"),
]
COMMON_MOD_KEYS = [
    ("sun_modulation_depth", "sun"),
    ("planet_modulation_depth", "planet"),
    ("carrier_modulation_depth", "carrier"),
]

# SC/SCoh 指标字段
SC_SCOH_KEYS = [
    ("sun_fault_scoh_snr", "sun"),
    ("planet_fault_scoh_snr", "planet"),
    ("carrier_scoh_snr", "carrier"),
    ("sun_fault_sc_snr", "sun_sc"),
    ("planet_fault_sc_snr", "planet_sc"),
    ("carrier_sc_snr", "carrier_sc"),
]

# MSB 指标字段
MSB_KEYS = [
    ("msb_se_snr", "msb_se"),
    ("msb_sun_fault_snr", "sun"),
    ("msb_planet_fault_snr", "planet"),
    ("msb_carrier_snr", "carrier"),
]

# VMD 额外指标字段
VMD_EXTRA_KEYS = [
    ("amp_sun_snr", "amp_sun"),
    ("amp_planet_snr", "amp_planet"),
    ("freq_sun_snr", "freq_sun"),
    ("freq_planet_snr", "freq_planet"),
]


def extract_method_metrics(method_name, method_data):
    """从方法结果中提取关键指标"""
    metrics = {}
    if "error" in method_data:
        metrics["error"] = method_data["error"]
        return metrics

    if method_name == "sc_scoh":
        for key, target in SC_SCOH_KEYS:
            metrics[target] = method_data.get(key, 0.0)
        # 谱相干均值
        metrics["sun_scoh_mean"] = method_data.get("sun_fault_scoh_mean", 0.0)
        metrics["planet_scoh_mean"] = method_data.get("planet_fault_scoh_mean", 0.0)
        metrics["carrier_scoh_mean"] = method_data.get("carrier_scoh_mean", 0.0)
        metrics["sun_fault_significant"] = method_data.get("sun_fault_significant", False)
        metrics["planet_fault_significant"] = method_data.get("planet_fault_significant", False)
        metrics["carrier_significant"] = method_data.get("carrier_significant", False)
    elif method_name == "msb":
        for key, target in MSB_KEYS:
            metrics[target] = method_data.get(key, 0.0)
        metrics["msb_se_mesh_carrier"] = method_data.get("msb_se_mesh_carrier", 0.0)
        metrics["msb_se_mesh_carrier_significant"] = method_data.get("msb_se_mesh_carrier_significant", False)
        metrics["msb_sun_fault_significant"] = method_data.get("msb_sun_fault_significant", False)
        metrics["msb_planet_fault_significant"] = method_data.get("msb_planet_fault_significant", False)
    elif method_name == "vmd_demod":
        for key, target in COMMON_SNR_KEYS:
            metrics[target] = method_data.get(key, 0.0)
        for key, target in VMD_EXTRA_KEYS:
            metrics[target] = method_data.get(key, 0.0)
        metrics["envelope_kurtosis"] = method_data.get("envelope_kurtosis", 0.0)
        metrics["sun_fault_significant"] = method_data.get("sun_fault_significant", False)
        metrics["planet_fault_significant"] = method_data.get("planet_fault_significant", False)
    elif method_name == "tsa_envelope":
        for key, target in COMMON_SNR_KEYS:
            metrics[target] = method_data.get(key, 0.0)
        metrics["envelope_kurtosis"] = method_data.get("envelope_kurtosis", 0.0)
        metrics["residual_kurtosis"] = method_data.get("residual_kurtosis", 0.0)
        metrics["sun_fault_significant"] = method_data.get("sun_fault_significant", False)
        metrics["planet_fault_significant"] = method_data.get("planet_fault_significant", False)
    else:
        # narrowband / fullband / hp_envelope
        for key, target in COMMON_SNR_KEYS:
            metrics[target] = method_data.get(key, 0.0)
        for key, target in COMMON_MOD_KEYS:
            metrics[target + "_mod"] = method_data.get(key, 0.0)
        metrics["envelope_kurtosis"] = method_data.get("envelope_kurtosis", 0.0)
        metrics["sun_fault_significant"] = method_data.get("sun_fault_significant", False)
        metrics["planet_fault_significant"] = method_data.get("planet_fault_significant", False)

    return metrics


def run_all_methods(signal, fs, rot_freq, gear_teeth, skip_vmd=False):
    """运行所有解调方法，记录计算时间"""
    results = {}
    methods = [
        ("narrowband", planetary_envelope_order_analysis),
        ("fullband", planetary_fullband_envelope_order_analysis),
        ("tsa_envelope", planetary_tsa_envelope_analysis),
        ("hp_envelope", planetary_hp_envelope_order_analysis),
        ("sc_scoh", planetary_sc_scoh_analysis),
        ("msb", planetary_msb_analysis),
    ]
    if not skip_vmd:
        methods.append(("vmd_demod", planetary_vmd_demod_analysis))

    for name, func in methods:
        t0 = time.perf_counter()
        try:
            r = func(signal, fs, rot_freq, gear_teeth)
            elapsed = time.perf_counter() - t0
            results[name] = {"elapsed_sec": round(elapsed, 3)}
            if "error" in r:
                results[name]["error"] = r["error"]
            else:
                metrics = extract_method_metrics(name, r)
                results[name].update(metrics)
        except Exception as e:
            elapsed = time.perf_counter() - t0
            results[name] = {"elapsed_sec": round(elapsed, 3), "error": str(e)}

    return results


def main():
    skip_vmd = "--skip-vmd" in sys.argv
    all_files = sorted(DATA_DIR.glob("*.npy"))
    print(f"找到 {len(all_files)} 个文件")
    if skip_vmd:
        print("⚠️ VMD 方法已跳过（使用 --skip-vmd 参数）")

    # 按故障类型分组
    groups = {}
    for f in all_files:
        fname = f.name
        fault_type = fname.split("_")[0]
        if fault_type not in groups:
            groups[fault_type] = []
        groups[fault_type].append(fname)

    # 方法列表
    method_list = ["narrowband", "fullband", "tsa_envelope", "hp_envelope", "sc_scoh", "msb"]
    if not skip_vmd:
        method_list.append("vmd_demod")

    # 运行评估
    all_results = {}
    total_start = time.perf_counter()

    for fault_type, files in sorted(groups.items()):
        fault_name = FAULT_MAP.get(fault_type, fault_type)
        print(f"\n=== {fault_name} ({fault_type}) - {len(files)} files ===")
        all_results[fault_type] = []

        for fname in files:
            signal = load_file(fname)
            if signal is None:
                continue

            rot_freq = get_rot_freq_from_filename(fname)
            # 截断5秒
            max_samples = int(FS * 5)
            if len(signal) > max_samples:
                signal = signal[:max_samples]

            results = run_all_methods(signal, FS, rot_freq, GEAR_TEETH, skip_vmd=skip_vmd)
            entry = {
                "filename": fname,
                "rot_freq": rot_freq,
                "results": results,
            }
            all_results[fault_type].append(entry)

            # 实时输出
            ch = fname.split("-")[1].replace(".npy", "")
            sub = fname.split("_")[1]
            for method_name, method_data in results.items():
                elapsed = method_data.get("elapsed_sec", 0.0)
                if "error" in method_data:
                    slow_tag = " 🔴慢" if method_name in SLOW_METHODS else ""
                    print(f"  {fname} [{method_name}{slow_tag}] ERROR: {method_data['error']} ({elapsed:.2f}s)")
                else:
                    sun_snr = method_data.get("sun", 0)
                    planet_snr = method_data.get("planet", 0)
                    carrier_snr = method_data.get("carrier", 0)
                    slow_tag = " 🔴慢" if method_name in SLOW_METHODS and elapsed > 5.0 else ""
                    print(f"  {fname} [{method_name}] sun={sun_snr:.2f} planet={planet_snr:.2f} carrier={carrier_snr:.2f} ({elapsed:.2f}s{slow_tag})")

    total_elapsed = time.perf_counter() - total_start
    print(f"\n\n总评估时间: {total_elapsed:.1f}s ({total_elapsed/60:.1f}min)")

    # === 计算时间统计 ===
    print("\n\n========== 各方法计算时间统计 ========== ")
    for method_name in method_list:
        times = []
        for fault_type, entries in all_results.items():
            for entry in entries:
                r = entry["results"].get(method_name, {})
                t = r.get("elapsed_sec", 0.0)
                if t > 0 and "error" not in r:
                    times.append(t)
        if times:
            avg_t = np.mean(times)
            med_t = np.median(times)
            max_t = max(times)
            slow_tag = " 🔴慢" if method_name in SLOW_METHODS else ""
            print(f"  {method_name}{slow_tag}: avg={avg_t:.2f}s median={med_t:.2f}s max={max_t:.2f}s (N={len(times)})")
        else:
            print(f"  {method_name}: 无成功计算")

    # === SNR 区分力统计 ===
    print("\n\n========== 各方法 SNR 区分力统计 ==========")

    # 定义各方法的主要 SNR 指标键
    method_primary_snr = {
        "narrowband": [("sun", "sun_fault_order"), ("planet", "planet_fault_order"), ("carrier", "carrier")],
        "fullband": [("sun", "sun_fault_order"), ("planet", "planet_fault_order"), ("carrier", "carrier")],
        "tsa_envelope": [("sun", "sun_fault_order"), ("planet", "planet_fault_order"), ("carrier", "carrier")],
        "hp_envelope": [("sun", "sun_fault_order"), ("planet", "planet_fault_order"), ("carrier", "carrier")],
        "vmd_demod": [("sun", "sun_fault_order"), ("planet", "planet_fault_order"), ("carrier", "carrier")],
        "sc_scoh": [("sun", "sun_scoh"), ("planet", "planet_scoh"), ("carrier", "carrier_scoh"),
                    ("sun_sc", "sun_SC"), ("planet_sc", "planet_SC"), ("carrier_sc", "carrier_SC")],
        "msb": [("msb_se", "MSB-SE"), ("sun", "sun_fault"), ("planet", "planet_fault"), ("carrier", "carrier")],
    }

    for method_name in method_list:
        snr_targets = method_primary_snr.get(method_name, [("sun", "sun"), ("planet", "planet"), ("carrier", "carrier")])
        slow_tag = " 🔴慢" if method_name in SLOW_METHODS else ""
        print(f"\n--- {method_name}{slow_tag} ---")

        for metric_key, label in snr_targets:
            healthy_vals = []
            faulty_vals = []

            for fault_type, entries in all_results.items():
                for entry in entries:
                    r = entry["results"].get(method_name, {})
                    if "error" in r:
                        continue
                    val = r.get(metric_key, 0.0)
                    if val > 0:
                        if fault_type == "He":
                            healthy_vals.append(val)
                        else:
                            faulty_vals.append(val)

            if healthy_vals and faulty_vals:
                h_min, h_max, h_med = min(healthy_vals), max(healthy_vals), np.median(healthy_vals)
                f_min, f_max, f_med = min(faulty_vals), max(faulty_vals), np.median(faulty_vals)
                discrimination = f_med / h_med if h_med > 0 else 0
                overlap = max(0, min(h_max, f_max) - max(h_min, f_min)) / max(h_max - h_min, f_max - f_min, 1e-12)
                print(f"  {label} SNR:")
                print(f"    健康: min={h_min:.2f} max={h_max:.2f} median={h_med:.2f} (N={len(healthy_vals)})")
                print(f"    故障: min={f_min:.2f} max={f_max:.2f} median={f_med:.2f} (N={len(faulty_vals)})")
                print(f"    区分力(discrimination)={discrimination:.2f}  overlap={overlap:.2f}")
                h_above3 = sum(1 for v in healthy_vals if v > 3.0)
                f_above3 = sum(1 for v in faulty_vals if v > 3.0)
                h_above5 = sum(1 for v in healthy_vals if v > 5.0)
                f_above5 = sum(1 for v in faulty_vals if v > 5.0)
                print(f"    SNR>3: 健康{h_above3}/{len(healthy_vals)}({h_above3/len(healthy_vals)*100:.0f}%) 故障{f_above3}/{len(faulty_vals)}({f_above3/len(faulty_vals)*100:.0f}%)")
                print(f"    SNR>5: 健康{h_above5}/{len(healthy_vals)}({h_above5/len(healthy_vals)*100:.0f}%) 故障{f_above5}/{len(faulty_vals)}({f_above5/len(faulty_vals)*100:.0f}%)")
            elif healthy_vals:
                print(f"  {label} SNR: 仅健康 min={min(healthy_vals):.2f} max={max(healthy_vals):.2f}")
            elif faulty_vals:
                print(f"  {label} SNR: 仅故障 min={min(faulty_vals):.2f} max={max(faulty_vals):.2f}")
            else:
                print(f"  {label} SNR: 无数据")

    # === 按故障类型细分 ===
    print("\n\n========== 按故障类型细分（sun_fault_snr 或等效指标）==========")
    for method_name in method_list:
        slow_tag = " 🔴慢" if method_name in SLOW_METHODS else ""
        print(f"\n--- {method_name}{slow_tag} ---")
        # 确定主 sun 指标键
        if method_name == "sc_scoh":
            sun_key = "sun"
        elif method_name == "msb":
            sun_key = "sun"
        else:
            sun_key = "sun"

        for fault_type in ["He", "Br", "Mi", "We", "Rc"]:
            fault_name = FAULT_MAP.get(fault_type, fault_type)
            snrs = []
            for entry in all_results.get(fault_type, []):
                r = entry["results"].get(method_name, {})
                if "error" in r:
                    continue
                val = r.get(sun_key, 0.0)
                if val > 0:
                    snrs.append(val)
            if snrs:
                print(f"  {fault_name}: min={min(snrs):.2f} max={max(snrs):.2f} median={np.median(snrs):.2f} (N={len(snrs)})")
            else:
                print(f"  {fault_name}: 无数据")

    # === TSA 残差峭度统计 ===
    print("\n\n========== TSA residual kurtosis ========== ")
    healthy_kurt = []
    faulty_kurt = []
    for fault_type, entries in all_results.items():
        for entry in entries:
            r = entry["results"].get("tsa_envelope", {})
            if "error" in r:
                continue
            val = r.get("residual_kurtosis", 0.0)
            if val > 0:
                if fault_type == "He":
                    healthy_kurt.append(val)
                else:
                    faulty_kurt.append(val)
    if healthy_kurt and faulty_kurt:
        print(f"  健康: min={min(healthy_kurt):.2f} max={max(healthy_kurt):.2f} median={np.median(healthy_kurt):.2f}")
        print(f"  故障: min={min(faulty_kurt):.2f} max={max(faulty_kurt):.2f} median={np.median(faulty_kurt):.2f}")
        discrimination = np.median(faulty_kurt) / np.median(healthy_kurt) if np.median(healthy_kurt) > 0 else 0
        print(f"  区分力={discrimination:.2f}")

    # === 调制深度比统计（narrowband/fullband/hp）===
    print("\n\n========== 调制深度比统计（sun_modulation_depth）==========")
    mod_methods = ["narrowband", "fullband", "hp_envelope"]
    for method_name in mod_methods:
        healthy_md = []
        faulty_md = []
        for fault_type, entries in all_results.items():
            for entry in entries:
                r = entry["results"].get(method_name, {})
                if "error" in r:
                    continue
                val = r.get("sun_mod", 0.0)
                if val > 0:
                    if fault_type == "He":
                        healthy_md.append(val)
                    else:
                        faulty_md.append(val)
        print(f"\n--- {method_name} sun_modulation_depth ---")
        if healthy_md and faulty_md:
            h_med = np.median(healthy_md)
            f_med = np.median(faulty_md)
            discrimination = f_med / h_med if h_med > 0 else 0
            print(f"  健康: min={min(healthy_md):.4f} max={max(healthy_md):.4f} median={h_med:.4f} (N={len(healthy_md)})")
            print(f"  故障: min={min(faulty_md):.4f} max={max(faulty_md):.4f} median={f_med:.4f} (N={len(faulty_md)})")
            print(f"  区分力={discrimination:.2f}")

    # === 包络峭度统计 ===
    print("\n\n========== 包络峭度统计 ========== ")
    for method_name in method_list:
        healthy_kurt = []
        faulty_kurt = []
        for fault_type, entries in all_results.items():
            for entry in entries:
                r = entry["results"].get(method_name, {})
                if "error" in r:
                    continue
                val = r.get("envelope_kurtosis", 0.0)
                if val > 0:
                    if fault_type == "He":
                        healthy_kurt.append(val)
                    else:
                        faulty_kurt.append(val)
        if healthy_kurt and faulty_kurt:
            h_med = np.median(healthy_kurt)
            f_med = np.median(faulty_kurt)
            discrimination = f_med / h_med if h_med > 0 else 0
            print(f"  {method_name}: 健康_median={h_med:.4f} 故障_median={f_med:.4f} 区分力={discrimination:.2f}")

    # === 显著性统计 ===
    print("\n\n========== 显著性检出统计 ========== ")
    for method_name in method_list:
        sig_keys = {
            "sc_scoh": ["sun_fault_significant", "planet_fault_significant"],
            "msb": ["msb_sun_fault_significant", "msb_planet_fault_significant"],
        }
        default_keys = ["sun_fault_significant", "planet_fault_significant"]
        check_keys = sig_keys.get(method_name, default_keys)

        for sig_key in check_keys:
            healthy_sig = 0
            healthy_total = 0
            faulty_sig = 0
            faulty_total = 0
            for fault_type, entries in all_results.items():
                for entry in entries:
                    r = entry["results"].get(method_name, {})
                    if "error" in r:
                        continue
                    val = r.get(sig_key, False)
                    if fault_type == "He":
                        healthy_total += 1
                        if val:
                            healthy_sig += 1
                    else:
                        faulty_total += 1
                        if val:
                            faulty_sig += 1
            if healthy_total > 0 or faulty_total > 0:
                h_rate = healthy_sig / healthy_total * 100 if healthy_total > 0 else 0
                f_rate = faulty_sig / faulty_total * 100 if faulty_total > 0 else 0
                print(f"  {method_name}/{sig_key}: 健康{h_rate:.0f}%({healthy_sig}/{healthy_total}) 故障{f_rate:.0f}%({faulty_sig}/{faulty_total})")

    # === 保存详细结果 ===
    output_path = Path(__file__).parent / "planetary_demod_results.json"
    serializable = {}
    for fault_type, entries in all_results.items():
        serializable[fault_type] = []
        for entry in entries:
            e = {"filename": entry["filename"], "rot_freq": entry["rot_freq"]}
            for method_name, method_data in entry["results"].items():
                e[method_name] = {}
                for k, v in method_data.items():
                    if isinstance(v, (np.floating, np.integer)):
                        e[method_name][k] = float(v)
                    elif isinstance(v, bool):
                        e[method_name][k] = v
                    else:
                        e[method_name][k] = v
            serializable[fault_type].append(e)

    with open(str(output_path), "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存至 {output_path}")

    # === 慢算法标记汇总 ===
    print("\n\n========== 慢算法标记 ========== ")
    for method_name, note in SLOW_METHODS.items():
        if method_name not in method_list:
            continue
        times = []
        for fault_type, entries in all_results.items():
            for entry in entries:
                r = entry["results"].get(method_name, {})
                t = r.get("elapsed_sec", 0.0)
                if t > 0:
                    times.append(t)
        if times:
            avg_t = np.mean(times)
            print(f"  {method_name}: avg={avg_t:.2f}s — {note}")
        else:
            print(f"  {method_name}: 未运行 — {note}")


if __name__ == "__main__":
    main()