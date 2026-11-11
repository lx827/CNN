# Bug 记录

> 最后更新: 2026-11-12 | 新增四套原始数据效果实验发现的评估策略/适用域问题；实验完成不代表诊断质量达标。

## 未修复 (4)

| # | 文件 | 描述 |
|---|------|------|
| 11d | 历史 ensemble/评分实验 | 旧 D-S 未生效的 0/30 实验需按 #78 新 Evidence 重建效果；旧实现已删除，不把结构修复等同于真实检出恢复 |
| 13d | 历史 WTG 五分类实验 | 断齿检出 0% 的旧标签/实验协议已退役，新对象 Pipeline 不直接命名断齿；新分类效果仍归 #78，未宣称已解决 |
| 44 | `algorithms/gear/planetary/`、本地健康基线策略 | **跨拆装健康基线误报（适用域问题）**：同速度同通道用 N1 健康记录训练太阳轮事件候选峰界限，再评估独立拆装后的 N2 健康记录，窄带包络候选峰触发异常，组合结果随之误报。预期是经独立健康对照验证后才将界限作为可用告警依据；实际临时界限不能覆盖安装变化。后续先补独立健康安装用于训练/验证并检查方法级界限，再用原冻结测试清单验收；不在当前测试标签上改阈值。未证实为算法数学错误，未部署该试验基线。 |
| 45 | `algorithms/bearing/evaluation.py`、`algorithms/gear/fixed_axis/evaluation.py` | **健康记录触发工程阈值（评估策略问题）**：Ottawa 当前模型及自动估速下健康记录出现包络统计/物理候选峰告警；HUSTbear 名义几何/速度条件与 HUST 定轴名义速度条件下，健康记录也触发包络统计、SER、边带计数或阶次统计告警。预期是参数前提与健康阈值均在相应工况独立验证后形成可用异常判断；实际补参数增加覆盖却未解决误报。后续分开核对估速/参考轴证据、健康安装差异与各指标阈值，不将条件实验视作已校准产品能力，也不据此宣称数学实现错误。 |

**本地效果问题复现**：按 [四来源实验说明](benchmarks/diagnosis_effectiveness.md) 运行冻结清单。生成的逐记录结果、指标与分析报告仅保留在 `DATA_ROOT/real_diagnosis/effectiveness/`，不入库；本轮没有据测试结果调整生产阈值或删除困难样本。

## 已修复

