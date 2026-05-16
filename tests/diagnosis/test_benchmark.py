"""
离线基准评估框架

对三个数据集（HUSTbear, CW, WTgearbox）批量运行诊断引擎，
统计健康度评分分布和故障检出率，评估诊断算法性能。

用法：
  cd /d/code/CNN/cloud
  . venv/Scripts/activate
  python ../tests/diagnosis/test_benchmark.py

输出：
  - 每个数据集的统计摘要（健康/故障数据的健康度分布）
  - 检出率：故障数据被标记为 warning/fault 的比例
  - 误报率：健康数据被标记为 warning/fault 的比例
  - 分离度：健康与故障健康度均值之差
"""
import os
import sys
import numpy as np
from collections import defaultdict

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cloud"))

from app.services.diagnosis import DiagnosisEngine, BearingMethod, GearMethod, DenoiseMethod
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum

SAMPLE_RATE = 8192

# ═══════════════════════════════════════════════════════════
# 数据集路径配置
# ═══════════════════════════════════════════════════════════
HUSTBEAR_DIR = r"D:\code\wavelet_study\dataset\HUSTbear\down8192"
CW_DIR = r"D:\code\CNN\CW\down8192_CW"
WTGEARBOX_DIR = r"D:\code\wavelet_study\dataset\WTgearbox\down8192"

# ═══════════════════════════════════════════════════════════
# 机械参数配置
# ═══════════════════════════════════════════════════════════

# HUSTbear 轴承参数（SKF 6205-2RS）
HUSTBEAR_BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 39.04}  # 9 球, 球径7.94mm, 节径39.04mm

# CW 轴承参数（Baddour 2018 数据集）
CW_BEARING_PARAMS = {"n": 8, "d": 6.35, "D": 33.5}  # 近似参数

# WTgearbox 行星齿轮箱参数
WTGEARBOX_GEAR_TEETH = {"input": 28, "ring": 100, "planet": 36, "num_planets": 4}


# ═══════════════════════════════════════════════════════════
# 数据集分类函数
# ═══════════════════════════════════════════════════════════

def classify_hustbear(filename: str) -> dict:
    """分类 HUSTbear 文件: healthy/ball/inner/outer/composite"""
    # 文件格式: {负载}_{故障类型}_{转速模式}-{通道}.npy
    # 故障类型: N=健康, B=球故障, IR=内圈, OR=外圈, C=复合
    parts = filename.replace(".npy", "").split("-")
    name_part = parts[0]
    channel = parts[1] if len(parts) > 1 else "X"

    if "_N_" in name_part:
        return {"label": "healthy", "fault": None, "channel": channel}
    elif "_B_" in name_part:
        return {"label": "ball", "fault": "ball", "channel": channel}
    elif "_IR_" in name_part:
        return {"label": "inner", "fault": "inner", "channel": channel}
    elif "_OR_" in name_part:
        return {"label": "outer", "fault": "outer", "channel": channel}
    elif "_C_" in name_part:
        return {"label": "composite", "fault": "composite", "channel": channel}
    return {"label": "unknown", "fault": None, "channel": channel}


def classify_cw(filename: str) -> dict:
    """分类 CW 文件: healthy/inner/outer"""
    name = filename.replace(".npy", "")
    parts = name.split("-")
    health_state = parts[0]  # H/I/O
    speed_mode = parts[1] if len(parts) > 1 else "A"
    seq = parts[2] if len(parts) > 2 else "1"

    if health_state == "H":
        return {"label": "healthy", "fault": None, "speed_mode": speed_mode, "seq": seq}
    elif health_state == "I":
        return {"label": "inner", "fault": "inner", "speed_mode": speed_mode, "seq": seq}
    elif health_state == "O":
        return {"label": "outer", "fault": "outer", "speed_mode": speed_mode, "seq": seq}
    return {"label": "unknown", "fault": None, "speed_mode": speed_mode, "seq": seq}


