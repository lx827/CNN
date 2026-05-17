# `config.py` — 全局配置

**对应源码**：`cloud/app/core/config.py`

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `USE_SQLITE` | bool | true | 数据库类型 |
| `DATABASE_URL` | str | sqlite:///./turbine.db | 连接 URL |
| `API_HOST` | str | 0.0.0.0 | 监听地址 |
| `API_PORT` | int | 8000 | 监听端口 |
| `CORS_ORIGINS` | list | 多个 localhost | CORS 源 |
| `ANALYZE_INTERVAL_SECONDS` | int | 30 | 后台分析间隔 |
| `SENSOR_SAMPLE_RATE` | int | 25600 | 默认采样率 |
| `SENSOR_WINDOW_SECONDS` | int | 10 | 采集窗口秒数 |
| `ANALYZE_DENOISE_METHOD` | str | wavelet | 默认去噪方法 |
| `NN_ENABLED` | bool | false | 神经网络开关 |
| `NN_MODEL_PATH` | str | ./models/... | 模型路径 |
| `ADMIN_PASSWORD` | str | admin123 | 网页密码 |
| `SECRET_KEY` | str | change-me... | JWT 密钥 |
| `EDGE_API_KEY` | str | turbine-edge-secret | 边端 API Key |
| `DIAGNOSIS_WEIGHTS` | dict | 20+ 项 | 诊断权重（kurtosis, crest_factor, rms, peak, bpfo, bpfi, bsf, sideband, fm4, ser, car, gear_sideband, na4_nb4, scoh_evidence, wp_entropy, ds_conflict, worst_channel, avg_channel） |