| # | 文件 | 描述 |
|---|------|------|
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
| 25 | `dc24/replay.py`（已退役） | **启动器退出后遗留 Vite 子进程** — 持有 cmd/npm 包装进程且忽略终止失败，无法可靠确认 Node 已退出；改为直接持有 Vite 的 Node 进程，终止失败时回退并等待退出 |
| 26 | `dc24/replay.py`（已退役） | **快速启动重复打开两个页面** — Vite 的 `open:true` 与启动器的 `webbrowser.open` 同时执行；仅对子进程设置 `BROWSER=none`，统一由启动器打开一次 |
| 27 | `dc24/dc24_vendor_bridge.ps1` | **厂商 DLL 连接在首个采样帧后自动停止**。边端经 DLL 套接字发送 B7 前先同步该设备在 DLL 中的采集状态。实机重测及网页网卡抓包确认连续收样与正常停止。见 [DC24 工作记录](DC24_ACQUISITION_WORKLOG.md)。 |
| 28 | `algorithms/bearing/`, `engine.py`, `data_view/envelope.py` | **标准包络谱未归一化、频带元数据失真、max_freq 未生效、转频失败默认 10Hz** — 新 Pipeline 返回实际频带和单边幅值谱；非法输入显式报错，缺转频返回 `indeterminate`，HTTP 与集成测试覆盖 |
| 29 | `algorithms/bearing/analysis.py`, `evaluation.py` | **展示截断改变诊断、粗分辨率共享谱峰、BPFI 边带补救被覆盖、低频能量误判转频谐波、边带分母错误** — 分析/展示分离；唯一局部峰和 `not_evaluable`；载波/边带/最终证据分离；转频整数倍窄带判定；独立数学回归覆盖 |
| 30 | `algorithms/bearing/analysis.py`, `evaluation.py`, `ensemble.py`, `health_score_continuous.py` | **最近 bin 漏掉偏移真峰、边带只计检出峰放大密度、带后缀低频键被消费者忽略** — 改为容差内局部峰全局唯一分配；理论可观测目标与实际峰分离；健康评分与 ensemble 统一读取 `low_freq_ratio_stat`，真实提取测试验证 |
| 31 | `algorithms/order/`, `order_tracking.py`, `engine.py`, `data_view/order.py` | **阶次轴语义重载、幅值未按单边峰值归一化、固定 STFT 512 分辨率过粗、MAD 近零误删、失败默认 10Hz/退回恒速** — 转速/相位结构化分型；自适应 STFT 与梯形积分；逐帧谱平均和连续相位分离；不可判定显式失败；独立公式测试与 Engine/API 集成覆盖 |
| 32 | `algorithms/order/`, `engine.py`, `gear/metrics.py`, `data_view/order.py` | **单帧/slow 失败绕过 fast、长期越界被 clip、首尾 bin 误判越界、边缘帧数/采样点单位混用、零 MAD 保留离群、窄带纯音误拒、快速变速轴承摘要成恒速、FM0 主瓣重复计数、/order 伪造健康并覆盖通道缓存** — 全记录解析反例回归；亚 bin 峰位与外侧能量区分近边界/越界；FM0 改取谐波峰值；只更新明确批次记录并标记 JSON 变更；失败测试脚本非零退出 |
| 33 | `tests/.../synthetic_signals.py`, `algorithms/order/estimation.py` | **轴承合成器声明 rot_freq 却未生成轴频，BPFO 冲击被误当转频** — 合成器加入可观测弱 1×轴频；保持谐波/次谐波/Welch/自相关仲裁，不按故障阶次比例猜转速；Engine 同时验证 25Hz 转频与约 90Hz BPFO，foundation 失败非零退出 |
| 34 | `deploy.sh` | **一键部署在 venv 时代旧 ECS 上两处失效(单元未更新/根环境未生成)** — 防御性修复:uv 引导 PATH 无条件生效并验证可执行;`uv sync` 后断言 `.venv/bin/python` 存在,缺失即中止不动服务;unit 强制校验指向 `.venv` 解释器,不符即备份覆盖;重启后等待真正 active(30s)。WSL dry-run 与 ECS 实跑全绿,边端心跳自动恢复 |
| 35 | 生产 `cloud/.env` | **旧文件缺少网页密码与 JWT 密钥,服务回退到默认值** — 2026-11-11 在 ECS 补入独立生成的 32 字符随机密码与 96 字符随机 hex 签名密钥,原子替换并收紧权限为 root/0600,保留私密备份后重启。现有 ASCII `EDGE_API_KEY` 保持不变。新登录/新 JWT/边端密钥读取均 200,默认密码/旧 JWT 均 401,Nginx 登录 200;详见下方证据 |
| 36 | `algorithms/gear/fixed_axis/`、齿轮业务消费者 | **TSA 表示混用、FM0 主瓣重复计数、无历史仍报告趋势、服务层重复重算** — #71 使用对象 Pipeline，明确 regular/residual/differential 与 nonsynchronous，独立评估并保留 NA4/NB4 不可评估；PR #85 已合并 |
| 37 | `algorithms/bearing/`、`advanced_bearing.py` | **伪 Fast Kurtogram、MCKD 目标/更新混用、CPW 空先验冒名、SC 专属评估被覆盖、TEO 单位失真、秩亏有限解误报成功** — #73 真实命名滤波器组、显式目标与实际 MED 回退、稳定梳状门控、SC 频移专属评估、TEO 平方单位、SVD 数值秩；开发分支已集成 |
| 38 | `algorithms/decomposition/`、去噪/模态消费者 | **WP 顺序/系数时间轴、DWT 混入未选频带、EMD 镜像/停止、VMD Hz/补零、熵归一化、未收敛仍诊断及吞错原信号** — #74 族专属 adapter、有效区间、原始指标/选择/故障阈值与质量门控；删除旧数学/导出，DenoisingError→HTTP422，后台未知不转规则成功、None 健康阈值不告警 |
| 39 | `algorithms/transforms/`、DataView/Monitor/DC24、`rule_based.py` | **未归一化重复频谱、先慢去噪后截断、倒谱表示混评估、规则回退伪健康/概率矛盾** — #76 统一数值表示、计算后抽点、counts 不诊断、复用对象评估；有效证据门控与阈值概率一致，校验嵌套 Mapping；开发分支已集成 |
| 40 | `algorithms/gear/planetary/`、行星业务/API/前端 | **行星 SER 被定轴覆盖、角域 residual 误用 fs、几何/参考轴丢失、原始研究结果冒充融合和故障命名** — #72 独立固定齿圈模型、carrier 搜索、角域点/转、当前通道完整配置与四方法公共入口；基线不足明确 unknown、未校准指标不告警；删除旧重复实现和三件旧测试，开发分支已集成 |
| 41 | composite 算法/Pipeline/研究 HTTP | **AM/FM 搜错载波边带、MSB 先取绝对值、伪 CVS 与虚假串联、研究组合误进生产** — #75 明确调制谱、Guo 四阶复平均与同量纲背景、真实相位/独立圈 CVS→MED→MSB、VMD→ICA 逆映射与资源门控；专用研究入口不写缓存/投票/告警 |
| 42 | domain/assessment/adapters/存储/流程 | **未知默认正常、相关方法重复票、扣分键回退/重复权重、缓存跨通道/去噪与手工覆盖批摘要** — #77/#84 类型化两维状态与 coverage、dependency 连通分组、规范扣分/单源建议、精确追加缓存与 channel0/none 摘要、旧 JSON 要求重分析、原始标记/告警同事务 |
| 43 | 统一前端状态 adapter/实际消费者 | **缺分补87/部件偏移造分、RMS自判健康、旧status默认正常/故障、隐藏局部未知** — getDiagnosisView 接完整 Domain 严格判定，DiagnosisCoverage 显示partial/局部原因；移除旧映射/votes/best/概率读取，未知中性、null不变0 |
| 25 | `composables/useSettings.js`(`MechanicalParamsCard.vue` 消费) | **设置页首渲染即崩、整页空白** — `gear_teeth/bearing_params` 初始为 {},模板无守卫直访通道字段,挂载中止致 onMounted 不执行无法自愈(396cf64 引入);现按 channel_count 预填并在通道数调大时补齐,三条崩溃路径真实模板回归覆盖(见下) |

