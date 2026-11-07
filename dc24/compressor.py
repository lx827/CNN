"""
边端数据压缩模块

压缩流程：
  1. 峰值保持降采样：5000点 → 1000点（每5点取最大绝对值，避免漏掉冲击故障）
  2. msgpack 序列化：比 JSON 体积小 30%~50%
  3. zlib 压缩：进一步压缩
  4. base64 编码：变成字符串放入 JSON

解压流程（云端执行）：
  base64解码 → zlib解压 → msgpack解包

压缩率实测：约 10~20 倍（120KB → 6~12KB）
"""
import base64
import json
import zlib

import numpy as np


def downsample_peak(signal: list, target_ratio: int = 5) -> list:
    """
    峰值保持降采样
    每 target_ratio 个点取绝对值最大的那个
    目的：保留冲击峰值，避免降采样后漏掉故障特征
    """
    arr = np.array(signal)
    n = len(arr)
    result = []
    for i in range(0, n, target_ratio):
        window = arr[i:i + target_ratio]
        # 取绝对值最大的点（保持原符号）
        idx = np.argmax(np.abs(window))
        result.append(float(window[idx]))
    return result


def compress_payload(channels_data: dict, sample_rate: int = 1000, downsample_ratio: int = 5) -> dict:
    """
    压缩边端上传数据

    Returns:
        {
            "device_id": "WTG-001",
            "timestamp": "...",
            "compressed_data": "base64字符串",
            "original_points": 5000,      # 原始每通道点数
            "compressed_points": 1000,    # 降采样后点数
            "sample_rate": 1000,
            "compression_method": "downsample+msgpack+zlib"
        }
    """
    try:
        import msgpack
    except ImportError:
        # 如果没有 msgpack，回退到 JSON + zlib
        raw_bytes = json.dumps(channels_data).encode('utf-8')
        compressed = zlib.compress(raw_bytes, level=6)
        b64 = base64.b64encode(compressed).decode('ascii')
        return {
            "compressed_data": b64,
            "original_points": len(next(iter(channels_data.values()))),
            "compressed_points": len(next(iter(channels_data.values()))),
            "compression_method": "json+zlib",
            "encoding": "base64"
        }

    # 1. 降采样
    downsampled = {}
    for ch_name, signal in channels_data.items():
        downsampled[ch_name] = downsample_peak(signal, target_ratio=downsample_ratio)

    # 2. msgpack 序列化
    raw_bytes = msgpack.packb(downsampled, use_bin_type=True)

    # 3. zlib 压缩
    compressed = zlib.compress(raw_bytes, level=6)

    # 4. base64 编码（方便放入 JSON）
    b64 = base64.b64encode(compressed).decode('ascii')

    return {
        "compressed_data": b64,
        "original_points": len(next(iter(channels_data.values()))),
        "compressed_points": len(next(iter(downsampled.values()))),
        "compression_method": f"downsample({downsample_ratio}x)+msgpack+zlib",
        "encoding": "base64"
    }


def decompress_payload(compressed_b64: str, compression_method: str = "") -> dict:
    """
    解压数据（供云端或调试用）
    """
    compressed = base64.b64decode(compressed_b64)
    raw_bytes = zlib.decompress(compressed)

    if "msgpack" in compression_method:
        import msgpack
        return msgpack.unpackb(raw_bytes, raw=False, strict_map_key=False)
    else:
        return json.loads(raw_bytes.decode('utf-8'))



