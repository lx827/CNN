# Bug 记录

> 最后更新: 2026-10-25 | 详见 AGENTS.md §14

## 未修复 (2)

| # | 文件 | 描述 |
|---|------|------|
| 11d | `ensemble.py`, `health_score.py` | D-S 证据融合未生效（0/30 样本被覆盖）|
| 13d | `ensemble.py` | **WTG 五分类断齿检出 0%** — gear_abnormal 标签映射缺失 |

## 已修复 (31)

| # | 文件 | 描述 |
|---|------|------|
| 29 | 本机CQU批量实验汇总脚本 | **第二组结束后汇总报FileExistsError** — 误用独占创建JSON函数反复更新进度；改为本任务临时文件原子替换，校验配置后复用已完成目录。后续两组及扩展进度更新成功，旧模型未覆盖；实验随后按用户要求停止 |
| 27 | `training/cqu/full_model.py`（O9现场适配） | **域对抗方向反转两次** — 固定版本负熵目标经过GRL后令编码器降低熵；经用户确认，在CQU适配中固定D、直接最小化负熵且只施加一次ramp，原上游代码保留 |
| 28 | `training/cqu/full_model.py`（STFT适配） | **完整O9的CUDA反向在确定性模式报错** — 原反射补边缺少确定性反向，改用等价切片/翻转/拼接，保留原信号边界和STFT设置 |
| 11 | `run_all.py`, `ensemble.py`, `engine.py` | **Ensemble 五分类偏向 BPFO** — 根因链修复（见下） |
| 11c | `engine.py` | ✅ **显著性主导比过滤** — 主导峰需 > 次强峰 1.5× |
| 12 | `engine.py` | **Teager Ottawa/CW 耗时爆炸（212s→0.3s）** — samples_per_rev 1024→256 |
| 13 | `features.py`, `ensemble.py`, 评估脚本 | ✅ **WTG 五分类 20%→51.25%** — 全链路修复（见下） |
| 14 | `preprocessing.py`, `vmd_denoise.py` | ✅ **小波+VMD 级联 ΔSNR +0.19→+0.98dB** — 见下 |
| 15 | `Monitor.vue` | **实时监测首次进入/返回后波形为空，切换通道才显示** — 先初始化图表再加载数据，同步注册卸载清理并移除旧推送订阅 |
| 16 | `dashboard.py`, `monitor.py`, `data_view/core.py`, `diagnosis_queries.py` | **列表慢/摘要不一致** — N+1、全量诊断 JSON 加载、按插入顺序覆盖；改为批量摘要查询，统一按时间/id 选最新，补复合索引 |
| 17 | `data_view/research.py` | **研究诊断缓存一直无法保存** — 使用未导入的 timezone，NameError 被捕获；显式导入并验证插入/更新 |
| 18 | `core/json_utils.py`, `data_view/__init__.py` | **NaN/Infinity 导致 HTTP JSON 编码失败** — 原转换器未递归处理数组中的非有限值；严格转换为 null |
| 19 | `spectrum.py`, `cepstrum.py`, `order.py` | **去噪阻塞全站协程调度** — async 路由直接执行慢去噪；改为复用原有两线程池 |
| 20 | `Dashboard.vue` | **离开后轮询/订阅泄漏、仪表盘不刷新、critical 显示未知** — 同步卸载注册，刷新选中对象，兼容 critical/fault |
| 21 | `Monitor.vue` | **重复刷新、旧设备慢响应覆盖、慢轮询叠加** — 合并推送/串行刷新/保留一次后续刷新，丢弃旧设备响应，完成后再调度轮询 |
| 22 | `utils/websocket.js` | **重复握手、旧 close 破坏新心跳、多个重连定时器** — OPEN/CONNECTING 幂等，校验连接实例，定时器去重 |
| 23 | `Dashboard.vue` | **总览推送与轮询并发，慢响应可覆盖新数据** — 多个入口直接查询且无串行约束；共用在途 Promise，保留一次后续查询，卸载丢弃排队事件 |
| 24 | `lifespan.py` | **后台诊断入库 JSON 序列化失败，批次长期未分析** — 仅转换通道缓存，遗漏批次结果中的 NumPy 类型；现于算法返回后统一转换完整结果（本地及云端验证通过） |
| 25 | `edge/replay.py` | **启动器退出后遗留 Vite 子进程** — 持有 cmd/npm 包装进程且忽略终止失败，无法可靠确认 Node 已退出；改为直接持有 Vite 的 Node 进程，终止失败时回退并等待退出 |
| 26 | `edge/replay.py` | **快速启动重复打开两个页面** — Vite 的 `open:true` 与启动器的 `webbrowser.open` 同时执行；仅对子进程设置 `BROWSER=none`，统一由启动器打开一次 |

