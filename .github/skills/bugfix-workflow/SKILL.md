---
name: bugfix-workflow
description: "On-demand workflow for systematically diagnosing and fixing backend bugs in the CNN project. Use when: user reports a bug, timeout, or regression; need to trace a request end-to-end; want to avoid 'fix one bug create another'."
user-invocable: true
---

# Bug 修复标准流程

基于本项目实际修复经验提炼。核心原则：**先复现、再定位、后修复、必验证、要文档**。

---

## 第一步：建立独立分支

建立分支之前先与云端同步

```bash
git checkout -b fix/<issue-description> main
```

分支命名格式：`fix/<简短描述>`，如 `fix/envelope-timeout`。

---

## 第二步：复现 Bug

**不要猜测**，先用最小可复现代码确认问题确实存在。

### 2.1 优选 TestClient（后端 Bug）

```python
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
resp = client.get("/api/data/{device}/{batch}/{ch}/envelope", params={...})
print(resp.status_code, resp.text[:500])
```

### 2.2 备选：独立 Python 脚本

```python
# 直接调用 service 层，跳过 HTTP 层
from app.services.diagnosis import DiagnosisEngine
engine = DiagnosisEngine(...)
result = engine.analyze_bearing(signal, fs)
```

### 2.3 确认 Bug 表现

- 记录完整错误日志（不要截断）
- 确认是**超时**、**500 错误**、还是**结果不正确**

### 2.4 无法本地复现时

- 通过 SSH 登录服务器查看日志：`journalctl -u CNN.service --since "5 min ago"`
- 从 `docs/scripts/INDEX.md` 中选择对应诊断脚本在服务器上运行
- 收集错误发生时的上下文（设备 ID、批次号、操作步骤）

---

## 第三步：逐层排查

从外到内，**逐层排查**，每次只验证一层：

| 层级 | 检查点 | 方法 |
|------|--------|------|
| 网络/代理 | 后端是否可达 | `curl` / 浏览器直接访问 |
| HTTP 层 | 路由是否存在 | `app.routes` 检查 |
| 序列化层 | JSON 能否编码返回值 | TestClient 看报错 |
| 计算层 | 核心计算是否卡死 | 独立脚本计时 |
| 导入层 | 循环导入/模块加载 | 单独 `import` 测试 |

> 如果某一层通过，直接进入下一层；如果失败，该层就是根因所在层，停止排查并深入该层。

**常见根因速查：**

| 现象 | 可能根因 |
|------|---------|
| 60s 超时 | `numpy.bool_` / `numpy.int64` 等类型未被 `_sanitize_for_json` 转换 |
| 500 + TypeError | FastAPI `jsonable_encoder` 无法序列化返回值中的 numpy 类型 |
| 一直 loading | 线程池耗尽（分析 worker 占满 `max_workers=2`） |
| ModuleNotFoundError | 循环导入或 import 路径错误 |

---

## 第四步：最小修复

- **只改必要的文件**，不要顺手重构
- 如果改动涉及 API 返回值格式，检查前端是否依赖该格式
- 在该端点所在的模块及其**直接依赖的子模块**中，搜索是否存在相同模式的问题（如其他端点已调用 `_sanitize_for_json` 而当前端点遗漏）

---

## 第五步：验证修复

### 5.1 回归测试（必跑）

```bash
d:\code\CNN\cloud\venv\Scripts\python.exe d:\code\CNN\tests\diagnosis\regression\test_none_params.py
d:\code\CNN\cloud\venv\Scripts\python.exe d:\code\CNN\tests\diagnosis\regression\test_cpw_robustness.py
```

### 5.2 原 Bug 场景确认

用第二步的复现脚本重新运行，确认问题已消失。

### 5.3 交叉验证

- 如果改了 API 返回值，用 `TestClient` 确认 `status_code == 200` 且返回数据完整
- 如果改了服务层函数，确认其他调用方仍正常工作

---

## 第六步：同步文档

1. 更新对应的 `docs/backend/app/` 下 `.md` 文档
2. 如果改了公开函数签名，更新 `docs/api/backend_api.md`
3. 如果改了 API 端点，更新 `docs/api/frontend_backend_interaction.md`

---

## 第七步：提交并创建 PR

```bash
git add <changed-files>
git commit -m "fix: <简短描述根因>"
git push origin fix/<branch-name>
```

PR 标题格式：`fix: <问题简述> — <根因关键词>`

PR 描述必须包含：
- 问题表现
- 根因（为什么）
- 修复（怎么改）
- 验证结果

---

## 第八步：合并后清理

```bash
git checkout main
git pull
git branch -d fix/<branch-name>
git push origin --delete fix/<branch-name>
```
