"""
应用生命周期管理
包含 lifespan、后台分析 worker 和线程池配置
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.database import SessionLocal
from app.models import Device
from app.core.config import (
    ANALYZE_INTERVAL_SECONDS,
    SENSOR_SAMPLE_RATE,
    SENSOR_WINDOW_SECONDS,
)
from datetime import datetime
from app.core.websocket import manager
from app.services.analyzer import analyze_device
from app.services.diagnosis.features import compute_channel_features
from app.services.alarms import generate_alarms
from app.services.offline_monitor import offline_monitor_worker
from app.startup import init_database, create_initial_devices

logger = logging.getLogger(__name__)

# 信号量：一次只允许一个分析批次在运行，防止多批次并发导致内存爆掉
ANALYSIS_SEM = asyncio.Semaphore(1)


async def analysis_worker():
    """
    后台协程：扫描所有设备的未检测批次，执行分析，标记为已检测
    """
    from app.models import SensorData, Diagnosis

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
                    logger.info("[分析服务] 没有待检测数据，跳过")
                    continue

                for (device_id,) in devices_with_pending:
                    # 获取设备配置，离线设备直接跳过，防止旧数据触发异常监测
                    device = db.query(Device).filter(Device.device_id == device_id).first()
                    if not device or not device.is_online:
                        logger.info(f"[分析服务] {device_id} 当前离线，跳过未分析批次")
                        continue

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

                        expected_channels = device.channel_count if device else 3
                        sample_rate = device.sample_rate if device else SENSOR_SAMPLE_RATE

                        if len(records) < expected_channels:
                            logger.warning(
                                f"[分析服务] {device_id} 批次 {batch_index} "
                                f"通道不完整 ({len(records)}/{expected_channels})，跳过"
                            )
                            continue

                        # 组装通道数据
                        channels_data = {}
                        for r in records:
                            channels_data[f"ch{r.channel}"] = r.data

                        # 执行分析（传入 device 以获取齿轮/轴承参数）
                        # CPU 密集型计算放到线程池，避免阻塞 asyncio 事件循环
                        # Semaphore 确保一次只分析一个批次
                        async with ANALYSIS_SEM:
                            result = await asyncio.to_thread(analyze_device, channels_data, sample_rate, device)

                        # 写入诊断结果（关联到批次）
                        diag = Diagnosis(
                            device_id=device_id,
                            batch_index=batch_index,
                            health_score=result["health_score"],
                            fault_probabilities=result["fault_probabilities"],
                            imf_energy=result["imf_energy"],
                            order_analysis=result.get("order_analysis"),
                            rot_freq=result.get("rot_freq"),
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

                        # 计算通道级振动特征（CPU 密集型，放入线程池）
                        # 复用同一个 Semaphore，确保和 analyze_device 串行执行
                        channel_features = {}
                        async with ANALYSIS_SEM:
                            for ch_key, signal in channels_data.items():
                                channel_features[ch_key] = await asyncio.to_thread(compute_channel_features, signal)

                        # 提取通道级诊断结果（含齿轮/轴承详细指标）
                        channel_diagnosis = result.get("order_analysis", {}).get("channels", {})

                        # 生成告警（通道级 + 设备级），关联到当前批次
                        generate_alarms(
                            db, device_id,
                            result["health_score"],
                            result["fault_probabilities"],
                            channel_features,
                            batch_index=batch_index,
                            order_analysis=result.get("order_analysis"),
                            channel_diagnosis=channel_diagnosis,
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

                        logger.info(
                            f"[分析服务] {device_id} 批次 {batch_index} 分析完成，"
                            f"健康度: {result['health_score']}, 状态: {result['status']}"
                        )

            except Exception as e:
                logger.error(f"[分析服务] 异常: {e}", exc_info=True)
            finally:
                db.close()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[分析服务] 严重异常: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用启动和关闭时的生命周期事件
    """
    # 启动时：初始化数据库 + 插入默认设备
    logger.info("[启动] 初始化数据库...")
    init_database()
    create_initial_devices()

    # 限制全局默认线程池为 2 个线程（阿里云 2核2G 必须严格控制）
    # 所有 asyncio.to_thread / loop.run_in_executor(None, ...) 都会使用此线程池
    cpu_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cpu_worker")
    loop = asyncio.get_running_loop()
    loop.set_default_executor(cpu_executor)
    logger.info("[启动] CPU 线程池已限制为 max_workers=2")

    # 启动后台分析任务
    analysis_task = asyncio.create_task(analysis_worker())
    logger.info("[启动] 后台分析任务已启动")

    # 启动离线监测任务（独立协程，与 analysis_worker 并列）
    offline_task = asyncio.create_task(offline_monitor_worker())
    logger.info("[启动] 离线监测任务已启动")

    yield  # 应用运行期间

    # 关闭时
    analysis_task.cancel()
    offline_task.cancel()
    cpu_executor.shutdown(wait=True)
    logger.info("[关闭] 后台任务已停止，CPU 线程池已关闭")