**Bug #27–28 验证（2026-10-25）**：

- #27触发于负熵损失经正强度GRL回传编码器。独立三类分数检查中，一步更新的归一化熵由0.477208降到0.476073；修正后提高到0.478345，梯度方向与原来相反。完整单步检查确认主更新不向D参数产生梯度，判别器仍按来源监督更新。不据此推断历史所有模型的成绩，也未修改另一个wavelet仓库。
- #28触发于启用`torch.use_deterministic_algorithms(True)`的CUDA重构损失反向。CPU双精度四尺度STFT前向逐值相同、梯度误差在`1e-12`内；CUDA前向逐值相同，等价实现的严格确定性反向通过。三个任务×四种初始化共12次完整短程GPU运行通过，覆盖健康预训练、原型/原始重构及有效域对抗路径。
- 本机测试、原失败日志及详细结果留在忽略目录`tmp/cqu/o9_full_training_20261025/`。这仅验证训练链路和修正方向，不是正式识别率或旧类能力保留实验。

**Bug #26 验证（2026-10-24）**：`tests/edge/test_browser_open.py` 使用真实 Vite、临时端口和浏览器脚本探针，在修复前确认 Vite 额外打开，修复后探针不再触发且启动器只打开一次；复用已有前端同样只打开一次。父进程浏览器环境保持原值，不修改前端代理或 `open:true` 配置，不访问云端、不上传数据。

**Bug #25 验证（2026-10-23）**：清理工作区前确认残留 Node 占用本机 3000 端口。`tests/edge/test_frontend_lifecycle.py` 使用真实 Vite，覆盖正常返回及 Ctrl+C 两条路径；修复后均确认所创建 Node 退出、3000 端口不再提供服务。不访问云端或上传数据，已运行的用户前端仍直接复用。

**Bug #24 验证（2026-10-23）**：

- 触发条件：后台分析输出的批次 `order_analysis` 含 NumPy 布尔等非 JSON 原生类型；普通数据上传仍成功，但诊断事务提交失败，已分析标记和健康度更新一起回滚。
- 根因：`full_analysis` 的转换不覆盖批次诊断，SQLAlchemy JSON 编码抛出 `Object of type bool is not JSON serializable`。在 `analyze_device` 返回后对完整结果调用现有 `sanitize_for_json`，供后续入库、告警与推送使用；不改算法评分或数据来源。
- `tests/backend/test_analysis_worker_json.py` 两项修复前均复现同一错误，修复后通过；覆盖真实内存 SQLite 提交、通道新增/覆盖、原始数据已分析、设备健康度、告警输入与严格 JSON 推送。后端 12 项测试、三项 P0 回归通过；变速阶次回归使用恢复目录的 HUSTbear 样本。
- 云端 SSH 非交互认证未通过，改由用户通过阿里云 Workbench 在独立本地任务分支应用同一处修复；保留原文件备份，重启后 `CNN` 服务为 active。未整体升级云端代码。
- 云端实测（2026-10-23，北京时间 19:51 后）：沿用已确认的 CW 回放，每台上传一批恢复在线；WTG-001 批次 6/7、WTG-002 批次 7/8、WTG-003 批次 7/8 六个新旧批次均 `is_analyzed=1`，已保存的通道诊断均可读取，近期日志未再出现序列化错误。未启动持续回放，不代表算法诊断准确率评估。
- 本地修复与另一 AI 的主工作区改动通过独立 worktree 隔离，未推送或合并。

**Bug #16–22 验证（2026-10-21）**：

