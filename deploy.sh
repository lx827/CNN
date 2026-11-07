#!/bin/bash
# 阿里云 ECS 一键部署(uv 链路,ADR-0001 / ADR-0002)
#
# 用法(服务器上执行):
#   bash /opt/CNN/deploy.sh              完整部署(代码 + 依赖 + 后端重启 + 前端构建)
#   bash /opt/CNN/deploy.sh -s           跳过前端构建(只更新后端)
#   bash /opt/CNN/deploy.sh --skip-frontend   同上
#   bash /opt/CNN/deploy.sh --dry-run    只打印将要执行的步骤,不改动任何东西(演练/核对用)
#
# 环境变量(一般无需修改;本地演练时可覆盖):
#   CNN_DEPLOY_ROOT  部署目录,默认 /opt/CNN
#   CNN_SERVICE      systemd 服务名,默认 CNN
#
# 约定:Python 环境全程 uv(铁律,AGENTS.md §2)——不存在则官方脚本安装,
# 依赖只经 `uv sync --frozen` 按 uv.lock 安装,禁 pip / 手工 venv。

set -euo pipefail

DEPLOY_ROOT="${CNN_DEPLOY_ROOT:-/opt/CNN}"
SERVICE="${CNN_SERVICE:-CNN}"
SKIP_FRONTEND=false
DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        -s|--skip-frontend) SKIP_FRONTEND=true ;;
        --dry-run) DRY_RUN=true ;;
        *) echo "未知参数: $arg(可用: -s/--skip-frontend 跳过前端, --dry-run 演练)"; exit 1 ;;
    esac
done

# dry-run 下只打印命令,不执行(包括 git / uv / systemctl,保证演练零改动)
run() {
    if $DRY_RUN; then
        echo "[dry-run] $*"
    else
        "$@"
    fi
}

echo "==> 部署目录: $DEPLOY_ROOT(dry-run=$DRY_RUN)"
cd "$DEPLOY_ROOT"

# 1) uv 引导:不存在则官方脚本安装
if command -v uv >/dev/null 2>&1; then
    echo "==> uv 已就绪: $(command -v uv)"
else
    echo "==> 未检测到 uv,使用官方脚本安装"
    run curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh
    run sh /tmp/uv-install.sh
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || { echo "uv 安装失败;请手动安装后重试(https://docs.astral.sh/uv/)"; exit 1; }
fi

# 2) 同步代码(保留 main 分支直进的方式;--ff-only 避免意外合并提交)
run git switch main
run git pull --ff-only

# 3) 安装依赖:workspace 根 uv sync --frozen,严格按 uv.lock,
#    Python 3.13 由 uv 托管下载,不依赖系统 Python(ADR-0001)
run uv sync --frozen

# 4) systemd 服务:首次安装 / 与模板不一致时备份更新 CNN.service
#    (ExecStart 直指 .venv 解释器,模板见 deploy/cloud/CNN.service)
SERVICE_SRC="$DEPLOY_ROOT/deploy/cloud/CNN.service"
SERVICE_DST="/etc/systemd/system/${SERVICE}.service"
install_service() {
    run sudo cp "$SERVICE_SRC" "$SERVICE_DST"
    run sudo systemctl daemon-reload
    run sudo systemctl enable "$SERVICE"
}
if [ -f "$SERVICE_DST" ]; then
    if sudo cmp -s "$SERVICE_SRC" "$SERVICE_DST"; then
        echo "==> ${SERVICE}.service 已与模板一致"
    else
        echo "==> ${SERVICE}.service 与模板不一致,备份后更新"
        run sudo cp "$SERVICE_DST" "${SERVICE_DST}.bak.$(date +%Y%m%d%H%M%S)"
        install_service
    fi
else
    echo "==> 首次安装 ${SERVICE}.service"
    install_service
fi

# 5) 重启后端(2G 红线:重启前后均不引入额外并发,单服务单进程)
echo "==> 重启后端"
run sudo systemctl restart "$SERVICE"

# 6) 前端构建(默认执行;传 -s / --skip-frontend 跳过)
if [ "$SKIP_FRONTEND" = false ]; then
    echo "==> 构建前端"
    run npm --prefix "$DEPLOY_ROOT/wind-turbine-diagnosis" run build
else
    echo "==> 跳过前端构建"
fi

# 7) 查看状态
echo "==> 查看服务状态"
run sudo systemctl status "$SERVICE" --no-pager

if $DRY_RUN; then
    echo "==> dry-run 演练结束,未做任何改动"
else
    echo "==> 部署完成"
fi
