"""
行星齿轮箱解调算法全数据集评估

对 WTgearbox 160 个 .npy 文件运行所有解调方法，
输出各方法对健康/故障的区分力统计。

用法：
  cd /d D:\code\CNN\cloud
  . venv\Scripts\activate
  PYTHONPATH=D:\code\CNN\cloud python ../tests/diagnosis/test_planetary_demod.py
"""
import sys
import os
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


def load_file(filename):
    """加载 .npy 文件"""
    path = DATA_DIR / filename
    if not path.exists():
        return None
    return np.load(str(path))


def get_rot_freq_from_filename(filename):
    """从文件名提取转速"""
    # 格式: {Fault}_{Sub}_{Speed}-c{Ch}.npy
    parts = filename.replace(".npy", "").split("-")
    speed_part = parts[0].split("_")[-1]  # 最后一部分是转速
    try:
        return float(speed_part)
    except ValueError:
        return 35.0  # 默认


def run_all_methods(signal, fs, rot_freq, gear_teeth, skip_vmd=False):
    """运行所有解调方法"""
    results = {}
    methods = [
        ("narrowband", planetary_envelope_order_analysis),
        ("fullband", planetary_fullband_envelope_order_analysis),
        ("tsa_envelope", planetary_tsa_envelope_analysis),
        ("hp_envelope", planetary_hp_envelope_order_analysis),
    ]
    if not skip_vmd:
        methods.append(("vmd_demod", planetary_vmd_demod_analysis))
    for name, func in methods:
        try:
            r = func(signal, fs, rot_freq, gear_teeth)
            if "error" in r:
                results[name] = {"error": r["error"]}
            else:
                results[name] = {
                    "sun_fault_snr": r.get("sun_fault_snr", 0.0),
                    "planet_fault_snr": r.get("planet_fault_snr", 0.0),
                    "carrier_snr": r.get("carrier_snr", 0.0),
                    "sun_fault_significant": r.get("sun_fault_significant", False),
                    "planet_fault_significant": r.get("planet_fault_significant", False),
                    "sun_modulation_depth": r.get("sun_modulation_depth", 0.0),
                    "planet_modulation_depth": r.get("planet_modulation_depth", 0.0),
                    "carrier_modulation_depth": r.get("carrier_modulation_depth", 0.0),
                    "sun_fault_amp": r.get("sun_fault_amp", 0.0),
                    "planet_fault_amp": r.get("planet_fault_amp", 0.0),
                    "carrier_amp": r.get("carrier_amp", 0.0),
                    "mesh_amp": r.get("mesh_amp", 0.0),
                    "envelope_kurtosis": r.get("envelope_kurtosis", 0.0),
                }
                # VMD 有额外的幅值/频率解调结果
                if name == "vmd_demod":
                    amp_demod = r.get("amplitude_demod", {})
                    freq_demod = r.get("frequency_demod", {})
                    results[name]["amp_sun_snr"] = amp_demod.get("amp_demod_sun_fault_snr", 0.0)
                    results[name]["amp_planet_snr"] = amp_demod.get("amp_demod_planet_fault_snr", 0.0)
                    results[name]["freq_sun_snr"] = freq_demod.get("freq_demod_sun_fault_snr", 0.0)
                    results[name]["freq_planet_snr"] = freq_demod.get("freq_demod_planet_fault_snr", 0.0)
                # TSA 有残差峭度
                if name == "tsa_envelope":
                    results[name]["residual_kurtosis"] = r.get("residual_kurtosis", 0.0)
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def main():
    skip_vmd = "--skip-vmd" in sys.argv
    # 收集所有文件
    all_files = sorted(DATA_DIR.glob("*.npy"))
    print(f"找到 {len(all_files)} 个文件")
    if skip_vmd:
        print("⚠️ VMD 方法已跳过（使用 --skip-vmd 参数）")

    # 按故障类型分组
    groups = {}
    for f in all_files:
        fname = f.name
        fault_type = fname.split("_")[0]  # He, Br, Mi, We, Rc
        if fault_type not in groups:
            groups[fault_type] = []
        groups[fault_type].append(fname)

    # 运行评估
    all_results = {}
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
                if "error" in method_data:
                    print(f"  {fname} [{method_name}] ERROR: {method_data['error']}")
                else:
                    sun_snr = method_data.get("sun_fault_snr", 0)
                    planet_snr = method_data.get("planet_fault_snr", 0)
                    carrier_snr = method_data.get("carrier_snr", 0)
                    print(f"  {fname} [{method_name}] sun_snr={sun_snr:.2f} planet_snr={planet_snr:.2f} carrier_snr={carrier_snr:.2f}")

    # === 统计汇总 ===
    print("\n\n========== 各方法区分力统计 ==========")

    method_list = ["narrowband", "fullband", "tsa_envelope", "hp_envelope"]
    if not skip_vmd:
        method_list.append("vmd_demod")

    # 按方法收集健康/故障的 SNR 范围
    for method_name in method_list:
        healthy_snrs = {"sun": [], "planet": [], "carrier": []}
        faulty_snrs = {"sun": [], "planet": [], "carrier": []}

        for fault_type, entries in all_results.items():
            for entry in entries:
                r = entry["results"].get(method_name, {})
                if "error" in r:
                    continue

                for key, target in [("sun_fault_snr", "sun"), ("planet_fault_snr", "planet"), ("carrier_snr", "carrier")]:
                    val = r.get(key, 0.0)
                    if val > 0:
                        if fault_type == "He":
                            healthy_snrs[target].append(val)
                        else:
                            faulty_snrs[target].append(val)

                # VMD 幅值解调额外指标
                if method_name == "vmd_demod":
                    for key, target in [("amp_sun_snr", "sun"), ("amp_planet_snr", "planet")]:
                        val = r.get(key, 0.0)
                        if val > 0:
                            if fault_type == "He":
                                healthy_snrs[target].append(val)
                            else:
                                faulty_snrs[target].append(val)
                    for key, target in [("freq_sun_snr", "sun"), ("freq_planet_snr", "planet")]:
                        val = r.get(key, 0.0)
                        if val > 0:
                            if fault_type == "He":
                                healthy_snrs[target].append(val)
                            else:
                                faulty_snrs[target].append(val)

        print(f"\n--- {method_name} ---")
        for target in ["sun", "planet", "carrier"]:
            h = healthy_snrs[target]
            f = faulty_snrs[target]
            if h and f:
                h_min, h_max, h_med = min(h), max(h), np.median(h)
                f_min, f_max, f_med = min(f), max(f), np.median(f)
                # 区分力指标：故障中位数 / 健康中位数
                discrimination = f_med / h_med if h_med > 0 else 0
                overlap = max(0, min(h_max, f_max) - max(h_min, f_min)) / max(h_max - h_min, f_max - f_min, 1e-12)
                print(f"  {target}_fault_order SNR:")
                print(f"    健康: min={h_min:.2f} max={h_max:.2f} median={h_med:.2f} (N={len(h)})")
                print(f"    故障: min={f_min:.2f} max={f_max:.2f} median={f_med:.2f} (N={len(f)})")
                print(f"    区分力(discrimination)={discrimination:.2f}  overlap={overlap:.2f}")
                # 检出率分析
                h_above3 = sum(1 for v in h if v > 3.0)
                f_above3 = sum(1 for v in f if v > 3.0)
                h_above5 = sum(1 for v in h if v > 5.0)
                f_above5 = sum(1 for v in f if v > 5.0)
                print(f"    SNR>3: 健康{h_above3}/{len(h)}({h_above3/len(h)*100:.0f}%) 故障{f_above3}/{len(f)}({f_above3/len(f)*100:.0f}%)")
                print(f"    SNR>5: 健康{h_above5}/{len(h)}({h_above5/len(h)*100:.0f}%) 故障{f_above5}/{len(f)}({f_above5/len(f)*100:.0f}%)")
            elif h:
                print(f"  {target}_fault_order SNR: 仅健康数据 min={min(h):.2f} max={max(h):.2f}")
            elif f:
                print(f"  {target}_fault_order SNR: 仅故障数据 min={min(f):.2f} max={max(f):.2f}")
            else:
                print(f"  {target}_fault_order SNR: 无数据")

    # TSA 残差峭度单独统计
    print("\n--- TSA residual kurtosis ---")
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

    # 调制深度比统计
    print("\n\n========== 调制深度比统计（sun_modulation_depth）==========")
    for method_name in method_list:
        healthy_md = []
        faulty_md = []
        for fault_type, entries in all_results.items():
            for entry in entries:
                r = entry["results"].get(method_name, {})
                if "error" in r:
                    continue
                val = r.get("sun_modulation_depth", 0.0)
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
            overlap = max(0, min(max(healthy_md), max(faulty_md)) - max(min(healthy_md), min(faulty_md))) / max(max(healthy_md) - min(healthy_md), max(faulty_md) - min(faulty_md), 1e-12)
            print(f"  健康: min={min(healthy_md):.4f} max={max(healthy_md):.4f} median={h_med:.4f} (N={len(healthy_md)})")
            print(f"  故障: min={min(faulty_md):.4f} max={max(faulty_md):.4f} median={f_med:.4f} (N={len(faulty_md)})")
            print(f"  区分力={discrimination:.2f}  overlap={overlap:.2f}")

    # 包络峭度统计
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
        print(f"\n--- {method_name} envelope_kurtosis ---")
        if healthy_kurt and faulty_kurt:
            h_med = np.median(healthy_kurt)
            f_med = np.median(faulty_kurt)
            discrimination = f_med / h_med if h_med > 0 else 0
            print(f"  健康: min={min(healthy_kurt):.4f} max={max(healthy_kurt):.4f} median={h_med:.4f}")
            print(f"  故障: min={min(faulty_kurt):.4f} max={max(faulty_kurt):.4f} median={f_med:.4f}")
            print(f"  区分力={discrimination:.2f}")

    # 按故障类型细分的 SNR
    print("\n\n========== 按故障类型细分（sun_fault_snr）==========")
    for method_name in method_list:
        print(f"\n--- {method_name} ---")
        for fault_type in ["He", "Br", "Mi", "We", "Rc"]:
            fault_name = FAULT_MAP.get(fault_type, fault_type)
            snrs = []
            for entry in all_results.get(fault_type, []):
                r = entry["results"].get(method_name, {})
                if "error" in r:
                    continue
                val = r.get("sun_fault_snr", 0.0)
                if val > 0:
                    snrs.append(val)
            if snrs:
                print(f"  {fault_name}: min={min(snrs):.2f} max={max(snrs):.2f} median={np.median(snrs):.2f} (N={len(snrs)})")
            else:
                print(f"  {fault_name}: 无数据")

    # 保存详细结果
    output_path = Path(__file__).parent / "planetary_demod_results.json"
    # 转换为可序列化格式
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


if __name__ == "__main__":
    main()