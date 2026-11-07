#!/usr/bin/env bash
# =============================================================================
# 边端(Rust, dc24-edge)交叉编译一键构建 —— WSL / Linux 用
# 在 Docker 容器内交叉编译,产物导出到 deploy/edge/out/<目标三元组>/。
# 绝不在树莓派上编译(ADR-0002)。详细说明:deploy/edge/README.md
#
# 用法:
#   ./build.sh                          # ARM64(树莓派,默认)
#   ./build.sh --target x86_64-unknown-linux-gnu   # x64 本机
#   ./build.sh --with-tests             # 先在容器内跑 cargo test --locked
#   ./build.sh --image rust:1.93-bookworm         # 钉死基础镜像版本
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

TARGET_TRIPLE="aarch64-unknown-linux-gnu"
RUST_IMAGE="rust:1-bookworm"
RUN_TESTS=0

while [ $# -gt 0 ]; do
    case "$1" in
        --target) TARGET_TRIPLE="$2"; shift 2 ;;
        --image)  RUST_IMAGE="$2"; shift 2 ;;
        --with-tests) RUN_TESTS=1; shift ;;
        -h|--help)
            sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "未知参数: $1(见 --help)" >&2; exit 2 ;;
    esac
done

# Rust 源码目录:当前为 edge-rust/,平移工单合入后为 edge/。自动探测。
SRC_DIR=""
for cand in "$ROOT_DIR/edge-rust" "$ROOT_DIR/edge"; do
    [ -f "$cand/Cargo.toml" ] && SRC_DIR="$cand" && break
done
if [ -z "$SRC_DIR" ]; then
    echo "错误:未找到 Rust 边端源码目录(需含 Cargo.toml,尝试 edge-rust/ 与 edge/)" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "错误:docker 不可用。请在 WSL 内安装 Docker 或启动 Docker Desktop 后重试。" >&2
    exit 1
fi
if ! docker buildx version >/dev/null 2>&1; then
    echo "错误:docker buildx 不可用(--output 导出与按名匹配 dockerignore 均依赖 BuildKit)。" >&2
    exit 1
fi

OUT_DIR="$SCRIPT_DIR/out/$TARGET_TRIPLE"
mkdir -p "$OUT_DIR"

echo "==> 源码目录 : $SRC_DIR"
echo "==> 目标     : $TARGET_TRIPLE"
echo "==> 基础镜像 : $RUST_IMAGE"
echo "==> 产物目录 : $OUT_DIR"

# 可选:容器内(x86_64)跑测试,验证源码逻辑,与 ARM64 产物构建互不影响
if [ "$RUN_TESTS" = "1" ]; then
    echo "==> cargo test --locked(容器内)..."
    docker buildx build \
        -f "$SCRIPT_DIR/Dockerfile" \
        --target test \
        --build-arg RUST_IMAGE="$RUST_IMAGE" \
        --progress=plain \
        "$SRC_DIR"
fi

echo "==> cargo build --release --locked --target $TARGET_TRIPLE(容器内)..."
docker buildx build \
    -f "$SCRIPT_DIR/Dockerfile" \
    --target export \
    --build-arg TARGET_TRIPLE="$TARGET_TRIPLE" \
    --build-arg RUST_IMAGE="$RUST_IMAGE" \
    --output "type=local,dest=$OUT_DIR" \
    --progress=plain \
    "$SRC_DIR"

echo "==> 产物:"
ls -lh "$OUT_DIR"
if command -v file >/dev/null 2>&1; then
    file "$OUT_DIR/dc24-edge" || true
fi

echo "完成。部署到树莓派的步骤见 deploy/edge/README.md。"
