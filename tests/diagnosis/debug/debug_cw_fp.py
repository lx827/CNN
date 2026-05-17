"""
CW 健康数据误判原因诊断脚本

逐项打印健康度评分的每个中间值和扣分项，
揭示为什么 kurtosis < 5 的数据仍得到 59-77 的健康度。

运行方式:
    cd /d D:\code\CNN\cloud && venv\Scripts\activate && python ../tests/diagnosis/debug_cw_fp.py
"""
import sys
import os
import numpy as np

# 把 cloud 目录加入路径
CLOUD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "cloud"))
if CLOUD_DIR not in sys.path:
    sys.path.insert(0, CLOUD_DIR)

from app.services.diagnosis.engine import DiagnosisEngine, BearingMethod
from app.services.diagnosis.features import compute_time_features
from app.services.diagnosis.health_score import _compute_health_score

# ==================== 配置 ====================
CW_DIR = r"D:\code\CNN\CW\down8192_CW"
FS = 8192
MAX_SECONDS = 5
MAX_SAMPLES = FS * MAX_SECONDS

# 4 个已知的 FP 案例
FP_CASES = ["H-C-1", "H-C-3", "H-D-1", "H-D-3"]
# 加上几个正常案例做对比
NORMAL_CASES = ["H-A-1", "H-A-2", "H-B-1", "H-B-2"]


def load_cw(filename):
    path = os.path.join(CW_DIR, f"{filename}.npy")
    if not os.path.exists(path):
        print(f"  [WARN] 文件不存在: {path}")
        return None
    sig = np.load(path)
    if len(sig) > MAX_SAMPLES:
        sig = sig[:MAX_SAMPLES]
    return sig


