#!/usr/bin/env bash
# =============================================================================
# cnn_compute aarch64 交叉构建一键入口 —— Windows Git Bash / PowerShell(wsl) / WSL 用
#
# 在 WSL Docker 容器内按 cmake/toolchains/linux-aarch64.cmake 交叉构建
# libcnn_compute.so,并在容器内用 aarch64 gcc 冒烟编译/链接 capi/tests/consumer.c
# (x64 容器不运行 aarch64 二进制,编译+链接成功即通过;运行验证在树莓派上做)。
# 产物导出到 edge-diag/build/out/aarch64/:libcnn_compute.so、cnn_compute.h、
# cnn_c_consumer(rpath=$ORIGIN,与 .so 同目录在 Pi 上直接运行)。
#
# 用法:
#   bash edge-diag/build/build.sh            # Windows Git Bash(自动转 WSL 默认发行版)
#   wsl bash edge-diag/build/build.sh        # PowerShell(经 wsl 进入默认发行版)
#   ./build.sh                               # 已在 WSL/Linux 内
#   ./build.sh --image debian:bookworm       # 钉死基础镜像
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

BASE_IMAGE="debian:bookworm"
while [ $# -gt 0 ]; do
    case "$1" in
        --image) BASE_IMAGE="$2"; shift 2 ;;
        -h|--help) sed -n '11,16p' "$0"; exit 0 ;;
        *) echo "未知参数: $1(见 --help)" >&2; exit 2 ;;
    esac
done

case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        # Windows Git Bash:docker 在 WSL 内,转进 WSL 默认发行版重跑本脚本
        wsl_root="$(printf '%s' "$ROOT_DIR" | sed 's|^/\([a-zA-Z]\)/|/mnt/\L\1/|')"
        exec wsl.exe bash -c "cd '$wsl_root' && exec bash edge-diag/build/build.sh --image '$BASE_IMAGE'"
        ;;
esac

if ! command -v docker >/dev/null 2>&1; then
    echo "错误:docker 不可用。请在 WSL 内安装并启动 Docker 后重试。" >&2
    exit 1
fi
if ! docker buildx version >/dev/null 2>&1; then
    echo "错误:docker buildx 不可用(--output 导出与按名匹配 dockerignore 均依赖 BuildKit)。" >&2
    exit 1
fi

OUT_DIR="$SCRIPT_DIR/out/aarch64"
mkdir -p "$OUT_DIR"

echo "==> 上下文   : $ROOT_DIR"
echo "==> 基础镜像 : $BASE_IMAGE"
echo "==> 产物目录 : $OUT_DIR"

echo "==> 容器内交叉构建 libcnn_compute.so(aarch64)..."
docker buildx build \
    -f "$SCRIPT_DIR/Dockerfile" \
    --target export \
    --build-arg BASE_IMAGE="$BASE_IMAGE" \
    --output "type=local,dest=$OUT_DIR" \
    --progress=plain \
    "$ROOT_DIR"

for artifact in libcnn_compute.so cnn_compute.h cnn_c_consumer; do
    [ -f "$OUT_DIR/$artifact" ] || { echo "错误:缺少预期产物 $OUT_DIR/$artifact" >&2; exit 1; }
done

echo "==> 产物:"
ls -lh "$OUT_DIR"
if command -v file >/dev/null 2>&1; then
    file "$OUT_DIR"/*
fi
echo "完成。cnn_c_consumer 的运行验证在树莓派上做(与 libcnn_compute.so 同目录直接执行)。"
