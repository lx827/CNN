r"""
行星齿轮箱诊断端到端评估

使用 DiagnosisEngine 对 WTgearbox 160 个 .npy 文件运行完整诊断流水线，
评估检出率（故障检出）、误报率（健康误报）和区分力。

评估维度：
  - health_score: 健康 vs 故障的评分区分力
  - status: 正常/warning/critical 的检出率/误报率
  - fault_probabilities: "齿轮磨损" 概率的区分力
  - ensemble confidence: gear_confidence 的检出率

用法：
  cd /d D:\code\CNN\cloud
  . venv\Scripts\activate
  PYTHONPATH=D:\code\CNN\cloud python ..\tests\diagnosis\test_planetary_e2e.py
"""
import sys
import os
import numpy as np
import json
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cloud"))

from app.services.diagnosis.engine import DiagnosisEngine, DenoiseMethod, DiagnosisStrategy, GearMethod

DATA_DIR = Path(r"D:\code\wavelet_study\dataset\WTgearbox\down8192")
FS = 8192

GEAR_TEETH = {"sun": 28, "ring": 100, "planet": 36, "planet_count": 4, "input": 28}

FAULT_MAP = {"He": "健康", "Br": "断齿", "Mi": "缺齿", "We": "磨损", "Rc": "裂纹"}


def get_rot_freq_from_filename(filename):
    parts = filename.replace(".npy", "").split("-")
    speed_part = parts[0].split("_")[-1]
    try:
        return float(speed_part)
    except ValueError:
        return 35.0


