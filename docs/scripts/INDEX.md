# Scripts — 运维调试工具集

> **文档用途**：统一记录 `scripts/` 目录下所有脚本的用途、运行环境和依赖。
> **注意**：大部分脚本硬编码了服务器路径 `/opt/CNN/cloud/turbine.db`，**仅在生产服务器 (Ubuntu) 上运行**。
> 本地开发需改路径为 `D:\code\CNN\cloud\turbine.db`。

---

## 目录结构

```
scripts/
├── README.md                        # 原始说明
│
├── # ========== 设备在线/离线管理 ==========
├── check_online.py                  # 查询所有设备在线状态
├── check_online2.py                 # 极简版在线状态查询
├── set_offline.py                   # 强制所有设备设为离线
├── test_offline.py                  # 离线判定逻辑验证（ORM）
├── test_offline2.py                 # 离线判定逻辑验证（SQL）
│
├── # ========== 诊断结果概览 ==========
├── check_diag_all.py                # 所有诊断记录概览
├── check_all_diag.py                # 诊断去噪方法与通道信息
├── check_wtg004.py                  # WTG-004 故障概率分布
├── check_db_fields.py               # diagnosis 表最新记录全部字段
│
├── # ========== 诊断数据结构调试 ==========
├── check_diagnosis.py               # 最近10条记录时域特征指标
├── check_diag_server.py             # 服务器端诊断结果查询
├── check_diag_detail_server.py      # 服务器端诊断详情查询
├── check_er_structure.py            # engine_result JSON 顶层结构
├── check_oa_struct.py               # order_analysis 中 engine_result 的键与类型
├── check_oa_detail.py               # health_score < 80 的时域特征详情
├── check_offline_detail.py          # 离线设备详情查询
├── dump_er.py                       # engine_result 完整结构递归遍历
│
├── # ========== 数据修复/重新诊断 ==========
├── reanalyze_gear.py                # 齿轮设备批量重新诊断
│
└── # ========== 工具 ==========
    draw_architecture.py             # 绘制系统架构图（论文用）
```

---

## 1. 设备在线/离线管理

### `check_online.py`

```bash
cd /opt/CNN/scripts
source /opt/CNN/cloud/venv/bin/activate
python check_online.py
```

- **用途**：查询所有设备的 `is_online`、`last_seen_at`、`status` 字段
- **环境**：服务器
- **依赖**：SQLite（直接连接 `/opt/CNN/cloud/turbine.db`）

### `check_online2.py`

- **用途**：极简版，只查询 `is_online` + `last_seen_at`
- **与 check_online.py 区别**：输出更简洁

### `set_offline.py`

- **用途**：批量将所有设备 `is_online` 设为 0
- **场景**：服务器维护前/数据迁移前
- **⚠️ 危险操作**：执行后所有设备离线，需手动恢复

### `test_offline.py` / `test_offline2.py`

- **用途**：验证 `offline_monitor.py` 中 `_is_device_offline()` 判定逻辑
- **test_offline.py**：通过 ORM 调用
- **test_offline2.py**：直接 SQL 查询

---

## 2. 诊断结果概览

| 脚本 | 查询内容 | 用途 |
|------|---------|------|
| `check_diag_all.py` | 所有诊断记录 (device/batch/hs/status) | 快速掌握全局诊断状态 |
| `check_all_diag.py` | 诊断记录的去噪方法与通道信息 | 验证多去噪方法缓存是否正常 |
| `check_wtg004.py` | WTG-004 的故障概率分布详情 | 齿轮诊断结果深度排查 |
| `check_db_fields.py` | diagnosis 表最新记录的**全部字段** | 检查字段值完整性 |
| `check_diagnosis.py` | 最近 10 条记录的时域特征指标 | 验证时域特征计算正确性 |

---

## 3. 诊断数据结构调试

当 API 返回的诊断结果与预期不一致时，用这些脚本直接查看数据库中的 JSON 结构。

| 脚本 | 查询深度 | 用途 |
|------|---------|------|
| `check_er_structure.py` | `order_analysis.engine_result` 的顶层键 | 确认 engine_result 结构是否正确 |
| `check_oa_struct.py` | `order_analysis` 中各项的键与类型 | 排查前端解析失败 |
| `dump_er.py` | **递归遍历 engine_result 全部结构** | 深度排查（输出最长） |
| `check_oa_detail.py` | health_score < 80 的时域特征详情 | 定位低分原因 |
| `check_diag_server.py` | 服务器端诊断结果概览 | 远程快速诊断 |
| `check_diag_detail_server.py` | 服务器端诊断详情 | 远程深度排查 |
| `check_offline_detail.py` | 离线设备详情 | 排查离线监测问题 |

---

## 4. 数据修复

### `reanalyze_gear.py`

```bash
cd /opt/CNN
source cloud/venv/bin/activate
python scripts/reanalyze_gear.py
```

- **用途**：对齿轮设备（WTG-004 ~ WTG-009）批量重新诊断
- **原理**：直接调用 `analyzer.analyze_device()`，覆盖数据库中的 Diagnosis 记录
- **场景**：齿轮诊断算法升级后，需要重新评估历史数据
- **⚠️ 注意**：运行时间取决于数据量，可能较久

---

## 5. 工具

### `draw_architecture.py`

- **用途**：使用 matplotlib 绘制系统架构图（论文/答辩用）
- **环境**：本地 Windows（需要中文字体 SimHei）
- **输出**：`figures/system_architecture.png`

---

## 6. 本地开发适配

大部分脚本硬编码了 `/opt/CNN/cloud/turbine.db` 路径。本地开发时需修改：

```python
# 服务器
conn = sqlite3.connect('/opt/CNN/cloud/turbine.db')

# 本地 → 改为
conn = sqlite3.connect(r'D:\code\CNN\cloud\turbine.db')
```

或设置环境变量后修改脚本读取方式：

```python
import os
DB_PATH = os.environ.get('CNN_DB_PATH', '/opt/CNN/cloud/turbine.db')
conn = sqlite3.connect(DB_PATH)
```

---

*文档生成时间：2026-05-19*
*维护者：AI Agent（新增脚本时请务必同步更新）*
