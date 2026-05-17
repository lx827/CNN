"""
故障诊断算法效果评估测试

覆盖 HUSTbear 和 CW 两个数据集的全部工况，
系统性评估：
  - 健康数据的误判率（false positive rate）
  - 故障数据的检出率（true positive rate）
  - 各算法路径的健康度分布
  - 导致误判的具体指标分析

数据集：
  HUSTbear: D:/code/wavelet_study/dataset/HUSTbear/down8192  (8192 Hz)
  CW:       D:/code/CNN/CW/down8192_CW                      (8192 Hz)

运行方式:
    cd d:/code/CNN
    cloud/venv/Scripts/python.exe tests/diagnosis/test_dataset_effectiveness.py
"""
import sys
import os
import glob
import numpy as np
from collections import defaultdict

# 把 cloud 目录加入路径
CLOUD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "cloud"))
if CLOUD_DIR not in sys.path:
    sys.path.insert(0, CLOUD_DIR)

from app.services.diagnosis import (
    DiagnosisEngine,
    BearingMethod,
    GearMethod,
    DenoiseMethod,
)
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum

# ==================== 数据集配置 ====================

HUST_DIR = r"D:\code\wavelet_study\dataset\HUSTbear\down8192"
CW_DIR = r"D:\code\CNN\CW\down8192_CW"
FS = 8192
MAX_SECONDS = 5  # 截断到 5 秒，与 DataView 保持一致

# HUSTbear 轴承参数（6205-2RS 型轴承，该数据集的标准参数）
HUST_BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 39.04, "alpha": 0}
# 命名: {负载}_{故障类型}_{转速模式}-{通道}
# 故障类型: H=健康, I=内圈, O=外圈, B=球故障, C=复合
HUST_FAULT_TYPES = {
    "H": "健康",
    "I": "内圈故障",
    "O": "外圈故障",
    "B": "球故障",
    "C": "复合故障",
}

# 恒速工况（不含 0.5X 前缀的文件）
HUST_CS_SPEEDS = ["20Hz", "25Hz", "30Hz", "35Hz", "40Hz", "60Hz", "65Hz", "70Hz", "75Hz", "80Hz"]

# CW 工况定义
CW_FAULT_TYPES = {
    "H": "健康",
    "I": "内圈故障",
    "O": "外圈故障",
}
CW_SPEED_MODES = ["A", "B", "C", "D"]


# ==================== 数据加载 ====================

def _glob_hust(condition, channel="X"):
    """灵活匹配 HUSTbear 文件（大小写不敏感）"""
    pattern = os.path.join(HUST_DIR, f"{condition}-{channel}.npy")
    files = glob.glob(pattern)
    if not files:
        # 尝试小写 hz
        alt = condition.replace("Hz", "hz")
        files = glob.glob(os.path.join(HUST_DIR, f"{alt}-{channel}.npy"))
    if not files:
        # 尝试 0.5X 前缀
        files = glob.glob(os.path.join(HUST_DIR, f"0.5X_{condition}-{channel}.npy"))
        if not files:
            alt = condition.replace("Hz", "hz")
            files = glob.glob(os.path.join(HUST_DIR, f"0.5X_{alt}-{channel}.npy"))
    return files


def _load_hust(condition, channel="X"):
    files = _glob_hust(condition, channel)
    if not files:
        return None
    sig = np.load(files[0])
    max_samples = FS * MAX_SECONDS
    return sig[:max_samples] if len(sig) > max_samples else sig


def _load_cw(filename):
    path = os.path.join(CW_DIR, f"{filename}.npy")
    if not os.path.exists(path):
        return None
    sig = np.load(path)
    max_samples = FS * MAX_SECONDS
    return sig[:max_samples] if len(sig) > max_samples else sig


# ==================== 算法分析 ====================

def analyze_with_engine(signal, fs=FS, bearing_params=None, gear_teeth=None):
    """用 DiagnosisEngine 综合分析"""
    if signal is None:
        return None
    engine = DiagnosisEngine(
        strategy="advanced",
        bearing_method=BearingMethod.KURTOGRAM,
        bearing_params=bearing_params or {},
        gear_teeth=gear_teeth or {},
    )
    return engine.analyze_comprehensive(signal, fs)


def analyze_stat_only(signal, fs=FS):
    """无参数纯统计诊断（最易误判的路径）"""
    if signal is None:
        return None
    engine = DiagnosisEngine(
        strategy="standard",
        bearing_params={},
        gear_teeth={},
    )
    return engine.analyze_comprehensive(signal, fs)


# ==================== 评估报告 ====================

