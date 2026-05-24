"""
诊断算法全链路测试汇总 — 跨层综合图

从 Layer1~5 的 output/*.json 汇聚全部测试结果，生成一张总览图。

用法:
    python tests/diagnosis/foundation/plot_results.py
"""
import json
from pathlib import Path
import numpy as np

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

OUTPUT_DIR = Path(__file__).parent / "output"
PLOT_DIR = OUTPUT_DIR / "plots"

# ============================================================
# 各层模块名 → 展示名映射 (key 必须与 layer*/output/*.json 文件名一致)
LAYER_MODULES = {
    1: {
        "signal_utils_correctness": "signal_utils\n(信号基元)",
        "vmd_denoise_correctness": "vmd_denoise\n(VMD分解)",
        "health_score_continuous": "health_score_continuous\n(连续扣分)",
        "bearing_sideband": "bearing_sideband\n(边带分析)",
        "channel_consensus": "channel_consensus\n(通道一致性)",
        "recommendation": "recommendation\n(建议生成)",
        "msb_correctness": "msb\n(调制双谱)",
        "savgol_denoise": "savgol_denoise\n(S-G平滑)",
        "wavelet_packet": "wavelet_packet\n(小波包)",
        "bearing_cyclostationary": "bearing_cyclostationary\n(循环平稳)",
        "modality_bearing": "modality_bearing\n(EMD/CEEMDAN/VMD)",
        "sensitive_selector": "sensitive_selector\n(敏感分量)",
        "trend_prediction": "trend_prediction\n(趋势预测)",
        "probability_calibration": "probability_calibration\n(概率校准)",
    },
    2: {
        "features_correctness": "features\n(特征提取)",
        "bearing_correctness": "bearing\n(轴承诊断)",
        "bearing_advanced_correctness": "bearing_advanced\n(高级轴承)",
        "preprocessing_correctness": "preprocessing\n(预处理)",
        "preprocessing_cascade_correctness": "preprocessing_cascade\n(级联去噪)",
        "gear_metrics_correctness": "gear_metrics\n(齿轮指标)",
        "order_tracking_correctness": "order_tracking\n(阶次跟踪)",
        "health_score_correctness": "health_score\n(健康度评分)",
        "rule_based_correctness": "rule_based\n(规则诊断)",
        "planetary_demod_correctness": "planetary_demod\n(行星箱解调)",
    },
    3: {
        "engine_integration": "engine\n(调度器集成)",
        "ensemble_integration": "ensemble\n(集成诊断)",
        "analyzer_integration": "analyzer\n(分析入口)",
        "real_data_integration": "real_data\n(真实数据e2e)",
    },
    4: {
        "engine_deep": "engine_deep\n(深层逻辑)",
        "engine_deep_real": "engine_deep_real\n(真实数据深层)",
    },
    5: {
        "ensemble_helpers": "ensemble_helpers\n(集成辅助)",
        "analyzer_helpers": "analyzer_helpers\n(分析辅助)",
        "helpers_real": "helpers_boundary\n(边界覆盖)",
    },
}

# 颜色语义
COLOR_PASS = '#52C41A'
COLOR_FAIL = '#FF4D4F'
COLOR_WARN = '#FAAD14'
COLOR_GT = '#B0B0B0'
COLOR_EST = '#165DFF'
COLOR_LAYER_BG = {
    1: '#E8F5E9',  # 浅绿
    2: '#E3F2FD',  # 浅蓝
    3: '#FFF3E0',  # 浅橙
    4: '#F3E5F5',  # 浅紫
    5: '#FFEBEE',  # 浅红
}


