# scripts — 运维调试工具集

> 下列旧运维脚本多使用 `/opt/CNN/cloud/turbine.db` 路径，**仅在生产服务器 (Ubuntu) 上运行**。
> 本地开发需改路径为 `D:\code\CNN\cloud\turbine.db`。

## 脚本分类

### HUSTbear 独立设备注册

`register_hustbear_devices.py` 使用后端现有 `.env` 与 SQLAlchemy 连接，只新增 HUST-001～005，不覆盖 CW 或同编号冲突设备；冲突时整批回滚，重复执行无重复行。参数为 `{n:9,d:7.94,D:38.52,alpha:0}`，X/Y/Z 三轴，8192 Hz，仅轴承诊断。新设备离线创建，首次上传后上线。无需修改数据库结构或重启后端。

在云端 Ubuntu 终端运行（需要数据库写入权限，不要求额外管理员权限；脚本须先上传至 `/opt/CNN/scripts/`）：

```bash
# 进入云端后端目录，读取现有 .env 和数据库。
cd /opt/CNN/cloud
# 激活云端后端现有 Python 环境，不安装新依赖。
source venv/bin/activate
# 向现有云端数据库注册五台独立设备；仅此步骤写入数据，不访问网络。
python ../scripts/register_hustbear_devices.py
```

预期输出新增 5 台，重复运行新增 0 台。刷新页面总览检查 HUSTbear 设备，首次回放前显示离线正常。`register_devices(db)` 返回本次新增编号列表，成功提交，失败回滚；`CNN_CLOUD_DIR` 可指定后端目录。

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
