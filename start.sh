#!/bin/bash
# 风机齿轮箱智能故障诊断系统 — 一键启动脚本（Linux / macOS）

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "  风机齿轮箱智能故障诊断系统 — 一键启动"
echo "=========================================="
echo ""
echo "将依次启动：后端服务、边端采集、前端界面"
echo ""
read -p "按 Enter 键开始启动..."

# 启动后端
echo "[1/3] 启动云端后端..."
osascript -e 'tell app "Terminal" to do script "cd '"$ROOT/cloud"' && source venv/bin/activate && python -m app.main"' 2>/dev/null || \
  gnome-terminal -- bash -c "cd '$ROOT/cloud' && source venv/bin/activate && python -m app.main; exec bash" 2>/dev/null || \
  xterm -e "cd '$ROOT/cloud' && source venv/bin/activate && python -m app.main" 2>/dev/null || \
  (cd "$ROOT/cloud" && source venv/bin/activate && python -m app.main &)

sleep 4

# 启动边端
echo "[2/3] 启动边端采集..."
osascript -e 'tell app "Terminal" to do script "cd '"$ROOT/edge"' && source venv/bin/activate && python edge_client.py"' 2>/dev/null || \
  gnome-terminal -- bash -c "cd '$ROOT/edge' && source venv/bin/activate && python edge_client.py; exec bash" 2>/dev/null || \
  xterm -e "cd '$ROOT/edge' && source venv/bin/activate && python edge_client.py" 2>/dev/null || \
  (cd "$ROOT/edge" && source venv/bin/activate && python edge_client.py &)

sleep 2

# 启动前端
echo "[3/3] 启动前端界面..."
osascript -e 'tell app "Terminal" to do script "cd '"$ROOT/wind-turbine-diagnosis"' && npm run dev"' 2>/dev/null || \
  gnome-terminal -- bash -c "cd '$ROOT/wind-turbine-diagnosis' && npm run dev; exec bash" 2>/dev/null || \
  xterm -e "cd '$ROOT/wind-turbine-diagnosis' && npm run dev" 2>/dev/null || \
  (cd "$ROOT/wind-turbine-diagnosis" && npm run dev &)

echo ""
echo "=========================================="
echo "  三个服务已启动"
echo "  前端: http://localhost:3000"
echo "  API:  http://localhost:8000/docs"
echo "=========================================="
