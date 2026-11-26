#!/bin/bash
# 云端形态一键部署:阿里云 ECS(uv 链路,ADR-0001 / ADR-0002)
#
# 本脚本只部署云端形态。三种部署形态各有唯一入口:
#   云端       本脚本(服务器上执行)
#   本地工作站  双击仓库根 start.bat(本机后端+前端+采集进程,免登录)
#   树莓派边端  deploy/edge/build.sh 交叉编译 + edge/acquire/deploy/pi/deploy_pi.sh 安装
#
# 用法(服务器上执行):
#   bash /opt/CNN/deploy.sh              完整部署(代码 + 依赖 + 后端重启 + 前端构建)
#   bash /opt/CNN/deploy.sh -s           跳过前端构建(只更新后端)
#   bash /opt/CNN/deploy.sh --skip-frontend   同上
#   bash /opt/CNN/deploy.sh --dry-run    只打印将要执行的步骤,不改动任何东西(演练/核对用)
#
# 停机语义:部署在服务停止的窗口内完成(2G 机器上 C++ 扩展编译与前端构建都需要
# 服务占用的内存余量,边跑边部会触发 swap 颠簸导致部署假死);窗口内任一步失败
# 中止时,EXIT trap 会尽力恢复启动服务。
#
# 环境变量(一般无需修改;本地演练时可覆盖):
#   CNN_DEPLOY_ROOT  部署目录,默认 /opt/CNN
#   CNN_SERVICE      systemd 服务名,默认 CNN
#   CNN_NGINX_SITE   已启用的生产站点,默认 /etc/nginx/sites-enabled/CNN
#
# 约定:Python 环境全程 uv(铁律,AGENTS.md §2)——不存在则官方脚本安装,
# 依赖只经 `uv sync --frozen` 按 uv.lock 安装,禁 pip / 手工 venv。

set -euo pipefail

DEPLOY_ROOT="${CNN_DEPLOY_ROOT:-/opt/CNN}"
SERVICE="${CNN_SERVICE:-CNN}"
NGINX_SITE="${CNN_NGINX_SITE:-/etc/nginx/sites-enabled/CNN}"
PUBLIC_ROOT="$DEPLOY_ROOT/web/dist"
LEGACY_ROOT="$DEPLOY_ROOT/wind-turbine-diagnosis/dist"
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

# 1) uv 引导:不存在或不可用则官方脚本安装;PATH 无论如何都带上 ~/.local/bin
#    (非交互 SSH 下 Ubuntu 的 .bashrc 提前返回,拿不到 ~/.local/bin —— 2026-11-11
#     生产事故诱因之一:uv 引导状态与后续步骤不一致)
export PATH="$HOME/.local/bin:$PATH"
if command -v uv >/dev/null 2>&1 && uv --version >/dev/null 2>&1; then
    echo "==> uv 已就绪: $(command -v uv) ($(uv --version 2>/dev/null || echo 版本未知))"
else
    echo "==> 未检测到可用 uv,使用官方脚本安装"
    run curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh
    run sh /tmp/uv-install.sh
    export PATH="$HOME/.local/bin:$PATH"
    if ! $DRY_RUN; then
        uv --version
    fi
fi

# 2) 在停机前同步代码；新版改动了脚本本身时以新版执行剩余步骤。
if $DRY_RUN; then
    run git switch main
    run git pull --ff-only
else
    git switch main
    before=$(git rev-parse HEAD:deploy.sh)
    git pull --ff-only
    if [ "$before" != "$(git rev-parse HEAD:deploy.sh)" ]; then
        exec bash "$DEPLOY_ROOT/deploy.sh" "$@"
    fi
    if ! $SKIP_FRONTEND; then
        command -v npm >/dev/null || { echo '完整部署需要 Node.js/npm'; exit 1; }
        sudo test -f "$NGINX_SITE" || { echo "未启用 Nginx 站点: $NGINX_SITE"; exit 1; }
    fi
fi

