"""
FastAPI 应用入口
启动命令：python -m app.main
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, SessionLocal
from app.models import Device
from app.core.config import (
    ANALYZE_INTERVAL_SECONDS,
    DEVICE_ID,
    DEVICE_NAME,
    SENSOR_SAMPLE_RATE,
    SENSOR_WINDOW_SECONDS,
)
from app.api import ingest, dashboard, monitor, diagnosis, alarms, devices, data_view, collect, auth
from app.api.auth import get_current_user
from fastapi import Depends
from app.core.websocket import manager
from app.services.analyzer import analyze_device, compute_channel_features
from app.services.alarm_service import generate_alarms


# ==================== 后台分析任务 ====================
async def analysis_worker():
    """
    后台协程：扫描所有设备的未检测批次，执行分析，标记为已检测
    """
    from app.models import SensorData, Diagnosis
    from datetime import datetime

    while True:
        try:
            await asyncio.sleep(ANALYZE_INTERVAL_SECONDS)

            db = SessionLocal()
            try:
                # 查询所有存在未分析数据的设备
                devices_with_pending = db.query(SensorData.device_id).filter(
                    SensorData.is_analyzed == 0
                ).distinct().all()

                if not devices_with_pending:
                    print("[分析服务] 没有待检测数据，跳过")
                    continue

                for (device_id,) in devices_with_pending:
                    # 获取该设备所有未分析的批次号
                    pending_batches = db.query(SensorData.batch_index).filter(
                        SensorData.device_id == device_id,
                        SensorData.is_analyzed == 0
                    ).distinct().all()

                    for (batch_index,) in pending_batches:
                        # 读取该批次所有通道的数据
                        records = db.query(SensorData).filter(
                            SensorData.device_id == device_id,
                            SensorData.batch_index == batch_index
                        ).all()

                        # 获取设备配置（通道数、采样率）
                        device = db.query(Device).filter(Device.device_id == device_id).first()
                        expected_channels = device.channel_count if device else 3
                        sample_rate = device.sample_rate if device else SENSOR_SAMPLE_RATE

                        if len(records) < expected_channels:
                            print(f"[分析服务] {device_id} 批次 {batch_index} 通道不完整 ({len(records)}/{expected_channels})，跳过")
                            continue

                        # 组装通道数据
                        channels_data = {}
                        for r in records:
                            channels_data[f"ch{r.channel}"] = r.data

                        # 执行分析
                        result = analyze_device(channels_data, sample_rate)

                        # 写入诊断结果（关联到批次）
                        diag = Diagnosis(
                            device_id=device_id,
                            batch_index=batch_index,
                            health_score=result["health_score"],
                            fault_probabilities=result["fault_probabilities"],
                            imf_energy=result["imf_energy"],
                            status=result["status"],
                            analyzed_at=datetime.utcnow(),
                        )
                        db.add(diag)

                        # 标记该批次所有记录为已检测
                        for r in records:
                            r.is_analyzed = 1
                            r.analyzed_at = datetime.utcnow()

                        # 更新设备健康度
                        if device:
                            device.health_score = result["health_score"]
                            device.status = result["status"]

                        db.commit()

                        # 计算通道级振动特征
                        channel_features = {}
                        for ch_key, signal in channels_data.items():
                            channel_features[ch_key] = compute_channel_features(signal)

                        # 生成告警（通道级 + 设备级）
                        generate_alarms(
                            db, device_id,
                            result["health_score"],
                            result["fault_probabilities"],
                            channel_features
                        )

                        # WebSocket 推送
                        await manager.broadcast({
                            "type": "diagnosis_update",
                            "data": {
                                "device_id": device_id,
                                "batch_index": batch_index,
                                "health_score": result["health_score"],
                                "status": result["status"],
                                "fault_probabilities": result["fault_probabilities"],
                                "imf_energy": result["imf_energy"],
                            }
                        })

                        print(f"[分析服务] {device_id} 批次 {batch_index} 分析完成，健康度: {result['health_score']}, 状态: {result['status']}")

            except Exception as e:
                print(f"[分析服务] 异常: {e}")
            finally:
                db.close()

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[分析服务] 严重异常: {e}")


# ==================== 生命周期管理 ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用启动和关闭时的生命周期事件
    """
    # 启动时：初始化数据库 + 插入默认设备
    print("[启动] 初始化数据库...")
    init_db()

    db = SessionLocal()
    try:
        # 预定义多个模拟设备
        default_devices = [
            {
                "device_id": "WTG-001",
                "name": "风机齿轮箱 #01",
                "location": "某风电场 A 区 03 号机组",
                "health_score": 87,
                "status": "normal",
                "runtime_hours": 3456,
            },
            {
                "device_id": "WTG-002",
                "name": "风机齿轮箱 #02",
                "location": "某风电场 A 区 04 号机组",
                "health_score": 92,
                "status": "normal",
                "runtime_hours": 2890,
            },
            {
                "device_id": "WTG-003",
                "name": "风机齿轮箱 #03",
                "location": "某风电场 A 区 05 号机组",
                "health_score": 65,
                "status": "warning",
                "runtime_hours": 4102,
            },
            {
                "device_id": "WTG-004",
                "name": "风机齿轮箱 #04",
                "location": "某风电场 B 区 01 号机组",
                "health_score": 78,
                "status": "normal",
                "runtime_hours": 1567,
            },
            {
                "device_id": "WTG-005",
                "name": "风机齿轮箱 #05",
                "location": "某风电场 B 区 02 号机组",
                "health_score": 45,
                "status": "fault",
                "runtime_hours": 5234,
            },
        ]

        for dev_info in default_devices:
            existing = db.query(Device).filter(Device.device_id == dev_info["device_id"]).first()
            if not existing:
                device = Device(
                    device_id=dev_info["device_id"],
                    name=dev_info["name"],
                    location=dev_info["location"],
                    channel_count=3,
                    channel_names={"1": "轴承附近", "2": "驱动端", "3": "风扇端"},
                    sample_rate=SENSOR_SAMPLE_RATE,
                    window_seconds=SENSOR_WINDOW_SECONDS,
                    health_score=dev_info["health_score"],
                    status=dev_info["status"],
                    runtime_hours=dev_info["runtime_hours"],
                    upload_interval=10,
                    task_poll_interval=5,
                )
                db.add(device)
                print(f"[启动] 创建设备: {dev_info['device_id']} (健康度 {dev_info['health_score']}, 状态 {dev_info['status']})")

        db.commit()
    finally:
        db.close()

    # 启动后台分析任务
    task = asyncio.create_task(analysis_worker())
    print("[启动] 后台分析任务已启动")

    yield  # 应用运行期间

    # 关闭时
    task.cancel()
    print("[关闭] 后台分析任务已停止")


# ==================== 创建 FastAPI 应用 ====================
app = FastAPI(
    title="风机齿轮箱智能故障诊断系统 - 云端 API",
    description="边端上传数据 → 云端分析诊断 → 前端展示",
    version="1.0.0",
    lifespan=lifespan,
)

# 允许前端跨域访问（开发环境）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
# 认证和边端数据接入不需要登录保护
app.include_router(auth.router)
app.include_router(ingest.router)

# 前端页面调用的接口需要 Bearer Token 认证
app.include_router(dashboard.router, dependencies=[Depends(get_current_user)])
app.include_router(monitor.router, dependencies=[Depends(get_current_user)])
app.include_router(diagnosis.router, dependencies=[Depends(get_current_user)])
app.include_router(alarms.router, dependencies=[Depends(get_current_user)])
app.include_router(devices.router, dependencies=[Depends(get_current_user)])
app.include_router(data_view.router, dependencies=[Depends(get_current_user)])
app.include_router(collect.router, dependencies=[Depends(get_current_user)])


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
