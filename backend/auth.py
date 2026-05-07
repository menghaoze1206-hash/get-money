"""Auth utilities for FastAPI: FastAPI dependency for token-based auth."""

from fastapi import Header, HTTPException

from backend.database import get_user_by_token


async def get_current_user(authorization: str = Header(default=None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="无效的认证格式")
    token = authorization[len("Bearer "):]
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已过期")
    return user