def debug_single_case(filename, engine):
    """对单个数据文件做深度诊断，打印所有中间值"""
    sig = load_cw(filename)
    if sig is None:
        return

    print(f"\n{'='*70}")
    print(f"  诊断: {filename}")
    print(f"  信号长度: {len(sig)} 点 ({len(sig)/FS:.2f} 秒)")
    print(f"{'='*70}")

    # 1. 时域特征（核心门控指标）
    time_features = compute_time_features(sig)
    kurt = time_features.get("kurtosis", 0)
    crest = time_features.get("crest_factor", 0)
    rms = time_features.get("rms", 0)
    rms_mad_z = time_features.get("rms_mad_z", 0)
    kurt_mad_z = time_features.get("kurtosis_mad_z", 0)
    ewma_drift = time_features.get("ewma_drift", 0)
    cusum_score = time_features.get("cusum_score", 0)

    print(f"\n  === 时域特征 ===")
    print(f"    kurtosis (时域):       {kurt:.4f}   [门控阈值: >5.0 → 开启统计扣分]")
    print(f"    crest_factor (时域):   {crest:.4f}   [门控阈值: >7.0 → 开启统计扣分]")
    print(f"    rms:                   {rms:.6f}")
    print(f"    rms_mad_z:             {rms_mad_z:.4f}   [阈值: >4 → baseline_warning(10), >6 → baseline_extreme(18)]")
    print(f"    kurtosis_mad_z:        {kurt_mad_z:.4f}   [阈值: >4 → baseline_warning(10), >6 → baseline_extreme(18)]")
    print(f"    ewma_drift:            {ewma_drift:.4f}   [阈值: >4 → trend_drift_warning(8)]")
    print(f"    cusum_score:           {cusum_score:.4f}   [阈值: >8 → trend_drift_warning(8)]")

    # 判断门控条件
    kurt_gate = kurt > 5.0
    crest_gate = crest > 7.0
    print(f"\n  === 门控条件 ===")
    print(f"    kurt > 5.0:            {kurt_gate}  (kurt={kurt:.4f})")
    print(f"    crest > 7.0:           {crest_gate}  (crest={crest:.4f})")
    print(f"    时域冲击证据:          {kurt_gate or crest_gate}")

    # 2. 综合分析（获取 bearing/gear fault_indicators）
    result = engine.analyze_comprehensive(sig, FS)

    bearing_result = result.get("bearing", {})
    gear_result = result.get("gear", {})

    # 3. 轴承 fault_indicators 详细
    bearing_ind = bearing_result.get("fault_indicators", {})
    print(f"\n  === 轴承 fault_indicators ===")
    for key, val in bearing_ind.items():
        if isinstance(val, dict):
            significant = val.get("significant", False)
            value = val.get("value", val.get("snr", "?"))
            extra = ""
            if "rotation_harmonic_dominant" in val:
                extra = f", rotation_harmonic_dominant={val['rotation_harmonic_dominant']}"
            if "theory_hz" in val:
                extra += f", theory_hz={val.get('theory_hz')}"
            print(f"    {key:30s}: value={value}, significant={significant}{extra}")
        else:
            print(f"    {key:30s}: {val}")

    # 计算各分类的 significant 数量
    freq_sig_count = sum(
        v.get("significant") for k, v in bearing_ind.items()
        if isinstance(v, dict) and not k.endswith("_stat")
        and k not in {"envelope_peak_snr", "envelope_kurtosis", "high_freq_ratio", "peak_concentration"}
    )
    stat_sig_count = sum(
        v.get("significant") for k, v in bearing_ind.items()
        if isinstance(v, dict) and (k.endswith("_stat") or k in {
            "envelope_peak_snr", "envelope_kurtosis", "high_freq_ratio", "peak_concentration"
        })
    )

    # rotation_dominant
    low_freq_ind = bearing_ind.get("low_freq_ratio")
    rotation_dominant = False
    if isinstance(low_freq_ind, dict):
        rotation_dominant = low_freq_ind.get("rotation_harmonic_dominant", False)

    stat_has_evidence = (kurt > 5.0 or crest > 7.0) and not rotation_dominant

    print(f"\n  === 轴承扣分门控 ===")
    print(f"    freq_sig_count (物理参数路径):  {freq_sig_count}")
    print(f"    stat_sig_count (统计路径):      {stat_sig_count}")
    print(f"    rotation_dominant:              {rotation_dominant}")
    print(f"    stat_has_evidence:              {stat_has_evidence}")
    print(f"      = (kurt>{5.0} or crest>{7.0}) and not rotation_dominant")
    print(f"      = ({kurt_gate} or {crest_gate}) and not {rotation_dominant}")
    print(f"      = {kurt_gate or crest_gate} and not {rotation_dominant}")
    print(f"      = {stat_has_evidence}")

    # 4. 齿轮 fault_indicators 详细
    gear_ind = gear_result.get("fault_indicators", {})
    print(f"\n  === 齿轮 fault_indicators ===")
    for key, val in gear_ind.items():
        if isinstance(val, dict):
            warning = val.get("warning", False)
            critical = val.get("critical", False)
            value = val.get("value", "?")
            print(f"    {key:30s}: value={value}, warning={warning}, critical={critical}")
        else:
            print(f"    {key:30s}: {val}")

    # 齿轮扣分门控
    gear_teeth = engine.gear_teeth
    try:
        has_gear = bool(gear_teeth and float(gear_teeth.get("input") or 0) > 0)
    except (TypeError, ValueError):
        has_gear = False

    gear_freq_has_evidence = (kurt > 5.0 or crest > 7.0)
    gear_stat_has_evidence = (kurt > 5.0 or crest > 7.0)

    print(f"\n  === 齿轮扣分门控 ===")
    print(f"    has_gear (有齿轮参数):    {has_gear}")
    print(f"    gear_freq_has_evidence:   {gear_freq_has_evidence}")
    print(f"      = (kurt>{5.0} or crest>{7.0}) = ({kurt_gate} or {crest_gate}) = {gear_freq_has_evidence}")
    print(f"    gear_stat_has_evidence:   {gear_stat_has_evidence}")
    print(f"      = (kurt>{5.0} or crest>{7.0}) = ({kurt_gate} or {crest_gate}) = {gear_stat_has_evidence}")
    print(f"    *** 注意: 齿轮统计门控没有 rotation_dominant 保护! ***")

    # 5. 手动模拟 health_score.py 的扣分逻辑，逐项打印
    print(f"\n  === 模拟 _compute_health_score 扣分 ===")

    deductions = []
    total_from_code = 0

    # 峭度扣分
    if kurt > 20:
        d = ("kurtosis_extreme", 40)
        deductions.append(d)
        print(f"    kurtosis_extreme:  40  (kurt={kurt:.4f} > 20)")
    elif kurt > 12:
        d = ("kurtosis_high", 30)
        deductions.append(d)
        print(f"    kurtosis_high:     30  (kurt={kurt:.4f} > 12)")
    elif kurt > 8:
        d = ("kurtosis_moderate", 22)
        deductions.append(d)
        print(f"    kurtosis_moderate: 22  (kurt={kurt:.4f} > 8)")
    elif kurt > 5:
        d = ("kurtosis_mild", 15)
        deductions.append(d)
        print(f"    kurtosis_mild:     15  (kurt={kurt:.4f} > 5)")
    else:
        print(f"    [无峭度扣分]  kurt={kurt:.4f} < 5.0")

    # 峰值因子扣分
    if crest > 15:
        d = ("crest_very_high", 15)
        deductions.append(d)
        print(f"    crest_very_high:   15  (crest={crest:.4f} > 15)")
    elif crest > 10:
        d = ("crest_high", 10)
        deductions.append(d)
        print(f"    crest_high:        10  (crest={crest:.4f} > 10)")
    elif crest > 7:
        d = ("crest_moderate", 5)
        deductions.append(d)
        print(f"    crest_moderate:     5  (crest={crest:.4f} > 7)  *** 这个可能是关键! ***")
    else:
        print(f"    [无峰值因子扣分]  crest={crest:.4f} < 7.0")

    # 动态基线扣分
    if rms_mad_z > 6 or kurt_mad_z > 6:
        d = ("dynamic_baseline_extreme", 18)
        deductions.append(d)
        trigger = []
        if rms_mad_z > 6: trigger.append(f"rms_mad_z={rms_mad_z:.4f}")
        if kurt_mad_z > 6: trigger.append(f"kurt_mad_z={kurt_mad_z:.4f}")
        print(f"    dynamic_baseline_extreme: 18  ({', '.join(trigger)})")
    elif rms_mad_z > 4 or kurt_mad_z > 4:
        d = ("dynamic_baseline_warning", 10)
        deductions.append(d)
        trigger = []
        if rms_mad_z > 4: trigger.append(f"rms_mad_z={rms_mad_z:.4f}")
        if kurt_mad_z > 4: trigger.append(f"kurt_mad_z={kurt_mad_z:.4f}")
        print(f"    dynamic_baseline_warning: 10  ({', '.join(trigger)})")
    else:
        print(f"    [无动态基线扣分]  rms_mad_z={rms_mad_z:.4f}, kurt_mad_z={kurt_mad_z:.4f}")

    # 趋势漂移扣分
    if cusum_score > 8 or ewma_drift > 4:
        d = ("trend_drift_warning", 8)
        deductions.append(d)
        trigger = []
        if cusum_score > 8: trigger.append(f"cusum_score={cusum_score:.4f}")
        if ewma_drift > 4: trigger.append(f"ewma_drift={ewma_drift:.4f}")
        print(f"    trend_drift_warning:  8  ({', '.join(trigger)})")
    else:
        print(f"    [无趋势漂移扣分]  cusum={cusum_score:.4f}, ewma={ewma_drift:.4f}")

    # 轴承频率匹配扣分
    if kurt > 5.0:
        if freq_sig_count >= 2:
            d = ("bearing_multi_freq", 10)
            deductions.append(d)
            print(f"    bearing_multi_freq:  10  (kurt>5, freq_sig={freq_sig_count})")
        elif freq_sig_count == 1:
            d = ("bearing_single_freq", 5)
            deductions.append(d)
            print(f"    bearing_single_freq:   5  (kurt>5, freq_sig={freq_sig_count})")
    else:
        print(f"    [无轴承频率扣分]  kurt={kurt:.4f} < 5.0, 频率路径关闭")

    # 轴承统计扣分
    if stat_has_evidence:
        if stat_sig_count >= 2:
            d = ("bearing_statistical_abnormal", 10)
            deductions.append(d)
            print(f"    bearing_statistical_abnormal: 10  (stat_evidence=True, stat_sig={stat_sig_count})")
        elif stat_sig_count == 1:
            d = ("bearing_statistical_hint", 5)
            deductions.append(d)
            print(f"    bearing_statistical_hint:      5  (stat_evidence=True, stat_sig={stat_sig_count})")
    else:
        print(f"    [无轴承统计扣分]  stat_has_evidence=False")
        print(f"      原因: kurt_gate={kurt_gate}, crest_gate={crest_gate}, rotation_dominant={rotation_dominant}")
        if not (kurt_gate or crest_gate):
            print(f"      → 时域无冲击证据 (kurt<5, crest<7)")
        elif rotation_dominant:
            print(f"      → rotation_dominant=True 抑制了统计扣分")

    # 齿轮扣分
    if has_gear:
        print(f"    [齿轮参数路径 - 有齿轮参数]")
        if gear_freq_has_evidence:
            ser = gear_ind.get("ser", {}) if isinstance(gear_ind.get("ser"), dict) else {}
            if ser.get("critical"):
                d = ("gear_ser_critical", 12)
                deductions.append(d)
                print(f"    gear_ser_critical:   12")
            elif ser.get("warning"):
                d = ("gear_ser_warning", 6)
                deductions.append(d)
                print(f"    gear_ser_warning:     6")
            sb = gear_ind.get("sideband_count", {}) if isinstance(gear_ind.get("sideband_count"), dict) else {}
            if sb.get("critical"):
                d = ("gear_sb_critical", 8)
                deductions.append(d)
                print(f"    gear_sb_critical:     8")
            elif sb.get("warning"):
                d = ("gear_sb_warning", 4)
                deductions.append(d)
                print(f"    gear_sb_warning:      4")
        else:
            print(f"    [齿轮频率扣分关闭]  gear_freq_has_evidence=False")
    else:
        print(f"    [齿轮统计路径 - 无齿轮参数]")
        car = gear_ind.get("car", {}) if isinstance(gear_ind.get("car"), dict) else {}
        order_peak = gear_ind.get("order_peak_concentration", {}) if isinstance(gear_ind.get("order_peak_concentration"), dict) else {}
        order_kurt = gear_ind.get("order_kurtosis", {}) if isinstance(gear_ind.get("order_kurtosis"), dict) else {}
        print(f"      car:             value={car.get('value', '?')}, warning={car.get('warning', '?')}, critical={car.get('critical', '?')}")
        print(f"      order_peak_conc: value={order_peak.get('value', '?')}, warning={order_peak.get('warning', '?')}, critical={order_peak.get('critical', '?')}")
        print(f"      order_kurtosis:  value={order_kurt.get('value', '?')}, warning={order_kurt.get('warning', '?')}, critical={order_kurt.get('critical', '?')}")

        if gear_stat_has_evidence:
            if car.get("critical"):
                d = ("gear_car_critical", 8)
                deductions.append(d)
                print(f"    gear_car_critical:    8  (gear_stat_evidence=True)")
            elif car.get("warning"):
                d = ("gear_car_warning", 4)
                deductions.append(d)
                print(f"    gear_car_warning:     4  (gear_stat_evidence=True)")
            if order_peak.get("critical") or order_kurt.get("critical"):
                d = ("gear_order_stat_critical", 8)
                deductions.append(d)
                print(f"    gear_order_stat_critical: 8  (gear_stat_evidence=True)")
            elif order_peak.get("warning") or order_kurt.get("warning"):
                d = ("gear_order_stat_warning", 4)
                deductions.append(d)
                print(f"    gear_order_stat_warning:  4  (gear_stat_evidence=True)")
        else:
            print(f"    [齿轮统计扣分关闭]  gear_stat_has_evidence=False")
            print(f"      = (kurt>{5.0} or crest>{7.0}) = ({kurt_gate} or {crest_gate}) = {gear_stat_has_evidence}")

    # 6. 汇总
    total_manual = min(sum(d[1] for d in deductions), 75)
    score_manual = int(max(0, min(100, 100 - total_manual)))

    # 状态判定
    has_critical = any("critical" in d[0] for d in deductions)
    time_abnormal = kurt > 5 or crest > 10 or rms_mad_z > 4 or cusum_score > 8

    if score_manual >= 85:
        status_manual = "normal"
    elif score_manual >= 60:
        status_manual = "warning" if (has_critical or time_abnormal) else "normal"
    else:
        status_manual = "fault" if has_critical else "warning"

    print(f"\n  === 扣分汇总 ===")
    print(f"    扣分项总计: {len(deductions)} 个")
    total_pts = 0
    for name, pts in deductions:
        print(f"      {name:35s}: -{pts}")
        total_pts += pts
    print(f"    总扣分: {total_pts}  (上限75: min({total_pts}, 75) = {total_manual})")
    print(f"    手动计算健康度: 100 - {total_manual} = {score_manual}")
    print(f"    手动计算状态:   {status_manual}")
    print(f"    has_critical:   {has_critical}")
    print(f"    time_abnormal:  {time_abnormal}  (kurt>5 or crest>10 or rms_mad_z>4 or cusum>8)")

    # 7. 与引擎实际结果对比
    hs_engine = result.get("health_score", "?")
    status_engine = result.get("status", "?")

    print(f"\n  === 结果对比 ===")
    print(f"    手动健康度:   {score_manual}")
    print(f"    引擎健康度:   {hs_engine}")
    print(f"    手动状态:     {status_manual}")
    print(f"    引擎状态:     {status_engine}")
    if score_manual != hs_engine:
        print(f"    *** 不一致! 手动={score_manual}, 引擎={hs_engine} — 需进一步排查 ***")

    # 8. 显示引擎结果中的详细信息（用于交叉验证）
    print(f"\n  === 引擎返回结果摘要 ===")
    print(f"    health_score:  {result.get('health_score')}")
    print(f"    status:        {result.get('status')}")
    print(f"    recommendation: {result.get('recommendation', '')[:100]}")

    # 检查 significant 轴承指标（从 test 输出的视角）
    sig_bearing = [k for k, v in bearing_ind.items() if isinstance(v, dict) and v.get("significant")]
    sig_gear = [k for k, v in gear_ind.items() if isinstance(v, dict) and v.get("significant")]
    print(f"    significant_bearing: {sig_bearing}")
    print(f"    significant_gear:    {sig_gear}")

    return result


