import subprocess
from fastapi import APIRouter, Depends
from app.api.auth import optional_auth

router = APIRouter(prefix="/api/logs", tags=["系统日志"])


@router.get("/")
def get_logs(lines: int = 200, user=Depends(optional_auth)):
    """
    读取 CNN 服务的 systemd 日志（journalctl）
    """
    try:
        result = subprocess.run(
            ["journalctl", "-u", "CNN", "-n", str(lines), "--no-pager"],
            capture_output=True, text=True, timeout=10
        )
        return {
            "logs": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
        }
    except Exception as e:
        return {"logs": "", "error": str(e)}
