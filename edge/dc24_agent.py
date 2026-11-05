"""DC24 边端：云端任务 → 原始采集/明确标记的回放 → 完整文件上传。

不使用旧 compressor 的抽点压缩，不接入自动机械故障诊断。
"""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
import zipfile

from dotenv import load_dotenv
import requests

from dc24_capture import record, B5_PROFILES, INPUT_CONFIGURATION

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(Path(__file__).with_name(".env"))
FILES = ("samples.csv", "metadata.json", "rx_stream.bin", "commands.jsonl")


def replay(source, output, job, stop, progress):
    """保持原记录采样率和数值；不把文件回放标成实时硬件。"""
    meta = json.loads((source/"metadata.json").read_text(encoding="utf-8"))
    if not meta.get("complete") or meta.get("sequence_gaps") or meta.get("unparsed_tail_bytes") or meta.get("error"):
        raise ValueError("回放源须为无帧缺口、已完整结束的记录")
    if meta["sample_rate_hz"] != job["sample_rate"]:
        raise ValueError("回放任务采样率与原文件不同")
    needed = ((job["sample_rate"]*job["duration"]+253)//254)*254
    if meta["samples_per_channel"] < needed:
        raise ValueError("原记录长度不足，请缩短回放时长")
    output.mkdir(parents=True, exist_ok=False)
    count = 0
    with (source/"samples.csv").open(encoding="utf-8-sig", newline="") as a, (output/"samples.csv").open("x", encoding="utf-8", newline="") as b:
        reader, writer = csv.reader(a), csv.writer(b)
        writer.writerow(next(reader))
        for row in reader:
            if count >= needed or stop.is_set():
                break
            writer.writerow(row)
            count += 1
    # 只继承信号定义；原采集的网络字节数、到达速率等不能冒充本次回放测量。
    meta = {key: meta[key] for key in ("sample_rate_hz", "value_unit", "physical_scaling", "channel_tags", "time_axis") if key in meta}
    meta.update(source="recording_replay", complete=not stop.is_set(), cancelled=stop.is_set(),
                requested_duration_s=job["duration"], samples_per_channel=count,
                target_samples_per_channel=job["sample_rate"]*job["duration"],
                recorded_sample_duration_s=count/job["sample_rate"], replay_of=str(source),
                sequence_gaps=[], unparsed_tail_bytes=0)
    (output/"metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    progress({"stage": "capturing", "samples_per_channel": count, "hardware_connected": False})
    return meta


class Agent:
    def __init__(self, cloud, agent_id, output, replay_dir=None):
        self.cloud = cloud.rstrip("/") + "/api/acquisition"
        self.agent_id, self.output, self.replay_dir = agent_id, Path(output), replay_dir
        self.source = "recording_replay" if replay_dir else "dc24_tcp"
        # 与既有 edge_client/cloud 保持同一认证配置约定。
        self.headers = {"X-Edge-Key": os.getenv("EDGE_API_KEY", "turbine-edge-secret")}
        if not self.headers["X-Edge-Key"]:
            raise ValueError("请在边端 .env 配置与云端一致的 EDGE_API_KEY")
        self.state = {"stage": "idle", "hardware_connected": False,
                      "sample_rates": sorted(B5_PROFILES), "channel_count": 4,
                      "save_directory": str(self.output.resolve()), "version": 3,
                      "input_configuration": dict(INPUT_CONFIGURATION)}
        self.picker = None
        self.picker_id = None
        if replay_dir:
            meta = json.loads((replay_dir/"metadata.json").read_text(encoding="utf-8"))
            self.state.update(sample_rate=meta["sample_rate_hz"], sample_rates=[meta["sample_rate_hz"]])
        self.lock = threading.Lock()

    def call(self, method, path, **kwargs):
        response = requests.request(method, self.cloud+path, headers=self.headers,
                                    timeout=kwargs.pop("timeout", (3, 8)), **kwargs)
        response.raise_for_status()
        return response.json().get("data")

    def progress(self, state):
        with self.lock:
            self.state.update(state)

    def heartbeat(self):
        with self.lock:
            state = dict(self.state)
        self.call("POST", "/agents/heartbeat", json={"agent_id": self.agent_id,
                  "source": self.source, "state": state})

    def get_control(self):
        result = self.call('GET', f'/agents/{self.agent_id}/control')
        picker = result.get('picker')
        if picker and picker['status'] == 'pending' and picker['id'] != self.picker_id and self.picker is None:
            self.picker_id = picker['id']
            self.picker = subprocess.Popen([sys.executable, str(ROOT/'scripts/dc24_select_directory.py')],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if self.picker and self.picker.poll() is not None:
            try:
                selected = json.loads(self.picker.stdout.read().decode('utf-8'))
            except Exception:
                selected = {'error': '无法打开目录选择器，请直接填写绝对路径'}
            self.call('POST', f'/agents/{self.agent_id}/directory-result', json={'id': self.picker_id, **selected})
            if selected.get('directory'):
                self.progress({'save_directory': selected['directory']})
            self.picker.stdout.close(); self.picker = None
        return result

    def report(self, job_id, stage=None, message=""):
        with self.lock:
            state = dict(self.state)
        return self.call("POST", f"/jobs/{job_id}/progress", params={"agent_id": self.agent_id},
                         json={"stage": stage or state["stage"],
                               "samples_per_channel": state.get("samples_per_channel", 0),
                               "message": message[:500]})

    def execute(self, job):
        stop, finished = threading.Event(), threading.Event()
        self.progress({"stage": "waiting_device", "samples_per_channel": 0, "job_id": job["id"]})
        output = self.output/job["id"]

        def monitor():
            while not finished.is_set():
                try:
                    self.heartbeat()
                    status = self.report(job["id"])
                    if status and status.get("cancel_requested"):
                        stop.set()
                except requests.RequestException:
                    pass  # 云端暂时断开不删除或截断本地原始数据。
                finished.wait(1)

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        try:
            if job.get("source") != self.source:
                raise ValueError("任务创建后边端数据来源已改变，请按当前来源重新创建任务")
            if self.replay_dir:
                meta = replay(self.replay_dir, output, job, stop, self.progress)
            else:
                meta = record(output, job["duration"], sample_rate=job["sample_rate"],
                              on_progress=self.progress, should_stop=stop.is_set)
            if meta.get("samples_per_channel", 0) == 0 and meta.get("cancelled"):
                self.report(job["id"], "cancelled")
                return
            meta["source"] = self.source
            (output/"metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            self.progress({"stage": "uploading", "hardware_connected": False})
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
                for name in FILES:
                    if (output/name).is_file():
                        archive.write(output/name, name)
            # 网络重试只重传同一份已保存数据，不重新采集。
            for attempt in range(3):
                try:
                    self.call("POST", f"/jobs/{job['id']}/upload", params={"agent_id": self.agent_id},
                              data=payload.getvalue(), timeout=(5, 180))
                    break
                except requests.RequestException:
                    if attempt == 2:
                        raise
                    time.sleep(2)
        except Exception as exc:
            message = str(exc)
            if isinstance(exc, OSError) and getattr(exc, "winerror", None) in (10013, 10048):
                message = "电脑TCP 6800端口被占用，请先让原厂软件脱机或退出其他采集进程"
            try:
                self.report(job["id"], "failed", message)
            except requests.RequestException:
                pass
            print(f"任务失败；本地文件保留在 {output}。{type(exc).__name__}", flush=True)
        finally:
            finished.set()
            thread.join(timeout=12)
            self.progress({"stage": "idle", "hardware_connected": False, "job_id": None})

    def run(self, once=False):
        while True:
            try:
                self.heartbeat()
                control = self.get_control()
                if control.get('session'):
                    from dc24_live import SessionRunner
                    SessionRunner(self, control['session']).run()
                    if once:
                        return
                    continue
                job = self.call("GET", f"/agents/{self.agent_id}/next")
                if job:
                    self.execute(job)
                    if once:
                        return
            except requests.RequestException:
                print("暂未连上云端，将继续重试；请检查地址、认证和网络。", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    default_url = os.getenv("CLOUD_BASE_URL") or os.getenv("CLOUD_INGEST_URL", "http://127.0.0.1:8000/api/ingest/").split("/api/")[0]
    parser.add_argument("--cloud", default=default_url, help="CNN 后端根地址")
    parser.add_argument("--agent-id", default="dc24-"+re.sub(r"[^A-Za-z0-9_-]", "_", socket.gethostname()))
    parser.add_argument("--output", type=Path, default=ROOT/"tmp/dc24_acquisition/recordings")
    parser.add_argument("--replay-dir", type=Path, help="显式使用历史采集记录，不连接硬件")
    parser.add_argument("--once", action="store_true", help="完成一个任务后退出")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", args.agent_id):
        parser.error("边端ID只能包含1~64个字母、数字、点、横杠、下划线")
    Agent(args.cloud, args.agent_id, args.output, args.replay_dir).run(args.once)