- 每组均先通过实际函数/端点/真实 Vue 生命周期的测试复现，再修改实现；没有使用线上数据库或向现场设备下发采集。
- 后端 `tests/backend/test_read_paths.py`：总览 11 台设备由 16 次 SELECT 降为 3 次，历史 16 个批次由 17 次降为 2 次；批次列表不加载完整算法 JSON，两列表结果一致；缓存插入/覆盖、严格 JSON、旧库重复补索引、真实应用五条 HTTP 读路径均通过。
- 后端 `tests/backend/test_event_loop.py`：用受控慢去噪在 STFT/倒谱/阶次实际端点上验证其他协程能被调度，修复前三个端点均失败，修复后通过。不代表真实 VMD 算法耗时降低。
- 前端 `monitor_lifecycle.test.cjs`（7 项）、`dashboard_lifecycle.test.cjs`（6 项）、`websocket.test.cjs`（3 项）全部通过；不覆盖实际浏览器像素渲染。
- 三项 P0 回归通过，前端生产构建通过。线上 P95 延迟、MySQL/Ubuntu 环境、完整数据集分类效果未验证。原有 #11d/#13d 仍未解决。

**仍需核实的语义/架构问题**：`/monitor/latest` 默认按最大 batch_index 取批次，普通批次循环覆盖、特殊批次长期保留，因此“最新”不必等于采集时间最近；设备转频与所展示批次也可能不是同批。改变此规则会影响结果含义，本轮未改。同步数据库访问、后台事务范围、重复诊断缓存写入的竞争还需进一步单独验证。详见 [本轮架构记录](架构整顿记录_20261021.md)。

**Bug #23 复核补充（2026-10-21）**：慢总览查询期间，上线、离线推送和兜底轮询同时触发时，原代码会产生 4 个并发请求；响应顺序不受控制，可能回写旧状态。新增三项受控 Promise 回归，修复前全部失败，修复后通过：验证同一时刻仅一个查询、连续事件只保留一次后续刷新、卸载不再刷新、失败后仍处理后续事件且不会锁死。通过串行调度消除并发响应倒序，不改变设备状态或诊断含义。

**Bug #15 详细（2026-10-19）**：

- **触发条件**：首次进入实时监测，或切换到其他路由后返回；请求未完成时离开页面也会遗留资源。
- **根因**：挂载回调先执行 `loadLatestData()`，其中的 `updateCharts()` 在图表实例创建前调用，随后 `initCharts()` 创建的是空图表；手动切换通道才重新绘图。`onUnmounted` 又在异步挂载的 await 之后注册，Vue 无法关联组件，导致清理不执行；单例 WebSocket 的匿名回调也未被移除。
- **修复**：先初始化图表，再请求并绘制数据；在 setup 阶段同步注册卸载钩子，用具名回调取消 WebSocket 订阅，释放图表、轮询和 resize 监听，并阻止卸载后的异步初始化和绘图。
- **验证**：`tests/frontend/monitor_lifecycle.test.cjs` 使用真实 Vue 生命周期和模拟 API/ECharts，修复前 3 项均失败，修复后 3 项通过，覆盖默认通道首屏、切换通道、离开再进入、订阅清理和请求尚未完成时离开。该测试不验证浏览器实际像素渲染或云端在线采集。

**Bug #11 详细**（根因分析与修复记录）：

**现象**：HUSTbear 五分类 Accuracy=30%，内圈/外圈/复合全部预测为"外圈"。

**根因链**：

1. **评估脚本标签映射子串匹配 Bug（直接原因）**
   - `run_all.py`：`"bpfo" in "bearing_bpfo_bpfi"` → True，复合故障被误判为外圈

2. **`_fault_label` 拼接逻辑无区分力（直接原因）**
   - `ensemble.py`：`return "bearing_" + "_".join(param_hits[:2])`
   - 字典插入顺序固定为 BPFO→BPFI→BSF，只要 BPFO 被标记就排第一

3. **物理参数路径 `significant` 阈值过低（深层原因）**
   - `engine.py`：`significant = snr > 4.5`
   - 诊断统计：健康样本 4/6 被误检；内圈样本 BPFO 被强检（SNR 126.5±60.0）

