#!/bin/bash
cd /opt/CNN
git pull

# 重启后端
sudo systemctl restart CNN
echo "后端已重启"

# 重新构建前端
cd /opt/CNN/wind-turbine-diagnosis
npm run build
echo "前端已构建"

# 查看状态
sudo systemctl status CNN --no-pager