**本批 #75/#77/#84 证据范围**：核心已知解/负对照与消融、真实隔离 HTTP/SQLite 缓存/worker/事务/告警及前端52项/构建有记录；首次后端79项的失败只做定向修复复验，没有伪称重跑全部。SQLite 旧库迁移幂等实际验证，MySQL SQL 未连接真实服务；真实数据效果、性能与生产部署未验证。当前已实现结构/业务修复不替代 #78/#79。

**2026-11-11 本轮证据范围**：算法专项以公式/手算、已知合成信号、负对照与独立审查为依据；业务/API/前端回归保护门控、状态和消费路径。新 Pipeline 的真实数据分类效果、阈值校准、性能与生产部署尚未由这些测试证明。主仓 CW 有 36 个变速 `.npy`，不应笼统记录为所有数据缺失；数据效果待 #78 按新契约建立。旧 #11d/#13d 的历史效果问题不因删除旧入口自动关闭。

**Bug #25(设置页首渲染)验证(2026-11-11)**:`wind-turbine-diagnosis/tests/settings_mechanical.test.cjs` 以真实 SFC 模板编译 + 透传插槽桩(保留 `el-tab-pane` 非 lazy 全渲染语义)覆盖三条路径——配置未返回首渲染、通道数 3→8 即时调整、配置加载失败;修复前均复现 `Cannot read properties of undefined (reading 'gear_type')`,修复后 3 项通过,前端全部 55 项测试与生产构建全绿。不覆盖浏览器像素渲染与真实云端配置加载。