def classify_wtgearbox(filename: str) -> dict:
    """分类 WTgearbox 文件: healthy/break/missing/crack/wear"""
    # 文件格式: {故障类别}_{故障子类}_{转速}-c{通道}.npy
    name = filename.replace(".npy", "")
    parts = name.split("-")
    main_part = parts[0]
    channel_part = parts[1] if len(parts) > 1 else "c1"

    fault_parts = main_part.split("_")
    category = fault_parts[0]  # He/Br/Mi/Rc/We

    if category == "He":
        return {"label": "healthy", "fault": None, "channel": channel_part}
    elif category == "Br":
        return {"label": "break", "fault": "break", "channel": channel_part}
    elif category == "Mi":
        return {"label": "missing", "fault": "missing", "channel": channel_part}
    elif category == "Rc":
        return {"label": "crack", "fault": "crack", "channel": channel_part}
    elif category == "We":
        return {"label": "wear", "fault": "wear", "channel": channel_part}
    return {"label": "unknown", "fault": None, "channel": channel_part}


# ═══════════════════════════════════════════════════════════
# 诊断引擎运行
# ═══════════════════════════════════════════════════════════

def run_diagnosis(signal: np.ndarray, bearing_params: dict = None,
                  gear_teeth: dict = None, rot_freq: float = None) -> dict:
    """运行诊断引擎并返回结果"""
    engine = DiagnosisEngine(
        strategy="advanced",
        bearing_method="ensemble",
        gear_method="ensemble",
        denoise_method="wavelet",
        bearing_params=bearing_params,
        gear_teeth=gear_teeth,
    )
    result = engine.analyze_research_ensemble(
        signal, SAMPLE_RATE, rot_freq=rot_freq, profile="benchmark",
    )
    return result


# ═══════════════════════════════════════════════════════════
# 评估统计
# ═══════════════════════════════════════════════════════════

def compute_stats(results: dict) -> dict:
    """计算评估统计"""
    stats = {}
    for label, scores in results.items():
        if not scores:
            stats[label] = {"count": 0}
            continue
        hs = np.array(scores)
        detection_rate = np.sum(hs < 85) / len(hs)  # health < 85 → warning/fault
        false_alarm_threshold = 85  # health >= 85 → normal
        stats[label] = {
            "count": len(hs),
            "mean": round(np.mean(hs), 1),
            "std": round(np.std(hs), 1),
            "min": int(np.min(hs)),
            "max": int(np.max(hs)),
            "median": int(np.median(hs)),
            "detection_rate": round(detection_rate, 3),
            "normal_rate": round(1.0 - detection_rate, 3),
        }
    return stats


def print_report(dataset_name: str, stats: dict):
    """打印评估报告"""
    print(f"\n{'='*60}")
    print(f"  {dataset_name} 基准评估报告")
    print(f"{'='*60}")

    healthy_stats = stats.get("healthy", {})
    fault_labels = [k for k in stats if k != "healthy" and k != "unknown"]

    print(f"\n  健康数据:")
    if healthy_stats.get("count", 0) > 0:
        print(f"    样本数: {healthy_stats['count']}")
        print(f"    均值: {healthy_stats['mean']}  标准差: {healthy_stats['std']}")
        print(f"    范围: [{healthy_stats['min']}, {healthy_stats['max']}]")
        print(f"    误报率(warning/fault): {healthy_stats.get('detection_rate', 'N/A')}")

    for label in fault_labels:
        s = stats[label]
        print(f"\n  {label}故障数据:")
        if s.get("count", 0) > 0:
            print(f"    样本数: {s['count']}")
            print(f"    均值: {s['mean']}  标准差: {s['std']}")
            print(f"    范围: [{s['min']}, {s['max']}]")
            print(f"    检出率(warning/fault): {s.get('detection_rate', 'N/A')}")

    # 分离度
    if healthy_stats.get("count", 0) > 0 and fault_labels:
        healthy_mean = healthy_stats.get("mean", 100)
        fault_means = [stats[l].get("mean", 100) for l in fault_labels if stats[l].get("count", 0) > 0]
        if fault_means:
            separation = healthy_mean - min(fault_means)
            print(f"\n  分离度(健康均值-故障最低均值): {round(separation, 1)}")


# ═══════════════════════════════════════════════════════════
# 主评估流程
# ═══════════════════════════════════════════════════════════