def run_e2e_diagnosis():
    all_files = sorted(DATA_DIR.glob("*.npy"))
    print(f"找到 {len(all_files)} 个文件")

    # 按故障类型分组
    groups = {}
    for f in all_files:
        fault_type = f.name.split("_")[0]
        if fault_type not in groups:
            groups[fault_type] = []
        groups[fault_type].append(f.name)

    results = {}

    engine = DiagnosisEngine(
        strategy=DiagnosisStrategy.EXPERT,
        gear_method=GearMethod.STANDARD,
        denoise_method=DenoiseMethod.NONE,
        bearing_params={},  # 行星箱无轴承参数
        gear_teeth=GEAR_TEETH,
    )

    for fault_type, files in sorted(groups.items()):
        fault_name = FAULT_MAP.get(fault_type, fault_type)
        print(f"\n=== {fault_name} ({fault_type}) - {len(files)} files ===")
        results[fault_type] = []

        for fname in files:
            path = DATA_DIR / fname
            if not path.exists():
                continue
            signal = np.load(str(path))
            rot_freq = get_rot_freq_from_filename(fname)

            # 截断5秒
            max_samples = int(FS * 5)
            if len(signal) > max_samples:
                signal = signal[:max_samples]

            # 运行完整诊断流水线（analyze_research_ensemble）
            try:
                ensemble_result = engine.analyze_research_ensemble(
                    signal, FS, rot_freq=rot_freq, profile="runtime"
                )
            except Exception as e:
                print(f"  {fname} ERROR: {e}")
                continue

            # 也运行 analyze_gear 来获取 planetary_tsa_demod
            try:
                gear_result = engine.analyze_gear(signal, FS, rot_freq)
            except Exception as e:
                gear_result = {"error": str(e)}

            # 提取关键指标
            entry = {
                "filename": fname,
                "rot_freq": rot_freq,
                "health_score": ensemble_result.get("health_score", 100),
                "status": ensemble_result.get("status", "normal"),
                "kurtosis": ensemble_result.get("time_features", {}).get("kurtosis", 3.0),
                "crest_factor": ensemble_result.get("time_features", {}).get("crest_factor", 3.0),
            }

            # ensemble 齿轮置信度
            ensemble_detail = ensemble_result.get("ensemble", {})
            gear_conf = ensemble_detail.get("gear_confidence", 0.0)
            if isinstance(gear_conf, dict):
                entry["gear_confidence"] = gear_conf.get("confidence", 0.0)
                entry["gear_abnormal"] = gear_conf.get("abnormal", False)
            else:
                entry["gear_confidence"] = float(gear_conf) if gear_conf else 0.0
                entry["gear_abnormal"] = bool(gear_conf and float(gear_conf) >= 0.55)

            # fault_probabilities
            fp = ensemble_result.get("fault_probabilities", {})
            entry["gear_wear_prob"] = fp.get("齿轮磨损", 0.0)

            # TSA 残差峭度
            tsa_demod = gear_result.get("planetary_tsa_demod") or {}
            if isinstance(tsa_demod, dict) and "error" not in tsa_demod:
                entry["tsa_residual_kurtosis"] = tsa_demod.get("residual_kurtosis", 0.0)
            else:
                entry["tsa_residual_kurtosis"] = 0.0

            # fault_indicators 中的 planetary 指标
            fi = gear_result.get("fault_indicators", {})
            planetary_sun = fi.get("planetary_sun_fault") or {}
            if isinstance(planetary_sun, dict):
                entry["planetary_sun_warning"] = planetary_sun.get("warning", False)
                entry["planetary_sun_critical"] = planetary_sun.get("critical", False)
                entry["planetary_sun_value"] = planetary_sun.get("value", 0.0)

            planetary_order_snr = fi.get("planetary_order_snr") or {}
            if isinstance(planetary_order_snr, dict):
                entry["planetary_sun_snr_value"] = planetary_order_snr.get("sun_fault_snr", 0.0) if isinstance(planetary_order_snr.get("sun_fault_snr"), (int, float)) else 0.0

            results[fault_type].append(entry)

            # 实时输出
            ch = fname.split("-")[1].replace(".npy", "")
            hs = entry["health_score"]
            st = entry["status"]
            gc = entry["gear_confidence"]
            gwp = entry["gear_wear_prob"]
            tsa_rk = entry["tsa_residual_kurtosis"]
            kurt = entry["kurtosis"]
            print(f"  {fname}: hs={hs} status={st} kurt={kurt:.2f} gear_conf={gc:.2f} wear_prob={gwp:.2f} tsa_rk={tsa_rk:.2f}")

    # === 统计汇总 ===
    print("\n\n========== 端到端评估结果 ========== ")

    # 1. health_score 区分力
    print("\n--- health_score 区分力 ---")
    healthy_scores = []
    faulty_scores = []
    for ft, entries in results.items():
        for e in entries:
            if ft == "He":
                healthy_scores.append(e["health_score"])
            else:
                faulty_scores.append(e["health_score"])
    if healthy_scores and faulty_scores:
        h_min, h_max, h_med = min(healthy_scores), max(healthy_scores), np.median(healthy_scores)
        f_min, f_max, f_med = min(faulty_scores), max(faulty_scores), np.median(faulty_scores)
        discrimination = h_med - f_med
        overlap = max(0, min(h_max, f_max) - max(h_min, f_min)) / max(h_max - h_min, f_max - f_min, 1e-12)
        print(f"  健康: min={h_min} max={h_max} median={h_med:.1f}")
        print(f"  故障: min={f_min} max={f_max} median={f_med:.1f}")
        print(f"  区分力(健康median-故障median)={discrimination:.1f}  overlap={overlap:.2f}")

    # 2. status 检出率/误报率
    print("\n--- status 检出率/误报率 ---")
    healthy_total = 0
    healthy_warning_or_fault = 0
    faulty_total = 0
    faulty_warning_or_fault = 0
    faulty_fault = 0
    for ft, entries in results.items():
        for e in entries:
            st = e["status"]
            if ft == "He":
                healthy_total += 1
                if st in ("warning", "fault", "critical"):
                    healthy_warning_or_fault += 1
            else:
                faulty_total += 1
                if st in ("warning", "fault", "critical"):
                    faulty_warning_or_fault += 1
                if st in ("fault", "critical"):
                    faulty_fault += 1
    if healthy_total > 0:
        print(f"  误报率(健康被判warning/fault): {healthy_warning_or_fault}/{healthy_total} = {healthy_warning_or_fault/healthy_total*100:.1f}%")
    if faulty_total > 0:
        print(f"  检出率(故障被判warning/fault): {faulty_warning_or_fault}/{faulty_total} = {faulty_warning_or_fault/faulty_total*100:.1f}%")
        print(f"  严格检出率(故障被判fault): {faulty_fault}/{faulty_total} = {faulty_fault/faulty_total*100:.1f}%")

    # 3. 按故障类型细分检出率
    print("\n--- 按故障类型细分检出率 ---")
    for ft in ["He", "Br", "Mi", "We", "Rc"]:
        fn = FAULT_MAP.get(ft, ft)
        entries = results.get(ft, [])
        total = len(entries)
        detected = sum(1 for e in entries if e["status"] in ("warning", "fault", "critical"))
        strict = sum(1 for e in entries if e["status"] in ("fault", "critical"))
        if total > 0:
            print(f"  {fn}: detected={detected}/{total}({detected/total*100:.1f}%) strict={strict}/{total}({strict/total*100:.1f}%)")

    # 4. gear_confidence 检出率
    print("\n--- gear_confidence 检出率 (confidence>=0.35) ---")
    healthy_total = 0
    healthy_abnormal = 0
    faulty_total = 0
    faulty_abnormal = 0
    for ft, entries in results.items():
        for e in entries:
            gc = e["gear_confidence"]
            ga = e["gear_abnormal"]
            if ft == "He":
                healthy_total += 1
                if ga or gc >= 0.35:
                    healthy_abnormal += 1
            else:
                faulty_total += 1
                if ga or gc >= 0.35:
                    faulty_abnormal += 1
    if healthy_total > 0:
        print(f"  误报率: {healthy_abnormal}/{healthy_total} = {healthy_abnormal/healthy_total*100:.1f}%")
    if faulty_total > 0:
        print(f"  检出率: {faulty_abnormal}/{faulty_total} = {faulty_abnormal/faulty_total*100:.1f}%")

    # 5. fault_probabilities 区分力
    print("\n--- 齿轮磨损概率区分力 ---")
    healthy_probs = []
    faulty_probs = []
    for ft, entries in results.items():
        for e in entries:
            p = e["gear_wear_prob"]
            if ft == "He":
                healthy_probs.append(p)
            else:
                faulty_probs.append(p)
    if healthy_probs and faulty_probs:
        h_med = np.median(healthy_probs)
        f_med = np.median(faulty_probs)
        discrimination = f_med - h_med
        overlap = max(0, min(max(healthy_probs), max(faulty_probs)) - max(min(healthy_probs), min(faulty_probs))) / max(max(healthy_probs) - min(healthy_probs), max(faulty_probs) - min(faulty_probs), 1e-12)
        print(f"  健康: min={min(healthy_probs):.3f} max={max(healthy_probs):.3f} median={h_med:.3f}")
        print(f"  故障: min={min(faulty_probs):.3f} max={max(faulty_probs):.3f} median={f_med:.3f}")
        print(f"  区分力(故障median-健康median)={discrimination:.3f}  overlap={overlap:.2f}")

    # 6. TSA 残差峭度检出率
    print("\n--- TSA 残差峭度检出率 (rk>2.5) ---")
    healthy_total = 0
    healthy_tsa_hit = 0
    faulty_total = 0
    faulty_tsa_hit = 0
    for ft, entries in results.items():
        for e in entries:
            rk = e.get("tsa_residual_kurtosis", 0.0)
            if ft == "He":
                healthy_total += 1
                if rk > 2.5:
                    healthy_tsa_hit += 1
            else:
                faulty_total += 1
                if rk > 2.5:
                    faulty_tsa_hit += 1
    if healthy_total > 0:
        print(f"  误报率: {healthy_tsa_hit}/{healthy_total} = {healthy_tsa_hit/healthy_total*100:.1f}%")
    if faulty_total > 0:
        print(f"  检出率: {faulty_tsa_hit}/{faulty_total} = {faulty_tsa_hit/faulty_total*100:.1f}%")

    # 7. kurtosis 检出率（当前主要检出手段）
    print("\n--- kurtosis 检出率 (kurt>12) ---")
    healthy_total = 0
    healthy_kurt_hit = 0
    faulty_total = 0
    faulty_kurt_hit = 0
    for ft, entries in results.items():
        for e in entries:
            k = e.get("kurtosis", 3.0)
            if ft == "He":
                healthy_total += 1
                if k > 12.0:
                    healthy_kurt_hit += 1
            else:
                faulty_total += 1
                if k > 12.0:
                    faulty_kurt_hit += 1
    if healthy_total > 0:
        print(f"  误报率: {healthy_kurt_hit}/{healthy_total} = {healthy_kurt_hit/healthy_total*100:.1f}%")
    if faulty_total > 0:
        print(f"  检出率: {faulty_kurt_hit}/{faulty_total} = {faulty_kurt_hit/faulty_total*100:.1f}%")

    # 8. 按故障类型细分 kurt/TSA 检出
    print("\n--- 按故障类型细分 kurt/TSA 检出 ---")
    for ft in ["He", "Br", "Mi", "We", "Rc"]:
        fn = FAULT_MAP.get(ft, ft)
        entries = results.get(ft, [])
        total = len(entries)
        kurt_hit = sum(1 for e in entries if e.get("kurtosis", 3.0) > 12.0)
        tsa_hit = sum(1 for e in entries if e.get("tsa_residual_kurtosis", 0.0) > 2.5)
        tsa_strict = sum(1 for e in entries if e.get("tsa_residual_kurtosis", 0.0) > 5.0)
        if total > 0:
            print(f"  {fn}: kurt>12={kurt_hit}/{total}({kurt_hit/total*100:.1f}%) tsa_rk>2.5={tsa_hit}/{total}({tsa_hit/total*100:.1f}%) tsa_rk>5={tsa_strict}/{total}({tsa_strict/total*100:.1f}%)")

    # 保存结果
    output_path = Path(__file__).parent / "planetary_e2e_results.json"
    serializable = {}
    for ft, entries in results.items():
        serializable[ft] = []
        for e in entries:
            se = {}
            for k, v in e.items():
                if isinstance(v, (np.floating, np.integer)):
                    se[k] = float(v)
                elif isinstance(v, bool):
                    se[k] = v
                else:
                    se[k] = v
            serializable[ft].append(se)
    with open(str(output_path), "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存至 {output_path}")


if __name__ == "__main__":
    run_e2e_diagnosis()