# scripts — 运维调试工具集

> 所有脚本硬编码了 `/opt/CNN/cloud/turbine.db` 路径，**仅在生产服务器 (Ubuntu) 上运行**。
> 本地开发需改路径为 `D:\code\CNN\cloud\turbine.db`。

## 脚本分类

### 设备在线/离线管理

| 脚本 | 用途 |
|------|------|
| `check_online.py` | 查询设备在线状态及 status 字段 |
| `check_online2.py` | 极简版，查询 is_online + last_seen_at |
| `set_offline.py` | 强制所有设备设为离线 (is_online=0) |
| `test_offline.py` | 通过 ORM 调用 `_is_device_offline()` 验证离线判定逻辑 |
| `test_offline2.py` | 直接 SQL 查询 devices 表检查在线状态 |

### 诊断结果概览

| 脚本 | 用途 |
|------|------|
| `check_diag_all.py` | 查看所有诊断记录概览 (device/batch/hs/status) |
| `check_all_diag.py` | 查看诊断去噪方法与通道信息（验证多去噪方法缓存） |
| `check_wtg004.py` | 查看 WTG-004 设备的故障概率分布 |
| `check_db_fields.py` | 查看 diagnosis 表最新记录的全部字段 |

### 诊断数据结构调试

| 脚本 | 用途 |
|------|------|
| `check_er_structure.py` | 查看 engine_result JSON 顶层结构 |
| `check_oa_struct.py` | 查看 order_analysis 中 engine_result 的键与类型 |
| `dump_er.py` | 递归遍历 engine_result 全部结构 |
| `check_oa_detail.py` | 查看 health_score<80 的时域特征详情 |
| `check_diagnosis.py` | 查看最近10条记录的时域特征指标 |

## 使用方式

```bash
cd /opt/CNN/scripts
source /opt/CNN/cloud/venv/bin/activate
python check_online.py
```