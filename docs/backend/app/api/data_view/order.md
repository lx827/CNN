# `order.py` — 阶次跟踪

**对应源码**：`cloud/app/api/data_view/order.py`

路由只负责数据库读取、5 秒截断、线程池调度、诊断转频写入和 JSON 适配。算法唯一来源为 [`algorithms/order/`](../../algorithms/order/__init__.md)。

## `GET /{device_id}/{batch_index}/{channel}/order`

参数保持 `freq_min/freq_max/samples_per_rev/max_order/rot_freq/detrend/denoise/db` 不变，响应 `data` 字段也保持：

```text
{device_id, batch_index, channel, channel_name, sample_rate, is_special,
 rot_freq, rot_rpm, rot_freq_std, tracking_method, samples_per_rev,
 orders, spectrum}
```

- `rot_freq` 传入：已知准确标量转频，走无 tach 恒速等角重采样。
- 未传入：先分帧估计并做 MAD 异常帧处理；CV≤10% 返回逐帧角域谱平均，CV>10% 切换 STFT 脊线、连续转速、积分相位和等相位重采样。
- `tracking_method` 仍为 `single_frame/multi_frame/varying_speed`。
- `orders` 是 FFT bin 阶次轴，不是角域采样点位置；`spectrum` 是输入单位下的 `single_sided_amplitude`。两者序列化均保留六位小数，避免粗取整破坏谱轴和幅值验证。
- 多帧结果不对外伪装连续相位；快速变速的 `rot_freq/rot_freq_std` 只是连续轨迹摘要。
- 转速估计使用未去噪的 `raw_sig`；调用方显式选择的 `denoise` 只作用于重采样信号。去噪和计算继续通过 `asyncio.to_thread`，不新增并发。

无可靠标量转频或快速变速脊线时返回 HTTP 400 和具体原因，不写正常阶次谱、不回退固定 10 Hz。只有有效结果且已存在明确批次级记录时才更新转频摘要：规范记录为 `channel=0/denoise_method="none"`，另兼容 `channel/denoise_method` 全为 NULL 的旧批次记录。没有批次记录时仅返回阶次结果，不创建 `health_score=100/status="normal"` 的伪诊断；通道级和其他去噪缓存绝不参与该更新。JSON 字典更新显式标记变更，确保提交后真正持久化。
