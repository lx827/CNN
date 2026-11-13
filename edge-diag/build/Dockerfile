# syntax=docker/dockerfile:1
# =============================================================================
# cnn_compute C++ 计算库 + edge-diag Rust CLI 的 aarch64 交叉构建容器
#
# 用途:在 x64 开发机的 WSL Docker 内,分两个 stage 交叉构建:
#   1) builder:Debian 交叉工具链按 cmake/toolchains/linux-aarch64.cmake
#      构建 libcnn_compute.so,并用 aarch64 gcc 冒烟编译/链接
#      capi/tests/consumer.c(x64 容器内不能运行 aarch64 二进制,
#      编译+链接成功即通过,运行验证在树莓派上做)。
#      构建命令与 docs/native_compute_distribution.md ARM64 节一致。
#   2) rust-builder:官方 rust 镜像(同为 Debian bookworm/glibc 2.36,与
#      builder 产物基线一致)对 edge-diag/ crate 执行
#      cargo build --release --locked(交叉模式同 deploy/edge/Dockerfile:
#      rustup 目标 aarch64-unknown-linux-gnu + gcc-aarch64-linux-gnu 链接器),
#      设 EDGE_DIAG_LIB 指向 builder 安装树,由 edge-diag/build.rs 注入
#      dylib=cnn_compute 链接指令;rpath=$ORIGIN 使导出的 edge-diag 与
#      .so 同目录即可直接运行(同 cnn_c_consumer 约定)。
#
# 用法(经 edge-diag/build/build.sh 调用;等价手动命令):
#   docker buildx build \
#     -f edge-diag/build/Dockerfile --target export \
#     --output type=local,dest=edge-diag/build/out/aarch64 \
#     --progress=plain <仓库根目录>
#
# 构建上下文白名单见 edge-diag/build/Dockerfile.dockerignore
# (lib/ capi/ cmake/ CMakeLists.txt 归 builder,edge-diag/ 归 rust-builder)。
# Eigen 为 FetchContent 固定来源与 SHA256,configure 阶段需联网;
# rust-builder 需联网拉取 crates.io 依赖(按已提交 Cargo.lock --locked 构建)。
#
# 基础镜像 Debian bookworm 交叉工具链针对 glibc 2.36:产物要求目标系统
# glibc >= 2.36,与树莓派 Pi 5 的 Debian 13 兼容;需钉死版本时
# --build-arg BASE_IMAGE=debian:bookworm-<snapshot>、
# --build-arg RUST_IMAGE=rust:<具体版本>-bookworm。
# =============================================================================

ARG BASE_IMAGE=debian:bookworm
ARG RUST_IMAGE=rust:1-bookworm
FROM ${BASE_IMAGE} AS builder

