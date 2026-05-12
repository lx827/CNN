#!/bin/bash
# Usage:
#   ./deploy.sh         完整部署（后端+前端）
#   ./deploy.sh -s      跳过前端构建（只更新后端）
#   ./deploy.sh --skip-frontend  同上

SKIP_FRONTEND=false
for arg in "$@"; do
    if [[ "$arg" == "-s" || "$arg" == "--skip-frontend" ]]; then
        SKIP_FRONTEND=true
    fi
done

cd /opt/CNN
git pull

# 重启后端
sudo systemctl restart CNN
echo "后端已重启"

# 重新构建前端（默认执行，传 -s 或 --skip-frontend 时跳过）
if [ "$SKIP_FRONTEND" = false ]; then
    cd /opt/CNN/wind-turbine-diagnosis
    npm run build
    echo "前端已构建"
else
    echo "跳过前端构建"
fi

# 查看状态
sudo systemctl status CNN --no-pager