# 3) 停止后端,进入部署窗口(2G 红线:编译与前端构建必须拿到服务占用的内存
#    余量,否则与运行中的服务互相挤压触发 swap 颠簸,部署假死——2026-11-13
#    生产 uv sync 卡死诱因)。窗口内任一步失败经 EXIT trap 尽力恢复服务;
#    成功路径在服务确认启动后解除恢复。
SERVICE_STOPPED=false
FRONTEND_STAGE=
restore_service_on_abort() {
    if [[ "$FRONTEND_STAGE" == "$DEPLOY_ROOT/web/.dist."* ]] && [ -d "$FRONTEND_STAGE" ]; then
        rm -rf -- "$FRONTEND_STAGE"
    fi
    if [ "$SERVICE_STOPPED" = true ]; then
        echo "!! 部署中止,尝试恢复 ${SERVICE}(环境为中止时的实际状态)"
        if sudo systemctl start "$SERVICE" 2>/dev/null && sudo systemctl is-active --quiet "$SERVICE"; then
            echo "==> ${SERVICE} 已恢复运行"
        else
            echo "!! ${SERVICE} 恢复失败,保持停止;排查后重跑 deploy.sh 或手动 systemctl start ${SERVICE}"
        fi
    fi
}
trap restore_service_on_abort EXIT
echo "==> 停止后端,进入部署窗口(完成前服务不可用)"
if $DRY_RUN; then
    echo "[dry-run] systemctl stop $SERVICE"
else
    sudo systemctl stop "$SERVICE"
    SERVICE_STOPPED=true
fi

# 3.5) 一次性目录迁移(2026-11 重组 cloud/→server/):生产状态文件跟随新目录名。
#      .env 与 turbine.db 不入库,git pull 不会移动它们;只在目标不存在时迁移。
if [ -d "$DEPLOY_ROOT/cloud" ]; then
    if [ -f "$DEPLOY_ROOT/cloud/.env" ] && [ ! -f "$DEPLOY_ROOT/server/.env" ]; then
        run mv "$DEPLOY_ROOT/cloud/.env" "$DEPLOY_ROOT/server/.env"
    fi
    if [ -f "$DEPLOY_ROOT/cloud/turbine.db" ] && [ ! -f "$DEPLOY_ROOT/server/turbine.db" ]; then
        run mv "$DEPLOY_ROOT/cloud/turbine.db" "$DEPLOY_ROOT/server/turbine.db"
    fi
fi

# 4) 根项目按锁文件同步运行依赖并从源码构建计算扩展；目标需 C++20 工具链。
#    构建后端版本在根配置固定，CMake 管理原生依赖，编译并行度为 1。
#    云端只装 cloud 组:采集宿主(dc24)、驱动适配器与开发工具不进生产。
run uv sync --frozen --no-default-groups --group cloud

# 4.1) 断言根项目解释器确实生成。2026-11-11 生产事故:uv sync 正常返回但
#      /opt/CNN/.venv 未生成,服务被切到不存在的解释器上进入崩溃循环;此断言让
#      该类失效在部署期响亮失败,绝不带病重启。
VENV_PY="$DEPLOY_ROOT/.venv/bin/python"
if $DRY_RUN; then
    echo "[dry-run] 断言 $VENV_PY 可执行(当前实际状态: $([ -x "$VENV_PY" ] && echo 存在 || echo 缺失))"
else
    [ -x "$VENV_PY" ] || { echo "!! uv sync 返回成功但 $VENV_PY 不存在,中止部署(服务未被动过)"; exit 1; }
    echo "==> 依赖就绪: $VENV_PY"
fi

# 5) systemd 服务:首次安装 / 与模板不一致时备份更新 CNN.service
#    (ExecStart 直指 .venv 解释器,模板见 deploy/server/CNN.service)
SERVICE_SRC="$DEPLOY_ROOT/deploy/server/CNN.service"
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

# 5.1) 断言磁盘上的 unit 确实指向 workspace 解释器。cmp "一致"只说明与模板相等,
#      不能兜住"模板与现状都被污染/未被替换"的组合;2026-11-11 生产事故中旧单元
#      残留 venv 时代路径,服务一直跑在 /opt/CNN/cloud/venv 上。不指向 .venv 即强制覆盖。
if ! $DRY_RUN; then
    if ! sudo grep -q '\.venv/bin/python' "$SERVICE_DST" 2>/dev/null; then
        echo "!! ${SERVICE}.service 未指向 workspace 解释器($VENV_PY),备份后强制以模板覆盖"
        run sudo cp "$SERVICE_DST" "${SERVICE_DST}.bak.$(date +%Y%m%d%H%M%S)"
        install_service
    fi