**Bug #35 生产验证（2026-11-11，北京时间 20:43 后）**：

- SSH 核查 `/opt/CNN/cloud/.env` 缺少 `ADMIN_PASSWORD` 与 `SECRET_KEY`,应用解析得到默认值,systemd 进程环境也没有覆盖这两个键。`.env` 未被 Git 跟踪;当前 `deploy.sh` 未写入该文件,此次部署沿用了旧配置。
- 原文件备份到 `/root/.config/CNN/`（目录 0700、备份 0600）,仅追加两个独立随机值,验证原有所有键值及 `EDGE_API_KEY` 均未改变后原子替换 `.env`（0600）。新网页密码在服务器私密目录与操作者本机受限目录保存,秘密值不入库。
- 重启 `CNN.service` 后为 active/running。实际 HTTP 验证：新密码登录 200、`admin123` 登录 401;`GET /api/acquisition/agents` 使用新 JWT 为 200,使用重启前签发的旧 JWT 为 401,使用现有边端密钥为 200;经本机 Nginx 入口的新密码登录为 200。
- 验证时 `dc24-pi` 显示离线,最后心跳为北京时间 17:55:18,早于本次修复;未修改树莓派或声称现场心跳恢复。本次只修正生产配置,未修改认证代码或算法,未重跑算法回归。

**Bug #26 验证（2026-10-24）**：`tests/edge/test_browser_open.py`（已随旧回放链退役）使用真实 Vite、临时端口和浏览器脚本探针，在修复前确认 Vite 额外打开，修复后探针不再触发且启动器只打开一次；复用已有前端同样只打开一次。父进程浏览器环境保持原值，不修改前端代理或 `open:true` 配置，不访问云端、不上传数据。

**Bug #25 验证（2026-10-23）**：清理工作区前确认残留 Node 占用本机 3000 端口。`tests/edge/test_frontend_lifecycle.py`（已随旧回放链退役）使用真实 Vite，覆盖正常返回及 Ctrl+C 两条路径；修复后均确认所创建 Node 退出、3000 端口不再提供服务。不访问云端或上传数据，已运行的用户前端仍直接复用。

**Bug #24 验证（2026-10-23）**：

- 触发条件：后台分析输出的批次 `order_analysis` 含 NumPy 布尔等非 JSON 原生类型；普通数据上传仍成功，但诊断事务提交失败，已分析标记和健康度更新一起回滚。
- 根因：`full_analysis` 的转换不覆盖批次诊断，SQLAlchemy JSON 编码抛出 `Object of type bool is not JSON serializable`。在 `analyze_device` 返回后对完整结果调用现有 `sanitize_for_json`，供后续入库、告警与推送使用；不改算法评分或数据来源。
- `cloud/tests/test_analysis_worker_json.py`（2026-11 分立后新位置）两项修复前均复现同一错误，修复后通过；覆盖真实内存 SQLite 提交、通道新增/覆盖、原始数据已分析、设备健康度、告警输入与严格 JSON 推送。后端 12 项测试、三项 P0 回归通过；变速阶次回归使用恢复目录的 HUSTbear 样本。
- 云端 SSH 非交互认证未通过，改由用户通过阿里云 Workbench 在独立本地任务分支应用同一处修复；保留原文件备份，重启后 `CNN` 服务为 active。未整体升级云端代码。
- 云端实测（2026-10-23，北京时间 19:51 后）：沿用已确认的 CW 回放，每台上传一批恢复在线；WTG-001 批次 6/7、WTG-002 批次 7/8、WTG-003 批次 7/8 六个新旧批次均 `is_analyzed=1`，已保存的通道诊断均可读取，近期日志未再出现序列化错误。未启动持续回放，不代表算法诊断准确率评估。
- 本地修复与另一 AI 的主工作区改动通过独立 worktree 隔离，未推送或合并。

