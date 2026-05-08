"""
数据库连接管理
使用 SQLAlchemy 作为 ORM，自动处理连接池

默认使用 SQLite（零配置）：
  不需要安装 Docker/MySQL，数据自动保存在 cloud/turbine.db 文件中。

如需切换 MySQL：
  1. 安装 MySQL（Windows 版或 Linux 版）
  2. 创建数据库：CREATE DATABASE turbine_db CHARACTER SET utf8mb4;
  3. 修改 .env：USE_SQLITE=false + 填写 DB_HOST/DB_USER/DB_PASSWORD
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import DATABASE_URL, USE_SQLITE

# 创建数据库引擎
if USE_SQLITE:
    # SQLite 需要 check_same_thread=False 才能在线程/协程中正常使用
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)
else:
    # MySQL 配置：pool_pre_ping 自动检测断线
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 模型基类，所有数据表模型都继承它
Base = declarative_base()


def get_db():
    """
    依赖注入函数，FastAPI 路由中通过依赖获取数据库会话
    用 yield 确保会话用完自动关闭
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库：创建所有表（如果表不存在）"""
    Base.metadata.create_all(bind=engine)
