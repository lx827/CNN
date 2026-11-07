# syntax=docker/dockerfile:1
# =============================================================================
# 边端(Rust, dc24-edge)交叉编译构建容器
#
# 用途:在 x64 开发机(WSL Docker)内,用与树莓派同源的环境交叉编译出
#       ARM64 (aarch64) 二进制,产物拷贝到树莓派运行 —— 绝不在树莓派上编译。
#       见 docs/adr/0002-edge-crossbuild-cloud-systemd.md 与 deploy/edge/README.md
#
# 用法(构建上下文 = Rust 边端源码目录,不是仓库根目录):
#   docker buildx build \
#     -f deploy/edge/Dockerfile \
#     --target export \
#     --build-arg TARGET_TRIPLE=aarch64-unknown-linux-gnu \
#     --output type=local,dest=deploy/edge/out/aarch64-unknown-linux-gnu \
#     <Rust 源码目录>          # 当前为 edge-rust/,平移工单合入后为 edge/
#
# 说明:本 Dockerfile 不含任何源码目录名(源码通过构建上下文只读复制进来),
#       目录平移(edge-rust/ -> edge/)后无需改动本文件。
# =============================================================================

# 基础镜像:官方 rust(Debian bookworm,自带 x86_64 原生 gcc)。
# 需要完全可复现时可用 --build-arg RUST_IMAGE=rust:<具体版本>-bookworm 钉死。
ARG RUST_IMAGE=rust:1-bookworm
FROM ${RUST_IMAGE} AS builder

# 目标三元组:
#   aarch64-unknown-linux-gnu —— 树莓派 64 位(默认)
#   x86_64-unknown-linux-gnu  —— x64 本机构建(WSL/ECS 上试跑)
ARG TARGET_TRIPLE=aarch64-unknown-linux-gnu

# 交叉目标需要 aarch64 的 gcc/binutils:
# - 链接器(rustc 只调用 linker,自身不带 C 工具链)
# - ring 0.17(rustls 后端)含 C/汇编,由 cc 构建脚本编译,同样走交叉 gcc
RUN set -eux; \
    if [ "$TARGET_TRIPLE" = "aarch64-unknown-linux-gnu" ]; then \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu; \
        rm -rf /var/lib/apt/lists/*; \
    fi; \
    rustup target add "$TARGET_TRIPLE"

# aarch64 交叉链接配置( cargo 与 cc 均读取;对 x86_64 原生目标无影响 )
ENV CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=aarch64-linux-gnu-gcc \
    CC_aarch64_unknown_linux_gnu=aarch64-linux-gnu-gcc \
    AR_aarch64_unknown_linux_gnu=aarch64-linux-gnu-ar \
    CARGO_TERM_COLOR=always

WORKDIR /build
# 源码经构建上下文复制进容器(对宿主只读,不改源文件)。
# 排除项见同目录 Dockerfile.dockerignore(BuildKit 按 Dockerfile 名匹配):
# target/ 本地构建缓存、.git/ 不进上下文。
COPY . .

# --locked:严格按已提交的 Cargo.lock 构建,禁止悄悄改依赖版本。
RUN cargo build --release --locked --target "$TARGET_TRIPLE"

# -----------------------------------------------------------------------------
# 可选测试层:x86_64 容器内跑 cargo test --locked(端到端回环测试,不需外设)。
#   docker buildx build --target test <Rust 源码目录>
# 注意:ARM64 产物无法在 x64 容器内直接执行;跨架构跑测试需 qemu-user,未内置。
# -----------------------------------------------------------------------------
FROM builder AS test
RUN cargo test --locked

# -----------------------------------------------------------------------------
# 产物导出层:配合 buildx --output type=local 把部署所需文件拷出到宿主。
# 产物三件套:二进制 + 配置样例 + systemd 服务模板,布局见 deploy/edge/README.md
# -----------------------------------------------------------------------------
FROM scratch AS export
ARG TARGET_TRIPLE=aarch64-unknown-linux-gnu
COPY --from=builder /build/target/${TARGET_TRIPLE}/release/dc24-edge /dc24-edge
COPY --from=builder /build/config.example.json /config.example.json
COPY --from=builder /build/deploy/dc24-edge.service /dc24-edge.service
