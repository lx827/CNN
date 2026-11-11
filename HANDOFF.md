# 诊断业务与研究流程交接（2026-11-11）

## 当前批次

上批 PR #89 已合 main `752d4045df439199129838b6c6e397229bde481a`，#72/#73/#74/#76/#80 已关闭。本批 **草稿 PR #90** 收口 #75/#77/#84，最终开发源码为 `fc93117a129e9e580ccb3e7135effb7cf13a5741`。本交接不声明 PR #90 已合并或生产已部署。

开发主控分支 `codex/diagnosis-development`，工作区 `C:/Users/25619/.codex/worktrees/diagnosis-development/CNN`；本批文档分支 `codex/diagnosis-business-docs`，工作区 `D:/code/CNN/.claude/worktrees/diagnosis-business-docs`。旧完成 worktree 保留，不在本轮清理。主控串行合并，文档/代码/测试按逻辑提交；不重复开 review、算法验证或 Issue 评论。

## 已形成的交付

- #75 复用正常算法族建立 VMD AM/FM、四阶 MSB、真实 CVS→MED→MSB、VMD→ICA 与 MSWPEE；AM 输入单位、FM Hz、MSB 输入四次方、先复平均后幅值。CVS 真实相位/空间/独立圈不足无信号输出，不能回退原信号或 TSA。五组合 POST/GET/元数据与真实 Vue 展示已接；research_only/production_eligible=false，顶层 Domain 未知/空分，不进生产缓存、评分、投票、告警。旧 BSS/VMD demod/MSB 重复实现删除。
- #77/#84 使用 Evidence→对象 Evaluation→总体 Diagnosis，evaluation_status 与 diagnosis_conclusion 分开；coverage 保留 complete/partial/none，局部未知不隐藏，总体只覆盖合法证据。共同依赖连通去重、二元 normal/anomaly 融合、精确扣分与单次权重，assessment 单源评分/建议，已有规范 Evidence 可直接重评。
- 精确四元键追加历史缓存；channel=0/denoise=none 唯一设备/批次摘要，手动通道与转频更新不覆盖它的诊断状态。旧 JSON 返回 unknown/null 和需重分析原因，重评409、无精确缓存404。PUT batch diagnosis 只收 JSON `{rot_freq}`。worker/手工共用 process_batch，缓存、原始标记、告警同 commit，失败整体 rollback，commit 后 WS。
- 旧库新增两维状态与 coverage，health_score nullable Float；旧状态不可可信回填，首次加两维列清旧分，后续启动不重复清分。旧物理 status/JSON 保留但不按旧协议读写；旧 NULL 通道/去噪不补身份。SQLite 实测，MySQL SQL 无实际服务验证。
- 前端 getDiagnosisView 唯一接完整对象，非法/未来/空状态和分值中性，null 不变0；DiagnosisCoverage 显示 partial 与局部原因。Dashboard/Monitor/详情/综合/谱/齿轮/Research 已接，不补87分、不造部件偏移分、不以RMS判健康、不读旧status/votes/best/概率。

权威入口：[复合算法](docs/algorithms/composite/INDEX.md)、[证据与状态](docs/backend/assessment.md)、[业务编排](docs/backend/diagnosis.md)、[持久化迁移](docs/backend/persistence.md)、[API](docs/api/backend_api.md)、[前后端交互](docs/api/frontend_backend_interaction.md)、[测试](docs/tests/INDEX.md)、[ADR0004](docs/adr/0004-evidence-and-diagnosis-state.md)。

## 验证证据与限制

实现方记录：P0 None7/CPW5/order17 通过。后端集中首次 Ran79，3 FAIL+2 ERROR 子项（一个测试方法含两route）；修复后只复验四失败方法+分解10共14通过，另 order4、真实PUT1、权重/直接重评1通过。没有声称重新全跑79或P0。新的 domain/workflow 实际 HTTP/SQLite/缓存/worker/事务/告警替代旧规则、评分、校准和投票 helper 协议测试。

前端最终 `node --test tests/*.test.cjs` **52/52**、生产构建通过，2307 modules。此前 SSR 单失败源于纯展示 helper 间接加载浏览器 request，修复后最终全套已过。#75 沿用核心13、早期HTTP3/SSR3/build，以及末次参数3/summary HTTP1/SSR1，不因文档重复算法检查。

数学公式、单位、前提、已知解、负对照和实际消融是算法证据；业务测试保护状态与副作用，不证明真实设备检出效果。历史 dataset 实验脚本尚未按新 Domain 重建，不作为当前可直接执行效果验收。主仓 CW 有36个变速npy，独立 worktree 无数据不代表全缺；其余数据等用户后给。#78 重建真实效果/基线，#79 性能后置；本批未做真实数据效果、性能、生产部署或 MySQL 服务实测。

生产仍 **2C2G**：两线程、ANALYSIS_SEM=1、逐批串行、业务窗口先于慢算法，研究同样受限。DC24 counts 仍只是显示/数组产物，不进设备物理诊断。

## 收口与后续

#75/#77/#84 可按本批结构和实际业务验收随 PR #90 关闭，不能据此宣称研究组合生产就绪或真实效果完成。#78/#79 保持开放，等用户数据和后续性能任务。权重只在 assessment 消费规范 DIAGNOSIS_WEIGHTS；旧 sideband/na4_nb4/wp_entropy/worst_channel/avg_channel 五键无兼容别名。

本批在最终公开源码上只真实导出一次 OpenAPI，**71 路径**。Git Bash 执行一次集中文档检查退出0：**56 个 Markdown、252 个相对链接、6 算法族各9必需章节**，链接/结构/镜像清理全部 PASS；git diff --check 通过。没有重复运行算法/业务/前端测试。旧 #89 文档与原 cloud-numeric 草稿工作区均保留，不恢复镜像文档或已删除兼容入口。