def main():
    print("=" * 70)
    print("  CW 健康数据误判原因诊断")
    print("  目标: 找出为什么 kurtosis < 5 的数据仍得到 hs=59-77")
    print("=" * 70)

    engine = DiagnosisEngine(
        strategy="advanced",
        bearing_method=BearingMethod.KURTOGRAM,
        bearing_params={},    # CW 无轴承参数
        gear_teeth={},        # CW 无齿轮参数
    )

    # 先诊断 4 个已知 FP 案例
    print("\n\n" + "!" * 70)
    print("  第一部分: 已知误判案例 (FP)")
    print("!" * 70)
    for case in FP_CASES:
        debug_single_case(case, engine)

    # 再诊断几个正常案例做对比
    print("\n\n" + "!" * 70)
    print("  第二部分: 正常案例 (对照)")
    print("!" * 70)
    for case in NORMAL_CASES:
        debug_single_case(case, engine)

    # 汇总对比
    print(f"\n\n{'='*70}")
    print(f"  汇总对比")
    print(f"{'='*70}")
    print(f"  {'文件':12s} | {'kurt':8s} | {'crest':8s} | {'rms_mad_z':10s} | {'kurt_mad_z':10s} | {'ewma_drift':10s} | {'cusum_score':10s} | {'HS':4s} | {'状态':8s}")
    print(f"  {'-'*12} | {'-'*8} | {'-'*8} | {'-'*10} | {'-'*10} | {'-'*10} | {'-'*10} | {'-'*4} | {'-'*8}")

    all_cases = FP_CASES + NORMAL_CASES
    for case in all_cases:
        sig = load_cw(case)
        if sig is None:
            continue
        tf = compute_time_features(sig)
        result = engine.analyze_comprehensive(sig, FS)
        k = tf.get("kurtosis", 0)
        c = tf.get("crest_factor", 0)
        r_mad = tf.get("rms_mad_z", 0)
        k_mad = tf.get("kurtosis_mad_z", 0)
        ew = tf.get("ewma_drift", 0)
        cs = tf.get("cusum_score", 0)
        hs = result.get("health_score", "?")
        st = result.get("status", "?")
        print(f"  {case:12s} | {k:8.4f} | {c:8.4f} | {r_mad:10.4f} | {k_mad:10.4f} | {ew:10.4f} | {cs:10.4f} | {hs:4s} | {st:8s}")


if __name__ == "__main__":
    main()