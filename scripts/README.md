# scripts — 业务脚本

> 2026-11 清理后仅保留有长期业务价值的脚本;历史一次性调试脚本已删除,需要时从 git 历史找回。

## register_hustbear_devices.py — HUSTbear 独立设备注册

使用后端现有 `.env` 与 SQLAlchemy 连接,只新增 HUST-001～005,不覆盖 CW 或同编号冲突设备;冲突时整批回滚,重复执行无重复行。参数为 `{n:9, d:7.94, D:38.52, alpha:0}`,X/Y/Z 三轴,8192 Hz,仅轴承诊断。新设备离线创建,首次上传后上线。无需修改数据库结构或重启后端。

云端 Ubuntu 运行(脚本须先上传至 `/opt/CNN/scripts/`):

```bash
cd /opt/CNN/cloud
source venv/bin/activate
python ../scripts/register_hustbear_devices.py
```

预期输出新增 5 台,重复运行新增 0 台。`CNN_CLOUD_DIR` 可指定后端目录。

本地回归(仓库根目录,uv workspace):

```bash
cd cloud
uv run python -m unittest tests.test_hustbear_registration -v
```
