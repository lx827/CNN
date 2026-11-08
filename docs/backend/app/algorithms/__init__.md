# `algorithms/` — 独立数值算法库

**对应源码**：`cloud/app/algorithms/__init__.py`

算法库只包含纯计算，不导入 FastAPI、SQLAlchemy、ORM、设备数据库、缓存或全局业务配置。

## 分层

- `core/`：带单位的结构化数据类型。
- `mechanics/`：机械对象运动学模型。
- `bearing/`：包络计算、指标提取与评估。
- `order/`：标量/局部/连续转速、积分相位、等角重采样与单边幅值阶次谱。
- `pipelines/`：按诊断对象组合算法、分析和评估。

数组在算法层保持 NumPy；到业务或 HTTP 输出层再转换为列表。算法失败通过明确异常或 `indeterminate` 状态表达，不把失败伪装成健康。
