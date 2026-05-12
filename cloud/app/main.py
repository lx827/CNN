"""
FastAPI 应用入口
启动命令：python -m app.main
"""
import logging

from fastapi import FastAPI, Depends
from app.core.memory_log import setup_memory_logging

from app.api import ingest, dashboard, monitor, diagnosis, alarms, devices, collect, auth, system
from app.api.data_view import router as data_view_router
from app.api.auth import optional_auth
from app.lifespan import lifespan
from app.middleware import setup_cors, setup_static_files
from app.core.websocket import manager

# 启动时即初始化内存日志捕获，确保所有 print/logging 输出都被前端可见
setup_memory_logging(capacity=2000, level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== 创建 FastAPI 应用 ====================
app = FastAPI(
    title="风机齿轮箱智能故障诊断系统 - 云端 API",
    description="边端上传数据 → 云端分析诊断 → 前端展示",
    version="1.0.0",
    lifespan=lifespan,
)

# 中间件配置
setup_cors(app)
setup_static_files(app)

# 注册路由
# 认证接口不需要登录保护
app.include_router(auth.router)
# 边端数据接入需要 X-Edge-Key 认证
app.include_router(ingest.router, dependencies=[Depends(optional_auth)])

# 需要认证的路由（前端 Bearer Token 或边端 X-Edge-Key）
app.include_router(dashboard.router, dependencies=[Depends(optional_auth)])
app.include_router(monitor.router, dependencies=[Depends(optional_auth)])
app.include_router(diagnosis.router, dependencies=[Depends(optional_auth)])
app.include_router(alarms.router, dependencies=[Depends(optional_auth)])
app.include_router(devices.router, dependencies=[Depends(optional_auth)])
app.include_router(data_view_router, dependencies=[Depends(optional_auth)])
app.include_router(collect.router, dependencies=[Depends(optional_auth)])
app.include_router(system.router, dependencies=[Depends(optional_auth)])


# WebSocket 实时推送端点
@app.websocket("/ws/monitor")
async def websocket_endpoint(websocket):
    await manager.connect(websocket)
    try:
        while True:
            # 保持连接，接收前端心跳（可选）
            data = await websocket.receive_text()
            # 可以解析心跳并回复
            await websocket.send_text('{"type":"pong"}')
    except Exception:
        manager.disconnect(websocket)


@app.get("/")
def root():
    return {
        "message": "风机齿轮箱智能故障诊断系统 API 服务运行中",
        "docs": "/docs",
    }


# 直接运行入口
if __name__ == "__main__":
    import uvicorn
    from app.core.config import API_HOST, API_PORT
    uvicorn.run("app.main:app", host=API_HOST, port=API_PORT, reload=True)
