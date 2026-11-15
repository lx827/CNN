"""DC24 单次采集宿主：可选驱动 → 四路原始计数文件。

协议与传输分别由 dc24-driver 及所选驱动发行包提供；本模块只编排采集进度、
停止和现有文件格式，不加载诊断算法，也不进行物理单位转换。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import time

from dc24_driver import (
    B5_PROFILES,
    CONFIG_B2,
    HOST,
    INPUT_CONFIGURATION,
    PEER,
    PORT,
    RATE,
    SAMPLES_PER_FRAME,
    Frames,
    Link,
    command,
    decode,
    samples,
)

__all__ = [
    "B5_PROFILES",
    "CONFIG_B2",
    "HOST",
    "INPUT_CONFIGURATION",
    "PEER",
    "PORT",
    "RATE",
    "SAMPLES_PER_FRAME",
    "Frames",
    "Link",
    "command",
    "create_driver",
    "decode",
    "record",
    "samples",
]


def create_driver(vendor_root=None, host=HOST, peer=PEER, port=PORT):
    """按显式本机配置创建驱动；未配置原厂目录时保持 Python TCP 默认。"""
    if vendor_root:
        from dc24_driver_vendor import VendorDriver

        return VendorDriver(vendor_root, host=host, peer=peer, port=port)
    from dc24_driver_python import PythonTcpDriver

    return PythonTcpDriver(host=host, peer=peer, port=port)


def record(
    output: Path,
    seconds: float,
    host=HOST,
    peer=PEER,
    wait=45,
    sample_rate=RATE,
    on_progress=None,
    should_stop=None,
    driver=None,
):
    if sample_rate not in B5_PROFILES:
        raise ValueError("Sampling rate must be a supported native profile")
    target_samples = math.ceil(seconds * sample_rate)
    output.mkdir(parents=True, exist_ok=False)  # 永不覆盖已有采集结果。
    metadata = {
        "profile": f"DC24_observed_{sample_rate}Hz_four_channels",
        "host_ip": host,
        "device_ip": peer,
        "host_tcp_port": PORT,
        "sample_rate_hz": sample_rate,
        "sample_rate_source": "native supported rate; IEPE/PASS base captured at 10000Hz; verified rate field",
        "b5_payload_hex": B5_PROFILES[sample_rate].hex(),
        "b2_payload_hex": CONFIG_B2.hex(),
        "input_configuration": dict(INPUT_CONFIGURATION),
        "channel_tags": [0, 1, 2, 3],
        "value_unit": "signed_24_bit_ADC_counts",
        "physical_scaling": "NOT VERIFIED; no voltage/acceleration conversion applied",
        "time_axis": f"relative sample index / {sample_rate}; not a device UTC timestamp",
        "duration_policy": "at least requested samples; stop on whole frames",
        "target_samples_per_channel": target_samples,
        "requested_duration_s": seconds,
        "data_frames": 0,
        "samples_per_channel": 0,
        "sequence_gaps": [],
        "complete": False,
    }
    driver = driver or create_driver(host=host, peer=peer, port=PORT)
    metadata["transport"] = driver.transport
    previous_sequence = None
    current_index = 0
    first_frame_time = None
    first_frame_samples = 0
    last_frame_time = None
    stopping = should_stop or (lambda: False)

    def notify(stage):
        if on_progress:
            on_progress(
                {
                    "stage": stage,
                    "samples_per_channel": current_index,
                    "target_samples_per_channel": target_samples,
                    "hardware_connected": stage in ("configuring", "capturing"),
                }
            )

    try:
        notify("waiting_device")
        if not driver.connect(stopping, wait):
            metadata["cancelled"] = True
        else:
            if driver.device_source_port is not None:
                metadata["device_source_port"] = driver.device_source_port
            notify("configuring")
            with (
                (output / "rx_stream.bin").open("xb") as raw,
                (output / "commands.jsonl").open("x", encoding="utf-8") as events,
                (output / "samples.csv").open(
                    "x", encoding="utf-8", newline=""
                ) as csvfile,
            ):
                try:
                    writer = csv.writer(csvfile)
                    writer.writerow(
                        [
                            "sample_index",
                            "time_s",
                            "ch0_counts",
                            "ch1_counts",
                            "ch2_counts",
                            "ch3_counts",
                        ]
                    )

                    def consume(block):
                        nonlocal \
                            previous_sequence, \
                            current_index, \
                            first_frame_time, \
                            last_frame_time, \
                            first_frame_samples
                        sequence, values = block.sequence, block.values
                        now = time.monotonic()
                        if first_frame_time is None:
                            first_frame_time = now
                            first_frame_samples = len(values)
                        last_frame_time = now
                        if previous_sequence is None:
                            if sequence != 0:
                                raise ValueError(
                                    f"First data sequence is {sequence}, not 0"
                                )
                        elif (sequence - previous_sequence) & 0xFFFF != 1:
                            metadata["sequence_gaps"].append(
                                [previous_sequence, sequence]
                            )
                            raise ValueError(
                                f"Nonconsecutive frame sequence: {previous_sequence} -> {sequence}"
                            )
                        for row in values.tolist():
                            writer.writerow(
                                [
                                    current_index,
                                    f"{current_index / sample_rate:.7f}",
                                    *row,
                                ]
                            )
                            current_index += 1
                        previous_sequence = sequence
                        metadata["data_frames"] += 1
                        metadata["samples_per_channel"] += len(values)
                        notify("capturing")

                    driver.start(sample_rate, consume, raw, events)
                    if driver.identity_frame is not None:
                        metadata["identity_frame_hex"] = driver.identity_frame.hex()
                    # 主机计时会包含设备启动等待；以实际样本数保证记录时长。
                    until = time.monotonic() + seconds + max(10, seconds * 0.25)
                    next_progress = sample_rate * 10
                    while current_index < target_samples and not stopping():
                        driver.poll()
                        if current_index >= next_progress:
                            print(
                                f"Samples/channel: {current_index}/{target_samples}",
                                flush=True,
                            )
                            next_progress += sample_rate * 10
                        if time.monotonic() > until:
                            raise TimeoutError(
                                f"Only {current_index}/{target_samples} samples received"
                            )
                    driver.stop()
                    metadata["cancelled"] = bool(stopping())
                    if driver.unparsed_tail_bytes:
                        raise RuntimeError(
                            "Incomplete frame remains after the stop acknowledgement"
                        )
                    if metadata["data_frames"] == 0 and not metadata["cancelled"]:
                        raise RuntimeError(
                            "Start/stop acknowledged but no sample frames received"
                        )
                    metadata["complete"] = not metadata["cancelled"]
                finally:
                    driver.close()
    except BaseException as exc:
        metadata["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        driver.close()
        metadata["received_tcp_bytes"] = driver.received_tcp_bytes
        metadata["unparsed_tail_bytes"] = driver.unparsed_tail_bytes
        if driver.emergency_stop_error:
            metadata["emergency_stop_error"] = driver.emergency_stop_error
        metadata["recorded_sample_duration_s"] = (
            metadata["samples_per_channel"] / sample_rate
        )
        if first_frame_time is not None and last_frame_time > first_frame_time:
            span = last_frame_time - first_frame_time
            metadata["data_frame_arrival_span_s"] = span
            metadata["arrival_rate_estimate_hz"] = (
                current_index - first_frame_samples
            ) / span
        (output / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(metadata, ensure_ascii=False), flush=True)
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seconds", type=float, default=5, help="最少样本时长，默认 5 秒；按完整帧收尾"
    )
    parser.add_argument(
        "--rate",
        type=int,
        choices=sorted(B5_PROFILES),
        default=RATE,
        help="采用原厂支持的采样率，默认 10000 Hz；IEPE/AC0.2Hz/PASS配置",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="新目录，不覆盖旧结果"
    )
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error("--seconds 必须为大于 0 的有限数")
    record(args.output, args.seconds, sample_rate=args.rate)