def benchmark_hustbear():
    """评估 HUSTbear 数据集"""
    if not os.path.exists(HUSTBEAR_DIR):
        print("[跳过] HUSTbear 数据集路径不存在")
        return None

    results = defaultdict(list)
    files = [f for f in os.listdir(HUSTBEAR_DIR) if f.endswith(".npy")]

    # 只取 X 通道（避免同设备重复计算）
    x_files = [f for f in files if f.endswith("-X.npy")]

    for fname in x_files:
        info = classify_hustbear(fname)
        if info["label"] == "unknown":
            continue

        data = np.load(os.path.join(HUSTBEAR_DIR, fname))
        # 截断到 5 秒
        max_samples = SAMPLE_RATE * 5
        if len(data) > max_samples:
            data = data[:max_samples]

        # 估计转频
        rot_freq = estimate_rot_freq_spectrum(data, SAMPLE_RATE)

        result = run_diagnosis(data, bearing_params=HUSTBEAR_BEARING_PARAMS, rot_freq=rot_freq)
        hs = result.get("health_score", 100)
        results[info["label"]].append(hs)

    stats = compute_stats(results)
    print_report("HUSTbear 轴承数据集", stats)
    return stats


def benchmark_cw():
    """评估 CW 变速轴承数据集"""
    if not os.path.exists(CW_DIR):
        print("[跳过] CW 数据集路径不存在")
        return None

    results = defaultdict(list)
    files = [f for f in os.listdir(CW_DIR) if f.endswith(".npy")]

    for fname in files:
        info = classify_cw(fname)
        if info["label"] == "unknown":
            continue

        data = np.load(os.path.join(CW_DIR, fname))
        max_samples = SAMPLE_RATE * 5
        if len(data) > max_samples:
            data = data[:max_samples]

        # CW 全部为变速工况，估计转频可能不准确
        rot_freq = estimate_rot_freq_spectrum(data, SAMPLE_RATE)

        result = run_diagnosis(data, bearing_params=CW_BEARING_PARAMS, rot_freq=rot_freq)
        hs = result.get("health_score", 100)
        results[info["label"]].append(hs)

    stats = compute_stats(results)
    print_report("CW 变速轴承数据集", stats)
    return stats


def benchmark_wtgearbox():
    """评估 WTgearbox 行星齿轮箱数据集"""
    if not os.path.exists(WTGEARBOX_DIR):
        print("[跳过] WTgearbox 数据集路径不存在")
        return None

    results = defaultdict(list)
    files = [f for f in os.listdir(WTGEARBOX_DIR) if f.endswith(".npy")]

    # 只取 c1 通道
    c1_files = [f for f in files if f.endswith("-c1.npy")]

    for fname in c1_files:
        info = classify_wtgearbox(fname)
        if info["label"] == "unknown":
            continue

        data = np.load(os.path.join(WTGEARBOX_DIR, fname))
        max_samples = SAMPLE_RATE * 5
        if len(data) > max_samples:
            data = data[:max_samples]

        # 提取转速: 文件名中包含转速（如 40 Hz）
        # 格式: {类别}_{子类}_{转速}-c{通道}.npy
        parts = fname.replace(".npy", "").split("-")
        main_parts = parts[0].split("_")
        try:
            speed_hz = float(main_parts[-1])
        except ValueError:
            speed_hz = 30.0  # 默认

        result = run_diagnosis(data, gear_teeth=WTGEARBOX_GEAR_TEETH, rot_freq=speed_hz)
        hs = result.get("health_score", 100)
        results[info["label"]].append(hs)

    stats = compute_stats(results)
    print_report("WTgearbox 行星齿轮箱数据集", stats)
    return stats


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════╗")
    print("║       风机齿轮箱智能故障诊断 — 离线基准评估     ║")
    print("║       HUSTbear + CW + WTgearbox 三数据集       ║")
    print("╚══════════════════════════════════════════════════╝")

    hustbear_stats = benchmark_hustbear()
    cw_stats = benchmark_cw()
    wtgearbox_stats = benchmark_wtgearbox()

    print(f"\n{'='*60}")
    print("  总体评估完成")
    print(f"{'='*60}")