def _collect_layer_stats(layer_dir: Path) -> dict:
    """收集单个 layer 的测试通过统计"""
    result = {"total": 0, "passed": 0, "failed": 0, "modules": {}}
    layer_output = layer_dir / "output"
    if not layer_output.exists():
        return result
    for json_file in sorted(layer_output.glob("*.json")):
        module_name = json_file.stem
        if module_name == "plots":
            continue
        try:
            data = json.loads(json_file.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        m_total, m_passed, m_failed = _count_tests(data)
        if m_total > 0:
            result["modules"][module_name] = {
                "total": m_total, "passed": m_passed, "failed": m_failed,
                "rate": m_passed / m_total if m_total else 0,
            }
            result["total"] += m_total
            result["passed"] += m_passed
            result["failed"] += m_failed
    return result


def _count_tests(data) -> tuple:
    """递归统计 JSON 中的测试 total/passed/failed"""
    total, passed, failed = 0, 0, 0
    if isinstance(data, list):
        for item in data:
            t, p, f = _count_tests(item)
            total += t; passed += p; failed += f
    elif isinstance(data, dict):
        if "passed" in data and isinstance(data["passed"], bool):
            total = 1
            if data["passed"]:
                passed = 1
            else:
                failed = 1
        for v in data.values():
            t, p, f = _count_tests(v)
            total += t; passed += p; failed += f
    return total, passed, failed


def _gather_stats():
    """收集所有层统计数据，返回 layer_summaries"""
    foundation_dir = Path(__file__).parent
    layer_summaries = {}
    for layer_num in range(1, 6):
        layer_dir = foundation_dir / f"layer{layer_num}"
        stats = _collect_layer_stats(layer_dir)
        total = stats["total"]
        passed = stats["passed"]
        rate = passed / total if total > 0 else 0
        layer_summaries[layer_num] = {
            "total": total, "passed": passed, "failed": stats["failed"],
            "rate": rate, "modules": stats["modules"],
        }
    return layer_summaries


def plot_cross_layer_layers():
    """图1：各层通过/失败 堆叠柱状图"""
    layer_summaries = _gather_stats()
    if all(s["total"] == 0 for s in layer_summaries.values()):
        return

    global_total = sum(s["total"] for s in layer_summaries.values())
    global_passed = sum(s["passed"] for s in layer_summaries.values())
    global_failed = sum(s["failed"] for s in layer_summaries.values())

    layer_labels = ['Layer 1\n信号基元', 'Layer 2\n特征提取', 'Layer 3\n集成调度', 'Layer 4\n深层逻辑', 'Layer 5\n辅助函数']

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.set_title(f"各层测试通过/失败统计  (共 {global_total} 项)", fontsize=13, fontweight='bold')

    x = np.arange(5)
    width = 0.55
    passed_vals = [layer_summaries[i+1]["passed"] for i in range(5)]
    failed_vals = [layer_summaries[i+1]["failed"] for i in range(5)]
    totals_vals = [layer_summaries[i+1]["total"] for i in range(5)]
    rates_vals = [layer_summaries[i+1]["rate"] for i in range(5)]

    ax.bar(x, passed_vals, width, color=COLOR_PASS, label='通过', edgecolor='white', linewidth=0.8)
    ax.bar(x, failed_vals, width, bottom=passed_vals, color=COLOR_FAIL, label='失败', edgecolor='white', linewidth=0.8)

    for i, (rate, total) in enumerate(zip(rates_vals, totals_vals)):
        color = COLOR_PASS if rate >= 0.9 else (COLOR_WARN if rate >= 0.7 else COLOR_FAIL)
        ax.text(i, total + max(totals_vals) * 0.03, f"{rate*100:.0f}%",
                ha='center', fontsize=14, fontweight='bold', color=color)
        ax.text(i, total + max(totals_vals) * 0.12, f"({passed_vals[i]}/{total})",
                ha='center', fontsize=9, color='#555')

    ax.set_xticks(x)
    ax.set_xticklabels(layer_labels, fontsize=10)
    ax.set_ylabel("测试项数", fontsize=11)
    ax.legend(loc='upper right', fontsize=10)
    ax.set_ylim(0, max(totals_vals) * 1.25)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "cross_layer_summary.svg")
    plt.close(fig)
    print(f"  [OK] cross_layer_summary.svg (各层: {global_total} 项, {global_passed} 通过, {global_failed} 失败)")


