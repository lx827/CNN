"""
认证接口
提供登录和 Token 验证功能
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.core.config import SECRET_KEY, ADMIN_PASSWORD, EDGE_API_KEY
from app.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["认证"])

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# auto_error=False 允许我们在依赖中自定义 401 响应
security = HTTPBearer(auto_error=False)


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """生成 JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token_string(token: str) -> str:
    """验证 JWT 字符串，返回用户名。"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise JWTError("missing subject")
        return username
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证令牌已过期或无效",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    FastAPI 依赖：验证 Bearer Token。
    在需要保护的接口上使用：Depends(get_current_user)
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证信息",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_token_string(credentials.credentials)


async def optional_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    兼容认证：优先检查边端 API Key，没有则检查 JWT Token。
    用于需要同时被前端（登录用户）和边端（设备）访问的接口。
    """
    edge_key = request.headers.get("X-Edge-Key")
    if edge_key and edge_key == EDGE_API_KEY:
        return "edge"
    return await get_current_user(credentials)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    用户登录接口
    密码正确后返回 JWT Token，前端存储并在后续请求中携带
    """
    if request.password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": "admin"})
    return {"access_token": access_token, "token_type": "bearer"}
