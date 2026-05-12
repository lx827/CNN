import subprocess
import platform
from fastapi import APIRouter, Depends
from app.api.auth import optional_auth
from app.core.memory_log import get_memory_logs

router = APIRouter(prefix="/api/logs", tags=["系统日志"])


@router.get("/")
def get_logs(lines: int = 200, user=Depends(optional_auth)):
    """
    读取应用日志

    优先返回内存中的环形缓冲区日志（跨平台，Windows/Linux 均可查看），
    若运行在 Linux 且 journalctl 可用，则将其输出追加在末尾作为补充。
    """
    # 1. 获取内存日志（始终可用）
    memory_logs = get_memory_logs(lines=lines)

    # 2. 如果是 Linux 生产环境，尝试获取 systemd journalctl 日志
    journal_logs = ""
    journal_error = None
    if platform.system() == "Linux":
        try:
            result = subprocess.run(
                ["journalctl", "-u", "CNN", "-n", str(lines), "--no-pager"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                journal_logs = result.stdout
            else:
                journal_error = result.stderr
        except Exception as e:
            journal_error = str(e)

    # 3. 合并输出
    parts = []
    if memory_logs:
        parts.append("===== 应用运行日志 =====\n" + memory_logs)
    if journal_logs:
        parts.append("\n===== systemd journalctl =====\n" + journal_logs)

    logs = "\n".join(parts) if parts else "暂无日志"
    error = journal_error if not memory_logs and not journal_logs else None

    return {
        "code": 200,
        "data": {
            "logs": logs,
            "error": error,
        }
    }
