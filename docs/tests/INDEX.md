# Tests — 回归测试与评估套件

## 数据集启动回归（2026-10-23）

- `tests/edge/test_replay.py`：HUSTbear 故障字段、X/Y/Z 信号映射、缺轴拒绝、云端设备缺失或参数不匹配时禁止继续、注册后正常放行，5 项，不联网、不上传。
- `tests/edge/test_frontend_lifecycle.py`：Windows 真实 Vite 进程验证正常返回、Ctrl+C 两条退出路径均释放 Node 进程和端口，1 项含两种场景；需 Node.js、前端依赖及空闲 3000 端口，只访问本机，不上传。环境不满足会明确跳过。
- `tests/backend/test_hustbear_registration.py`：真实内存 SQLite 验证独立注册、幂等、CW 保持原样、冲突整批回滚，2 项，不连接业务数据库。

本机 Windows cmd，仓库根目录运行（无需管理员权限）：

```bat
:: 激活边端已有虚拟环境，不安装依赖。
call edge\venv\Scripts\activate.bat
:: unittest discover 扫描指定边端测试目录，-p 匹配全部测试文件，-v 输出每项结果。
python -m unittest discover -s tests/edge -p test_*.py -v
:: 启动器只检查两份本地数据的全部工况，不启动前端、不联网、不上传。
python edge/replay.py --dataset both --check
:: 切换到后端已有虚拟环境以使用 SQLAlchemy。
call cloud\venv\Scripts\activate.bat
:: 验证设备注册事务，-s 指定目录，-p 指定文件，-v 输出每项结果。
python -m unittest discover -s tests/backend -p test_hustbear_registration.py -v
```

> **文档用途**：统一记录所有测试文件的位置、用途、运行方式和依赖，避免重复编写测试。
> **维护要求**：新增测试文件时，必须在此索引中添加条目。

**前端监测回归**：在本机项目根目录执行 `node --test tests/frontend/monitor_lifecycle.test.cjs`；`--test` 使用 Node.js 自带测试运行器运行指定文件。依赖前端已安装的 `vue` 和 `@vue/compiler-sfc`，无需新增依赖，不访问云端或创建采集任务。使用真实 Vue 生命周期与模拟 API/ECharts，验证首屏默认通道、通道切换、页面返回和异步卸载清理；不覆盖浏览器像素渲染。

**2026-10-21 新增回归**：

| 文件 | 覆盖 | 依赖 |
|---|---|---|
| `tests/backend/test_read_paths.py` | 摘要 SQL/顺序、历史 N+1、严格 JSON、缓存、索引迁移、真实 HTTP 读路径（9 项） | cloud venv 中后端依赖及 httpx；隔离内存 SQLite |
| `tests/backend/test_event_loop.py` | 慢去噪期间的协程调度（1 项，覆盖 STFT/倒谱/阶次三个端点） | 同上；受控去噪替身，不测去噪数学效果 |
| `tests/backend/test_analysis_worker_json.py`（2026-10-23） | 实际后台 worker 的 NumPy 结果入库，通道缓存新增/更新，批次已分析标记、健康度、告警输入及严格 JSON 推送（2 项） | cloud venv；内存 SQLite，算法替身；不访问云端或业务数据库 |
| `tests/frontend/monitor_lifecycle.test.cjs` | 生命周期、推送合并、设备切换竞争、在途刷新、慢轮询（7 项） | 已安装前端依赖 |
| `tests/frontend/dashboard_lifecycle.test.cjs` | 卸载释放、异步卸载、选中对象刷新、critical 显示、推送/轮询串行合并、失败恢复（6 项） | 已安装前端依赖 |
| `tests/frontend/websocket.test.cjs` | 握手幂等、迟到回调、重连去重（3 项） | Node 自带 test/vm；WebSocket 替身 |

本机 Windows PowerShell，在 `E:/A-codehub/CNN/cloud` 执行：

```powershell
# 仅对当前 PowerShell 进程允许虚拟环境激活脚本，不修改系统持久策略，无需管理员。
Set-ExecutionPolicy -Scope Process Bypass
# 激活后端虚拟环境，使后续 python 使用 cloud/venv；不安装依赖、不访问网络。
. ./venv/Scripts/Activate.ps1
# 用 unittest 自动发现 ../tests/backend 中 test_*.py 文件，-v 输出每项结果；使用内存测试库，不修改业务库。
python -m unittest discover -s ../tests/backend -p 'test_*.py' -v
```

本机项目根目录执行前端整组回归：

