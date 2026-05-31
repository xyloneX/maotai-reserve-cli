from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.response import fail, ok
from ...core.security import create_access_token
from ...services.admin_user_service import authenticate
from ..deps import AuthUser, CurrentUser, get_current_user

router = APIRouter(prefix="/auth", tags=["认证"])


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = authenticate(db, body.username.strip(), body.password)
    if not user:
        raise HTTPException(status_code=401, detail=fail(40100, "用户名或密码错误"))
    token, expires = create_access_token(user.username, user.role)
    return ok(
        {
            "access_token": token,
            "expires_in": expires,
            "username": user.username,
            "role": user.role,
            "display_name": user.display_name,
        }
    )


@router.post("/refresh")
def refresh(user: CurrentUser = Depends(get_current_user)):
    token, expires = create_access_token(user.username, user.role)
    return ok({"access_token": token, "expires_in": expires})


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return ok(
        {
            "username": user.username,
            "role": user.role,
            "is_superadmin": user.is_superadmin,
        }
    )
