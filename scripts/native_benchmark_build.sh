#!/usr/bin/env bash
# #106 独立 Linux 源码构建。仅操作显式隔离目录，不部署或改生产配置。
set -euo pipefail
source_root="$(cd "${1:?source directory required}" && pwd)"
artifact_root="${2:?independent artifact directory required}"
mode="${3:?wsl or ecs}"
mkdir -p "$artifact_root"
artifact_root="$(cd "$artifact_root" && pwd)"
config="$source_root/cloud/tests/diagnosis/benchmarks/native_performance_config.json"
read_config() { awk -F: -v key="\"$1\"" 'index($1,key) { gsub(/[, ]/,"",$2); print $2; exit }' "$config"; }
if [[ "$mode" == ecs ]]; then
    maximum="$(read_config ecs_build_memory_max_bytes)"
    margin="$(read_config ecs_available_margin_bytes)"
    available="$(awk '/MemAvailable:/ { print $2*1024 }' /proc/meminfo)"
    if (( available < maximum + margin )); then
        printf 'build not started: MemAvailable=%s < scope=%s + reserve=%s\n' "$available" "$maximum" "$margin" | tee "$artifact_root/build-not-started.txt"
        exit 3
    fi
    cpus=0,1
else
    maximum="$(read_config wsl_measurement_memory_max_bytes)"
    cpus=0,2
fi
uv_command="$(command -v uv)"
unit="cnn106-build-$(date +%s)-$$"
printf 'source=%s\nartifacts=%s\nunit=%s\nmemory_max=%s\nswap_max=0\ncpus=%s\n' "$source_root" "$artifact_root" "$unit" "$maximum" "$cpus" > "$artifact_root/build-plan.txt"
# 构建目录、环境、uv 缓存全部与主仓及其他 OS 分离；Ninja 仍 -j1。
systemd-run --quiet --wait --pipe --collect --unit="$unit" \
    --working-directory="$source_root" \
    --property="MemoryMax=$maximum" --property=MemorySwapMax=0 \
    --property=CPUQuota=200% --property="AllowedCPUs=$cpus" \
    --setenv="UV_PROJECT_ENVIRONMENT=$artifact_root/env" \
    --setenv="UV_CACHE_DIR=$artifact_root/uv-cache" \
    --setenv=CC=gcc --setenv=CXX=g++ --setenv=CNN_COMPUTE_ARCH=baseline \
    --setenv="CNN106_BUILD_ARTIFACTS=$artifact_root" \
    --setenv="CNN106_UV=$uv_command" \
    bash -c '
      set -euo pipefail
      group="/sys/fs/cgroup$(awk -F: '\''$1==0 {print $3}'\'' /proc/self/cgroup)"
      for name in memory.max memory.swap.max cpu.max cpuset.cpus.effective; do
        printf "%s=" "$name"; cat "$group/$name"
      done > "$CNN106_BUILD_ARTIFACTS/build-constraints.txt"
      status=0
      /usr/bin/time -v -o "$CNN106_BUILD_ARTIFACTS/build-time.txt" \
        "$CNN106_UV" sync --frozen --no-default-groups --group cloud --group benchmark \
        --config-setting "build-dir=$CNN106_BUILD_ARTIFACTS/cmake-build" || status=$?
      for name in memory.current memory.peak memory.events memory.swap.current cpu.stat; do
        printf "%s=" "$name"
        if test -f "$group/$name"; then cat "$group/$name"; else printf "unsupported\n"; fi
      done > "$CNN106_BUILD_ARTIFACTS/build-resources-after.txt"
      printf "%s\n" "$status" > "$CNN106_BUILD_ARTIFACTS/build-exit-status.txt"
      exit "$status"
    ' > "$artifact_root/build.stdout.txt" 2> "$artifact_root/build.stderr.txt"
printf 'Build completed; GNU time max RSS is a process/child high-water figure, not aggregate cgroup peak.\n'