```powershell
# --test 调用 Node 自带测试运行器，依次列出三个测试文件；不连接云端、不下发采集。
node --test tests/frontend/monitor_lifecycle.test.cjs tests/frontend/dashboard_lifecycle.test.cjs tests/frontend/websocket.test.cjs
```

预期结果为后端 10 项、前端 16 项全部通过；P0 回归仍需按项目要求分别运行。测试运行环境和局限见 [架构整顿记录](../ARCHITECTURE_REFACTOR_20261021.md)。

---

## 目录结构

```
tests/
├── README.md                              # 原始测试说明（旧版）
├── frontend/
│   ├── monitor_lifecycle.test.cjs          # 监测初始化、请求/轮询调度及卸载
│   ├── dashboard_lifecycle.test.cjs        # 总览刷新、状态与生命周期
│   └── websocket.test.cjs                  # 连接状态竞争与重连去重
├── backend/
│   ├── test_read_paths.py                  # 摘要查询、缓存、索引和 HTTP
│   └── test_event_loop.py                  # 去噪期间事件循环响应
├── diagnosis/
│   ├── __init__.py
│   ├── regression/                        # [P0] 回归测试 — 每次修改后必跑
│   │   ├── test_none_params.py            # None 参数安全测试
│   │   ├── test_cpw_robustness.py         # CPW 鲁棒性测试
│   │   └── test_varying_speed_order.py    # 变速阶次跟踪测试
│   ├── algorithms/                        # 新增算法单元测试
│   │   ├── test_engine_regressions.py     # 诊断引擎回归（无参数/TSA/转频）
│   │   ├── test_new_algorithms.py         # 新算法（EMD/MCKD/小波包/SG）测试
│   │   └── test_emd_denoise.py            # EMD/CEEMDAN 降噪测试
│   ├── planetary/                         # 行星齿轮箱专项测试
│   │   ├── test_planetary_e2e.py          # 端到端评估（160文件检出率/误报率）
│   │   └── test_planetary_demod.py        # VMD/SC/SCoh/CVS 解调方法测试
│   ├── method_eval/                       # 方法级分类评估框架
│   │   ├── README.md                      # 评估框架说明
│   │   ├── main.py                        # 主入口
│   │   ├── config.py                      # 评估配置
│   │   ├── label_mapper.py                # 标签映射
│   │   ├── plot_generator.py              # 图表生成
│   │   ├── replot.py                      # 重新绘图工具
│   │   ├── visualizer.py                  # 可视化工具
│   │   ├── _final_gear_check.py           # 齿轮最终检查
│   │   ├── test_bearing_hustbear.py       # HUSTbear 轴承评估（11方法+集成）
│   │   ├── test_bearing_cw.py             # CW 轴承评估
│   │   ├── test_gear_wtgearbox.py         # WTgearbox 齿轮评估
│   │   └── test_binary_all.py             # 全部二分类评估
│   ├── evaluation/                        # 多维度评价框架
│   │   ├── main.py                        # 主入口（综合评估）
│   │   ├── config.py                      # 配置文件
│   │   ├── utils.py                       # 工具函数
│   │   ├── datasets.py                    # 数据集加载
│   │   ├── _check_imports.py              # 导入验证
│   │   ├── denoise_eval.py                # 去噪方法评估
│   │   ├── bearing_eval.py                # 轴承方法评估
│   │   ├── gear_eval.py                   # 齿轮方法评估
│   │   ├── comprehensive_eval.py          # 综合诊断评估
│   │   ├── robustness_eval.py             # 噪声鲁棒性评估
│   │   ├── classification_metrics_eval.py # 分类指标评估
│   │   ├── ds_fusion_eval.py              # D-S 融合评估
│   │   ├── health_trend_eval.py           # 健康趋势评估
│   │   ├── channel_consensus_eval.py      # 通道一致性评估
│   │   ├── report_generator.py            # 报告生成
│   │   └── generate_contest_plots.py      # 竞赛图表生成
│   ├── effectiveness/                     # 诊断有效性测试
│   │   ├── test_effectiveness.py          # 参数驱动跳过逻辑测试
│   │   ├── test_core_algorithms.py        # 核心算法有效性
│   │   └── test_dataset_effectiveness.py  # 数据集有效性
│   ├── benchmark/                         # 离线基准评估
│   │   ├── test_benchmark.py              # 三数据集批量评估
│   │   └── test_rot_freq_estimation.py    # 转频估计准确性
│   ├── contest/                           # 竞赛/答辩实验脚本
│   │   ├── main.py                        # 主入口
│   │   ├── config.py                      # 配置
│   │   ├── style.py                       # 图表风格
│   │   ├── experiment_a_bearing.py        # 实验A：轴承诊断
│   │   ├── experiment_b_gear.py           # 实验B：齿轮诊断
│   │   ├── experiment_c_denoise.py        # 实验C：去噪方法
│   │   ├── experiment_d_robustness.py     # 实验D：鲁棒性
│   │   ├── experiment_e_fusion.py         # 实验E：融合方法
│   │   └── experiment_f_health.py         # 实验F：健康度评分
│   ├── foundation/                         # [P0+] 分层正确性测试 → 详见 TEST_ARCHITECTURE.md
│   │   ├── synthetic_signals.py             # 合成信号生成器（含 ground truth）
│   │   ├── layer1/                          # 信号基元 (14模块, 158测试)
│   │   ├── layer2/                          # 特征提取 & 信号处理 (10模块)
│   │   ├── layer3/                          # 模块聚合 & 集成调度 (4模块)
│   │   ├── layer4/                          # 中央调度器深层 (2模块)
│   │   ├── layer5/                          # 应用入口辅助函数 (3模块)
│   │   └── output/                          # JSON 结果 + PNG 图表
│   │   └── output/                          # JSON 结果 + PNG 图表
│   ├── debug/                             # 调试脚本（临时）
│   │   └── debug_cw_fp.py                 # CW 健康数据误判诊断
│   └── output/                            # 测试输出（图表等）
└── output/                                # 顶层测试输出
```

