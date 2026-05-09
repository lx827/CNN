# 阿里云部署指南

> 将风机齿轮箱智能故障诊断系统部署到阿里云 ECS，实现 7×24 小时远程监测。

---

## 一、购买云服务器

### 1.1 购买 ECS

1. 登录 [阿里云控制台](https://ecs.console.aliyun.com/)
2. 创建实例，选择以下配置：

| 配置项 | 推荐值 | 说明 |
|--------|--------|------|
| 地域 | 离你最近的区域 | 延迟更低 |
| 实例规格 | ecs.t6-c1m2.large（2核4G） | 开发/演示足够 |
| 操作系统 | Ubuntu 22.04 LTS 64位 | 兼容性好 |
| 系统盘 | 40G SSD | 默认即可 |
| 带宽 | 按量付费，1-5Mbps | 开发阶段 1Mbps 够用 |
| 安全组 | 放行 22/80/443/8000 | 后面会详细说明 |

### 1.2 设置密码

购买时设置 **root 密码**，记住它，SSH 登录需要。

### 1.3 获取公网 IP

购买完成后，在 ECS 控制台找到你的 **公网 IP 地址**（如 `47.98.xxx.xxx`）。

---

## 二、连接服务器

### 2.1 Windows 用户

使用 PowerShell 或终端：

```bash
ssh root@你的公网IP
# 输入密码
```

或使用 SSH 工具（如 PuTTY、FinalShell、MobaXterm）。

### 2.2 首次连接

```bash
# 更新系统
apt update && apt upgrade -y

# 安装基础工具
apt install -y git curl wget zip unzip
```

---

## 三、安装运行环境

### 3.1 安装 Python

```bash
apt install -y python3 python3-pip python3-venv
```

验证：
```bash
python3 --version   # 应显示 3.10+
pip3 --version
```

### 3.2 安装 Node.js

```bash
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt install -y nodejs
```

验证：
```bash
node -v    # 应显示 v18+
npm -v
```

### 3.3 安装 Nginx（反向代理）

```bash
apt install -y nginx
systemctl enable nginx
systemctl start nginx
```

验证：浏览器访问 `http://你的公网IP`，看到 "Welcome to nginx!" 页面。

---

## 四、部署后端服务

### 4.1 上传代码

在**本地电脑**上执行（把代码上传到服务器）：

```bash
# 方式一：SCP 上传（简单直接）
scp -r cloud/ root@你的公网IP:/opt/turbine-diagnosis/
```

或使用 Git（推荐，方便后续更新）：

```bash
# 在服务器上执行
cd /opt
git clone https://你的Git仓库地址.git turbine-diagnosis
```

### 4.2 配置后端

```bash
# SSH 进入服务器后
cd /opt/turbine-diagnosis/cloud

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 4.3 修改 .env 配置

```bash
nano /opt/turbine-diagnosis/cloud/.env
```

修改以下关键配置：

```env
# 数据库（推荐用 MySQL，数据更安全）
USE_SQLITE=true              # 先用 SQLite，后续可切 MySQL

# 监听地址（必须改！否则外网无法访问）
API_HOST=0.0.0.0
API_PORT=8000

# 后台分析间隔
ANALYZE_INTERVAL_SECONDS=30

# 神经网络（如果没模型就保持 false）
NN_ENABLED=false
NN_MODEL_PATH=./models/turbine_fault_model.onnx
```

### 4.4 使用 Systemd 管理后端（推荐）

创建服务文件：

```bash
nano /etc/systemd/system/turbine-cloud.service
```

写入以下内容：

```ini
[Unit]
Description=风机齿轮箱诊断系统 - 云端后端
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/turbine-diagnosis/cloud
ExecStart=/opt/turbine-diagnosis/cloud/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
Environment=PATH=/opt/turbine-diagnosis/cloud/venv/bin

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
systemctl daemon-reload
systemctl enable turbine-cloud
systemctl start turbine-cloud

# 查看运行状态
systemctl status turbine-cloud
```

验证：浏览器访问 `http://你的公网IP:8000/docs`，看到 API 文档页面。

---

## 五、部署前端

### 5.1 构建前端

在**本地电脑**上执行：

```bash
cd wind-turbine-diagnosis

# 安装依赖
npm install

# 修改 API 代理配置（vite.config.js）
# 将 localhost:8000 改为你的公网 IP
```

修改 `vite.config.js`：

```javascript
server: {
  proxy: {
    '/api': {
      target: 'http://你的公网IP:8000',  // 改这里
      changeOrigin: true,
    },
    '/ws': {
      target: 'ws://你的公网IP:8000',    // 改这里
      ws: true,
    }
  }
}
```

打包：

```bash
npm run build
```

生成 `dist/` 目录。

### 5.2 上传到服务器

```bash
# 本地电脑执行
scp -r wind-turbine-diagnosis/dist/ root@你的公网IP:/opt/turbine-diagnosis/frontend/
```

### 5.3 配置 Nginx

```bash
# 服务器上执行
nano /etc/nginx/sites-available/turbine-diagnosis
```

写入以下内容：

```nginx
server {
    listen 80;
    server_name 你的公网IP;  # 如果有域名，填域名

    # 前端静态文件
    location / {
        root /opt/turbine-diagnosis/frontend;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # 后端 API 代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # WebSocket 代理
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

启用配置：

```bash
ln -s /etc/nginx/sites-available/turbine-diagnosis /etc/nginx/sites-enabled/
nginx -t                    # 检查配置
systemctl reload nginx      # 重载
```

验证：浏览器访问 `http://你的公网IP`，看到前端页面。

---

## 六、配置安全组（阿里云控制台）

在阿里云 ECS 控制台，找到你的实例 → 安全组 → 配置规则：

| 端口 | 协议 | 授权对象 | 用途 |
|------|------|----------|------|
| 22 | TCP | 你的IP/0.0.0.0/0 | SSH 登录 |
| 80 | TCP | 0.0.0.0/0 | HTTP 访问 |
| 8000 | TCP | 你的IP（内网可全开） | 后端 API |

> ⚠️ 生产环境建议 22 端口只对你自己的 IP 开放。

---

## 七、部署边端（风机现场）

### 7.1 方案一：工控机部署（推荐）

风机现场的工控机/树莓派上：

```bash
# 在工控机上
cd /path/to/edge

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

修改 `.env`：

```env
# 指向阿里云服务器
CLOUD_INGEST_URL=http://你的公网IP:8000/api/ingest/

DEVICE_IDS=WTG-001,WTG-002,WTG-003,WTG-004,WTG-005
SAMPLE_RATE=25600
DURATION=10
COMPRESSION_ENABLED=true
```

启动：

```bash
python3 edge_client.py
```

### 7.2 方案二：Systemd 后台运行

```bash
nano /etc/systemd/system/turbine-edge.service
```

```ini
[Unit]
Description=风机边端采集客户端
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/edge
ExecStart=/path/to/edge/venv/bin/python3 edge_client.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable turbine-edge
systemctl start turbine-edge
```

### 7.3 方案三：本地电脑临时测试

如果只是想测试云端是否正常工作，在你本地电脑上修改 `edge/.env`：

```env
CLOUD_INGEST_URL=http://你的公网IP:8000/api/ingest/
```

然后运行：

```bash
cd edge
venv\Scripts\activate
python edge_client.py
```

---

## 八、可选：切换 MySQL 数据库

SQLite 适合小规模数据。如果数据量大或需要多机部署，建议切 MySQL：

### 8.1 安装 MySQL

```bash
apt install -y mysql-server
systemctl enable mysql
systemctl start mysql

# 设置 root 密码
mysql_secure_installation
```

### 8.2 创建数据库

```bash
mysql -u root -p
```

```sql
CREATE DATABASE turbine_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'turbine'@'%' IDENTIFIED BY 'turbine1234';
GRANT ALL PRIVILEGES ON turbine_db.* TO 'turbine'@'%';
FLUSH PRIVILEGES;
EXIT;
```

### 8.3 修改 .env

```bash
nano /opt/turbine-diagnosis/cloud/.env
```

```env
USE_SQLITE=false
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=turbine
DB_PASSWORD=turbine1234
DB_NAME=turbine_db
```

### 8.4 安装 PyMySQL 并重启

```bash
cd /opt/turbine-diagnosis/cloud
source venv/bin/activate
pip install pymysql cryptography
systemctl restart turbine-cloud
```

---

## 九、可选：配置 HTTPS

### 9.1 申请免费证书

1. 购买域名并解析到云服务器公网 IP
2. 在阿里云控制台申请免费 SSL 证书（1年有效期）
3. 下载 Nginx 格式的证书文件

### 9.2 安装证书

将证书文件上传到服务器：

```bash
mkdir -p /etc/nginx/ssl
# 上传 cert.pem 和 cert.key 到 /etc/nginx/ssl/
```

### 9.3 修改 Nginx 配置

```nginx
server {
    listen 443 ssl;
    server_name 你的域名;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/cert.key;

    # ... 其余配置不变
}

# HTTP 自动跳转 HTTPS
server {
    listen 80;
    server_name 你的域名;
    return 301 https://$host$request_uri;
}
```

---

## 十、常用运维命令

```bash
# 查看后端状态
systemctl status turbine-cloud

# 查看后端日志
journalctl -u turbine-cloud -f

# 重启后端
systemctl restart turbine-cloud

# 查看边端状态（如果部署在服务器）
systemctl status turbine-edge

# 查看 Nginx 状态
systemctl status nginx

# 更新代码后
cd /opt/turbine-diagnosis
git pull
cd cloud && source venv/bin/activate && pip install -r requirements.txt
systemctl restart turbine-cloud
```

---

## 十一、费用估算

| 项目 | 费用（月） | 说明 |
|------|-----------|------|
| ECS 2核4G | ~50-100 元 | 按量付费/包月 |
| 带宽 1Mbps | ~20 元 | 按量付费更便宜 |
| MySQL（可选） | ~30 元 | 或使用 RDS |
| SSL 证书 | 免费 | 阿里云免费证书 |
| **合计** | **~70-150 元** | 开发阶段足够 |

---

## 十二、常见问题

### Q1: 后端启动失败

```bash
# 查看错误日志
journalctl -u turbine-cloud -n 50

# 常见原因：
# - 端口被占用：lsof -i:8000
# - 依赖没装：pip install -r requirements.txt
# - .env 配置错误
```

### Q2: 前端白屏

- 检查 Nginx 日志：`tail -f /var/log/nginx/error.log`
- 确认 `vite.config.js` 中的代理地址正确
- 浏览器 F12 → Network 查看接口是否通

### Q3: 边端上传失败

```bash
# 测试网络连通性
ping 你的公网IP
curl http://你的公网IP:8000/

# 确认安全组开放了 8000 端口
# 确认 .env 中地址正确
```

### Q4: 数据库文件丢失

SQLite 文件在 `cloud/turbine.db`，每次重新部署系统会重建。
**重要数据请备份**：

```bash
cp /opt/turbine-diagnosis/cloud/turbine.db /backup/$(date +%Y%m%d).db
```

### Q5: 内存不足

```bash
# 查看内存使用
free -h

# 如果 2G 不够，可以加 Swap
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
```

---

## 部署检查清单

- [ ] 购买 ECS，记录公网 IP
- [ ] 安全组开放 22/80/8000
- [ ] SSH 登录服务器
- [ ] 安装 Python/Node.js/Nginx
- [ ] 上传代码到 `/opt/turbine-diagnosis/`
- [ ] 配置 `cloud/.env`（API_HOST=0.0.0.0）
- [ ] 安装后端依赖并启动
- [ ] 构建前端并配置 Nginx
- [ ] 浏览器验证前端和 API
- [ ] 修改边端 `.env` 指向公网 IP
- [ ] 启动边端并确认数据上传成功
- [ ] 设置 Systemd 开机自启
