"""
数据接入接口
边端（edge_client.py）通过 HTTP POST 调用这里上传传感器数据

核心逻辑：
  1. 支持压缩模式和原图模式
  2. 普通数据：每个设备最多保留 16 个批次，新数据覆盖最旧批次
  3. 特殊数据：手动触发采集，batch_index 从 101 起自增，永不覆盖
  4. 同一批次所有通道共享 batch_index
  5. 插入时 is_analyzed = 0，等待分析服务检测
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import SensorData, Device
from app.core.websocket import manager
import asyncio
from datetime import datetime
import base64
import zlib

router = APIRouter(prefix="/api/ingest", tags=["数据接入"])

MAX_BATCHES_NORMAL = 16       # 普通数据最多保留 16 个批次
SPECIAL_BATCH_START = 100     # 特殊数据 batch_index 从 101 起


def _decompress_channels(payload: dict) -> dict:
    """解压边端传来的压缩数据，原图模式直接返回 channels"""
    if "compressed_data" in payload:
        try:
            compressed_b64 = payload["compressed_data"]
            compression_method = payload.get("compression_method", "")
            compressed = base64.b64decode(compressed_b64)
            raw_bytes = zlib.decompress(compressed)

            if "msgpack" in compression_method:
                import msgpack
                channels = msgpack.unpackb(raw_bytes, raw=False, strict_map_key=False)
            else:
                import json
                channels = json.loads(raw_bytes.decode('utf-8'))

            return channels
        except Exception as e:
            raise ValueError(f"数据解压失败: {e}")

    return payload.get("channels", {})


def _get_next_batch_index(db: Session, device_id: str, is_special: bool = False) -> int:
    """
    获取该设备下一个批次序号
    - 普通数据 (is_special=False)：1~16 循环覆盖
    - 特殊数据 (is_special=True)：从 101 起自增，永不覆盖
    """
    if is_special:
        max_idx = db.query(func.max(SensorData.batch_index)).filter(
            SensorData.device_id == device_id,
            SensorData.is_special == 1
        ).scalar()
        return (max_idx or SPECIAL_BATCH_START) + 1

    # 普通数据：1~16 循环
    max_index = db.query(func.max(SensorData.batch_index)).filter(
        SensorData.device_id == device_id,
        SensorData.is_special == 0
    ).scalar()

    if max_index is None:
        return 1

    # 查询当前有多少个不同批次
    batch_count = db.query(func.count(func.distinct(SensorData.batch_index))).filter(
        SensorData.device_id == device_id,
        SensorData.is_special == 0
    ).scalar()

    if batch_count < MAX_BATCHES_NORMAL:
        return max_index + 1
    else:
        # 已满 16 个，循环覆盖 created_at 最旧的那个批次
        oldest_batch = db.query(
            SensorData.batch_index,
            func.min(SensorData.created_at).label("oldest_time")
        ).filter(
            SensorData.device_id == device_id,
            SensorData.is_special == 0
        ).group_by(SensorData.batch_index).order_by("oldest_time").first()
        return oldest_batch[0] if oldest_batch else 1


@router.post("/")
def ingest_data(payload: dict, db: Session = Depends(get_db)):
    """
    边端上传传感器数据
    支持压缩模式和原图模式
    """
    try:
        # 解压缩（如果是压缩模式）
        channels_data = _decompress_channels(payload)

        device_id = payload.get("device_id", "WTG-001")
        sample_rate = payload.get("sample_rate", 25600)
        timestamp_str = payload.get("timestamp")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str)
            # 统一转为 naive UTC，避免与时区无关的 datetime 比较出错
            if timestamp.tzinfo is not None:
                timestamp = timestamp.replace(tzinfo=None)
        else:
            timestamp = datetime.utcnow()
        is_special = payload.get("is_special", 0)  # 0=普通, 1=特殊
        task_id = payload.get("task_id")  # 关联的采集任务ID（特殊采集时）

        # 获取设备信息（用于通道名称映射）
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if device:
            # 更新设备最后在线时间并标记为在线
            device.last_seen_at = timestamp
            device.is_online = 1
            # 根据边端实际上传的通道数更新 channel_count
            actual_channel_count = len(channels_data)
            if actual_channel_count > 0 and device.channel_count != actual_channel_count:
                device.channel_count = actual_channel_count

        # 获取下一个批次序号
        batch_index = _get_next_batch_index(db, device_id, is_special=bool(is_special))

        # 如果该批次已存在，先删除旧数据（覆盖策略）
        db.query(SensorData).filter(
            SensorData.device_id == device_id,
            SensorData.batch_index == batch_index
        ).delete(synchronize_session=False)

        # 插入新数据（所有通道）
        for ch_name, ch_values in channels_data.items():
            channel_num = int(ch_name.replace("ch", ""))

            # 获取通道名称（从设备配置或默认）
            channel_display_name = None
            if device and device.channel_names:
                channel_display_name = device.channel_names.get(str(channel_num))

            record = SensorData(
                device_id=device_id,
                batch_index=batch_index,
                channel=channel_num,
                data=ch_values,
                sample_rate=sample_rate,
                is_analyzed=0,
                is_special=1 if is_special else 0,
                analyzed_at=None,
                created_at=timestamp,
            )
            db.add(record)

        db.commit()

        # 如果有关联任务，标记任务完成
        if task_id:
            from app.models import CollectionTask
            task = db.query(CollectionTask).filter(CollectionTask.id == task_id).first()
            if task:
                task.status = "completed"
                task.completed_at = datetime.utcnow()
                task.result_batch_index = batch_index
                db.commit()

        # WebSocket 推送
        msg = {
            "type": "sensor_update",
            "data": {
                "device_id": device_id,
                "batch_index": batch_index,
                "is_special": bool(is_special),
                "channels": list(channels_data.keys()),
                "sample_count": len(next(iter(channels_data.values()))) if channels_data else 0,
                "timestamp": timestamp.isoformat(),
            }
        }
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(manager.broadcast(msg))
        except Exception:
            pass

        return {
            "code": 200,
            "message": "数据接收成功",
            "data": {
                "device_id": device_id,
                "batch_index": batch_index,
                "is_special": bool(is_special),
                "channels_count": len(channels_data),
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
