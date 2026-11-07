# 边端交叉编译构建容器

按 [ADR-0002](../../docs/adr/0002-edge-crossbuild-cloud-systemd.md):边端(Rust,`dc24-edge`,目标树莓派)在 x64 开发机的 WSL Docker 内用与树莓派同源的环境交叉编译,产物二进制直接拷贝到树莓派运行。

> **绝不在树莓派上编译。** 树莓派只运行产物,不装 Rust 工具链、不跑 `cargo build`。

本目录(`deploy/edge/`)是构建封装,**对 Rust 边端源码目录零改动**;源码经 `docker build` 上下文只读复制进容器。

## 目录内容

| 文件 | 用途 |
|------|------|
| `Dockerfile` | 构建容器:官方 rust 镜像 + 交叉目标 + `cargo build --release --locked`;`export` 层导出产物,`test` 层可选跑测试 |
| `Dockerfile.dockerignore` | 作用于**构建上下文**(Rust 源码目录)的排除规则(`target/`、`.git/`),按 Dockerfile 名匹配(BuildKit),不放进源码目录 |
| `build.sh` | 一键构建,WSL / Linux 用 |
| `build.ps1` | 一键构建,Windows(Docker Desktop)用 |
| `out/` | 构建产物输出目录(已 gitignore),按目标三元组建子目录 |

## 前置条件

- x64 开发机上的 Docker:WSL 内引擎或 Docker Desktop(Windows),需带 **buildx/BuildKit**(`docker buildx version` 可用)——产物导出(`--output`)和按名匹配的 dockerignore 都依赖它。
- 首次构建需联网:拉取基础镜像 + crates.io 依赖。
- 本机无需安装 Rust 工具链,一切在容器内。

## 快速开始

```bash
# WSL / Linux(在 deploy/edge/ 下)
./build.sh              # ARM64(树莓派,默认)
./build.sh --with-tests # 先在容器内跑 cargo test --locked

# Windows(Docker Desktop 运行中)
.\build.ps1             # ARM64
.\build.ps1 -WithTests
```

脚本自动探测 Rust 边端源码目录(**当前为 `edge-rust/`,目录平移工单合入后为 `edge/`**,按 `Cargo.toml` 存在与否判断),并以该目录为构建上下文调用 docker。

### 等价的手动命令

```bash
# 在仓库根目录;上下文是 Rust 源码目录,不是仓库根
docker buildx build \
  -f deploy/edge/Dockerfile \
  --target export \
  --build-arg TARGET_TRIPLE=aarch64-unknown-linux-gnu \
  --output type=local,dest=deploy/edge/out/aarch64-unknown-linux-gnu \
  edge-rust/        # 目录平移后改为 edge/

# 可选:容器内测试(x86_64)
docker buildx build -f deploy/edge/Dockerfile --target test edge-rust/
```

## 目标架构

| TARGET_TRIPLE | 用途 | 说明 |
|---------------|------|------|
| `aarch64-unknown-linux-gnu`(默认) | **树莓派产物** | 树莓派 3/4/5 + 64 位 Raspberry Pi OS。容器装 `gcc-aarch64-linux-gnu` 做交叉链接(`ring` 的 C/汇编同样走它),产物为动态链接 glibc 的 ARM64 ELF |
| `x86_64-unknown-linux-gnu` | x64 本机构建 | 在 WSL/ECS 上本机试跑程序逻辑用,与 ARM64 产物分目录输出,互不覆盖 |

**glibc 兼容性:** 基础镜像 `rust:1-bookworm` 是 Debian 12(glibc 2.36),要求树莓派跑 Raspberry Pi OS **Bookworm 或更新**(同为 glibc ≥ 2.36)。若树莓派仍是 Bullseye,需要换 Bullseye 基础镜像(`--image rust:1-bullseye`)或改用 musl 静态目标(当前未提供,遇到时再评估)。

## 产物与部署

`out/<三元组>/` 下三件套:

| 产物 | 内容 |
|------|------|
| `dc24-edge` | 优化构建的二进制(release profile 已 `strip=true`,`lto=true`) |
| `config.example.json` | 配置样例(**无真实云端地址/密钥**,部署前改) |
| `dc24-edge.service` | systemd 服务模板(源自 Rust 边端源码目录 `deploy/`,本文只核对不改) |

### 与 `dc24-edge.service` 的路径核对

服务模板关键行与产物布局的对应关系(文件本体在 Rust 源码目录 `deploy/dc24-edge.service`,部署前需人工核实账号与路径):

