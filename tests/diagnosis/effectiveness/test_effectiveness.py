"""
轴承诊断算法有效性测试

测试数据集：
  - CW 轴承数据集：健康(H)、内圈故障(I)、外圈故障(O)
  - WTgearbox 齿轮箱数据集：健康(He)、断齿(Br)、缺齿(Mi)、齿根裂纹(Rc)、磨损(We)

测试场景：
  1. 仅轴承参数 → 应只做轴承诊断，跳过齿轮
  2. 仅齿轮参数 → 应只做齿轮诊断，跳过轴承
  3. 都有参数 → 综合
  4. 都无参数 → 统计指标

指标：
  - 检出率：故障数据被正确检出为 warning/fault
  - 误诊率：健康数据被误判为 warning/fault
  - 健康度分布：正常数据应 ≥85，故障数据应 ≤75
"""
import os
import sys
import glob
import numpy as np

# 添加 cloud 模块路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'cloud'))

from app.services.diagnosis.ensemble import run_research_ensemble

# ============ 参数配置 ============
CW_BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 39.04, "alpha": 0}
WTGEAR_GEAR_TEETH = {"sun": 28, "ring": 100, "planet": 36, "planet_count": 4, "input": 28}
NO_PARAMS = None

CW_DATA_DIR = r"D:\code\CNN\CW\down8192_CW"
WTGEAR_DATA_DIR = r"D:\code\wavelet_study\dataset\WTgearbox\down8192"
FS = 8192  # 采样率


def load_npy_files(data_dir):
    """扫描数据目录，返回 {prefix: {ch: path}}"""
    groups = {}
    for fpath in sorted(glob.glob(os.path.join(data_dir, "*.npy"))):
        fname = os.path.basename(fpath)
        name_no_ext = fname.replace(".npy", "")
        parts = name_no_ext.split("-")
        ch = parts[-1]
        prefix = "-".join(parts[:-1])
        groups.setdefault(prefix, {})[ch] = fpath
    return groups


def load_signal(groups, prefix, ch_key=None):
    """加载指定工况的信号数据（取第一个通道）"""
    if prefix not in groups:
        return None
    ch_data = groups[prefix]
    # 取第一个通道
    first_ch = sorted(ch_data.keys())[0]
    data = np.load(ch_data[first_ch])
    # 截断到5秒
    max_samples = FS * 5
    if len(data) > max_samples:
        data = data[:max_samples]
    return data


def test_dataset(name, data_dir, prefix_filter, bearing_params, gear_teeth, expected_normal=True):
    """测试某个数据源的诊断结果"""
    groups = load_npy_files(data_dir)
    candidates = [p for p in groups.keys() if p.startswith(prefix_filter)]
    if not candidates:
        print(f"  ❌ 无匹配前缀 {prefix_filter}")
        return

    results = []
    for prefix in candidates:
        signal = load_signal(groups, prefix)
        if signal is None:
            continue
        try:
            result = run_research_ensemble(
                signal, FS,
                bearing_params=bearing_params,
                gear_teeth=gear_teeth,
                profile="runtime",
            )
            hs = result["health_score"]
            status = result["status"]
            skip_b = result["ensemble"]["skip_bearing"]
            skip_g = result["ensemble"]["skip_gear"]
            bearing_conf = result["ensemble"]["bearing_confidence"]
            gear_conf = result["ensemble"]["gear_confidence"]
            fault_label = result["fault_label"]
            results.append({
                "prefix": prefix, "hs": hs, "status": status,
                "skip_b": skip_b, "skip_g": skip_g,
                "bearing_conf": bearing_conf, "gear_conf": gear_conf,
                "fault_label": fault_label,
            })
        except Exception as e:
            print(f"  ❌ {prefix}: 异常 {e}")

    # 统计
    normal_count = sum(1 for r in results if r["status"] == "normal")
    warning_count = sum(1 for r in results if r["status"] == "warning")
    fault_count = sum(1 for r in results if r["status"] == "fault")
    abnormal_count = warning_count + fault_count

    if expected_normal:
        # 健康数据：期望全部 normal
        false_positive_rate = abnormal_count / len(results) if results else 0
        avg_hs = sum(r["hs"] for r in results) / len(results) if results else 0
        print(f"\n{'='*60}")
        print(f"【{name}】健康数据测试 (期望: 全部 normal)")
        print(f"  样本数: {len(results)}, normal={normal_count}, warning={warning_count}, fault={fault_count}")
        print(f"  误诊率: {false_positive_rate:.1%}")
        print(f"  平均健康度: {avg_hs:.1f}")
        print(f"  skip_bearing={results[0]['skip_b'] if results else '-'}, skip_gear={results[0]['skip_g'] if results else '-'}")
        for r in results:
            marker = "✅" if r["status"] == "normal" else "⚠️" if r["status"] == "warning" else "❌"
            print(f"  {marker} {r['prefix']}: hs={r['hs']}, status={r['status']}, "
                  f"bearing={r['bearing_conf']:.2f}, gear={r['gear_conf']:.2f}, label={r['fault_label']}")
    else:
        # 故障数据：期望检出为 warning/fault
        detection_rate = abnormal_count / len(results) if results else 0
        avg_hs = sum(r["hs"] for r in results) / len(results) if results else 0
        print(f"\n{'='*60}")
        print(f"【{name}】故障数据测试 (期望: warning/fault)")
        print(f"  样本数: {len(results)}, normal={normal_count}, warning={warning_count}, fault={fault_count}")
        print(f"  检出率: {detection_rate:.1%}")
        print(f"  平均健康度: {avg_hs:.1f}")
        print(f"  skip_bearing={results[0]['skip_b'] if results else '-'}, skip_gear={results[0]['skip_g'] if results else '-'}")
        for r in results:
            marker = "✅" if r["status"] != "normal" else "❌"
            print(f"  {marker} {r['prefix']}: hs={r['hs']}, status={r['status']}, "
                  f"bearing={r['bearing_conf']:.2f}, gear={r['gear_conf']:.2f}, label={r['fault_label']}")


