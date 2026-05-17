"""直接运行大创实验的启动脚本"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"D:\code\CNN")
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "diagnosis"))

from contest.main import main

main()