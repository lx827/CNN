### 文件: api/__init__.py -> docs/backend/app/api/__init__.md
- **状态**: 完整
- **已覆盖函数/方法**: []
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/alarms.py -> docs/backend/app/api/alarms.md
- **状态**: 完整
- **已覆盖函数/方法**: ['get_alarms', 'resolve_alarm', 'delete_alarm']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/auth.py -> docs/backend/app/api/auth.md
- **状态**: 完整
- **已覆盖函数/方法**: ['create_access_token', 'verify_token_string', 'get_current_user', 'optional_auth', 'login']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/collect.py -> docs/backend/app/api/collect.md
- **状态**: 完整
- **已覆盖函数/方法**: ['request_collection', 'get_pending_tasks', 'complete_task', 'get_task_status', 'get_collection_history']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/dashboard.py -> docs/backend/app/api/dashboard.md
- **状态**: 完整
- **已覆盖函数/方法**: ['get_dashboard']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/data_view/__init__.py -> docs/backend/app/api/data_view/__init__.md
- **状态**: 完整
- **已覆盖函数/方法**: ['prepare_signal', '_compute_cepstrum', '_get_channel_name']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/data_view/cepstrum.py -> docs/backend/app/api/data_view/cepstrum.md
- **状态**: 完整
- **已覆盖函数/方法**: ['get_channel_cepstrum']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 无

### 文件: api/data_view/core.py -> docs/backend/app/api/data_view/core.md
- **状态**: 完整
- **已覆盖函数/方法**: ['get_all_device_data', 'get_device_batches', 'get_channel_data', 'delete_special_batches', 'delete_batch']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/data_view/diagnosis_ops.py -> docs/backend/app/api/data_view/diagnosis_ops.md
- **状态**: 完整
- **已覆盖函数/方法**: ['_sanitize_for_json', 'update_batch_diagnosis', 'get_channel_diagnosis', 'reanalyze_batch', 'reanalyze_all_batches']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 无

### 文件: api/data_view/envelope.py -> docs/backend/app/api/data_view/envelope.md
- **状态**: 完整
- **已覆盖函数/方法**: ['get_channel_envelope']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 无

### 文件: api/data_view/export.py -> docs/backend/app/api/data_view/export.md
- **状态**: 完整
- **已覆盖函数/方法**: ['export_channel_csv']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/data_view/gear.py -> docs/backend/app/api/data_view/gear.md
- **状态**: 完整
- **已覆盖函数/方法**: ['_extract_device_param', '_has_valid_bearing', '_has_valid_gear', 'get_channel_gear', 'get_channel_analyze', 'get_channel_full_analysis']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 无

### 文件: api/data_view/order.py -> docs/backend/app/api/data_view/order.md
- **状态**: 完整
- **已覆盖函数/方法**: ['get_channel_order']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 无

### 文件: api/data_view/research.py -> docs/backend/app/api/data_view/research.md
- **状态**: 完整
- **已覆盖函数/方法**: ['_save_research_diagnosis', 'get_method_info', 'get_channel_method_analysis', 'get_channel_research_analysis']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/data_view/spectrum.py -> docs/backend/app/api/data_view/spectrum.md
- **状态**: 完整
- **已覆盖函数/方法**: ['get_channel_fft', 'get_channel_stft', 'get_channel_stats']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/devices/__init__.py -> docs/backend/app/api/devices/__init__.md
- **状态**: 部分缺失
- **已覆盖函数/方法**: []
- **缺失函数/类**: ['_get_channel_params(device, channel_index, field)']
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/devices/config.py -> docs/backend/app/api/devices/config.md
- **状态**: 完整
- **已覆盖函数/方法**: ['get_edge_config', 'get_device_config', 'update_device_config', 'update_batch_config', 'get_alarm_thresholds', 'update_alarm_thresholds']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/devices/core.py -> docs/backend/app/api/devices/core.md
- **状态**: 完整
- **已覆盖函数/方法**: ['get_devices']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/ingest.py -> docs/backend/app/api/ingest.md
- **状态**: 完整
- **已覆盖函数/方法**: ['_decompress_channels', '_get_next_batch_index', 'ingest_data']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/monitor.py -> docs/backend/app/api/monitor.md
- **状态**: 部分缺失
- **已覆盖函数/方法**: ['get_latest_monitor', 'get_monitor_history']
- **缺失函数/类**: ['_get_channel_name(device: Device, channel_num: int) -> str']
- **类型注解缺失**: []
- **算法链接**: 不适用

### 文件: api/system.py -> docs/backend/app/api/system.md
- **状态**: 完整
- **已覆盖函数/方法**: ['get_logs']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法链接**: 不适用

---
### 统计总结
- **总文件数**: 21
- **完整**: 19
- **部分缺失**: 2
- **文档缺失**: 0
- **算法文件总数**: 5
- **算法文件有链接**: 0
