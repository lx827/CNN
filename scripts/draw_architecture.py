"""
绘制系统架构图，用于论文
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

# 设置中文字体
plt.rcParams['font.family'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(1, 1, figsize=(14, 9.2))
ax.set_xlim(0, 14)
ax.set_ylim(0, 9.2)
ax.axis('off')

# 定义配色方案（学术风格）
COLORS = {
    'web_bg': '#E3F2FD',
    'web_border': '#1976D2',
    'web_title': '#0D47A1',
    'cloud_bg': '#FFF8E1',
    'cloud_border': '#F9A825',
    'cloud_title': '#E65100',
    'edge_bg': '#E8F5E9',
    'edge_border': '#43A047',
    'edge_title': '#1B5E20',
    'db_bg': '#F3E5F5',
    'db_border': '#8E24AA',
    'db_title': '#4A148C',
    'text_main': '#212121',
    'text_sub': '#424242',
    'arrow': '#546E7A',
    'arrow_ws': '#D84315',
}

def draw_rounded_box(ax, x, y, w, h, radius, facecolor, edgecolor, linewidth=1.5, alpha=1.0):
    box = FancyBboxPatch((x, y), w, h,
                         boxstyle=f"round,pad=0,rounding_size={radius}",
                         facecolor=facecolor, edgecolor=edgecolor,
                         linewidth=linewidth, alpha=alpha, zorder=2)
    ax.add_patch(box)
    return box

# ==================== 三层大框 ====================
# 用户层
y_web = 6.95
h_web = 1.95
draw_rounded_box(ax, 0.3, y_web, 13.4, h_web, 0.15,
                 COLORS['web_bg'], COLORS['web_border'], linewidth=2.0)
ax.text(7.0, y_web + h_web - 0.35, '用户层 (Web)', ha='center', va='center',
        fontsize=18, fontweight='bold', color=COLORS['web_title'])

# 云端
y_cloud = 3.0
h_cloud = 3.45
draw_rounded_box(ax, 0.3, y_cloud, 13.4, h_cloud, 0.15,
                 COLORS['cloud_bg'], COLORS['cloud_border'], linewidth=2.0)
ax.text(7.0, y_cloud + h_cloud - 0.35, '云端 (Cloud)', ha='center', va='center',
        fontsize=18, fontweight='bold', color=COLORS['cloud_title'])

# 边端
y_edge = 0.6
h_edge = 1.9
draw_rounded_box(ax, 0.3, y_edge, 13.4, h_edge, 0.15,
                 COLORS['edge_bg'], COLORS['edge_border'], linewidth=2.0)
ax.text(7.0, y_edge + h_edge - 0.35, '边端 (Edge)', ha='center', va='center',
        fontsize=18, fontweight='bold', color=COLORS['edge_title'])

# ==================== 用户层内容 ====================
draw_rounded_box(ax, 0.9, y_web + 0.22, 12.2, 1.25, 0.1,
                 '#FFFFFF', COLORS['web_border'], linewidth=1.2)
ax.text(7.0, y_web + 1.14, 'Vue 3 前端 (wind-turbine-diagnosis)', ha='center', va='center',
        fontsize=15, fontweight='bold', color=COLORS['web_title'])

# 功能模块标签
modules = [
    ('设备总览\nDashboard', 1.8),
    ('实时监测\nMonitor', 3.6),
    ('数据查看\nDataView', 5.4),
    ('故障诊断\nDiagnosis', 7.2),
    ('告警管理\nAlarm', 9.0),
    ('边端配置\nSettings', 10.8),
]
for label, x in modules:
    draw_rounded_box(ax, x - 0.68, y_web + 0.35, 1.36, 0.58, 0.08,
                     '#BBDEFB', COLORS['web_border'], linewidth=0.8)
    ax.text(x, y_web + 0.64, label, ha='center', va='center',
            fontsize=10.2, color=COLORS['text_main'])

# ==================== 云端内容 ====================
# 左侧：后端服务描述
draw_rounded_box(ax, 0.85, y_cloud + 0.3, 4.9, 2.55, 0.1,
                 '#FFFFFF', COLORS['cloud_border'], linewidth=1.2)
ax.text(3.3, y_cloud + 2.45, 'Python + FastAPI 后端服务', ha='center', va='center',
        fontsize=13.5, fontweight='bold', color=COLORS['cloud_title'])

ax.text(1.18, y_cloud + 1.97, '▸ API 层', ha='left', va='center',
        fontsize=11.5, fontweight='bold', color=COLORS['text_sub'])
ax.text(1.5, y_cloud + 1.62, '提供 RESTful 接口与\nWebSocket 实时推送', ha='left', va='center',
        fontsize=10.0, color=COLORS['text_sub'])

ax.text(1.18, y_cloud + 1.12, '▸ 数据接入层', ha='left', va='center',
        fontsize=11.5, fontweight='bold', color=COLORS['text_sub'])
ax.text(1.5, y_cloud + 0.79, '接收边端上传的\n压缩振动数据', ha='left', va='center',
        fontsize=10.0, color=COLORS['text_sub'])

ax.text(1.18, y_cloud + 0.33, '▸ 分析引擎', ha='left', va='center',
        fontsize=11.5, fontweight='bold', color=COLORS['text_sub'])
ax.text(1.5, y_cloud + 0.06, '多算法集成诊断 /\n特征提取 / 告警生成', ha='left', va='center',
        fontsize=10.0, color=COLORS['text_sub'])

# 中间：分析引擎详细流程框
draw_rounded_box(ax, 5.95, y_cloud + 0.3, 4.15, 2.55, 0.1,
                 '#FFF3E0', COLORS['cloud_border'], linewidth=1.0)
ax.text(8.03, y_cloud + 2.45, '分析引擎执行流程', ha='center', va='center',
        fontsize=13.2, fontweight='bold', color=COLORS['cloud_title'])

steps = [
    '1. 读取最近 60 s 传感器数据',
    '2. 调用诊断引擎（Ensemble / 单方法）',
    '3. 输出健康度 / 故障概率 / IMF 能量',
    '4. 计算振动特征（RMS / 峰值 / 峭度）',
    '5. 特征超阈值后生成通道级振动告警',
    '6. 诊断异常后生成设备级诊断告警',
]
for i, step in enumerate(steps):
    ax.text(6.14, y_cloud + 1.97 - i * 0.34, step, ha='left', va='center',
            fontsize=9.55, color=COLORS['text_sub'])

# 右侧：数据库框
draw_rounded_box(ax, 10.55, y_cloud + 0.3, 3.35, 2.55, 0.1,
                 COLORS['db_bg'], COLORS['db_border'], linewidth=1.2)
ax.text(12.22, y_cloud + 2.45, '数据库 (SQLite)', ha='center', va='center',
        fontsize=13.5, fontweight='bold', color=COLORS['db_title'])

tables = [
    ('devices', '设备信息表'),
    ('sensor_data', '传感器原始数据表'),
    ('diagnosis', '诊断结果表'),
    ('alarms', '告警记录表'),
]
for i, (name, desc) in enumerate(tables):
    y_pos = y_cloud + 1.95 - i * 0.48
    draw_rounded_box(ax, 10.82, y_pos - 0.14, 2.8, 0.29, 0.05,
                     '#FFFFFF', COLORS['db_border'], linewidth=0.6)
    ax.text(12.22, y_pos, f'{name}  —  {desc}', ha='center', va='center',
            fontsize=8.7, color=COLORS['text_sub'])

# ==================== 边端内容 ====================
draw_rounded_box(ax, 0.9, y_edge + 0.22, 12.2, 1.25, 0.1,
                 '#FFFFFF', COLORS['edge_border'], linewidth=1.2)
ax.text(7.0, y_edge + 1.12, 'Python 采集脚本 (edge_client.py)', ha='center', va='center',
        fontsize=15, fontweight='bold', color=COLORS['edge_title'])

edge_modules = [
    ('信号采集', '读取真实 .npy 振动数据\n或生成模拟信号'),
    ('数据压缩', '峰值保持降采样\nmsgpack + zlib'),
    ('数据上传', 'HTTP POST 上传\n到云端数据接入层'),
]
for i, (title, desc) in enumerate(edge_modules):
    x = 2.5 + i * 4.0
    draw_rounded_box(ax, x - 1.45, y_edge + 0.34, 2.9, 0.58, 0.08,
                     '#C8E6C9', COLORS['edge_border'], linewidth=0.8)
    ax.text(x, y_edge + 0.76, title, ha='center', va='center',
            fontsize=10.8, fontweight='bold', color=COLORS['edge_title'])
    ax.text(x, y_edge + 0.48, desc, ha='center', va='center',
            fontsize=8.9, color=COLORS['text_sub'])

# ==================== 层间箭头 ====================
# Web -> Cloud
ax.annotate('', xy=(7.0, y_cloud + h_cloud), xytext=(7.0, y_web),
            arrowprops=dict(arrowstyle='->', color=COLORS['arrow'], lw=2.2),
            zorder=3)
ax.text(7.0 + 0.3, (y_web + y_cloud + h_cloud) / 2, 'HTTP / WebSocket',
        ha='left', va='center', fontsize=10.2, fontweight='bold',
        color=COLORS['arrow_ws'],
        bbox=dict(boxstyle='round,pad=0.28', facecolor='#FFFFFF', edgecolor=COLORS['arrow_ws'], alpha=0.95, linewidth=1.2))

# Cloud <-> DB
ax.annotate('', xy=(10.2, y_cloud + 1.7), xytext=(9.9, y_cloud + 1.7),
            arrowprops=dict(arrowstyle='<->', color=COLORS['db_border'], lw=1.8),
            zorder=3)
ax.text(10.05, y_cloud + 2.0, 'SQL', ha='center', va='center', fontsize=9.6,
        color=COLORS['db_title'], fontweight='bold',
        bbox=dict(boxstyle='round,pad=0.18', facecolor='white', edgecolor='none', alpha=0.9))

# Edge -> Cloud
ax.annotate('', xy=(7.0, y_edge + h_edge), xytext=(7.0, y_cloud),
            arrowprops=dict(arrowstyle='->', color=COLORS['arrow'], lw=2.2),
            zorder=3)
ax.text(7.0 + 0.3, (y_cloud + y_edge + h_edge) / 2, 'HTTP POST',
        ha='left', va='center', fontsize=10.2, fontweight='bold',
        color=COLORS['arrow'],
        bbox=dict(boxstyle='round,pad=0.28', facecolor='#FFFFFF', edgecolor=COLORS['arrow'], alpha=0.95, linewidth=1.2))

plt.tight_layout()
plt.savefig('d:/code/CNN/figures/system_architecture.png', dpi=300, bbox_inches='tight',
            facecolor='white', edgecolor='none')
plt.savefig('d:/code/CNN/figures/system_architecture.svg', bbox_inches='tight',
            facecolor='white', edgecolor='none')
plt.savefig('d:/code/CNN/figures/system_architecture.pdf', bbox_inches='tight',
            facecolor='white', edgecolor='none')
print("架构图已保存到 d:/code/CNN/figures/")
print("  - system_architecture.png (300 DPI)")
print("  - system_architecture.svg (矢量图)")
print("  - system_architecture.pdf (矢量图)")
