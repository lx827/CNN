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
)
from app.services.offline_monitor import offline_monitor_worker
from app.startup import init_database, create_initial_devices

logger = logging.getLogger(__name__)

# 信号量：一次只允许一个分析批次在运行，防止多批次并发导致内存爆掉
ANALYSIS_SEM = asyncio.Semaphore(1)


async def analysis_worker():
    """逐设备/批次串行调用唯一事务流程，不另写缓存或推断告警。"""
    from app.models import SensorData
    from app.services.diagnosis_workflow import process_batch
    while True:
        try:
            await asyncio.sleep(ANALYZE_INTERVAL_SECONDS)
            db = SessionLocal()
            try:
                pending = db.query(SensorData.device_id, SensorData.batch_index).filter(
                    SensorData.is_analyzed == 0,
                ).distinct().order_by(SensorData.device_id, SensorData.batch_index).all()
                for device_id, batch_index in pending:
                    device = db.query(Device).filter(Device.device_id == device_id).first()
                    if device is None or device.is_online == 0:
                        continue
                    try:
                        await process_batch(db, device, batch_index, semaphore=ANALYSIS_SEM)
                    except Exception:
                        db.rollback()
                        logger.exception("批次诊断失败: %s/%s", device_id, batch_index)
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("后台分析循环失败")


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