4. **显著性判定缺乏故障类型间区分机制（本质原因）**
   - 三个故障频率独立判定，无相对强度排序
   - 无主导峰验证（外圈应以 BPFO 为最强峰）
   - 内圈边带验证仅用于 False→True 翻转，不参与主决策

5. **D-S 证据融合未生效**
   - `get_ds_label` 要求 `dominant_prob > 0.4 and uncertainty < 0.3`
   - 诊断结果：0/30 样本被 D-S 融合覆盖

**修复记录**：

| 层级 | 文件 | 修复内容 | 状态 |
|------|------|---------|------|
| 1 | `tests/diagnosis/eval_plots/run_all.py` | 标签映射改用精确匹配：`fl == "bearing_bpfo"` 替代 `"bpfo" in fl` | ✅ 已修复 |
| 2 | `cloud/app/services/diagnosis/ensemble.py` | `_fault_label` 按 SNR 降序取主导峰，不再拼接多故障标签 | ✅ 已修复 |
| 3 | `cloud/app/services/diagnosis/engine.py` | `significant` 增加相对主导过滤：只有最强峰或 SNR>15 才保留 significant | ✅ 已修复 |
| 4 | `cloud/app/services/diagnosis/engine.py` | 需引入主导峰排序、谐波族验证、相对 SNR 机制 | ⏳ 待修复 |
| 5 | `cloud/app/services/diagnosis/ensemble.py` | D-S 融合参数或输入质量待调整 | ⏳ 待修复 |

**Bug #12 详细**（Teager Ottawa/CW 耗时爆炸）✅ 已修复

**现象**：2026-05-21 评估中，Teager 在 HUSTbear 99 样本上平均 1,366ms，但在 Ottawa/CW 36 样本上平均 **212,654ms（×155）**。

**根因**：`engine.py:263` Teager 变速路径 `samples_per_rev=1024`，CW 5s@20Hz→102,400 点信号（原 ×2.5），`fast_kurtogram` L1 STFT nperseg=51,200→25,601 频点迭代。

**修复**：`samples_per_rev` 1024→256，信号 102,400→25,600，nperseg 51,200→12,800。

**效果**：CW 单文件 212,654ms→~300ms (**×700**)，准确率保持（H-A-1 302ms sig=3, I-A-1 361ms sig=2, O-A-1 217ms sig=2）。

**修复验证**（层级1+2+3修复后）：

- P0 回归测试：全部通过
- `run_all.py` 五分类（99样本）：Accuracy 24.24%
- 混淆矩阵变化：
  - **修复前**：内圈/外圈/复合 **全部预测为外圈**（子串匹配 Bug）
  - **修复后**：预测分布分散，不再全部偏向外圈
  - `fault_label_raw` 分布（30样本诊断）：
    - 健康：`bearing_bsf`(3), `unknown`(2), `bearing_bpfo`(1)
    - 球故障：`bearing_bpfo`(3), `bearing_bpfi`(2), `bearing_bsf`(1)
    - 内圈：`bearing_bpfi`(3), `bearing_bpfo`(3)
    - 外圈：`bearing_bsf`(4), `bearing_bpfo`(2) ⚠️ 外圈误判为球故障较多
    - 复合：`bearing_bpfo`(4), `bearing_bpfi`(2)
- 结论：层级1+2+3修复消除了"全部预测外圈"的假象和多参数误检，但**外圈→球故障**、**球故障→外圈**的交叉误判仍较严重，需层级4（谐波族/主导峰机制）进一步改善

**Bug #13 详细**（WTgearbox 五分类）✅ 已修复

**现象**：WTgearbox 五分类 20%，几乎所有故障→"健康"。

**根因链**：

1. `features.py:393`：`has_gear_params` 只认 `input`（定轴箱），不认 `sun`（行星箱）→ `skip_gear=True`
2. `ensemble.py:199`：行星箱 `GEAR_KURT_THRESHOLD=10` 过高 → `impulse_context=False`
3. `ensemble.py:321`：`_fault_label` 轴承优先 → 齿轮数据上报虚假轴承故障

**修复**：