**Bug #16–22 验证（2026-10-21）**：

- 每组均先通过实际函数/端点/真实 Vue 生命周期的测试复现，再修改实现；没有使用线上数据库或向现场设备下发采集。
- 后端 `cloud/tests/test_read_paths.py`（新位置）：总览 11 台设备由 16 次 SELECT 降为 3 次，历史 16 个批次由 17 次降为 2 次；批次列表不加载完整算法 JSON，两列表结果一致；缓存插入/覆盖、严格 JSON、旧库重复补索引、真实应用五条 HTTP 读路径均通过。
- 后端 `cloud/tests/test_event_loop.py`（新位置）：用受控慢去噪在 STFT/倒谱/阶次实际端点上验证其他协程能被调度，修复前三个端点均失败，修复后通过。不代表真实 VMD 算法耗时降低。
- 前端 `monitor_lifecycle.test.cjs`（7 项）、`dashboard_lifecycle.test.cjs`（6 项）、`websocket.test.cjs`（3 项）全部通过；不覆盖实际浏览器像素渲染。
- 三项 P0 回归通过，前端生产构建通过。线上 P95 延迟、MySQL/Ubuntu 环境、完整数据集分类效果未验证。原有 #11d/#13d 仍未解决。

**仍需核实的语义/架构问题**：`/monitor/latest` 默认按最大 batch_index 取批次，普通批次循环覆盖、特殊批次长期保留，因此“最新”不必等于采集时间最近；设备转频与所展示批次也可能不是同批。改变此规则会影响结果含义，本轮未改。同步数据库访问、后台事务范围、重复诊断缓存写入的竞争还需进一步单独验证。详见 [本轮架构记录](架构整顿记录_20261021.md)。

**Bug #23 复核补充（2026-10-21）**：慢总览查询期间，上线、离线推送和兜底轮询同时触发时，原代码会产生 4 个并发请求；响应顺序不受控制，可能回写旧状态。新增三项受控 Promise 回归，修复前全部失败，修复后通过：验证同一时刻仅一个查询、连续事件只保留一次后续刷新、卸载不再刷新、失败后仍处理后续事件且不会锁死。通过串行调度消除并发响应倒序，不改变设备状态或诊断含义。

**Bug #15 详细（2026-10-19）**：

- **触发条件**：首次进入实时监测，或切换到其他路由后返回；请求未完成时离开页面也会遗留资源。
- **根因**：挂载回调先执行 `loadLatestData()`，其中的 `updateCharts()` 在图表实例创建前调用，随后 `initCharts()` 创建的是空图表；手动切换通道才重新绘图。`onUnmounted` 又在异步挂载的 await 之后注册，Vue 无法关联组件，导致清理不执行；单例 WebSocket 的匿名回调也未被移除。
- **修复**：先初始化图表，再请求并绘制数据；在 setup 阶段同步注册卸载钩子，用具名回调取消 WebSocket 订阅，释放图表、轮询和 resize 监听，并阻止卸载后的异步初始化和绘图。
- **验证**：`wind-turbine-diagnosis/tests/monitor_lifecycle.test.cjs`（2026-11 分立后新位置）使用真实 Vue 生命周期和模拟 API/ECharts，修复前 3 项均失败，修复后 3 项通过，覆盖默认通道首屏、切换通道、离开再进入、订阅清理和请求尚未完成时离开。该测试不验证浏览器实际像素渲染或云端在线采集。

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
| 1 | `cloud/tests/diagnosis/eval_plots/run_all.py`（新位置） | 标签映射改用精确匹配：`fl == "bearing_bpfo"` 替代 `"bpfo" in fl` | ✅ 已修复 |
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
