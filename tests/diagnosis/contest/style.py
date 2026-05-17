"""
大创答辩图表统一风格规范

所有 contest 模块生成的图表必须使用此风格，保证视觉一致性。
"""
import matplotlib.pyplot as plt
import matplotlib as mpl

# ── 颜色体系 ──────────────────────────────────────────────────
COLORS = {
    "our_method":    "#E74C3C",   # 红色 — 我们的方法（高亮）
    "baseline":      "#95A5A6",   # 灰色 — baseline 方法
    "best_baseline": "#3498DB",   # 蓝色 — 最强 baseline
    "healthy":       "#2ECC71",   # 绿色 — 健康状态
    "warning":       "#F39C12",   # 橙色 — 预警状态
    "fault":         "#E74C3C",   # 红色 — 故障状态
    "critical":      "#C0392B",   # 深红色 — 严重故障
    "normal_line":   "#27AE60",   # 绿色虚线 — 正常阈值
    "warn_line":     "#F39C12",   # 橙色虚线 — 预警阈值
    "fault_line":    "#E74C3C",   # 红色虚线 — 故障阈值
    "diagonal":      "#BDC3C7",   # 浅灰 — ROC 对角线
}

# ── 混淆矩阵配色 ──────────────────────────────────────────────
CM_COLORS = {
    "correct":   "#2980B9",   # 深蓝 — 正确分类
    "incorrect": "#ECF0F1",   # 浅灰/白 — 错误分类
}

# ── 方法颜色列表（用于多条曲线/柱状图）────────────────────────
METHOD_COLORS = [
    "#95A5A6",   # baseline 灰
    "#3498DB",   # 蓝色
    "#2ECC71",   # 绿色
    "#F39C12",   # 橙色
    "#9B59B6",   # 紫色
    "#1ABC9C",   # 青色
    "#E74C3C",   # 红色 — 我们的 ensemble 方法放在最后
]

# ── 图表尺寸与 DPI ────────────────────────────────────────────
FIGURE_DPI = 300           # 高清，适合 PPT 放大
FIGURE_SIZE = (10, 6)      # 标准宽高
FIGURE_SIZE_WIDE = (14, 6) # 并排对比用
FIGURE_SIZE_TALL = (8, 8)  # 混淆矩阵用
FIGURE_SIZE_GRID = (14, 8) # 多子图用

# ── Matplotlib rcParams ───────────────────────────────────────
RC_PARAMS = {
    "font.family":        "sans-serif",
    "font.sans-serif":    ["SimHei", "Microsoft YaHei", "WenQuanYi Micro Hei",
                           "Noto Sans CJK SC", "PingFang SC", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "font.size":          14,
    "axes.titlesize":     16,
    "axes.labelsize":     14,
    "xtick.labelsize":    12,
    "ytick.labelsize":    12,
    "legend.fontsize":    12,
    "figure.dpi":         FIGURE_DPI,
    "savefig.dpi":        FIGURE_DPI,
    "savefig.format":     "svg",
    "savefig.bbox":       "tight",
    "axes.grid":          True,
    "grid.alpha":         0.3,
    "axes.spines.top":    False,
    "axes.spines.right":  False,
}


def apply_contest_style():
    """应用大创答辩统一风格到 matplotlib"""
    mpl.rcParams.update(RC_PARAMS)


def get_method_color(method_name: str) -> str:
    """根据方法名返回对应颜色

    - 包含 'ensemble'/'融合'/'集成' → 红色（our_method）
    - 否则从 METHOD_COLORS 按索引取
    """
    if any(kw in method_name.lower() for kw in ["ensemble", "融合", "集成", "ds", "综合", "consensus"]):
        return COLORS["our_method"]
    return COLORS["baseline"]


def make_conclusion_title(metric_name: str, baseline_val: float, our_val: float, unit: str = "") -> str:
    """生成结论式标题（直接写结论而非描述）

    例: "多算法集成将轴承故障诊断准确率从 78% 提升至 95%"
    """
    diff = our_val - baseline_val
    sign = "提升" if diff > 0 else "降低"
    abs_diff = abs(diff)
    return f"多算法集成将{metric_name}{sign} {abs_diff:.1f}{unit}（{baseline_val:.1f}{unit} → {our_val:.1f}{unit}）"