- `features.py`：`has_gear_params` 增加 `sun` 键识别
- `ensemble.py`：`GEAR_KURT_THRESHOLD` 10→6, `GEAR_CREST_THRESHOLD` 10→8
- `ensemble.py`：`_fault_label` 齿轮优先逻辑
- 评估脚本：6 处补传 `bearing_params`

**效果**：WTG 五分类 20%→**51.25%**，Bal Acc 61.4% 缺陷(F1=0.74)裂纹(F1=0.54)大幅提升。断齿仍 0%（#13d）。

**Bug #14 详细**（小波+VMD 级联去噪效果反常）

**现象**：`评估报告_20260521.md §4.7` 去噪效果评估中，VMD 单独 ΔSNR=+3.18dB，小波+VMD 级联仅 +0.19dB（差 ~15 倍）。

**根因链**：

1. **级联时 VMD 的 IMF 筛选基准错误（直接原因）**
   - `vmd_denoise.py:236-242`：IMF 相关性计算以 **VMD 输入信号**为参考
   - 级联时 VMD 输入 = 小波去噪后信号（已失真），而非原始含噪信号
   - 小波去噪后的信号能量已衰减，IMF 与这个"失真基准"的相关性被低估 → 有用 IMF 被错误丢弃

2. **"串联失真"叠加（设计原因）**
   - `preprocessing.py:255-266`：`cascade_wavelet_vmd` 先小波、后 VMD
   - 小波 `db8` 软阈值永久移除部分频带能量（含噪声 + 边缘有用信号）
   - VMD 再对"已失真信号"二次处理，两次非线性失真叠加

3. **单独 VMD 效果好的原因（对比）**
   - 单独 VMD 输入 = 原始含噪信号，噪声能量帮助提高了 IMF 整体相关性
   - 更多 IMF 通过 `corr>0.3` 筛选，重构信号结构更完整

**修复记录**：

| 层级 | 文件 | 修复内容 | 效果 |
|------|------|---------|------|
| 1 | `vmd_denoise.py` | `vmd_denoise()` 新增 `reference_signal` 参数，级联时以原始含噪信号为 IMF 筛选基准 | 避免 IMF 与"已失真小波输出"的相关性被低估 |
| 2 | `preprocessing.py` | `cascade_wavelet_vmd()` 新增 `wavelet_threshold_scale=0.5` 参数（默认 0.5，原为隐式 1.0） | 降低小波软阈值强度，避免过度去噪扭曲信号结构 |
| 3 | `preprocessing.py` | `cascade_wavelet_vmd()` 调用 `vmd_denoise()` 时传入 `reference_signal=arr` | 联合修复 |

**修复验证**：

- P0 回归测试：全部通过
- 去噪效果评估（`run_eval.py` 实验C）：
  - 修复前：小波+VMD 级联 ΔSNR = **+0.19 dB**
  - 修复后：小波+VMD 级联 ΔSNR = **+0.98 dB**（提升 **5.2×**）
  - 对比：VMD 单独仍为 +3.18 dB（级联受小波前置失真限制，无法超越单独 VMD）

## 2026-10-26：CQU训练页面缺少全部组回看入口，完成状态含义不清

**触发条件与现象：** 多组训练中，用户主要看到当前单组曲线和“已完成”，无法一屏回看全部组，也容易把单组结束理解成全批结束。用户反馈网页与终端状态不一致；检查时磁盘实时页和训练摘要均为32/36，未复现源文件将整批错误标为完成，具体浏览器旧页面状态未确认。

**根因：** 页面仅提供单组切换，没有按计划组织的全部组结果表；完成标签未明确限定为“本组”。结果数据没有丢失。

**修复：** 增加全部组总览、三折对比、任务筛选和逐组详情；明确整批与本组状态，仅在计划组全部有成功摘要时标记整批完成。完整数据嵌入HTML，最终快照可关闭终端后离线重开。

**验证：** 实际Edge旧页回归在缺少36组表时失败，修复后36组、12条三折汇总、筛选和跨组详情/重开通过；最终真实36/36离线页复核通过，无JavaScript异常或外部资源请求。未改变模型、数据划分或训练目标。详细证据在本机`tmp/cqu/o9_results_20261026/`，接口见`training/cqu/FULL_TRAINING.md`。
