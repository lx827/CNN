"""实时示波、示波中保存和逐文件流式接收。复用现有认证与采集任务。"""
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import socket
import uuid
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import optional_auth
from app.api.acquisition import (NATIVE_RATES, ACTIVE, AnalysisOptions, directory, edge_only,
                                job_or_404, owned, now, snapshot)
from app.database import get_db
from app.models import AcquisitionAgent, AcquisitionJob
from app.services.acquisition_live import live
from app.services.acquisition_analysis import analyze_counts, display_points

router = APIRouter(prefix='/api/acquisition', tags=['实时示波'], dependencies=[Depends(optional_auth)])
ROOT = Path(__file__).resolve().parents[3]


def get_session(session_id):
    try:
        return live.get(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


def online_agent(db, agent_id):
    a = db.get(AcquisitionAgent, agent_id)
    if a is None or a.last_seen_at < now()-timedelta(seconds=15):
        raise HTTPException(409, '请先启动连接采集器的现场边端')
    if a.source != 'dc24_tcp':
        raise HTTPException(409, '实时示波必须使用DC24硬件边端，不能使用文件回放')
    return a


@router.get('/capabilities')
def capabilities():
    return {'code': 200, 'data': {'service': 'cnn-dc24', 'version': 2, 'sample_rates': NATIVE_RATES,
                                 'hostname': socket.gethostname(), 'channel_count': 4}}


class StartSession(BaseModel):
    agent_id: str = Field(pattern=r'^[A-Za-z0-9_.-]{1,64}$')
    sample_rate: int


class RecordRequest(BaseModel):
    duration: int = Field(default=60, ge=0)  # 0：手动结束；正数：按实际点数定时。
    save_directory: str = Field(min_length=1, max_length=1024)
    analysis: AnalysisOptions = Field(default_factory=AnalysisOptions)


@router.post('/sessions')
def start(body: StartSession, db: Session = Depends(get_db)):
    online_agent(db, body.agent_id)
    if body.sample_rate not in NATIVE_RATES:
        raise HTTPException(422, '请选择原厂支持的采样率档位')
    if db.query(AcquisitionJob).filter(AcquisitionJob.agent_id == body.agent_id, AcquisitionJob.status.in_(ACTIVE)).first():
        raise HTTPException(409, '边端还有未完成的保存任务')
    try:
        s = live.create(body.agent_id, body.sample_rate)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {'code': 200, 'data': live.snapshot(s)}


@router.get('/sessions/{session_id}')
def session_status(session_id: str):
    return {'code': 200, 'data': live.snapshot(get_session(session_id))}


@router.post('/sessions/{session_id}/stop')
def stop(session_id: str):
    s = get_session(session_id)
    with live.lock:
        s['stop_requested'] = True
        if s['recording']:
            s['recording']['stop_requested'] = True
    return {'code': 200, 'data': live.snapshot(s)}


@router.post('/sessions/{session_id}/record')
def record(session_id: str, body: RecordRequest, db: Session = Depends(get_db)):
    s = get_session(session_id)
    online_agent(db, s['agent_id'])
    if s['stop_requested'] or s['status'] in ('stopped', 'failed'):
        raise HTTPException(409, '示波已经停止，请重新启动')
    a = body.analysis
    if a.envelope and (a.band_low is None or a.band_high is None or not 0 < a.band_low < a.band_high < s['sample_rate']/2):
        raise HTTPException(422, '包络频带须满足 0 < 下限 < 上限 < 采样率/2')
    with live.lock:
        if s['recording'] and s['recording']['status'] in ACTIVE:
            raise HTTPException(409, '上一次采集仍在保存，请稍候')
        job = AcquisitionJob(id=uuid.uuid4().hex, agent_id=s['agent_id'], source='dc24_tcp',
                             status='waiting_device', sample_rate=s['sample_rate'], duration=body.duration,
                             analysis_options=body.analysis.model_dump(), progress={}, created_at=now(), updated_at=now())
        db.add(job); db.commit()
        s['recording'] = dict(id=job.id, duration=body.duration, save_directory=body.save_directory,
                              status=job.status, stop_requested=False, samples_per_channel=0)
    return {'code': 200, 'data': snapshot(job)}


@router.post('/sessions/{session_id}/record/stop')
def stop_record(session_id: str):
    s = get_session(session_id)
    with live.lock:
        if s['recording']:
            s['recording']['stop_requested'] = True
    return {'code': 200}


@router.get('/agents/{agent_id}/control', dependencies=[Depends(edge_only)])
def control(agent_id: str):
    s = live.current(agent_id)
    return {'code': 200, 'data': {'session': live.snapshot(s) if s else None, 'picker': live.pickers.get(agent_id)}}


@router.get('/agents/{agent_id}/session')
def current_session(agent_id: str):
    s = live.current(agent_id)
    return {'code': 200, 'data': live.snapshot(s) if s else None}


@router.post('/agents/{agent_id}/select-directory')
def select_directory(agent_id: str, db: Session = Depends(get_db)):
    online_agent(db, agent_id)
    with live.lock:
        live.pickers[agent_id] = {'id': uuid.uuid4().hex, 'status': 'pending'}
    return {'code': 200, 'data': live.pickers[agent_id]}


class DirectoryResult(BaseModel):
    id: str
    directory: str | None = None
    error: str | None = None


@router.post('/agents/{agent_id}/directory-result', dependencies=[Depends(edge_only)])
def directory_result(agent_id: str, body: DirectoryResult):
    with live.lock:
        p = live.pickers.get(agent_id)
        if p and p['id'] == body.id:
            p.update(status='done', directory=body.directory, error=body.error)
    return {'code': 200}


@router.get('/agents/{agent_id}/directory')
def selected_directory(agent_id: str):
    return {'code': 200, 'data': live.pickers.get(agent_id)}


@router.post('/sessions/{session_id}/state', dependencies=[Depends(edge_only)])
def state(session_id: str, body: dict, agent_id: str):
    s = get_session(session_id)
    if s['agent_id'] != agent_id:
        raise HTTPException(403, '边端不匹配')
    with live.lock:
        if body.get('status') in ('waiting_device', 'configuring', 'streaming', 'stopping', 'stopped', 'failed'):
            s['status'] = body['status']
        s['error'] = str(body['error'])[:500] if body.get('error') else None
        if s['recording'] and body.get('recording') and body['recording'].get('id') == s['recording']['id']:
            s['recording'].update(body['recording'])
    return {'code': 200}


@router.post('/sessions/{session_id}/frames', dependencies=[Depends(edge_only)])
async def frames(session_id: str, request: Request, agent_id: str, start: int = Query(ge=0), sequence: int = Query(ge=0, le=65535)):
    s = get_session(session_id)
    if s['agent_id'] != agent_id:
        raise HTTPException(403, '边端不匹配')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > s['sample_rate']*2*16+65536:
            raise HTTPException(413, '实时窗口过大')
    if not raw or len(raw) % 16:
        raise HTTPException(422, '四通道原始计数格式无效')
    values = np.frombuffer(raw, dtype='<i4').reshape(-1, 4)
    if np.any(values < -8388608) or np.any(values > 8388607):
        raise HTTPException(422, '超出24位原始计数范围')
    live.push(s, values, start, sequence)
    return {'code': 200}


@router.get('/sessions/{session_id}/view')
async def view(session_id: str, waveform: bool = True, fft: bool = True, rms: bool = True,
               envelope: bool = False, band_low: float | None = None, band_high: float | None = None,
               wave_seconds: float = Query(.2, gt=0, le=2)):
    s = get_session(session_id)
    start, values = live.window(s)
    if len(values) < 64:
        return {'code': 200, 'data': {'session': live.snapshot(s), 'channels': [], 'waiting': True}}
    options = dict(fft=fft, rms=rms, envelope=envelope, band_low=band_low, band_high=band_high)
    try:
        result, _ = await asyncio.to_thread(analyze_counts, values, s['sample_rate'], options)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    n = max(2, int(wave_seconds*s['sample_rate']))
    for c in result['channels']:
        y = values[-n:, c['channel']]
        c['mean'] = float(values[:, c['channel']].mean())
        c['waveform'] = display_points(np.arange(len(values)-len(y), len(values))/s['sample_rate']+start/s['sample_rate'], y, 12000) if waveform else []
        if rms:
            with live.lock:
                c['rms_curve'] = [[r[0], r[c['channel']+1]] for r in s['rms_history']]
    result.update(session=live.snapshot(s), window_start=start/s['sample_rate'],
                  window_end=(start+len(values))/s['sample_rate'],
                  fresh=s['status'] == 'streaming' and __import__('time').monotonic()-s['last_upload'] < max(3, 508/s['sample_rate']),
                  scope='最近连续2秒以内的实时窗口；波形显示所选区间，原始保存不抽点')
    return {'code': 200, 'data': result}


STREAM_FILES = {'samples.csv', 'metadata.json', 'rx_stream.bin', 'commands.jsonl', 'counts.i32'}


@router.put('/jobs/{job_id}/stream-files/{name}', dependencies=[Depends(edge_only)])
async def upload_file(job_id: str, name: str, request: Request, agent_id: str, db: Session = Depends(get_db)):
    job = owned(db, job_id, agent_id)
    if name not in STREAM_FILES or job.status not in ACTIVE:
        raise HTTPException(409, '文件名或任务状态无效')
    p = directory(job_id); p.mkdir(parents=True, exist_ok=True)
    temp = p/(name+'.part')
    try:
        with temp.open('wb') as f:
            async for chunk in request.stream():
                f.write(chunk)
        temp.replace(p/name)
    except OSError as exc:
        raise HTTPException(507, '后端保存失败：'+str(exc)) from exc
    return {'code': 200}


@router.post('/jobs/{job_id}/finish-stream', dependencies=[Depends(edge_only)])
def finish(job_id: str, agent_id: str, db: Session = Depends(get_db)):
    job = owned(db, job_id, agent_id)
    p = directory(job_id)
    if not all((p/name).is_file() for name in STREAM_FILES):
        raise HTTPException(422, '完整采集文件尚未上传')
    meta = json.loads((p/'metadata.json').read_text(encoding='utf-8'))
    count = meta.get('samples_per_channel', 0)
    if (meta.get('source') != 'dc24_tcp' or meta.get('sample_rate_hz') != job.sample_rate
        or meta.get('value_unit') != 'signed_24_bit_ADC_counts' or count <= 0
        or (p/'counts.i32').stat().st_size != count*16):
        raise HTTPException(422, '实际数据、单位或采样率与任务不一致')
    job.result_metadata, job.updated_at = meta, now()
    job.status = 'completed' if meta.get('complete') else 'failed'
    job.error_message = meta.get('error')
    db.commit()
    with live.lock:
        for s in live.sessions.values():
            if s.get('recording') and s['recording']['id'] == job_id:
                s['recording'].update(status=job.status, samples_per_channel=count,
                                       saved_directory=meta.get('saved_directory'))
    return {'code': 200, 'data': snapshot(job)}