---

## 0. 分层正确性测试（详见 `TEST_ARCHITECTURE.md`）

> **用途**：按依赖层从下往上（Layer 1→5）验证诊断算法全链路，使用合成信号 + 4 个真实数据集。
> **完整文档**：`tests/diagnosis/TEST_ARCHITECTURE.md` — 含覆盖矩阵、测试列表、运行方式。
> **运行**：参见 `TEST_ARCHITECTURE.md` 底部运行方式。

---

## 1. 回归测试（P0 — 每次修改后必须运行）

> **⚠️ 重要**：对 `cloud/app/services/diagnosis/` 下任何文件的修改完成后，必须运行以下回归测试。

### 1.1 `test_none_params.py` — None 参数安全

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/regression/test_none_params.py
```

| 项目 | 说明 |
|------|------|
| **目的** | 验证设备参数为 None 时诊断引擎不崩溃 |
| **测试范围** | `_compute_bearing_fault_freqs`, `_extract_spectrum_features`, `DiagnosisEngine` 各方法 |
| **数据集** | 不需要（使用合成信号） |
| **通过标准** | 所有 assert 通过，无异常抛出 |

### 1.2 `test_cpw_robustness.py` — CPW 鲁棒性

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/regression/test_cpw_robustness.py
```

| 项目 | 说明 |
|------|------|
| **目的** | 验证 CPW 在非法参数（rot_freq=None/-5/0, 空 comb_frequencies）下不崩溃 |
| **数据集** | 不需要（使用合成信号） |
| **通过标准** | 所有边界条件测试通过 |

### 1.3 `test_varying_speed_order.py` — 变速阶次跟踪

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/regression/test_varying_speed_order.py
```

| 项目 | 说明 |
|------|------|
| **目的** | 验证变速工况下阶次跟踪算法正确性 |
| **数据集** | 需要 HUSTbear 数据集 `data/HUSTbear/down8192`（相对仓库根目录） |
| **通过标准** | 转频估计在合理范围，多帧 vs 单帧阶次谱差异可接受 |

### 1.4 一键回归测试

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/regression/test_none_params.py && python ../tests/diagnosis/regression/test_cpw_robustness.py && python ../tests/diagnosis/regression/test_varying_speed_order.py && echo "ALL REGRESSION TESTS PASSED"
```

---

## 2. 新增算法测试

> 位于 `tests/diagnosis/algorithms/`，用于验证新加算法模块的正确性。

| 文件 | 用途 | 需要数据集 | 运行方式 |
|------|------|-----------|---------|
| `test_engine_regressions.py` | 诊断引擎核心回归（无参数/TSA/转频/健康区分） | HUSTbear/CW（可选） | `python ../tests/diagnosis/algorithms/test_engine_regressions.py` |
| `test_new_algorithms.py` | EMD/MCKD/小波包/SG 等新算法功能验证 | 无 | 同上 |
| `test_emd_denoise.py` | EMD/CEEMDAN 降噪模块测试 | 无 | 同上 |

---

