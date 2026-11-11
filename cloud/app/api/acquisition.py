"""DC24 完整原始采集任务。沿用系统认证，独立于历史回放/物理量诊断。"""

import asyncio
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import uuid
import zipfile

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.api.auth import optional_auth
from app.database import get_db
from app.models import AcquisitionAgent, AcquisitionJob
from app.services.acquisition_analysis import analyze_counts

router = APIRouter(
    prefix="/api/acquisition", tags=["真实采集"], dependencies=[Depends(optional_auth)]
)
ACTIVE = (
    "pending",
    "waiting_device",
    "configuring",
    "capturing",
    "uploading",
    "analyzing",
)
INPUT_FILES = {"samples.csv", "metadata.json", "rx_stream.bin", "commands.jsonl"}
DOWNLOAD_FILES = INPUT_FILES | {"analysis.json", "analysis_arrays.npz"}
ANALYSIS_LOCK = asyncio.Semaphore(1)
NATIVE_RATES = sorted(
    int(k)
    for k in json.loads(
        (Path(__file__).resolve().parents[3] / "dc24/dc24_profiles.json").read_text()
    )
)


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def storage():
    root = Path(
        os.environ.get(
            "ACQUISITION_DATA_DIR",
            Path(__file__).resolve().parents[3] / "data/acquisitions",
        )
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def directory(job_id):
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise HTTPException(404, "采集任务不存在")
    return storage() / job_id


def job_or_404(db, job_id):
    job = db.get(AcquisitionJob, job_id)
    if job is None:
        raise HTTPException(404, "采集任务不存在")
    return job


def owned(db, job_id, agent_id):
    job = job_or_404(db, job_id)
    if job.agent_id != agent_id:
        raise HTTPException(403, "任务不属于此边端")
    return job


def snapshot(job):
    return {
        "id": job.id,
        "agent_id": job.agent_id,
        "source": job.source,
        "status": job.status,
        "sample_rate": job.sample_rate,
        "duration": job.duration,
        "analysis_options": job.analysis_options,
        "progress": job.progress,
        "metadata": job.result_metadata,
        "cancel_requested": bool(job.cancel_requested),
        "error": job.error_message,
        "created_at": job.created_at.isoformat() + "Z",
        "updated_at": job.updated_at.isoformat() + "Z",
    }


async def edge_only(user=Depends(optional_auth)):
    if user != "edge":
        raise HTTPException(403, "此接口仅供已认证边端使用")


class AnalysisOptions(BaseModel):
    fft: bool = True
    rms: bool = True
    envelope: bool = False
    band_low: float | None = None
    band_high: float | None = None


class CreateJob(BaseModel):
    agent_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    sample_rate: int = 5000
    duration: int = Field(default=60, ge=1)
    analysis: AnalysisOptions = Field(default_factory=AnalysisOptions)

    @model_validator(mode="after")
    def validate_profile(self):
        if self.sample_rate not in NATIVE_RATES:
            raise ValueError("采样率必须为原厂支持的档位")
        a = self.analysis
        if a.envelope and (
            a.band_low is None
            or a.band_high is None
            or not 0 < a.band_low < a.band_high < self.sample_rate / 2
        ):
            raise ValueError("包络频带须满足 0 < 下限 < 上限 < 采样率/2")
        return self


class Heartbeat(BaseModel):
    agent_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    source: str = Field(pattern=r"^(dc24_tcp|recording_replay)$")
    state: dict = Field(default_factory=dict)


class Progress(BaseModel):
    stage: str = Field(
        pattern=r"^(waiting_device|configuring|capturing|uploading|failed|cancelled)$"
    )
    samples_per_channel: int = Field(default=0, ge=0)
    message: str = Field(default="", max_length=500)


@router.post("/agents/heartbeat", dependencies=[Depends(edge_only)])
def heartbeat(body: Heartbeat, db: Session = Depends(get_db)):
    agent = db.get(AcquisitionAgent, body.agent_id)
    if agent is None:
        agent = AcquisitionAgent(id=body.agent_id)
        db.add(agent)
    agent.source, agent.last_seen_at, agent.state = body.source, now(), body.state
    db.commit()
    return {"code": 200}


@router.get("/agents")
def agents(db: Session = Depends(get_db)):
    return {
        "code": 200,
        "data": [
            {
                "id": a.id,
                "source": a.source,
                "state": a.state,
                "online": a.last_seen_at > now() - timedelta(seconds=15),
                "last_seen_at": a.last_seen_at.isoformat() + "Z",
            }
            for a in db.query(AcquisitionAgent).order_by(AcquisitionAgent.id).all()
        ],
    }


@router.post("/jobs")
def create_job(body: CreateJob, db: Session = Depends(get_db)):
    agent = db.get(AcquisitionAgent, body.agent_id)
    if agent is None or agent.last_seen_at < now() - timedelta(seconds=15):
        raise HTTPException(409, "采集边端不在线，请先启动本机边端")
    if agent.source == "recording_replay" and body.sample_rate != agent.state.get(
        "sample_rate"
    ):
        raise HTTPException(422, "回放采样率必须与原记录一致，不会通过修改标签重采样")
    if (
        db.query(AcquisitionJob)
        .filter(
            AcquisitionJob.agent_id == body.agent_id, AcquisitionJob.status.in_(ACTIVE)
        )
        .first()
    ):
        raise HTTPException(409, "该边端已有采集任务，请等待完成或停止")
    job = AcquisitionJob(
        id=uuid.uuid4().hex,
        agent_id=body.agent_id,
        source=agent.source,
        status="pending",
        sample_rate=body.sample_rate,
        duration=body.duration,
        analysis_options=body.analysis.model_dump(),
        progress={},
        created_at=now(),
        updated_at=now(),
    )
    db.add(job)
    db.commit()
    return {"code": 200, "data": snapshot(job)}


@router.get("/jobs")
def history(db: Session = Depends(get_db)):
    rows = (
        db.query(AcquisitionJob)
        .order_by(AcquisitionJob.created_at.desc())
        .limit(30)
        .all()
    )
    return {"code": 200, "data": [snapshot(j) for j in rows]}


@router.get("/agents/{agent_id}/next", dependencies=[Depends(edge_only)])
def claim(agent_id: str, db: Session = Depends(get_db)):
    job = (
        db.query(AcquisitionJob)
        .filter_by(agent_id=agent_id, status="pending")
        .order_by(AcquisitionJob.created_at)
        .first()
    )
    if job is None:
        return {"code": 200, "data": None}
    changed = (
        db.query(AcquisitionJob)
        .filter_by(id=job.id, status="pending")
        .update(
            {"status": "waiting_device", "updated_at": now()}, synchronize_session=False
        )
    )
    db.commit()
    if not changed:
        return {"code": 200, "data": None}
    db.refresh(job)
    return {"code": 200, "data": snapshot(job)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    return {"code": 200, "data": snapshot(job_or_404(db, job_id))}


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str, db: Session = Depends(get_db)):
    job = job_or_404(db, job_id)
    if job.status not in ACTIVE:
        raise HTTPException(409, "任务已经结束")
    job.cancel_requested, job.updated_at = 1, now()
    if job.status == "pending":
        job.status = "cancelled"
    db.commit()
    return {"code": 200, "data": snapshot(job)}


@router.post("/jobs/{job_id}/progress", dependencies=[Depends(edge_only)])
def progress(job_id: str, body: Progress, agent_id: str, db: Session = Depends(get_db)):
    job = owned(db, job_id, agent_id)
    if job.status in ACTIVE and job.status != "analyzing":
        job.status = body.stage
        job.progress = body.model_dump()
        if body.stage == "failed":
            job.error_message = body.message
        job.updated_at = now()
        db.commit()
    return {"code": 200, "data": {"cancel_requested": bool(job.cancel_requested)}}


def load_values(job_id):
    p = directory(job_id)
    if (p / "counts.i32").is_file():
        return np.memmap(p / "counts.i32", dtype="<i4", mode="r").reshape(-1, 4)
    with np.load(p / "counts.npz", allow_pickle=False) as a:
        return a["counts"]


def save_archive(job, archive):
    """校验 ZIP、CSV 和元数据，完整落盘，不进入旧回放诊断流水线。"""
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        members = z.infolist()
        names = [x.filename for x in members]
        if len(set(names)) != len(names) or not set(names) <= INPUT_FILES:
            raise ValueError("采集归档包含未知或重复文件")
        if not {"samples.csv", "metadata.json"} <= set(names):
            raise ValueError("归档缺少CSV或元数据")
        if job.source == "dc24_tcp" and not INPUT_FILES <= set(names):
            raise ValueError("真实采集归档缺少TCP字节或命令记录")
        if sum(x.file_size for x in members) > 96 * 1024 * 1024:
            raise ValueError("采集归档解压后过大")
        content = {name: z.read(name) for name in names}
    meta = json.loads(content["metadata.json"])
    if not isinstance(meta, dict):
        raise ValueError("元数据必须为JSON对象")
    if (
        meta.get("sample_rate_hz") != job.sample_rate
        or meta.get("value_unit") != "signed_24_bit_ADC_counts"
    ):
        raise ValueError("实际采样率或计数单位与任务不一致")
    csv_data = content["samples.csv"].decode("utf-8-sig")
    if (
        not csv_data.strip()
        or csv_data.splitlines()[0].strip()
        != "sample_index,time_s,ch0_counts,ch1_counts,ch2_counts,ch3_counts"
    ):
        raise ValueError("CSV列格式不符")
    data = np.loadtxt(io.StringIO(csv_data), delimiter=",", skiprows=1, ndmin=2)
    if data.ndim != 2 or data.shape[1] != 6 or not np.isfinite(data).all():
        raise ValueError("CSV形状或数值无效")
    n = len(data)
    if (
        n != meta.get("samples_per_channel")
        or n > job.sample_rate * job.duration + 2540
    ):
        raise ValueError("实际点数与任务/元数据不符")
    if not np.array_equal(data[:, 0], np.arange(n)) or not np.allclose(
        data[:, 1], np.arange(n) / job.sample_rate, atol=1e-8, rtol=0
    ):
        raise ValueError("样本索引或时间轴不连续")
    values = data[:, 2:]
    if (
        np.any(values < -8388608)
        or np.any(values > 8388607)
        or not np.equal(values, np.rint(values)).all()
    ):
        raise ValueError("不是有效的24位原始计数")
    if not meta.get("cancelled") and (
        not meta.get("complete")
        or n < job.sample_rate * job.duration
        or meta.get("sequence_gaps")
        or meta.get("unparsed_tail_bytes")
    ):
        raise ValueError("采集不完整或有帧序号缺口")
    p = directory(job.id)
    p.mkdir(parents=True, exist_ok=True)
    for name, data_bytes in content.items():
        (p / name).write_bytes(data_bytes)
    np.savez_compressed(p / "counts.npz", counts=values.astype(np.int32))
    meta["source"] = job.source
    return meta, values.astype(np.int32)


@router.post("/jobs/{job_id}/upload", dependencies=[Depends(edge_only)])
async def upload(
    job_id: str, request: Request, agent_id: str, db: Session = Depends(get_db)
):
    job = owned(db, job_id, agent_id)
    if job.status == "completed":
        return {"code": 200, "data": snapshot(job)}  # 网络重试幂等。
    if job.status not in ACTIVE and job.status != "cancelled":
        raise HTTPException(409, "此任务不能接收结果")
    archive = bytearray()
    async for chunk in request.stream():
        archive.extend(chunk)
        if len(archive) > 32 * 1024 * 1024:
            raise HTTPException(413, "采集归档超过32MB")
    try:
        async with ANALYSIS_LOCK:
            meta, values = await asyncio.to_thread(save_archive, job, archive)
            job.result_metadata, job.updated_at = meta, now()
            job.status = "analyzing"
            db.commit()
            if not job.cancel_requested and not meta.get("cancelled"):
                result, arrays = await asyncio.to_thread(
                    analyze_counts, values, job.sample_rate, job.analysis_options
                )
                p = directory(job.id)
                (p / "analysis.json").write_text(
                    json.dumps(result, ensure_ascii=False, allow_nan=False),
                    encoding="utf-8",
                )
                if arrays:
                    np.savez_compressed(p / "analysis_arrays.npz", **arrays)
            db.refresh(job)
            job.status = (
                "cancelled"
                if job.cancel_requested or meta.get("cancelled")
                else "completed"
            )
            job.updated_at = now()
            db.commit()
    except (ValueError, OSError, zipfile.BadZipFile, KeyError) as exc:
        job.status, job.error_message, job.updated_at = "failed", str(exc)[:500], now()
        db.commit()
        raise HTTPException(422, str(exc)) from exc
    return {"code": 200, "data": snapshot(job)}


@router.get("/jobs/{job_id}/analysis")
def analysis(job_id: str, db: Session = Depends(get_db)):
    job_or_404(db, job_id)
    path = directory(job_id) / "analysis.json"
    if not path.exists():
        raise HTTPException(404, "分析尚未完成或本次任务已停止")
    return {"code": 200, "data": json.loads(path.read_text(encoding="utf-8"))}


@router.get("/jobs/{job_id}/waveform")
def waveform(
    job_id: str,
    channel: int = Query(0, ge=0, le=3),
    start: float = Query(0, ge=0),
    seconds: float = Query(0.2, gt=0, le=5),
    db: Session = Depends(get_db),
):
    job = job_or_404(db, job_id)
    if job.result_metadata is None:
        raise HTTPException(404, "原始数据尚未保存")
    values = load_values(job_id)
    begin, end = (
        int(start * job.sample_rate),
        min(len(values), int((start + seconds) * job.sample_rate)),
    )
    if begin >= end:
        raise HTTPException(422, "所选时间区间超出记录")
    return {
        "code": 200,
        "data": np.column_stack(
            (np.arange(begin, end) / job.sample_rate, values[begin:end, channel])
        ).tolist(),
    }


@router.get("/jobs/{job_id}/files/{name}")
def download(job_id: str, name: str, db: Session = Depends(get_db)):
    job_or_404(db, job_id)
    if name not in DOWNLOAD_FILES:
        raise HTTPException(404, "文件不存在")
    p = directory(job_id) / name
    if not p.is_file():
        raise HTTPException(404, "文件尚未生成")
    return FileResponse(p, filename=f"{job_id}_{name}")
