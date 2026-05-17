# `auth.py` — 认证

**对应源码**：`cloud/app/api/auth.py` | `prefix=/api/auth` | `tags=[认证]`

## 常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `ALGORITHM` | `"HS256"` | JWT 算法 |
| `ACCESS_TOKEN_EXPIRE_DAYS` | `7` | Token 有效期 |
| `security` | `HTTPBearer(auto_error=False)` | Bearer Token 安全方案 |

## 函数

### `create_access_token`

```python
def create_access_token(data: dict, expires_delta: timedelta = None) -> str
```

- **返回值**：`str` — JWT Token
- **说明**：生成 JWT access token

### `verify_token_string`

```python
def verify_token_string(token: str) -> str
```

- **返回值**：`str` — 用户名
- **说明**：验证 JWT 字符串，返回用户名

### `get_current_user`

```python
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str
```

- **返回值**：`str` — 用户名
- **说明**：FastAPI 依赖，验证 Bearer Token

### `optional_auth`

```python
async def optional_auth(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)) -> str
```

- **返回值**：`str` — 用户名或 "edge"
- **说明**：兼容认证：优先 X-Edge-Key，再 JWT

## 路由端点

### `POST /api/auth/login`

```python
@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest) -> TokenResponse
```

- **请求体**：`LoginRequest(password)`
- **响应**：`TokenResponse(access_token, token_type)`
- **说明**：用户登录，密码匹配 ADMIN_PASSWORD 返回 JWT