def plot_cross_layer_modules():
    """图2：各模块通过率 水平条形图"""
    layer_summaries = _gather_stats()
    layer_colors = ['#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#F44336']

    all_modules = []
    for layer_num in range(1, 6):
        s = layer_summaries[layer_num]
        modules = LAYER_MODULES.get(layer_num, {})
        for json_name, display_name in modules.items():
            m = s["modules"].get(json_name)
            if m:
                all_modules.append({
                    "label": display_name.replace('\n', ' '),
                    "layer": layer_num,
                    "rate": m["rate"],
                    "total": m["total"],
                    "passed": m["passed"],
                    "failed": m["failed"],
                })

    if not all_modules:
        return

    all_modules.sort(key=lambda m: (m["layer"], -m["rate"]))
    n = len(all_modules)
    mid = (n + 1) // 2
    left_modules = all_modules[:mid]
    right_modules = all_modules[mid:]

    # 16:9 布局：左右两个子图
    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(16, 9))
    fig.suptitle("各模块测试通过率", fontsize=14, fontweight='bold', y=0.98)

    for ax, modules, side in [(ax_l, left_modules, " (1/2)"), (ax_r, right_modules, " (2/2)")]:
        _plot_module_bars(ax, modules, layer_colors, side)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(PLOT_DIR / "cross_layer_modules.svg")
    plt.close(fig)
    print(f"  [OK] cross_layer_modules.svg ({n} 个模块)")


def _plot_module_bars(ax, modules, layer_colors, side_label):
    """在单个轴上绘制模块通过率条形图"""
    n = len(modules)
    y_pos = list(range(n))
    labels = [m["label"] for m in modules]
    rates = [m["rate"] for m in modules]
    layer_nums = [m["layer"] for m in modules]

    colors = [layer_colors[ln-1] for ln in layer_nums]
    ax.barh(y_pos, rates, height=0.7, color=colors, alpha=0.85, edgecolor='white', linewidth=0.5)

    for i, m in enumerate(modules):
        r = m["rate"]
        ax.text(r + 0.02, i, f"{r*100:.0f}% ({m['passed']}/{m['total']})",
                va='center', fontsize=9, color='#333')

    ax.set_yticks(y_pos)
    ax.set_yticklabels([f"[L{ln}] {lbl}" for ln, lbl in zip(layer_nums, labels)], fontsize=9)
    ax.set_xlim(0, 1.2)
    ax.set_xlabel("通过率")
    ax.set_title(f"模块通过率{side_label}", fontsize=12, fontweight='bold')
    ax.axvline(x=1.0, color=COLOR_PASS, linestyle='--', linewidth=1, alpha=0.6)
    ax.axvline(x=0.9, color='#ccc', linestyle='--', linewidth=0.8, alpha=0.5)
    ax.invert_yaxis()
    ax.grid(axis='x', alpha=0.2)

    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, label=f"L{i+1}") for i, c in enumerate(layer_colors)]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=7, ncol=5)


def _plot_module_detail(ax, layer_summaries, title):
    """绘制模块级通过率水平条形图"""
    all_modules = []
    for layer_num in range(1, 6):
        s = layer_summaries[layer_num]
        modules = LAYER_MODULES.get(layer_num, {})
        for json_name, display_name in modules.items():
            m = s["modules"].get(json_name)
            if m:
                all_modules.append({
                    "label": display_name,
                    "layer": layer_num,
                    "rate": m["rate"],
                    "total": m["total"],
                    "passed": m["passed"],
                    "failed": m["failed"],
                })

    if not all_modules:
        ax.text(0.5, 0.5, "无模块数据", ha='center', va='center', transform=ax.transAxes,
                fontsize=12, color='gray')
        ax.axis('off')
        return

    # 按通过率排序（低通过率在上）
    all_modules.sort(key=lambda x: x["rate"])

    n = len(all_modules)
    y_positions = list(range(n))
    labels = [m["label"] for m in all_modules]
    rates = [m["rate"] for m in all_modules]
    totals = [m["total"] for m in all_modules]
    passed_list = [m["passed"] for m in all_modules]

    # 颜色映射
    colors = []
    for m in all_modules:
        if m["failed"] == 0:
            colors.append(COLOR_PASS)
        elif m["passed"] == 0:
            colors.append(COLOR_FAIL)
        else:
            colors.append(COLOR_WARN)

    bars = ax.barh(y_positions, rates, height=0.7, color=colors, alpha=0.85, edgecolor='white', linewidth=0.5)

    # 在每个条右侧标注
    for i, (r, t, p) in enumerate(zip(rates, totals, passed_list)):
        label_color = COLOR_PASS if r >= 0.9 else (COLOR_WARN if r >= 0.7 else COLOR_FAIL)
        ax.text(r + 0.02, i, f"{r*100:.0f}% ({p}/{t})", va='center', fontsize=8,
                color=label_color, fontweight='bold')

    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlim(0, 1.25)
    ax.set_xlabel("通过率")
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.axvline(x=0.9, color='#ccc', linestyle='--', alpha=0.5, linewidth=0.8)
    ax.axvline(x=0.7, color='#eee', linestyle='--', alpha=0.5, linewidth=0.8)
    ax.invert_yaxis()
    ax.grid(axis='x', alpha=0.2)

    # 图例
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=COLOR_PASS, label='全部通过'),
        Patch(facecolor=COLOR_WARN, label='部分失败'),
        Patch(facecolor=COLOR_FAIL, label='全部失败'),
        Patch(facecolor='none', edgecolor='#ccc', label='90% 基准线'),
    ]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=7, ncol=2)


