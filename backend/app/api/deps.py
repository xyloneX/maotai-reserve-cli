from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.response import fail
from ..core.security import decode_token

ROLE_SUPER = "superadmin"


@dataclass
class CurrentUser:
    username: str
    role: str

    @property
    def is_superadmin(self) -> bool:
        return self.role == ROLE_SUPER


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail=fail(40100, "未登录"))
    token = authorization[7:]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail=fail(40100, "Token 失效"))
    return CurrentUser(username=payload["username"], role=payload["role"])


def require_superadmin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail=fail(40300, "需要最高管理员权限"))
    return user


DbSession = Depends(get_db)
AuthUser = Depends(get_current_user)
SuperAdmin = Depends(require_superadmin)
