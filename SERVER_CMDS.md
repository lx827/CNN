# 云服务器常用运维命令速查表

> 适用于阿里云 ECS Ubuntu 22.04 部署的风机齿轮箱智能故障诊断系统。
> 所有命令均在 **SSH 连接的服务器终端** 中执行。

---

## 一、连接与传输

### 1. SSH 登录服务器
```bash
ssh root@8.137.96.104
# 输入密码后进入终端
```

### 2. 上传文件到服务器
在**本地电脑** PowerShell 执行：
```bash
# 上传整个文件夹
scp -r ./cloud/ root@8.137.96.104:/opt/turbine-diagnosis/

# 上传单个文件
scp ./cloud/app/main.py root@8.137.96.104:/opt/turbine-diagnosis/cloud/app/
```

### 3. 从服务器下载文件
在**本地电脑** PowerShell 执行：
```bash
# 下载数据库文件到本地
scp root@8.137.96.104:/opt/turbine-diagnosis/cloud/turbine.db ./backup.db
```

---

## 二、后端服务管理 (Python/FastAPI)

### 1. 重启后端服务
**每次修改 `cloud/` 下的 Python 代码后必须执行**：
```bash
systemctl restart turbine-cloud
```

### 2. 启动 / 停止服务
```bash
systemctl start turbine-cloud   # 启动
systemctl stop turbine-cloud    # 停止
systemctl status turbine-cloud  # 查看状态（绿色表示运行中）
```

### 3. 查看后端日志
```bash
# 查看最近 50 行日志（找报错）
journalctl -u turbine-cloud -n 50 --no-pager

# 实时监控日志（类似 tail -f，按 Ctrl+C 退出）
journalctl -u turbine-cloud -f
```

---

## 三、前端服务管理 (Vue/Nginx)

### 1. 重新构建前端代码
修改 `wind-turbine-diagnosis/src/` 代码后执行：
```bash
cd /opt/turbine-diagnosis/wind-turbine-diagnosis
npm run build
```

### 2. 重启 Nginx
配置 Nginx 后生效：
```bash
systemctl reload nginx
```

### 3. 查看 Nginx 状态与日志
```bash
systemctl status nginx
tail -f /var/log/nginx/error.log  # 查看 500 报错原因
```

---

## 四、环境配置与维护

### 1. 清理磁盘空间（删除 node_modules 等垃圾）
```bash
cd /opt/turbine-diagnosis
# 删除前端依赖（服务器会自动重新安装）
rm -rf wind-turbine-diagnosis/node_modules
# 删除 Python 虚拟环境（如果上传了本地环境）
rm -rf cloud/venv
# 查看磁盘占用
df -h /
```

### 2. 更新系统软件包
```bash
apt update && apt upgrade -y
```

### 3. 修改 Python 依赖后重新安装
```bash
cd /opt/turbine-diagnosis/cloud
source venv/bin/activate
pip install -r requirements.txt
```

---

## 五、数据库备份

### 备份 SQLite 数据库
```bash
cd /opt/turbine-diagnosis/cloud
cp turbine.db turbine_backup_$(date +%Y%m%d).db
```

---

## 六、排查 500 报错速查

1. **先确认后端是否存活**：
   ```bash
   curl http://127.0.0.1:8000
   ```
   如果有 JSON 返回，说明后端正常，问题在 Nginx 或前端代码。

2. **查看 Nginx 错误日志**：
   ```bash
   tail -n 50 /var/log/nginx/error.log
   ```

3. **查看后端报错日志**：
   ```bash
   journalctl -u turbine-cloud -n 50 --no-pager
   ```

---

## 七、其他常用

### 查看端口占用
```bash
lsof -i:8000   # 查看谁占用了 8000 端口
netstat -tulpn | grep 80
```

### 重启整个服务器
```bash
reboot
```
