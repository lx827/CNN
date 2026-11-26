"""实时示波、示波中保存和逐文件流式接收。复用现有认证与采集任务。

网页读取实时窗口:REST GET /sessions/{id}/view 轮询(保留兼容)与
WS /ws/acquisition/sessions/{id}/view 推送(2026-11 新增,issue #51)共用同一套
窗口计算;边端 POST /sessions/{id}/frames 上报保持 HTTP 不变。
"""

import asyncio
from datetime import timedelta
import json
from pathlib import Path
import socket
import time
import uuid
import numpy as np
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import optional_auth, verify_token_string
from app.api.acquisition import (
    ACTIVE,
    ANALYSIS_LOCK,
    AnalysisOptions,
    ChannelSelection,
    directory,
    edge_only,
    job_or_404,
    owned,
    now,
    expire_remote_wait,
    snapshot,
)
from app.database import get_db
from app.core import config
from app.core.config import DC24_CHANNELS
from app.models import AcquisitionAgent, AcquisitionJob, Device
from app.services.acquisition_live import live
from app.services.acquisition_analysis import analyze_counts, display_points
from app.services.acquisition_diagnosis import register_completed_acquisition

router = APIRouter(
    prefix="/api/acquisition", tags=["实时示波"], dependencies=[Depends(optional_auth)]
)
ROOT = Path(__file__).resolve().parents[3]


def get_session(session_id):
    try:
        return live.get(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


def online_agent(db, agent_id):
    a = db.get(AcquisitionAgent, agent_id)
    if a is None or a.last_seen_at < now() - timedelta(seconds=15):
        raise HTTPException(409, "请先启动连接采集器的现场边端")
    if a.source != "dc24_tcp":
        raise HTTPException(409, "实时示波必须使用DC24硬件边端，不能使用文件回放")
    if a.state.get("version", 0) < 3:
        raise HTTPException(409, "现场边端仍使用旧输入配置，请重启新版DC24边端后再示波")
    return a


@router.get("/capabilities")
def capabilities():
    # 采样率档位表属于采集侧硬件知识,由边端心跳上报(state.sample_rates),
    # 云端不持有卡片配置;capabilities 只回答服务身份与通道配置。
    return {
        "code": 200,
        "data": {
            "service": "cnn-dc24",
            "version": 2,
            "hostname": socket.gethostname(),
            "channel_count": 4,
            "channels": list(DC24_CHANNELS),
        },
    }


class StartSession(BaseModel):
    agent_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    sample_rate: int = Field(gt=0)


class RecordRequest(ChannelSelection):
    duration: int = Field(default=60, ge=0)  # 0：手动结束；正数：按实际点数定时。
    save_directory: str = Field(min_length=1, max_length=1024)
    analysis: AnalysisOptions = Field(default_factory=AnalysisOptions)


def validate_rate(agent, sample_rate):
    rates = agent.state.get("sample_rates") or []
    if sample_rate not in rates:
        raise HTTPException(
            422, f"请选择采集端支持的采样率(当前可选: {', '.join(map(str, rates))})"
        )


def ensure_no_active_recording(db, agent_id):
    job = db.query(AcquisitionJob).filter(
        AcquisitionJob.agent_id == agent_id, AcquisitionJob.status.in_(ACTIVE)
    ).first()
    if job is not None:
        s = live.current(agent_id)
        if s is not None and (s.get("recording") or {}).get("id") != job.id:
            s = None
        expire_remote_wait(job, s, db)
        if job.status in ACTIVE:
            raise HTTPException(409, "边端还有未完成的保存任务")


@router.post("/sessions")
def start(body: StartSession, db: Session = Depends(get_db)):
    agent = online_agent(db, body.agent_id)
    validate_rate(agent, body.sample_rate)
    with live.lock:
        ensure_no_active_recording(db, body.agent_id)
        try:
            s = live.create(body.agent_id, body.sample_rate)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"code": 200, "data": live.snapshot(s)}


@router.get("/sessions/{session_id}")
def session_status(session_id: str):
    return {"code": 200, "data": live.snapshot(get_session(session_id))}


@router.post("/sessions/{session_id}/stop")
def stop(session_id: str):
    s = get_session(session_id)
    with live.lock:
        s["stop_requested"] = True
        if s["recording"]:
            s["recording"]["stop_requested"] = True
    return {"code": 200, "data": live.snapshot(s)}


