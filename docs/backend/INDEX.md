# 后端代码目录索引

> **文档用途**：按文件模块结构组织后端代码，方便 AI Agent 快速定位代码位置和了解各模块职责。
> **维护要求**：新增、重命名或删除文件时，必须同步更新本文档。

---

## 目录

1. [应用入口与核心配置](#1-应用入口与核心配置)
2. [API 路由层](#2-api-路由层)
3. [数据查看与诊断路由 (data_view)](#3-数据查看与诊断路由-data_view)
4. [设备管理路由 (devices)](#4-设备管理路由-devices)
5. [核心工具层 (core)](#5-核心工具层-core)
6. [服务层 (services)](#6-服务层-services)
7. [告警服务 (services/alarms)](#7-告警服务-servicesalarms)
8. [诊断服务 (services/diagnosis)](#8-诊断服务-servicesdiagnosis)
9. [齿轮诊断子模块 (services/diagnosis/gear)](#9-齿轮诊断子模块-servicesdiagnosisgear)
10. [融合算法子模块 (services/diagnosis/fusion)](#10-融合算法子模块-servicesdiagnosisfusion)

---

## 1. 应用入口与核心配置

| 文件 | 路径 | 职责 |
|------|------|------|
| `main.py` | `cloud/app/main.py` | FastAPI 应用入口、路由注册、WebSocket 端点 |
| `lifespan.py` | `cloud/app/lifespan.py` | 应用生命周期管理、后台分析 worker、线程池初始化 |
| `startup.py` | `cloud/app/startup.py` | 数据库初始化、默认设备创建 |
| `middleware.py` | `cloud/app/middleware.py` | CORS 配置、静态文件挂载 |
| `database.py` | `cloud/app/database.py` | SQLite/MySQL 数据库连接管理 |
| `models.py` | `cloud/app/models.py` | SQLAlchemy 数据模型定义 |
| `schemas.py` | `cloud/app/schemas.py` | Pydantic 请求/响应数据模型 |

---

## 2. API 路由层

| 文件 | 路径 | 职责 | 主要端点 |
|------|------|------|----------|
| `auth.py` | `cloud/app/api/auth.py` | 用户认证、JWT 管理 | `POST /api/auth/login` |
| `dashboard.py` | `cloud/app/api/dashboard.py` | 设备总览、离线检测 | `GET /api/dashboard/` |
| `alarms.py` | `cloud/app/api/alarms.py` | 告警查询、处理、删除 | `GET/POST/DELETE /api/alarms/*` |
| `collect.py` | `cloud/app/api/collect.py` | 手动采集任务管理 | `POST/GET /api/collect/*` |
| `ingest.py` | `cloud/app/api/ingest.py` | 边端数据接入 | `POST /api/ingest/` |
| `monitor.py` | `cloud/app/api/monitor.py` | 实时监测数据查询 | `GET /api/monitor/*` |
| `system.py` | `cloud/app/api/system.py` | 系统日志查看 | `GET /api/logs/` |

---

## 3. 数据查看与诊断路由 (data_view)

> Router Prefix: `/api/data`
> Tag: `振动数据查看`

| 文件 | 路径 | 职责 | 主要端点 |
|------|------|------|----------|
| `__init__.py` | `cloud/app/api/data_view/__init__.py` | Router 初始化、公共函数 | — |
| `core.py` | `cloud/app/api/data_view/core.py` | 设备/批次管理、原始数据查询、删除 | `GET /devices`, `GET /{id}/batches`, `GET /{id}/{batch}/{ch}`, `DELETE` |
| `spectrum.py` | `cloud/app/api/data_view/spectrum.py` | FFT 频谱、STFT 时频谱、统计指标 | `/fft`, `/stft` (async), `/stats` |
| `envelope.py` | `cloud/app/api/data_view/envelope.py` | 包络谱分析 | `/envelope` (async) |
| `order.py` | `cloud/app/api/data_view/order.py` | 阶次跟踪分析 | `/order` (async) |
| `cepstrum.py` | `cloud/app/api/data_view/cepstrum.py` | 倒谱分析 | `/cepstrum` (async) |
| `gear.py` | `cloud/app/api/data_view/gear.py` | 齿轮诊断、综合分析、全分析 | `/gear`, `/analyze`, `/full-analysis` (async) |
| `diagnosis_ops.py` | `cloud/app/api/data_view/diagnosis_ops.py` | 诊断缓存查询、重新诊断 | `GET/PUT /diagnosis`, `/reanalyze`, `/reanalyze-all` |
| `research.py` | `cloud/app/api/data_view/research.py` | 研究级分析、方法元数据 | `/method-info`, `/method-analysis`, `/research-analysis` (async) |
| `export.py` | `cloud/app/api/data_view/export.py` | CSV 数据导出 | `/export` |

---

## 4. 设备管理路由 (devices)

| 文件 | 路径 | 职责 | 主要端点 |
|------|------|------|----------|
| `__init__.py` | `cloud/app/api/devices/__init__.py` | Router 初始化、公共导入 | — |
| `core.py` | `cloud/app/api/devices/core.py` | 设备 CRUD 操作 | `GET /api/devices/` |
| `config.py` | `cloud/app/api/devices/config.py` | 通道参数、告警阈值、机械参数配置 | `GET/PUT /config`, `/alarm-thresholds`, `/edge/config` |

---

## 5. 核心工具层 (core)

| 文件 | 路径 | 职责 |
|------|------|------|
| `config.py` | `cloud/app/core/config.py` | 全局配置（端口、采样率、NN 开关等） |
| `memory_log.py` | `cloud/app/core/memory_log.py` | 内存日志环形缓冲区 |
| `thresholds.py` | `cloud/app/core/thresholds.py` | 告警阈值管理工具 |
| `websocket.py` | `cloud/app/core/websocket.py` | WebSocket 连接管理器 |

---

## 6. 服务层 (services)

| 文件 | 路径 | 职责 |
|------|------|------|
| `analyzer.py` | `cloud/app/services/analyzer.py` | 多通道综合分析引擎入口 |
| `nn_predictor.py` | `cloud/app/services/nn_predictor.py` | 神经网络预测预留接口 |
| `offline_monitor.py` | `cloud/app/services/offline_monitor.py` | 设备离线状态监测 |

---

## 7. 告警服务 (services/alarms)

| 文件 | 路径 | 职责 |
|------|------|------|
| `__init__.py` | `cloud/app/services/alarms/__init__.py` | 统一导出 `generate_alarms` |
| `channel.py` | `cloud/app/services/alarms/channel.py` | 通道级振动特征告警 |
| `device.py` | `cloud/app/services/alarms/device.py` | 设备级综合告警 |
| `diagnosis.py` | `cloud/app/services/alarms/diagnosis.py` | 诊断结果告警 |

---

## 8. 诊断服务 (services/diagnosis)

### 8.1 核心诊断模块

| 文件 | 路径 | 职责 |
|------|------|------|
| `engine.py` | `cloud/app/services/diagnosis/engine.py` | DiagnosisEngine 主类（调度器） |
| `ensemble.py` | `cloud/app/services/diagnosis/ensemble.py` | 多算法集成诊断引擎 |
| `bearing.py` | `cloud/app/services/diagnosis/bearing.py` | 轴承诊断（包络/Kurtogram/CPW/MED 等） |
| `features.py` | `cloud/app/services/diagnosis/features.py` | 时域/频域/阶次/包络特征提取 |
| `order_tracking.py` | `cloud/app/services/diagnosis/order_tracking.py` | 阶次跟踪算法 |
| `rule_based.py` | `cloud/app/services/diagnosis/rule_based.py` | 规则诊断算法（回退方案） |
| `signal_utils.py` | `cloud/app/services/diagnosis/signal_utils.py` | 通用信号处理辅助函数 |

### 8.2 健康度与建议

| 文件 | 路径 | 职责 |
|------|------|------|
| `health_score.py` | `cloud/app/services/diagnosis/health_score.py` | 综合健康度评分 (0-100) |
| `health_score_continuous.py` | `cloud/app/services/diagnosis/health_score_continuous.py` | 连续健康度评分（Sigmoid/多阈值扣分） |
| `recommendation.py` | `cloud/app/services/diagnosis/recommendation.py` | 诊断建议生成 |

### 8.3 预处理与降噪

| 文件 | 路径 | 职责 |
|------|------|------|
| `preprocessing.py` | `cloud/app/services/diagnosis/preprocessing.py` | 小波去噪/CPW/MED/级联降噪 |
| `vmd_denoise.py` | `cloud/app/services/diagnosis/vmd_denoise.py` | VMD 变分模态分解 |
| `emd_denoise.py` | `cloud/app/services/diagnosis/emd_denoise.py` | EMD/CEEMDAN 经验模态分解 |
| `wavelet_bearing.py` | `cloud/app/services/diagnosis/wavelet_bearing.py` | 小波轴承分析 |
| `wavelet_packet.py` | `cloud/app/services/diagnosis/wavelet_packet.py` | 小波包能量熵 |
| `savgol_denoise.py` | `cloud/app/services/diagnosis/savgol_denoise.py` | Savitzky-Golay 平滑 |
| `mckd.py` | `cloud/app/services/diagnosis/mckd.py` | 最大相关峭度解卷积 |

### 8.4 高级分析模块

| 文件 | 路径 | 职责 |
|------|------|------|
| `bearing_cyclostationary.py` | `cloud/app/services/diagnosis/bearing_cyclostationary.py` | 轴承循环平稳分析 |
| `bearing_sideband.py` | `cloud/app/services/diagnosis/bearing_sideband.py` | 轴承边带分析 |
| `bss.py` | `cloud/app/services/diagnosis/bss.py` | 盲源分离 (ICA) |
| `lms_filter.py` | `cloud/app/services/diagnosis/lms_filter.py` | LMS 自适应滤波 |
| `channel_consensus.py` | `cloud/app/services/diagnosis/channel_consensus.py` | 通道一致性分析 |
| `modality_bearing.py` | `cloud/app/services/diagnosis/modality_bearing.py` | 轴承模态分析 |
| `sensitive_selector.py` | `cloud/app/services/diagnosis/sensitive_selector.py` | 敏感参数选择 |
| `probability_calibration.py` | `cloud/app/services/diagnosis/probability_calibration.py` | 概率校准 |
| `trend_prediction.py` | `cloud/app/services/diagnosis/trend_prediction.py` | 趋势预测 |

---

## 9. 齿轮诊断子模块 (services/diagnosis/gear)

| 文件 | 路径 | 职责 |
|------|------|------|
| `__init__.py` | `cloud/app/services/diagnosis/gear/__init__.py` | 齿轮诊断公共接口 |
| `metrics.py` | `cloud/app/services/diagnosis/gear/metrics.py` | FM0/FM4/CAR/M6A/M8A/SER/NA4/NB4 指标 |
| `planetary_demod.py` | `cloud/app/services/diagnosis/gear/planetary_demod.py` | 行星齿轮解调分析 |
| `vmd_demod.py` | `cloud/app/services/diagnosis/gear/vmd_demod.py` | VMD 齿轮解调 |
| `msb.py` | `cloud/app/services/diagnosis/gear/msb.py` | 双谱分析 (MSB) |

---

## 10. 融合算法子模块 (services/diagnosis/fusion)

| 文件 | 路径 | 职责 |
|------|------|------|
| `__init__.py` | `cloud/app/services/diagnosis/fusion/__init__.py` | 融合模块初始化 |
| `ds_fusion.py` | `cloud/app/services/diagnosis/fusion/ds_fusion.py` | Dempster-Shafer 证据理论融合 |

---

*文档生成时间：2026-05-17*
*维护者：AI Agent（修改代码结构时请务必同步更新）*
