# UV 单 workspace 统一 Python 3.13

> 布局决定已由 [ADR 0006](0006-native-diagnosis-compute-package.md) 的根目录单项目取代。当前计算库由根配置构建，cloud/dc24 依赖使用分组管理；单一 uv 托管 Python、根锁文件和根 `.venv` 的约束继续有效。以下保留原决策语境。

仓库原有 cloud/edge 两个独立 venv,本地 Python 3.13 与服务器 3.10 双版本漂移,依赖靠手写 requirements.txt。决定:根目录 `pyproject.toml` 建立 uv workspace,成员为 `cloud` 与 `edge`,全部统一为 UV 托管下载的单一 Python 3.13,锁文件 `uv.lock` 为唯一依赖事实源;服务器(ECS)通过 `uv sync --frozen` 安装,不再依赖系统 Python 版本。

## Considered Options

- 各端独立 pyproject 不用 workspace:被否,两份锁文件仍会漂移。
- 统一到服务器现有 3.10:被否,UV 托管下载后服务器不再受系统 Python 约束,选新版本更有利。