# 交叉与构建工具:
# - g++-aarch64-linux-gnu: aarch64 交叉 gcc/g++(toolchain 文件指定 aarch64-linux-gnu-gcc/g++)
# - libc6-dev-arm64-cross: 目标 libc/crt 头与库,缺它 CMake 编译器探针会误用宿主 x86 头
# - cmake>=3.28 与 ninja 按根 pyproject.toml 固定版本安装(bookworm apt 版 3.25 太老)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        gcc-aarch64-linux-gnu g++-aarch64-linux-gnu binutils-aarch64-linux-gnu \
        libc6-dev-arm64-cross \
        python3 python3-venv file ca-certificates; \
    rm -rf /var/lib/apt/lists/*; \
    python3 -m venv /opt/tools; \
    /opt/tools/bin/pip install --no-cache-dir cmake==4.4.4 ninja==1.13.2
ENV PATH=/opt/tools/bin:$PATH

WORKDIR /src
# 源码经构建上下文只读复制进容器,对宿主零改动
COPY . .

# 交叉构建 + 安装(Ninja 并行度固定 1,遵守仓库约定)
RUN set -eux; \
    cmake -S /src -B /tmp/build-aarch64 -G Ninja \
        -DCMAKE_TOOLCHAIN_FILE=/src/cmake/toolchains/linux-aarch64.cmake \
        -DCMAKE_BUILD_TYPE=Release \
        -DCNN_COMPUTE_BUILD_PYTHON=OFF \
        -DCMAKE_INSTALL_PREFIX=/opt/cnn-compute-aarch64 \
        -DCMAKE_INSTALL_LIBDIR=lib; \
    cmake --build /tmp/build-aarch64 --parallel 1; \
    cmake --install /tmp/build-aarch64

# 冒烟验证 + 产物汇总:用 aarch64 交叉 gcc 编译 capi/tests/consumer.c 并链接
# 安装树中的产物 .so。rpath=$ORIGIN 让导出的 consumer 与 .so 同目录即可直接运行。
RUN set -eux; \
    aarch64-linux-gnu-gcc -std=c11 /src/capi/tests/consumer.c \
        -I/opt/cnn-compute-aarch64/include \
        -L/opt/cnn-compute-aarch64/lib -lcnn_compute -lm \
        '-Wl,-rpath,$ORIGIN' \
        -o /tmp/cnn_c_consumer; \
    mkdir /export; \
    cp /opt/cnn-compute-aarch64/lib/libcnn_compute.so \
       /opt/cnn-compute-aarch64/include/cnn_compute.h \
       /tmp/cnn_c_consumer /export/; \
    file /export/*

# -----------------------------------------------------------------------------
# edge-diag Rust CLI 交叉构建层:官方 rust 镜像(Debian bookworm,与 builder
# 同 glibc 2.36,二进制与 libcnn_compute.so 运行时基线一致)。
# 交叉目标 aarch64-unknown-linux-gnu 的 gcc/binutils 与 libc 头文件/库:
# - 链接器(rustc 只调用 linker,自身不带 C 工具链)
# - 缺 libc6-dev-arm64-cross 时会误用宿主 x86 头文件
# (ARG RUST_IMAGE 声明在文件顶部,FROM 才能引用)
FROM ${RUST_IMAGE} AS rust-builder
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu \
        libc6-dev-arm64-cross file; \
    rm -rf /var/lib/apt/lists/*; \
    rustup target add aarch64-unknown-linux-gnu

# aarch64 交叉链接配置(cargo 读取;模式同 deploy/edge/Dockerfile)
ENV CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=aarch64-linux-gnu-gcc \
    CC_aarch64_unknown_linux_gnu=aarch64-linux-gnu-gcc \
    AR_aarch64_unknown_linux_gnu=aarch64-linux-gnu-ar \
    CARGO_TERM_COLOR=always

WORKDIR /src
# crate 源码经构建上下文只读复制进容器(白名单见 Dockerfile.dockerignore)
COPY edge-diag/ edge-diag/
# libcnn_compute.so 取自 builder 阶段安装树;EDGE_DIAG_LIB 由 edge-diag/build.rs
# 读取,注入 rustc-link-lib=dylib=cnn_compute 与该目录的链接搜索路径。
COPY --from=builder /opt/cnn-compute-aarch64/lib /opt/cnn-compute-aarch64/lib
ENV EDGE_DIAG_LIB=/opt/cnn-compute-aarch64/lib

# --locked:严格按已提交的 Cargo.lock 构建,禁止悄悄改依赖版本。
# rpath=$ORIGIN:导出后与 libcnn_compute.so 同目录直接运行(同 cnn_c_consumer)。
RUN set -eux; \
    RUSTFLAGS='-Clink-arg=-Wl,-rpath,$ORIGIN' \
    cargo build --release --locked --target aarch64-unknown-linux-gnu \
        --manifest-path edge-diag/Cargo.toml; \
    BIN=edge-diag/target/aarch64-unknown-linux-gnu/release/edge-diag; \
    file "$BIN"; \
    readelf -d "$BIN" | grep NEEDED

# -----------------------------------------------------------------------------
# 产物导出层:配合 buildx --output type=local 拷出到宿主 edge-diag/build/out/aarch64/
#   libcnn_compute.so  共享库(ARM64 ELF)
#   cnn_compute.h      C 头(与 .so 同源码版本配套升级)
#   cnn_c_consumer     C ABI 冒烟二进制(rpath=$ORIGIN,与 .so 同目录在树莓派上运行)
#   edge-diag          Rust CLI(动态链接 libcnn_compute.so,rpath=$ORIGIN)
# -----------------------------------------------------------------------------
FROM scratch AS export
COPY --from=builder /export/ /
COPY --from=rust-builder /src/edge-diag/target/aarch64-unknown-linux-gnu/release/edge-diag /edge-diag