## 3. 行星齿轮箱专项测试

| 文件 | 用途 | 数据集 | 运行时间 |
|------|------|--------|---------|
| `test_planetary_e2e.py` | 端到端评估：160 文件批量诊断，统计检出率/误报率/区分力 | WTgearbox (160文件) | ~10分钟 |
| `test_planetary_demod.py` | VMD/SC/SCoh/CVS/TSA 等解调方法单独测试 | WTgearbox | ~3分钟 |

```bash
# 端到端评估
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/planetary/test_planetary_e2e.py
```

---

## 4. 方法级分类评估框架 (`method_eval/`)

> 对每种诊断方法独立评估二分类/多分类性能，生成 ROC 曲线、混淆矩阵等。

| 文件 | 用途 | 数据集 |
|------|------|--------|
| `main.py` | 主入口，运行全部评估 | — |
| `test_bearing_hustbear.py` | HUSTbear 轴承评估：11种方法+集成，二分类+五分类 | HUSTbear |
| `test_bearing_cw.py` | CW 轴承评估：变速工况下的轴承方法性能 | CW |
| `test_gear_wtgearbox.py` | WTgearbox 齿轮评估：齿轮方法性能 | WTgearbox |
| `test_binary_all.py` | 全部二分类评估（健康 vs 故障） | 三个数据集 |

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/method_eval/test_bearing_hustbear.py
```

---

## 5. 多维度评价框架 (`evaluation/`)

> 系统性地评估去噪、轴承、齿轮、综合诊断、鲁棒性等各维度。

| 文件 | 用途 |
|------|------|
| `main.py` | 主入口，运行全部评估维度 |
| `denoise_eval.py` | 去噪方法对比评估 |
| `bearing_eval.py` | 轴承诊断方法评估 |
| `gear_eval.py` | 齿轮诊断方法评估 |
| `comprehensive_eval.py` | 综合诊断（轴承+齿轮）评估 |
| `robustness_eval.py` | 噪声鲁棒性评估 |
| `classification_metrics_eval.py` | 分类指标（准确率/召回率/F1） |
| `ds_fusion_eval.py` | D-S 证据融合效果评估 |
| `health_trend_eval.py` | 健康度趋势评估 |
| `channel_consensus_eval.py` | 多通道一致性评估 |
| `report_generator.py` | 评估报告生成 |

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/evaluation/main.py
```

---

## 6. 其他测试

### 7.1 有效性测试 (`effectiveness/`)

| 文件 | 用途 |
|------|------|
| `test_effectiveness.py` | 参数驱动跳过逻辑测试：仅轴承/仅齿轮/都有/都无 四种场景 |
| `test_dataset_effectiveness.py` | 数据集本身的诊断可行性评估 |

### 7.2 竞赛实验 (`contest/`)

> 大创/答辩用实验脚本，一键生成图表。

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/contest/main.py
```

### 7.3 调试 (`debug/`)

| 文件 | 用途 |
|------|------|
| `debug_cw_fp.py` | CW 健康数据误判原因诊断，逐项打印扣分项 |

---

## 7. 测试运行环境要求

| 数据集 | 路径 | 用途 |
|--------|------|------|
| HUSTbear | `data/HUSTbear/down8192` | 轴承诊断评估 |
| CW | `data/CW/down8192_CW` | 变速轴承诊断评估 |
| WTgearbox | `data/WTgearbox/down8192` | 齿轮诊断评估 |

> 路径均相对仓库根目录，由 `tests/diagnosis/data_paths.py` 统一解析；可用 `CNN_DATA_ROOT` 指向仓库外数据目录。

> 回归测试（P0）不需要数据集，使用合成信号即可运行。

---

## 8. 何时运行哪些测试

| 修改范围 | 最小测试集 |
|---------|-----------|
| `features.py`, `engine.py`, `ensemble.py` | P0回归 + algorithms/ |
| `bearing.py`, `bearing_cyclostationary.py` | P0回归 + `test_bearing_hustbear.py` |
| `gear/`, `planetary_demod.py` | P0回归 + `test_planetary_e2e.py` |
| `health_score.py` | P0回归 + `test_effectiveness.py` |
| `order_tracking.py` | `test_varying_speed_order.py` |
| `preprocessing.py`, `vmd_denoise.py` | P0回归 + `test_cpw_robustness.py` |
| API 路由 (`data_view/`, `ingest.py` 等) | P0回归 + 手动 API 调用验证 |

---

*文档生成时间：2026-05-19*
*维护者：AI Agent（新增测试文件时请务必同步更新）*
