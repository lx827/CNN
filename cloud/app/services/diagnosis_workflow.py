"""HTTP 重分析和后台 worker 共用的串行事务流程。"""

import asyncio
import logging
from datetime import datetime, timezone

from app.core.websocket import manager
from app.core.json_utils import sanitize_for_json
from app.models import SensorData
from app.services.analyzer import analyze_device
from app.services.alarms import generate_alarms
from app.services.diagnosis_store import save_batch, cache_query
from app.services.diagnosis.domain import DiagnosisKey

logger = logging.getLogger(__name__)


async def process_batch(
    db, device, batch_index, *, denoise="none", rot_freq=None, semaphore=None
):
    if semaphore is None:
        from app.lifespan import ANALYSIS_SEM

        semaphore = ANALYSIS_SEM
    async with semaphore:
        try:
            records = (
                db.query(SensorData)
                .filter(
                    SensorData.device_id == device.device_id,
                    SensorData.batch_index == batch_index,
                )
                .order_by(SensorData.channel.asc())
                .all()
            )
            if not records:
                raise ValueError("batch_data_not_found")
            rates = {record.sample_rate or device.sample_rate for record in records}
            if len(rates) != 1 or not next(iter(rates)):
                raise ValueError("batch_channel_sample_rates_must_match")
            if rot_freq is None:
                previous = cache_query(
                    db, DiagnosisKey(device.device_id, batch_index, 0, "none")
                ).first()
                rot_freq = previous.rot_freq if previous else None
            result = await asyncio.to_thread(
                analyze_device,
                {f"ch{record.channel}": record.data for record in records},
                next(iter(rates)),
                device,
                rot_freq,
                denoise,
                batch_index,
            )
            save_batch(db, device.device_id, batch_index, denoise, result)
            for record in records:
                record.is_analyzed = 1
                record.analyzed_at = datetime.now(timezone.utc)
            alarms = generate_alarms(
                db, device.device_id, result, batch_index=batch_index
            )
            db.commit()
            events = sanitize_for_json(
                [
                    {
                        "type": "diagnosis_update",
                        "data": {
                            "device_id": device.device_id,
                            "batch_index": batch_index,
                            **result,
                        },
                    }
                ]
                + [
                    {
                        "type": "new_alarm",
                        "data": {
                            "id": alarm.id,
                            "title": alarm.title,
                            "level": alarm.level,
                            "channel": alarm.channel,
                        },
                    }
                    for alarm in alarms
                ]
            )
        except Exception:
            db.rollback()
            raise
    for event in events:
        try:
            await manager.broadcast(event)
        except Exception:
            # 持久化已完成，失联的浏览器不能把成功事务变成需要重复执行的失败。
            logger.exception("诊断推送失败")
    return result