def begin_recording(db, s, body, *, remote=False):
    """在持有会话锁时登记任务，再将同一个任务发布给边端控制轮询。"""
    a = body.analysis
    if a.envelope and (
        a.band_low is None
        or a.band_high is None
        or not 0 < a.band_low < a.band_high < s["sample_rate"] / 2
    ):
        raise HTTPException(422, "包络频带须满足 0 < 下限 < 上限 < 采样率/2")
    initial = "pending" if remote else "waiting_device"
    job = AcquisitionJob(
        id=uuid.uuid4().hex,
        agent_id=s["agent_id"],
        source="dc24_tcp",
        status=initial,
        sample_rate=s["sample_rate"],
        duration=body.duration,
        analysis_options=body.analysis.model_dump(),
        enabled_channels=body.enabled_channels,
        progress={"remote_request": True} if remote else {},
        created_at=now(),
        updated_at=now(),
    )
    db.add(job)
    db.commit()
    s["recording"] = dict(
        id=job.id,
        remote_request=remote,
        duration=body.duration,
        save_directory=body.save_directory,
        status=job.status,
        stop_requested=False,
        samples_per_channel=0,
    )
    return {"code": 200, "data": snapshot(job)}


@router.post("/sessions/{session_id}/record")
def record(session_id: str, body: RecordRequest, db: Session = Depends(get_db)):
    s = get_session(session_id)
    online_agent(db, s["agent_id"])
    with live.lock:
        if s["stop_requested"] or s["status"] in ("stopped", "failed", "stopping"):
            raise HTTPException(409, "示波已经停止，请重新启动")
        ensure_no_active_recording(db, s["agent_id"])
        return begin_recording(db, s, body)


class RemoteRecording(BaseModel):
    agent_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    sample_rate: int | None = Field(default=None, gt=0)
    duration: int | None = Field(default=None, gt=0)


@router.post("/remote-recordings")
def request_remote_recording(body: RemoteRecording, db: Session = Depends(get_db)):
    agent = online_agent(db, body.agent_id)
    device = db.query(Device).filter_by(device_id=body.agent_id).first()
    rate = body.sample_rate or (device.sample_rate if device is not None else None)
    validate_rate(agent, rate)
    directory = agent.state.get("save_directory")
    if not directory:
        raise HTTPException(409, "边端未上报原件保存目录，请检查边端配置")
    request = RecordRequest(
        duration=body.duration or (device.window_seconds if device is not None else None)
        or config.SENSOR_WINDOW_SECONDS,
        save_directory=directory,
    )
    with live.lock:
        ensure_no_active_recording(db, body.agent_id)
        s = live.current(body.agent_id)
        if s is not None:
            if s["stop_requested"] or s["status"] == "stopping":
                raise HTTPException(409, "边端正在结束上一个会话，请稍后重试")
            if s["sample_rate"] != rate:
                raise HTTPException(409, f"当前示波为 {s['sample_rate']} Hz，请选同一档位或先停止示波")
            return begin_recording(db, s, request, remote=True)
        s = live.create(body.agent_id, rate)
        s["stop_after_recording"] = True
        try:
            return begin_recording(db, s, request, remote=True)
        except Exception:
            del live.sessions[s["id"]]
            raise


@router.post("/sessions/{session_id}/record/stop")
def stop_record(session_id: str):
    s = get_session(session_id)
    with live.lock:
        if s["recording"]:
            s["recording"]["stop_requested"] = True
    return {"code": 200}


@router.get("/agents/{agent_id}/control", dependencies=[Depends(edge_only)])
def control(agent_id: str, db: Session = Depends(get_db)):
    with live.lock:
        s = live.current(agent_id)
        recording = s["recording"] if s else None
        if recording and recording["remote_request"] and recording["status"] in (
            "pending", "waiting_device", "configuring"
        ):
            expire_remote_wait(job_or_404(db, recording["id"]), s, db)
        return {
            "code": 200,
            "data": {
                "session": live.snapshot(s) if s else None,
                "picker": live.pickers.get(agent_id),
            },
        }


@router.get("/agents/{agent_id}/session")
def current_session(agent_id: str):
    s = live.current(agent_id)
    return {"code": 200, "data": live.snapshot(s) if s else None}


@router.post("/agents/{agent_id}/select-directory")
def select_directory(agent_id: str, db: Session = Depends(get_db)):
    online_agent(db, agent_id)
    with live.lock:
        live.pickers[agent_id] = {"id": uuid.uuid4().hex, "status": "pending"}
    return {"code": 200, "data": live.pickers[agent_id]}


class DirectoryResult(BaseModel):
    id: str
    directory: str | None = None
    error: str | None = None


