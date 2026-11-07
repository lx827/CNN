# =============================================================================
# 边端(Rust, dc24-edge)交叉编译一键构建 —— Windows 用(需 Docker Desktop)
# 在 Docker 容器内交叉编译,产物导出到 deploy\edge\out\<目标三元组>\。
# 绝不在树莓派上编译(ADR-0002)。详细说明:deploy/edge/README.md
#
# 用法:
#   .\build.ps1                       # ARM64(树莓派,默认)
#   .\build.ps1 -TargetTriple x86_64-unknown-linux-gnu   # x64 本机
#   .\build.ps1 -WithTests            # 先在容器内跑 cargo test --locked
#   .\build.ps1 -RustImage rust:1.93-bookworm            # 钉死基础镜像版本
# =============================================================================
[CmdletBinding()]
param(
    [string]$TargetTriple = "aarch64-unknown-linux-gnu",
    [string]$RustImage = "rust:1-bookworm",
    [switch]$WithTests
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path

# Rust 源码目录:当前为 edge-rust/,平移工单合入后为 edge/。自动探测。
$SrcDir = $null
foreach ($cand in @((Join-Path $RootDir "edge-rust"), (Join-Path $RootDir "edge"))) {
    if (Test-Path (Join-Path $cand "Cargo.toml")) { $SrcDir = $cand; break }
}
if (-not $SrcDir) {
    throw "未找到 Rust 边端源码目录(需含 Cargo.toml,尝试 edge-rust\ 与 edge\)"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker 不可用。请安装/启动 Docker Desktop 后重试。"
}
docker buildx version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "docker buildx 不可用(--output 导出与按名匹配 dockerignore 均依赖 BuildKit)。"
}

$OutDir = Join-Path $ScriptDir "out\$TargetTriple"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "==> 源码目录 : $SrcDir"
Write-Host "==> 目标     : $TargetTriple"
Write-Host "==> 基础镜像 : $RustImage"
Write-Host "==> 产物目录 : $OutDir"

# 可选:容器内(x86_64)跑测试,验证源码逻辑,与 ARM64 产物构建互不影响
if ($WithTests) {
    Write-Host "==> cargo test --locked(容器内)..."
    docker buildx build `
        -f (Join-Path $ScriptDir "Dockerfile") `
        --target test `
        --build-arg "RUST_IMAGE=$RustImage" `
        --progress=plain `
        $SrcDir
    if ($LASTEXITCODE -ne 0) { throw "cargo test 失败(退出码 $LASTEXITCODE)。" }
}

Write-Host "==> cargo build --release --locked --target $TargetTriple(容器内)..."
docker buildx build `
    -f (Join-Path $ScriptDir "Dockerfile") `
    --target export `
    --build-arg "TARGET_TRIPLE=$TargetTriple" `
    --build-arg "RUST_IMAGE=$RustImage" `
    --output "type=local,dest=$OutDir" `
    --progress=plain `
    $SrcDir
if ($LASTEXITCODE -ne 0) { throw "构建失败(退出码 $LASTEXITCODE)。" }

Write-Host "==> 产物:"
Get-ChildItem $OutDir | Format-Table Name, Length, LastWriteTime -AutoSize

$Binary = Join-Path $OutDir "dc24-edge"
if (-not (Test-Path $Binary)) {
    throw "未找到预期产物 $Binary"
}

Write-Host "完成。部署到树莓派的步骤见 deploy/edge/README.md。"
