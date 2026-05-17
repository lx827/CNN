# 后端代码文档索引

> **文档用途**：按 `cloud/app/` 目录树结构，每个 `.py` 文件对应一个 `.md` 文档，方便 AI 快速查阅定位。
> **目录结构**：与源码完全一致。

---

## 目录结构

```
docs/backend/app/
├── __init__.md
├── main.md                  ← FastAPI 应用入口
├── lifespan.md              ← 应用生命周期管理
├── startup.md               ← 数据库初始化
├── middleware.md            ← 中间件配置
├── database.md              ← 数据库连接
├── models.md                ← SQLAlchemy 数据模型
├── schemas.md               ← Pydantic 数据模型
│
├── api/                     ← API 路由层
│   ├── __init__.md
│   ├── auth.md              ← 认证接口
│   ├── dashboard.md         ← 设备总览
│   ├── alarms.md            ← 告警管理
│   ├── collect.md           ← 采集任务
│   ├── ingest.md            ← 边端数据接入
│   ├── monitor.md           ← 实时监测
│   ├── system.md            ← 系统日志
│   │
│   ├── data_view/           ← 数据查看路由
│   │   ├── __init__.md      ← 路由初始化 + 公共函数
│   │   ├── core.md          ← 设备/批次/原始数据
│   │   ├── spectrum.md      ← FFT/STFT/统计
│   │   ├── envelope.md      ← 包络谱分析
│   │   ├── order.md         ← 阶次跟踪
│   │   ├── cepstrum.md      ← 倒谱分析
│   │   ├── gear.md          ← 齿轮诊断+综合分析+全分析
│   │   ├── research.md      ← 研究级分析
│   │   ├── diagnosis_ops.md ← 诊断缓存操作+重新诊断
│   │   └── export.md        ← CSV 导出
│   │
│   └── devices/             ← 设备管理路由
│       ├── __init__.md
│       ├── core.md          ← 设备 CRUD
│       └── config.md        ← 设备配置
│
├── core/                    ← 核心配置层
│   ├── __init__.md
│   ├── config.py            ← 全局配置
│   ├── memory_log.md        ← 内存日志
│   ├── thresholds.md        ← 全局阈值配置
│   └── websocket.md         ← WebSocket 连接管理器
│
└── services/                ← 服务层
    ├── __init__.md
    ├── analyzer.md          ← 综合分析引擎
    ├── nn_predictor.md      ← 神经网络预留接口
    ├── offline_monitor.md   ← 离线监测
    │
    ├── alarms/              ← 告警服务
    │   ├── __init__.md      ← 统一入口
    │   ├── channel.md       ← 通道级告警
    │   ├── device.md        ← 设备级告警
    │   └── diagnosis.md     ← 诊断结果告警
    │
    └── diagnosis/           ← 诊断服务
        ├── __init__.md
        ├── engine.md        ← 诊断引擎调度器
        ├── ensemble.md      ← 多算法集成诊断
        ├── bearing.md       ← 轴承诊断算法
        ├── health_score.md  ← 健康度评分
        ├── health_score_continuous.md ← 连续衰减扣分
        ├── recommendation.md ← 诊断建议
        ├── preprocessing.md ← 预处理与降噪
        ├── vmd_denoise.md   ← VMD 分解
        ├── emd_denoise.md   ← EMD/CEEMDAN 分解
        ├── features.md      ← 特征提取
        ├── order_tracking.md ← 阶次跟踪算法
        ├── signal_utils.md  ← 信号工具
        ├── rule_based.md    ← 规则诊断（回退）
        ├── wavelet_bearing.md ← 小波轴承分析
        ├── wavelet_packet.md ← 小波包
        ├── savgol_denoise.md ← S-G 平滑
        ├── mckd.md          ← MCKD 解卷积
        ├── bearing_cyclostationary.md ← 轴承循环平稳分析
        ├── bearing_sideband.md ← 轴承边带
        ├── bss.md           ← 盲源分离
        ├── lms_filter.md    ← LMS 自适应滤波
        ├── channel_consensus.md ← 通道共识
        ├── modality_bearing.md ← 模态分解轴承分析
        ├── sensitive_selector.md ← 敏感分量选择
        ├── probability_calibration.md ← 概率校准
        ├── trend_prediction.md ← 趋势预测
        │
        ├── gear/            ← 齿轮诊断
        │   ├── __init__.md  ← 齿轮诊断公共接口
        │   ├── metrics.md   ← 齿轮指标
        │   ├── planetary_demod.md ← 行星齿轮解调
        │   ├── vmd_demod.md ← VMD 齿轮解调
        │   └── msb.md       ← 双谱分析
        │
        └── fusion/          ← 融合算法
            ├── __init__.md
            └── ds_fusion.md ← D-S 证据理论融合
```

---

## 文件统计

| 目录 | 文件数 |
|------|--------|
| `app/` 根目录 | 8 |
| `app/api/` | 8 |
| `app/api/data_view/` | 10 |
| `app/api/devices/` | 3 |
| `app/core/` | 5 |
| `app/services/` | 4 |
| `app/services/alarms/` | 4 |
| `app/services/diagnosis/` | 20 |
| `app/services/diagnosis/gear/` | 5 |
| `app/services/diagnosis/fusion/` | 2 |
| **总计** | **69** |

---

*文档生成时间：2026-05-17*
*维护者：AI Agent（修改代码时请务必同步更新对应 .md 文件）*
