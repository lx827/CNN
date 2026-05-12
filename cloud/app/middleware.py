"""
中间件配置
包含 CORS、静态文件挂载等
"""
from fastapi.middleware.cors import CORSMiddleware


def setup_cors(app):
    """
    允许前端跨域访问（开发环境）
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def setup_static_files(app):
    """
    静态文件挂载（预留）
    如需挂载静态文件，可在此配置
    """
    pass