fi

# 6) 完整部署按锁文件安装前端依赖，再由 Vite 构建到 web/dist。
if ! $SKIP_FRONTEND; then
    echo "==> 安装并构建前端: $PUBLIC_ROOT"
    run npm --prefix "$DEPLOY_ROOT/web" ci --include=dev --no-audit --no-fund
    if $DRY_RUN; then
        FRONTEND_STAGE="$DEPLOY_ROOT/web/.dist.XXXXXX"
    else
        FRONTEND_STAGE=$(mktemp -d "$DEPLOY_ROOT/web/.dist.XXXXXX")
    fi
    run npm --prefix "$DEPLOY_ROOT/web" run build -- --outDir "$FRONTEND_STAGE"
    run test -s "$FRONTEND_STAGE/index.html"
else
    echo "==> 跳过前端安装、构建及 Nginx 迁移"
fi

migrate_nginx_root() (
    set -e
    local site legacy_count current_count backup next
    site=$(sudo realpath -e "$NGINX_SITE")
    root_count() {
        sudo awk -v target="$1;" '$1 == "root" && $2 == target { n++ } END { print n+0 }' "$site"
    }
    legacy_count=$(root_count "$LEGACY_ROOT")
    current_count=$(root_count "$PUBLIC_ROOT")
    if [ "$legacy_count" = 0 ] && [ "$current_count" = 1 ]; then
        return
    fi
    if [ "$legacy_count" != 1 ] || [ "$current_count" != 0 ]; then
        echo "无法定位唯一的 CNN 静态根目录，请检查 $NGINX_SITE" >&2
        return 1
    fi
    next=$(mktemp)
    trap 'rm -f -- "$next"' EXIT
    sudo awk -v legacy="$LEGACY_ROOT" -v current="$PUBLIC_ROOT" '
        $1 == "root" && $2 == legacy ";" {
            pos = index($0, legacy)
            $0 = substr($0, 1, pos-1) current substr($0, pos+length(legacy))
        }
        { print }
    ' "$site" > "$next"
    backup=$(sudo mktemp /var/backups/cnn-nginx.XXXXXX)
    sudo cp -- "$site" "$backup"
    if ! sudo tee "$site" < "$next" >/dev/null ||
        ! sudo nginx -t || ! sudo systemctl reload nginx; then
        sudo cp -- "$backup" "$site"
        sudo nginx -t && sudo systemctl reload nginx
        return 1
    fi
    echo "==> Nginx 静态根目录: $PUBLIC_ROOT（旧配置备份: $backup）"
)

# 7) 后端 HTTP 就绪后才发布单文件网页，不让旧网页在构建失败时消失。
echo "==> 启动后端"
run sudo systemctl start "$SERVICE"
if ! $DRY_RUN; then
    ready=false
    for _ in $(seq 1 30); do
        if sudo systemctl is-active --quiet "$SERVICE" &&
            curl -fsS --max-time 1 http://127.0.0.1:8000/openapi.json >/dev/null 2>&1; then
            ready=true
            break
        fi
        sleep 1
    done
    if ! $ready; then
        echo "!! $SERVICE 未就绪，最近日志:"
        sudo journalctl -u "$SERVICE" -n 15 --no-pager || true
        exit 1
    fi
    echo "==> $SERVICE 的 HTTP 服务已就绪"
fi
SERVICE_STOPPED=false

if ! $SKIP_FRONTEND; then
    run mkdir -p "$PUBLIC_ROOT"
    run mv -f -- "$FRONTEND_STAGE/index.html" "$PUBLIC_ROOT/index.html"
    if $DRY_RUN; then
        FRONTEND_STAGE=
        echo "[dry-run] 迁移站点 $NGINX_SITE 的旧根目录至 $PUBLIC_ROOT，nginx -t 后重载"
    else
        migrate_nginx_root
    fi
fi

# 8) 查看状态
echo "==> 查看服务状态"
run sudo systemctl status "$SERVICE" --no-pager

if $DRY_RUN; then
    echo "==> dry-run 演练结束,未做任何改动"
else
    echo "==> 部署完成"
fi
