"""管理端登录用户初始化与校验。"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.security import hash_password, verify_password
from ..models.entities import AdminUser

logger = logging.getLogger(__name__)

ROLE_SUPER = "superadmin"
ROLE_OPERATOR = "operator"


def authenticate(db: Session, username: str, password: str) -> AdminUser | None:
    user = db.query(AdminUser).filter(AdminUser.username == username, AdminUser.enabled == True).first()  # noqa: E712
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def upsert_user(
    db: Session,
    username: str,
    password: str,
    role: str,
    display_name: str = "",
) -> AdminUser:
    user = db.query(AdminUser).filter(AdminUser.username == username).first()
    h = hash_password(password)
    if user is None:
        user = AdminUser(
            username=username,
            password_hash=h,
            role=role,
            display_name=display_name or username,
        )
        db.add(user)
    else:
        user.password_hash = h
        user.role = role
        user.display_name = display_name or user.display_name
        user.enabled = True
    db.commit()
    db.refresh(user)
    return user


def ensure_default_users(db: Session) -> None:
    """从环境变量同步两个固定账号（部署时写入 deploy/.env）。"""
    owner_user = getattr(settings, "owner_username", None) or settings.admin_username
    owner_pass = getattr(settings, "owner_password", None) or settings.admin_password
    client_user = getattr(settings, "client_username", None) or "client"
    client_pass = getattr(settings, "client_password", None) or ""

    if owner_user and owner_pass and owner_pass not in ("admin123", "请改成强密码"):
        upsert_user(db, owner_user, owner_pass, ROLE_SUPER, "最高管理员")
        logger.info("已同步管理账号: %s (superadmin)", owner_user)

    if client_user and client_pass:
        upsert_user(db, client_user, client_pass, ROLE_OPERATOR, "甲方操作员")
        logger.info("已同步管理账号: %s (operator)", client_user)
    elif not db.query(AdminUser).filter(AdminUser.role == ROLE_OPERATOR).count():
        logger.warning("未配置 MT_CLIENT_PASSWORD，甲方操作员账号未创建")
