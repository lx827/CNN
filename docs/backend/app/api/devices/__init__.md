# `__init__.py`

**对应源码**：`cloud/app/api/devices/__init__.py`

路由器初始化 + 公共导入。

## 函数

### `_get_channel_params`

```python
def _get_channel_params(device, channel_index, field)
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `device` | `Device` 或 `None` | 设备实例 |
| `channel_index` | `int` | 通道索引（从 1 开始） |
| `field` | `str` | 配置字段名（如 `bearing_params`、`gear_teeth`） |

- **返回值**：`dict` / `None` — 该通道对应的参数字典；无配置时返回 `None`
- **说明**：从设备配置中按通道索引提取参数。支持旧格式（设备级共用，如 `{input:18}`）和新格式（通道级独立，如 `{"1":{input:18}}`）两种结构。若顶层包含业务字段（`input`/`n`/`output`）而非通道键，直接返回原字典作为兼容回退。
