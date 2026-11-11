#!/usr/bin/env bash
# 一键部署:交叉编译产物 + 三件套 → 树莓派 ~/edge-cnn,并重启 dc24-edge 服务
#
# 用法(WSL,产物已构建):
#   bash edge/deploy/pi/deploy_pi.sh <pi-host>          # 如 192.168.97.37
#   SUDO_PW=xxx bash edge/deploy/pi/deploy_pi.sh <host> # sudo 密码非默认时
#
# 前置:deploy/edge/out/aarch64-unknown-linux-gnu/dc24-edge 已构建(WSL: cd deploy/edge && bash build.sh)
# 行为:树莓派上已存在的 ~/edge-cnn/edge.env(真实密钥)不会被覆盖;不存在时生成占位并提示。
set -euo pipefail

HOST="${1:?用法: deploy_pi.sh <pi-host>}"
SUDO_PW="${SUDO_PW:-666}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
OUT="$ROOT/deploy/edge/out/aarch64-unknown-linux-gnu"
PI_DIR='$HOME/edge-cnn'

[ -f "$OUT/dc24-edge" ] || { echo "未找到 $OUT/dc24-edge;先在 WSL 执行: cd deploy/edge && bash build.sh"; exit 1; }

echo "==> 上传二进制与三件套到 $HOST"
scp "$OUT/dc24-edge" "$HOST:/tmp/dc24-edge.new"
scp "$ROOT/edge/deploy/pi/config.json" "$ROOT/edge/deploy/pi/dc24-edge.service" "$HOST:/tmp/"

echo "==> 就位 ~/edge-cnn(保留已有 edge.env)并重启服务"
ssh "$HOST" "mkdir -p $PI_DIR && { [ -f $PI_DIR/edge.env ] || { printf 'EDGE_API_KEY=CHANGE_ME\n' > $PI_DIR/edge.env; chmod 600 $PI_DIR/edge.env; echo '!! 已生成占位 edge.env,请填 ECS cloud/.env 里的真实 EDGE_API_KEY'; }; } \
  && mv /tmp/dc24-edge.new $PI_DIR/dc24-edge && chmod 755 $PI_DIR/dc24-edge \
  && mv /tmp/config.json $PI_DIR/config.json \
  && printf '%s\n' '$SUDO_PW' | sudo -S cp /tmp/dc24-edge.service /etc/systemd/system/dc24-edge.service \
  && printf '%s\n' '$SUDO_PW' | sudo -S systemctl daemon-reload \
  && printf '%s\n' '$SUDO_PW' | sudo -S systemctl enable --now dc24-edge \
  && printf '%s\n' '$SUDO_PW' | sudo -S systemctl restart dc24-edge \
  && sleep 3 && systemctl is-active dc24-edge && echo '部署完成'"

echo "==> 最近日志(Ctrl-C 退出)"
ssh "$HOST" "journalctl -u dc24-edge -n 10 --no-pager"
