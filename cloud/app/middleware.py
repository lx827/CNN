"""
中间件配置
包含 CORS、静态文件挂载等
"""
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import CORS_ORIGINS


def setup_cors(app):
    """
    允许前端跨域访问（开发环境）
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def setup_static_files(app):
    """
    静态文件挂载（预留）
    如需挂载静态文件，可在此配置
    """
    from pathlib import Path
    from fastapi.responses import HTMLResponse
    from fastapi import HTTPException

    @app.get('/dc24/', include_in_schema=False)
    def dc24_console():
        index = Path(__file__).resolve().parents[2]/'wind-turbine-diagnosis/dist/index.html'
        if not index.exists():
            raise HTTPException(503, '采集页面尚未构建，请使用根目录start_dc24.bat启动')
        content = index.read_text(encoding='utf-8')
        # 本机一键启动时，由同一后端提供前端；不修改既有Vite代理或浏览器保存配置。
        content = content.replace('<head>', '<head><script>window.__BACKEND_BASE_URL__=location.origin;</script>', 1)
        return HTMLResponse(content, headers={'Cache-Control': 'no-store'})