def _plot_failure_list(ax, all_layers):
    """列出所有失败测试项"""
    failures = []
    for layer_num in range(1, 6):
        stats = all_layers[layer_num]
        modules = LAYER_MODULES.get(layer_num, {})
        for json_name, display_name in modules.items():
            m = stats["modules"].get(json_name)
            if m and m["failed"] > 0:
                # 尝试读取具体失败项
                layer_dir = Path(__file__).parent / f"layer{layer_num}"
                json_path = layer_dir / "output" / f"{json_name}.json"
                failed_tests = []
                if json_path.exists():
                    try:
                        data = json.loads(json_path.read_text(encoding='utf-8'))
                        failed_tests = _collect_failed_names(data)
                    except Exception:
                        pass
                failures.append({
                    "layer": layer_num,
                    "module": display_name.replace('\n', ' '),
                    "total": m["total"],
                    "passed": m["passed"],
                    "failed": m["failed"],
                    "details": failed_tests[:5],  # 最多显示5个
                })

    if not failures:
        ax.text(0.5, 0.5, "*** 所有测试全部通过! ***", ha='center', va='center',
                transform=ax.transAxes, fontsize=16, fontweight='bold', color=COLOR_PASS)
        ax.axis('off')
        return

    ax.axis('off')
    ax.set_xlim(0, 10)
    ax.set_ylim(0, max(len(failures) * 2.5 + 1, 8))

    ax.text(5, len(failures) * 2.5 + 1.5, f"失败项清单 ({len(failures)} 个模块有失败)",
            ha='center', fontsize=11, fontweight='bold', color=COLOR_FAIL)

    y = len(failures) * 2.5
    for f in failures:
        # 模块名
        ax.text(0.3, y + 0.8,
                f"[L{f['layer']}] {f['module']}", fontsize=9, fontweight='bold',
                color='#333', va='top')
        # 统计
        ax.text(0.3, y + 0.2,
                f"  {f['passed']}/{f['total']} 通过, {f['failed']} 失败",
                fontsize=8, color=COLOR_FAIL, va='top')

        # 失败项详情
        if f["details"]:
            detail_text = "  [X] " + "\n  [X] ".join(f["details"])
            ax.text(0.3, y - 0.3, detail_text, fontsize=7, color='#888', va='top')
        y -= 2.5

    ax.text(0.3, y, "提示：从上往下按层级排查，先修 Layer 1 再修上层",
            fontsize=8, color='#aaa', fontstyle='italic')


def _collect_failed_names(data, prefix="") -> list:
    """递归收集失败测试名"""
    names = []
    if isinstance(data, list):
        for item in data:
            names.extend(_collect_failed_names(item, prefix))
    elif isinstance(data, dict):
        if data.get("passed") is False:
            test_name = data.get("test", "")
            if test_name:
                names.append(test_name)
        for k, v in data.items():
            if k != "passed" and k != "test":
                names.extend(_collect_failed_names(v, prefix))
    return names


def main():
    if not HAS_MPL:
        print("matplotlib 未安装，跳过绘图")
        return

    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    print("诊断算法全链路测试汇总")
    print("=" * 50)

    plot_cross_layer_layers()
    plot_cross_layer_modules()

    print(f"\n图表保存在: {PLOT_DIR}")


if __name__ == "__main__":
    main()