@router.post("/agents/{agent_id}/directory-result", dependencies=[Depends(edge_only)])
def directory_result(agent_id: str, body: DirectoryResult):
    with live.lock:
        p = live.pickers.get(agent_id)
        if p and p["id"] == body.id:
            p.update(status="done", directory=body.directory, error=body.error)
    return {"code": 200}


@router.get("/agents/{agent_id}/directory")
def selected_directory(agent_id: str):
    return {"code": 200, "data": live.pickers.get(agent_id)}


@router.post("/sessions/{session_id}/state", dependencies=[Depends(edge_only)])
def state(session_id: str, body: dict, agent_id: str, db: Session = Depends(get_db)):
    s = get_session(session_id)
    if s["agent_id"] != agent_id:
        raise HTTPException(403, "边端不匹配")
    with live.lock:
        if body.get("status") in (
            "waiting_device",
            "configuring",
            "streaming",
            "stopping",
            "stopped",
            "failed",
        ):
            s["status"] = body["status"]
        s["error"] = str(body["error"])[:500] if body.get("error") else None
        recording = s["recording"]
        if recording:
            report = body.get("recording") or {}
            matching = report.get("id") == recording["id"]
            if not recording["remote_request"]:
                if matching:
                    recording.update(report)
            elif recording["status"] in ("pending", "waiting_device", "configuring", "capturing"):
                stage = report.get("status") if matching else None
                count = report.get("samples_per_channel", 0) if matching else 0
                error = report.get("error") if matching else None
                if stage not in ("capturing", "uploading", "failed"):
                    if s["status"] in ("failed", "stopped"):
                        stage = "failed"
                        error = s["error"] or (
                            "采集已停止" if recording["stop_requested"]
                            else "采集卡未连接或未返回数据，请检查供电和接线"
                        )
                    elif s["status"] == "waiting_device" and recording["status"] == "pending":
                        stage = "waiting_device"
                    elif s["status"] == "configuring":
                        stage = "configuring"
                if stage in ("waiting_device", "configuring", "capturing", "uploading", "failed"):
                    job = job_or_404(db, recording["id"])
                    if job.status in ("pending", "waiting_device", "configuring", "capturing"):
                        previous = job.progress or {}
                        # 不逐帧写 SQLite；采集进度至多每秒持久化一次，阶段跃迁立即落库。
                        if job.status != stage or (
                            count != previous.get("samples_per_channel")
                            and now() - job.updated_at >= timedelta(seconds=1)
                        ):
                            job.status, job.updated_at = stage, now()
                            job.progress = dict(previous, stage=stage, samples_per_channel=count)
                            job.error_message = str(error)[:500] if stage == "failed" and error else None
                            db.commit()
                        recording.update(status=stage, samples_per_channel=count, error=error)
        if recording and s.get("stop_after_recording") and recording["status"] in (
            "uploading", "completed", "failed"
        ):
            s["stop_requested"] = True
    return {"code": 200}


@router.post("/sessions/{session_id}/frames", dependencies=[Depends(edge_only)])
async def frames(
    session_id: str,
    request: Request,
    agent_id: str,
    start: int = Query(ge=0),
    sequence: int = Query(ge=0, le=65535),
):
    s = get_session(session_id)
    if s["agent_id"] != agent_id:
        raise HTTPException(403, "边端不匹配")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > s["sample_rate"] * 2 * 16 + 65536:
            raise HTTPException(413, "实时窗口过大")
    if not raw or len(raw) % 16:
        raise HTTPException(422, "四通道原始计数格式无效")
    values = np.frombuffer(raw, dtype="<i4").reshape(-1, 4)
    if np.any(values < -8388608) or np.any(values > 8388607):
        raise HTTPException(422, "超出24位原始计数范围")
    live.push(s, values, start, sequence)
    return {"code": 200}