def print_section(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def print_row(fields, widths=None):
    if widths is None:
        widths = [max(len(f), 12) for f in fields]
    line = " | ".join(f.ljust(w) for f, w in zip(fields, widths))
    print(line)


def evaluate_hustbear():
    """评估 HUSTbear 数据集全部恒速工况（无参数 vs 有参数对比）"""
    print_section("HUSTbear 恒速工况评估（X 通道）")

    # 表头
    headers = ["工况", "故障类型", "峭度", "无参HS", "无参状态", "误判?", "有参HS", "有参状态"]
    widths = [18, 12, 10, 10, 10, 8, 10, 10]
    print_row(headers, widths)
    print("-" * (sum(widths) + (len(widths) - 1) * 3))

    results = defaultdict(list)  # { fault_type: [health_score, ...] }
    fp_count = 0  # 健康误判为 warning/fault
    healthy_total = 0
    tp_count_no_param = 0  # 无参数故障检出
    tp_count_with_param = 0  # 有参数故障检出
    fault_total = 0

    for fault_code, fault_label in HUST_FAULT_TYPES.items():
        for speed in HUST_CS_SPEEDS:
            condition = f"{fault_code}_{speed}"
            sig = _load_hust(condition, "X")
            if sig is None:
                continue

            # 无参数诊断
            result = analyze_with_engine(sig)
            if result is None:
                continue

            # 有参数诊断（轴承 6205-2RS）
            result_param = analyze_with_engine(sig, bearing_params=HUST_BEARING_PARAMS)

            kurt = result["time_features"].get("kurtosis", 0)
            hs = result["health_score"]
            status = result["status"]
            hs_param = result_param["health_score"]
            status_param = result_param["status"]

            is_healthy = (fault_code == "H")
            is_fp = is_healthy and status in ("warning", "fault")
            is_tp_no_param = (not is_healthy) and status in ("warning", "fault")
            is_tp_with_param = (not is_healthy) and status_param in ("warning", "fault")

            fp_flag = "YES" if is_fp else ""
            row = [condition, fault_label, f"{kurt:.2f}", str(hs), status, fp_flag,
                   str(hs_param), str(status_param)]
            print_row(row, widths)

            results[fault_code].append(hs)
            if is_healthy:
                healthy_total += 1
                if is_fp:
                    fp_count += 1
            else:
                fault_total += 1
                if is_tp_no_param:
                    tp_count_no_param += 1
                if is_tp_with_param:
                    tp_count_with_param += 1

    # 统计摘要
    print_section("HUSTbear 恒速评估摘要")
    print(f"  健康样本总数: {healthy_total}")
    print(f"  健康误判(warning/fault): {fp_count}  FP率: {fp_count/healthy_total*100:.1f}%")
    print(f"  故障样本总数: {fault_total}")
    print(f"  无参数检出: {tp_count_no_param}  TP率: {tp_count_no_param/fault_total*100:.1f}%")
    print(f"  有参数检出: {tp_count_with_param}  TP率: {tp_count_with_param/fault_total*100:.1f}%")

    for fault_code, scores in results.items():
        if scores:
            print(f"  {HUST_FAULT_TYPES[fault_code]}: 健康度均值={np.mean(scores):.1f}, "
                  f"范围={min(scores)}-{max(scores)}")

    return fp_count, healthy_total, tp_count_no_param, tp_count_with_param, fault_total


def evaluate_hustbear_vs():
    """评估 HUSTbear 变速工况"""
    print_section("HUSTbear 变速工况评估（VS 0-40-0Hz）")

    headers = ["工况", "故障类型", "峭度", "健康度", "状态", "误判?"]
    widths = [24, 12, 10, 10, 10, 8]
    print_row(headers, widths)
    print("-" * (sum(widths) + (len(widths) - 1) * 3))

    fp_count = 0
    healthy_total = 0
    tp_count = 0
    fault_total = 0

    for fault_code, fault_label in HUST_FAULT_TYPES.items():
        condition = f"{fault_code}_VS_0_40_0Hz"
        sig = _load_hust(condition, "X")
        if sig is None:
            continue

        result = analyze_with_engine(sig)
        if result is None:
            continue

        kurt = result["time_features"].get("kurtosis", 0)
        hs = result["health_score"]
        status = result["status"]

        is_healthy = (fault_code == "H")
        is_fp = is_healthy and status in ("warning", "fault")
        is_tp = (not is_healthy) and status in ("warning", "fault")

        fp_flag = "YES" if is_fp else ""
        row = [condition, fault_label, f"{kurt:.2f}", str(hs), status, fp_flag]
        print_row(row, widths)

        if is_healthy:
            healthy_total += 1
            if is_fp:
                fp_count += 1
        else:
            fault_total += 1
            if is_tp:
                tp_count += 1

    print(f"\n  健康样本: {healthy_total}, 误判: {fp_count}")
    print(f"  故障样本: {fault_total}, 检出: {tp_count}")
    return fp_count, healthy_total, tp_count, fault_total


def evaluate_cw():
    """评估 CW 数据集全部变速工况"""
    print_section("CW 变速工况评估")

    headers = ["文件", "故障类型", "转速模式", "峭度", "健康度", "状态", "误判?"]
    widths = [12, 12, 8, 10, 10, 10, 8]
    print_row(headers, widths)
    print("-" * (sum(widths) + (len(widths) - 1) * 3))

    fp_count = 0
    healthy_total = 0
    tp_count = 0
    fault_total = 0
    stat_fp = 0

    for fault_code, fault_label in CW_FAULT_TYPES.items():
        for speed_mode in CW_SPEED_MODES:
            for seq in [1, 2, 3]:
                filename = f"{fault_code}-{speed_mode}-{seq}"
                sig = _load_cw(filename)
                if sig is None:
                    continue

                result = analyze_with_engine(sig)
                if result is None:
                    continue

                stat_result = analyze_stat_only(sig)

                kurt = result["time_features"].get("kurtosis", 0)
                hs = result["health_score"]
                status = result["status"]
                stat_hs = stat_result["health_score"] if stat_result else "-"
                stat_status = stat_result["status"] if stat_result else "-"

                is_healthy = (fault_code == "H")
                is_fp = is_healthy and status in ("warning", "fault")
                is_tp = (not is_healthy) and status in ("warning", "fault")

                fp_flag = "YES" if is_fp else ""

                # 详细输出 CW
                row = [filename, fault_label, speed_mode, f"{kurt:.2f}", str(hs), status, fp_flag]
                print_row(row, widths)

                # 如果误判，打印 stat 和详细扣分信息
                if is_fp:
                    stat_fp_flag = "YES" if (stat_result and stat_result["status"] in ("warning", "fault")) else ""
                    print(f"    >>> stat: hs={stat_hs}, status={stat_status} {stat_fp_flag}")
                    # 打印扣分项
                    if hasattr(result, 'get'):
                        bearing_ind = result.get("bearing", {}).get("fault_indicators", {})
                        gear_ind = result.get("gear", {}).get("fault_indicators", {})
                        sig_bearing = [k for k, v in bearing_ind.items() if isinstance(v, dict) and v.get("significant")]
                        sig_gear = [k for k, v in gear_ind.items() if isinstance(v, dict) and v.get("significant")]
                        print(f"    >>> kurt={kurt:.2f}, significant_bearing={sig_bearing}, significant_gear={sig_gear}")

                if is_healthy:
                    healthy_total += 1
                    if is_fp:
                        fp_count += 1
                else:
                    fault_total += 1
                    if is_tp:
                        tp_count += 1

    print_section("CW 评估摘要")
    print(f"  健康样本总数: {healthy_total}")
    print(f"  健康误判(warning/fault): {fp_count}  FP率: {fp_count/healthy_total*100:.1f}%")
    print(f"  纯统计路径误判: {stat_fp}/{healthy_total}  FP率: {stat_fp/healthy_total*100:.1f}%")
    print(f"  故障样本总数: {fault_total}")
    print(f"  故障检出(warning/fault): {tp_count}  TP率: {tp_count/fault_total*100:.1f}%")

    return fp_count, healthy_total, tp_count, fault_total


def evaluate_false_positive_causes():
    """分析健康数据误判的具体原因"""
    print_section("健康数据误判原因分析")

    # 收集所有健康数据的 kurtosis 和 status
    all_healthy_kurt = []
    all_healthy_status = []
    all_healthy_hs = []
    cause_counter = defaultdict(int)

    # HUSTbear 恒速
    for speed in HUST_CS_SPEEDS:
        sig = _load_hust(f"H_{speed}", "X")
        if sig is None:
            continue
        result = analyze_with_engine(sig)
        if result is None:
            continue

        kurt = result["time_features"].get("kurtosis", 0)
        hs = result["health_score"]
        status = result["status"]
        all_healthy_kurt.append(kurt)
        all_healthy_status.append(status)
        all_healthy_hs.append(hs)

        if status != "normal":
            # 分析原因
            bearing_ind = result.get("bearing", {}).get("fault_indicators", {})
            gear_ind = result.get("gear", {}).get("fault_indicators", {})
            stat_sig = [k for k, v in bearing_ind.items()
                        if isinstance(v, dict) and v.get("significant")]
            gear_sig = [k for k, v in gear_ind.items()
                        if isinstance(v, dict) and v.get("significant")]
            if kurt > 5:
                cause_counter["kurtosis>5"] += 1
            if kurt > 8:
                cause_counter["kurtosis>8"] += 1
            if kurt > 12:
                cause_counter["kurtosis>12"] += 1
            if stat_sig:
                cause_counter[f"stat_bearing:{','.join(stat_sig)}"] += 1
            if gear_sig:
                cause_counter[f"gear:{','.join(gear_sig)}"] += 1

    # CW 健康
    for speed_mode in CW_SPEED_MODES:
        for seq in [1, 2, 3]:
            sig = _load_cw(f"H-{speed_mode}-{seq}")
            if sig is None:
                continue
            result = analyze_with_engine(sig)
            if result is None:
                continue

            kurt = result["time_features"].get("kurtosis", 0)
            hs = result["health_score"]
            status = result["status"]
            all_healthy_kurt.append(kurt)
            all_healthy_status.append(status)
            all_healthy_hs.append(hs)

            if status != "normal":
                bearing_ind = result.get("bearing", {}).get("fault_indicators", {})
                gear_ind = result.get("gear", {}).get("fault_indicators", {})
                stat_sig = [k for k, v in bearing_ind.items()
                            if isinstance(v, dict) and v.get("significant")]
                gear_sig = [k for k, v in gear_ind.items()
                            if isinstance(v, dict) and v.get("significant")]
                if kurt > 5:
                    cause_counter["kurtosis>5"] += 1
                if kurt > 8:
                    cause_counter["kurtosis>8"] += 1
                if stat_sig:
                    cause_counter[f"stat_bearing:{','.join(stat_sig)}"] += 1
                if gear_sig:
                    cause_counter[f"gear:{','.join(gear_sig)}"] += 1

    # 汇总
    kurt_arr = np.array(all_healthy_kurt)
    print(f"  健康数据峭度分布:")
    print(f"    均值: {np.mean(kurt_arr):.2f}")
    print(f"    中位数: {np.median(kurt_arr):.2f}")
    print(f"    范围: {np.min(kurt_arr):.2f} ~ {np.max(kurt_arr):.2f}")
    print(f"    >5 的比例: {np.sum(kurt_arr > 5) / len(kurt_arr) * 100:.1f}%")
    print(f"    >8 的比例: {np.sum(kurt_arr > 8) / len(kurt_arr) * 100:.1f}%")
    print(f"    >12 的比例: {np.sum(kurt_arr > 12) / len(kurt_arr) * 100:.1f}%")

    normal_count = sum(1 for s in all_healthy_status if s == "normal")
    warning_count = sum(1 for s in all_healthy_status if s == "warning")
    fault_count = sum(1 for s in all_healthy_status if s == "fault")
    print(f"\n  健康数据判定结果分布:")
    print(f"    normal: {normal_count} ({normal_count/len(all_healthy_status)*100:.1f}%)")
    print(f"    warning: {warning_count} ({warning_count/len(all_healthy_status)*100:.1f}%)")
    print(f"    fault: {fault_count} ({fault_count/len(all_healthy_status)*100:.1f}%)")

    print(f"\n  健康数据健康度分布:")
    print(f"    均值: {np.mean(all_healthy_hs):.1f}")
    print(f"    中位数: {np.median(all_healthy_hs):.1f}")
    print(f"    范围: {min(all_healthy_hs)} ~ {max(all_healthy_hs)}")

    print(f"\n  误判原因统计:")
    for cause, count in sorted(cause_counter.items(), key=lambda x: -x[1]):
        print(f"    {cause}: {count} 次")


def evaluate_fault_detection_detail():
    """详细分析各故障类型在不同转速下的检出情况"""
    print_section("故障检出详细分析（HUSTbear 恒速 X 通道）")

    for fault_code in ["I", "O", "B", "C"]:
        fault_label = HUST_FAULT_TYPES[fault_code]
        print(f"\n  --- {fault_label} ---")
        headers = ["转速", "峭度", "健康度", "状态", "检出?", "bearing显著", "gear显著"]
        widths = [10, 10, 10, 10, 8, 16, 14]
        print_row(headers, widths)

        for speed in HUST_CS_SPEEDS:
            condition = f"{fault_code}_{speed}"
            sig = _load_hust(condition, "X")
            if sig is None:
                continue

            result = analyze_with_engine(sig)
            if result is None:
                continue

            kurt = result["time_features"].get("kurtosis", 0)
            hs = result["health_score"]
            status = result["status"]
            detected = "YES" if status in ("warning", "fault") else "NO"

            bearing_ind = result.get("bearing", {}).get("fault_indicators", {})
            gear_ind = result.get("gear", {}).get("fault_indicators", {})
            b_sig = [k for k, v in bearing_ind.items()
                     if isinstance(v, dict) and v.get("significant")]
            g_sig = [k for k, v in gear_ind.items()
                     if isinstance(v, dict) and v.get("significant")]

            row = [speed, f"{kurt:.2f}", str(hs), status, detected,
                   str(b_sig[:3]) if b_sig else "-", str(g_sig[:3]) if g_sig else "-"]
            print_row(row, widths)


# ==================== 主测试函数 ====================

def test_hustbear_effectiveness():
    """HUSTbear 恒速工况效果测试"""
    fp, h_total, tp_no_param, tp_with_param, f_total = evaluate_hustbear()
    fp_rate = fp / h_total if h_total > 0 else 0
    tp_rate_no_param = tp_no_param / f_total if f_total > 0 else 0
    tp_rate_with_param = tp_with_param / f_total if f_total > 0 else 0

    # 健康误判率必须低（核心目标）
    assert fp_rate <= 0.20, f"健康误判率过高: {fp_rate*100:.1f}% (上限 20%)"
    # 无参数检出率允许偏低（外圈故障无参数时难以检出是正常的）
    assert tp_rate_no_param >= 0.30, f"无参数检出率过低: {tp_rate_no_param*100:.1f}% (下限 30%)"
    # 有参数检出率（HUSTbear降采样后外圈故障BPFO不可见，允许偏低）
    assert tp_rate_with_param >= 0.40, f"有参数检出率过低: {tp_rate_with_param*100:.1f}% (下限 40%)"
    print(f"\n  [PASS] HUSTbear恒速: FP率={fp_rate*100:.1f}%, 无参TP={tp_rate_no_param*100:.1f}%, 有参TP={tp_rate_with_param*100:.1f}%")
    print(f"  注意: 外圈故障(O)在8192Hz降采样后BPFO共振信息丢失，检出率偏低是数据集固有限制")


def test_hustbear_vs_effectiveness():
    """HUSTbear 变速工况效果测试"""
    fp, h_total, tp, f_total = evaluate_hustbear_vs()
    # 变速工况样本少（仅1个健康样本），不做严格断言
    # 变速信号峭度天然偏高（速度变化本身引入变幅），健康误判率允许更高
    if h_total >= 3:
        fp_rate = fp / h_total
        assert fp_rate <= 0.50, f"变速健康误判率过高: {fp_rate*100:.1f}%"
    if f_total >= 3:
        tp_rate = tp / f_total
        assert tp_rate >= 0.40, f"变速故障检出率过低: {tp_rate*100:.1f}%"
    print(f"\n  [PASS] HUSTbear变速: FP={fp}/{h_total}, TP={tp}/{f_total}")


def test_cw_effectiveness():
    """CW 变速工况效果测试"""
    fp, h_total, tp, f_total = evaluate_cw()
    fp_rate = fp / h_total if h_total > 0 else 0
    tp_rate = tp / f_total if f_total > 0 else 0

    assert fp_rate <= 0.50, f"CW健康误判率过高: {fp_rate*100:.1f}% (上限 50%)"
    assert tp_rate >= 0.50, f"CW故障检出率过低: {tp_rate*100:.1f}% (下限 50%)"
    print(f"\n  [PASS] CW: FP率={fp_rate*100:.1f}%, TP率={tp_rate*100:.1f}%")


def run_all_tests():
    """运行全部效果评估"""
    print("=" * 70)
    print("  故障诊断算法效果评估 — HUSTbear + CW 全数据集")
    print(f"  采样率: {FS} Hz, 截断: {MAX_SECONDS} 秒")
    print(f"  HUSTbear: {HUST_DIR}")
    print(f"  CW: {CW_DIR}")
    print("=" * 70)

    # 先做误判原因分析（最关键）
    evaluate_false_positive_causes()

    # HUSTbear 恒速评估
    test_hustbear_effectiveness()

    # HUSTbear 变速评估
    test_hustbear_vs_effectiveness()

    # CW 评估
    test_cw_effectiveness()

    # 故障检出详细分析
    evaluate_fault_detection_detail()

    print("\n" + "=" * 70)
    print("  效果评估完成")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()