| service 配置 | 要求的部署位置 |
|--------------|----------------|
| `ExecStart=/usr/local/bin/dc24-edge --config /etc/dc24-edge/config.json` | 二进制装到 **`/usr/local/bin/dc24-edge`**;配置放 **`/etc/dc24-edge/config.json`**(由产物 `config.example.json` 修改而来) |
| `EnvironmentFile=/etc/dc24-edge/edge.env` | 密钥文件 **`/etc/dc24-edge/edge.env`**,至少 `EDGE_API_KEY=...`(程序经 `api_key_env` 指定环境变量读取,默认变量名 `EDGE_API_KEY`) |
| `StateDirectory=dc24-edge` + `WorkingDirectory=/var/lib/dc24-edge` | systemd 自动创建 **`/var/lib/dc24-edge`**(采集数据落盘位置,勿手工改属主) |
| `User=nbclass` / `Group=nbclass` | 运行账号**需部署前核实存在**,不存在则改模板或建账号 |
| `KillSignal=SIGINT` / `TimeoutStopSec=200` | 停止时发 SIGINT,程序(ctrlc)优雅收尾、上传收尾文件;等待上限 200 s |
| `MemoryMax=192M` | 拟设的资源上限,**非实测占用**,1GB 树莓派适用性待真机核验 |

### 部署到树莓派的步骤

```bash
# 1. 传产物到树莓派(<pi> 为用户@主机)
scp deploy/edge/out/aarch64-unknown-linux-gnu/dc24-edge        pi@<pi>:/tmp/
scp deploy/edge/out/aarch64-unknown-linux-gnu/config.example.json pi@<pi>:/tmp/
scp deploy/edge/out/aarch64-unknown-linux-gnu/dc24-edge.service  pi@<pi>:/tmp/

# 2. 树莓派上就位(以下命令在树莓派执行,只装文件、不编译)
sudo install -m 0755 /tmp/dc24-edge /usr/local/bin/dc24-edge
sudo mkdir -p /etc/dc24-edge
sudo cp /tmp/config.example.json /etc/dc24-edge/config.json
sudoedit /etc/dc24-edge/config.json        # 填真实云端地址、边端身份、存储根目录
echo 'EDGE_API_KEY=<密钥>' | sudo tee /etc/dc24-edge/edge.env
sudo chmod 600 /etc/dc24-edge/config.json /etc/dc24-edge/edge.env
sudo cp /tmp/dc24-edge.service /etc/systemd/system/dc24-edge.service
#   User/Group=nbclass 不符实就先改模板

# 3. 校验后启动
file /usr/local/bin/dc24-edge   # 应显示: ELF 64-bit ... ARM aarch64 ... dynamically linked
dc24-edge --config /etc/dc24-edge/config.json --check   # 检查模式:只校验配置,不采集不上传
sudo systemctl daemon-reload
sudo systemctl enable --now dc24-edge
journalctl -u dc24-edge -f
```

在树莓派上只执行 `file`/`--check`/`systemctl` 这类运行与校验命令,不执行任何 `cargo`/`rustc` 命令。

## 容器内测试

`./build.sh --with-tests`(或 `.\build.ps1 -WithTests`)先执行 `--target test` 层:在 x86_64 容器内跑 `cargo test --locked`(含 `tests/end_to_end.rs` 回环模拟,不需外设)。这验证源码逻辑,**不等于 ARM64 二进制可运行**——ARM64 产物在 x64 容器内无法执行,跨架构运行需 qemu-user,未内置;最终行为以树莓派上 `--check` 与实机为准。

## 目录平移兼容

本目录所有文件均不含 Rust 源码目录名:构建上下文由脚本探测传入(当前 `edge-rust/`,平移工单合入后 `edge/`),`Dockerfile` 内只有 `/build` 这样的容器内路径。**目录平移后本目录零改动。** 文中以"Rust 边端源码目录"指代该目录。

## 本机验证状态(2026-11-07)

- 本机(Windows 11)+ WSL(Ubuntu-22.04)内均**未安装 Docker**(`docker` 命令不存在,Docker Desktop 未安装),`docker buildx build` 无法执行,**ARM64 构建在本机未实际验证**。
- Docker 就绪后的验证入口:`cd deploy/edge && ./build.sh --with-tests`,核对 `out/aarch64-unknown-linux-gnu/` 三件套与 `file` 输出。
- Rust 边端自述"完整构建与端到端测试尚未通过"(见 [edge-rust/README.md](../../edge-rust/README.md));本封装只负责构建容器,若源码现状编不过,构建会在 `cargo build` 一层如实失败并停在失败点,按工单 #52 口径这同样算交付——失败日志即记录。

## 常见问题

| 现象 | 处理 |
|------|------|
| `docker: command not found` / `docker buildx version` 失败 | 装 Docker(WSL 内引擎)或启动 Docker Desktop;老版本 Docker 无 buildx 时 `--output` 与 `Dockerfile.dockerignore` 均不可用 |
| 构建在 `cargo build` 层失败 | 先看是否源码自身问题(Rust 项目自述未通过完整构建);本封装不改源码,失败日志如实记录、停在失败点 |
| 树莓派上 `dc24-edge` 报 `GLIBC_2.xx not found` | 树莓派系统 glibc 低于基础镜像(Debian 12 / 2.36),见上文"glibc 兼容性"换基础镜像 |
| Windows 本机直接 `cargo build` 因中文路径链接失败 | Rust 项目 README 已知问题;本容器构建天然规避(容器内路径为 `/build`,不含中文) |