async def build_view_payload(s, options, wave_seconds):
    """实时窗口计算(REST view 与 WS 推送共用)。

    options: dict(waveform/fft/rms/envelope/band_low/band_high)
    wave_seconds: 波形显示区间秒数
    返回 view 端点的 data 部分(含 waiting 短数据分支)。
    """
    start, values = live.window(s)
    if len(values) < 64:
        return {"session": live.snapshot(s), "channels": [], "waiting": True}
    try:
        result, _ = await asyncio.to_thread(
            analyze_counts, values, s["sample_rate"], options
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    n = max(2, int(wave_seconds * s["sample_rate"]))
    for c in result["channels"]:
        y = values[-n:, c["channel"]]
        c["mean"] = float(values[:, c["channel"]].mean())
        c["waveform"] = (
            display_points(
                np.arange(len(values) - len(y), len(values)) / s["sample_rate"]
                + start / s["sample_rate"],
                y,
                12000,
            )
            if options.get("waveform", True)
            else []
        )
        if options.get("rms", True):
            with live.lock:
                c["rms_curve"] = [[r[0], r[c["channel"] + 1]] for r in s["rms_history"]]
    result.update(
        session=live.snapshot(s),
        window_start=start / s["sample_rate"],
        window_end=(start + len(values)) / s["sample_rate"],
        fresh=s["status"] == "streaming"
        and time.monotonic() - s["last_upload"] < max(3, 508 / s["sample_rate"]),
        scope="最近连续2秒以内的实时窗口；波形显示所选区间，原始保存不抽点",
    )
    return result


@router.get("/sessions/{session_id}/view")
async def view(
    session_id: str,
    waveform: bool = True,
    fft: bool = True,
    rms: bool = True,
    envelope: bool = False,
    band_low: float | None = None,
    band_high: float | None = None,
    wave_seconds: float = Query(0.2, gt=0, le=2),
):
    s = get_session(session_id)
    options = dict(
        fft=fft, rms=rms, envelope=envelope, band_low=band_low, band_high=band_high
    )
    result = await build_view_payload(s, options, wave_seconds)
    return {"code": 200, "data": result}


STREAM_FILES = {
    "samples.csv",
    "metadata.json",
    "rx_stream.bin",
    "commands.jsonl",
    "counts.i32",
}


@router.put("/jobs/{job_id}/stream-files/{name}", dependencies=[Depends(edge_only)])
async def upload_file(
    job_id: str,
    name: str,
    request: Request,
    agent_id: str,
    db: Session = Depends(get_db),
):
    job = owned(db, job_id, agent_id)
    if name not in STREAM_FILES or job.status not in ACTIVE:
        raise HTTPException(409, "文件名或任务状态无效")
    p = directory(job_id)
    p.mkdir(parents=True, exist_ok=True)
    temp = p / (name + ".part")
    try:
        with temp.open("wb") as f:
            async for chunk in request.stream():
                f.write(chunk)
        temp.replace(p / name)
    except OSError as exc:
        raise HTTPException(507, "后端保存失败：" + str(exc)) from exc
    return {"code": 200}


class FinishStream(BaseModel):
    local_directory: str | None = Field(default=None, min_length=1, max_length=1024)


@router.post("/jobs/{job_id}/finish-stream", dependencies=[Depends(edge_only)])
async def finish(
    job_id: str,
    agent_id: str,
    body: FinishStream | None = None,
    db: Session = Depends(get_db),
):
    local = body is not None and body.local_directory is not None
    if local and not config.IS_LOCAL_DEPLOYMENT:
        raise HTTPException(422, "本机原件登记仅本地工作站可用")
    async with ANALYSIS_LOCK:
        job = owned(db, job_id, agent_id)
        db.refresh(job)
        if job.status in ("completed", "failed"):
            return {"code": 200, "data": snapshot(job)}
        if local:
            p = Path(body.local_directory).expanduser()
            if not p.is_absolute():
                raise HTTPException(422, "本机原件目录必须是绝对路径")
            p = p.resolve()
        else:
            p = directory(job_id)
        if not all((p / name).is_file() for name in STREAM_FILES):
            raise HTTPException(
                422,
                "完整采集文件尚未上传" if not local else "本机原件目录缺少完整采集文件",
            )
        meta = json.loads((p / "metadata.json").read_text(encoding="utf-8"))
        count = meta.get("samples_per_channel", 0)
        if (
            meta.get("source") != "dc24_tcp"
            or meta.get("sample_rate_hz") != job.sample_rate
            or meta.get("value_unit") != "signed_24_bit_ADC_counts"
            or count <= 0
            or (p / "counts.i32").stat().st_size != count * 16
            or (local and meta.get("saved_directory") != str(p))
        ):
            raise HTTPException(422, "实际数据、单位或采样率与任务不一致")
        if local:
            meta["local_directory"] = str(p)
        job.result_metadata, job.updated_at = meta, now()
        job.status = "completed" if meta.get("complete") else "failed"
        job.error_message = meta.get("error")
        if job.status == "completed":
            register_completed_acquisition(db, job, p / "counts.i32")
        db.commit()
    with live.lock:
        for s in live.sessions.values():
            if s.get("recording") and s["recording"]["id"] == job_id:
                s["recording"].update(
                    status=job.status,
                    samples_per_channel=count,
                    saved_directory=meta.get("saved_directory"),
                )
                if s.get("stop_after_recording"):
                    s["stop_requested"] = True
    return {"code": 200, "data": snapshot(job)}


# ==================== WebSocket 实时窗口推送 ====================
# 独立路由:不挂 router 级 optional_auth(HTTP 头依赖,浏览器 WS 无法携带),
# 与 /ws/monitor 相同地用 token 查询参数 + verify_token_string 鉴权。

ws_router = APIRouter()

# 推送限频:与原 500ms HTTP 轮询同节奏,防止高频 revision 触发过密计算(2G 红线)
WS_PUSH_INTERVAL = 0.4
# 单次 receive 等待:兼听客户端消息(选项/心跳),超时进入推送判定
WS_RECEIVE_TIMEOUT = 0.2


@ws_router.websocket("/ws/acquisition/sessions/{session_id}/view")
async def ws_view(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(default=""),
    waveform: bool = True,
    fft: bool = True,
    rms: bool = True,
    envelope: bool = False,
    band_low: float | None = None,
    band_high: float | None = None,
    wave_seconds: float = Query(0.2, gt=0, le=2),
):
    try:
        verify_token_string(token)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        s = get_session(session_id)
    except HTTPException:
        # 会话不存在(后端可能已重启):接受握手后以 4404 关闭,前端走 REST 恢复路径
        await websocket.accept()
        await websocket.close(code=4404)
        return
    await websocket.accept()

    options = dict(
        fft=fft, rms=rms, envelope=envelope, band_low=band_low, band_high=band_high
    )
    seconds = wave_seconds
    last_revision = None
    last_snapshot_json = None
    last_session_push = 0.0
    last_view_push = 0.0

    def _send(obj):
        return websocket.send_text(json.dumps(obj, ensure_ascii=False, default=str))

    try:
        while True:
            # 1) 消化客户端消息:心跳 pong / 选项更新
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=WS_RECEIVE_TIMEOUT
                )
                try:
                    msg = json.loads(raw)
                except ValueError:
                    msg = {}
                if msg.get("type") == "ping":
                    await _send({"type": "pong"})
                elif msg.get("type") == "options":
                    new_options = dict(options)
                    for key in ("fft", "rms", "envelope"):
                        if key in msg:
                            new_options[key] = bool(msg[key])
                    for key in ("band_low", "band_high"):
                        if key in msg:
                            new_options[key] = msg[key]
                    if "wave_seconds" in msg:
                        try:
                            seconds = min(2, max(0.01, float(msg["wave_seconds"])))
                            last_revision = None  # 显示区间变化,立即重推
                        except (TypeError, ValueError):
                            pass
                    # 包络频带校验与 REST 一致:0 < 下限 < 上限 < 采样率/2
                    if new_options.get("envelope"):
                        lo, hi = (
                            new_options.get("band_low"),
                            new_options.get("band_high"),
                        )
                        if not (
                            lo is not None
                            and hi is not None
                            and 0 < lo < hi < s["sample_rate"] / 2
                        ):
                            await _send(
                                {
                                    "type": "error",
                                    "data": {
                                        "detail": "包络频带须满足 0 < 下限 < 上限 < 采样率/2"
                                    },
                                }
                            )
                        else:
                            options = new_options
                            last_revision = None
                    else:
                        options = new_options
                        last_revision = None
            except asyncio.TimeoutError:
                pass

            now = time.monotonic()
            # 2) 会话快照变化(状态/录制进度)→ 推送 session(限频)
            snap = live.snapshot(s)
            snap_json = json.dumps(snap, ensure_ascii=False, default=str)
            if (
                snap_json != last_snapshot_json
                and now - last_session_push >= WS_PUSH_INTERVAL
            ):
                last_snapshot_json = snap_json
                last_session_push = now
                await _send({"type": "session", "data": snap})
            # 3) 新数据(revision 变化)或选项变化 → 计算并推送 view(限频)
            if (
                s["revision"] != last_revision
                and now - last_view_push >= WS_PUSH_INTERVAL
            ):
                last_view_push = now
                last_revision = s["revision"]
                payload = await build_view_payload(s, options, seconds)
                await _send({"type": "view", "data": payload})
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        return
    except Exception:
        # 计算失败(HTTPException 422 等):关闭连接,前端回退 REST 轮询
        try:
            await websocket.close()
        except Exception:
            pass
        return