# ============ 测试执行 ============
print("=" * 60)
print("轴承诊断算法有效性测试")
print("=" * 60)

# --- 场景1：CW 轴承数据集 + 仅轴承参数 ---
# H（健康）→ 期望 normal，误诊率应低
test_dataset("CW-健康(H)+仅轴承参数", CW_DATA_DIR, "H", CW_BEARING_PARAMS, NO_PARAMS, expected_normal=True)
# I（内圈故障）→ 期望检出
test_dataset("CW-内圈(I)+仅轴承参数", CW_DATA_DIR, "I", CW_BEARING_PARAMS, NO_PARAMS, expected_normal=False)
# O（外圈故障）→ 期望检出
test_dataset("CW-外圈(O)+仅轴承参数", CW_DATA_DIR, "O", CW_BEARING_PARAMS, NO_PARAMS, expected_normal=False)

# --- 场景2：WTgearbox 齿轮箱数据集 + 仅齿轮参数 ---
# He（健康）→ 期望 normal
test_dataset("WTgear-健康(He)+仅齿轮参数", WTGEAR_DATA_DIR, "He", NO_PARAMS, WTGEAR_GEAR_TEETH, expected_normal=True)
# Br（断齿）→ 期望检出
test_dataset("WTgear-断齿(Br)+仅齿轮参数", WTGEAR_DATA_DIR, "Br", NO_PARAMS, WTGEAR_GEAR_TEETH, expected_normal=False)
# Mi（缺齿）→ 期望检出
test_dataset("WTgear-缺齿(Mi)+仅齿轮参数", WTGEAR_DATA_DIR, "Mi", NO_PARAMS, WTGEAR_GEAR_TEETH, expected_normal=False)
# Rc（齿根裂纹）→ 期望检出
test_dataset("WTgear-齿根裂纹(Rc)+仅齿轮参数", WTGEAR_DATA_DIR, "Rc", NO_PARAMS, WTGEAR_GEAR_TEETH, expected_normal=False)
# We（磨损）→ 期望检出
test_dataset("WTgear-磨损(We)+仅齿轮参数", WTGEAR_DATA_DIR, "We", NO_PARAMS, WTGEAR_GEAR_TEETH, expected_normal=False)

# --- 场景3：CW 健康数据 + 无参数（统计指标）---
test_dataset("CW-健康(H)+无参数(统计)", CW_DATA_DIR, "H", NO_PARAMS, NO_PARAMS, expected_normal=True)

# --- 场景4：CW 内圈故障 + 无参数（统计指标）---
test_dataset("CW-内圈(I)+无参数(统计)", CW_DATA_DIR, "I", NO_PARAMS, NO_PARAMS, expected_normal=False)

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)