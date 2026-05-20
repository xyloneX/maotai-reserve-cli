"""加载 config.yaml 与本地账号凭证（敏感字段加密存储）。"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .crypto import decrypt_local, encrypt_local
from .exceptions import ConfigError

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
CREDENTIALS_PATH = ROOT / "data" / "credentials.json"
ENC_PREFIX = "enc:"

PLACEHOLDER_SECRET = ("请改", "changeme", "your_secret")


@dataclass
class ItemConfig:
    code: str
    name: str


@dataclass
class ScheduleConfig:
    target_time: str = "09:00:00"
    advance_seconds: int = 2
    run_immediately_if_missed: bool = False


@dataclass
class AppConfig:
    secret_key: str
    amap_key: str
    items: list[ItemConfig]
    shop_strategy: str
    claim_energy: bool
    schedule: ScheduleConfig
    retry_count: int
    retry_interval: float
    pushplus_token: str
    session_wait_seconds: int
    session_poll_interval: int


@dataclass
class AccountCredentials:
    mobile: str
    token: str
    user_id: str
    province: str
    city: str
    lat: str
    lng: str
    device_id: str
    end_date: str = "99991231"
    receiver_name: str = ""
    receiver_mobile: str = ""
    district: str = ""
    detail_address: str = ""
    pay_password: str = ""  # 可选：支付密码备注（本地加密，i茅台登录仍用短信）


def validate_secret_key(secret_key: str) -> None:
    if not secret_key or not secret_key.strip():
        raise ConfigError("请在 config.yaml 中设置 secret_key")
    for p in PLACEHOLDER_SECRET:
        if p in secret_key:
            raise ConfigError("secret_key 仍为占位符，请改成你自己的随机字符串")


def _encrypt_field(plain: str, secret_key: str) -> str:
    return ENC_PREFIX + encrypt_local(plain, secret_key)


def _decrypt_field(value: str, secret_key: str) -> str:
    if value.startswith(ENC_PREFIX):
        return decrypt_local(value[len(ENC_PREFIX) :], secret_key)
    return value


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"未找到 {CONFIG_PATH}，请复制 config.example.yaml 为 config.yaml 并填写"
        )
    with open(CONFIG_PATH, encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    items = [
        ItemConfig(code=str(i["code"]), name=str(i.get("name", i["code"])))
        for i in raw.get("items", [])
    ]
    sched = raw.get("schedule", {}) or {}
    retry = raw.get("retry", {}) or {}
    session_cfg = raw.get("session", {}) or {}

    return AppConfig(
        secret_key=str(raw.get("secret_key", "")),
        amap_key=str(raw.get("amap_key", "")),
        items=items,
        shop_strategy=str(raw.get("shop_strategy", "max_inventory")),
        claim_energy=bool(raw.get("claim_energy", True)),
        schedule=ScheduleConfig(
            target_time=str(sched.get("target_time", "09:00:00")),
            advance_seconds=int(sched.get("advance_seconds", 2)),
            run_immediately_if_missed=bool(sched.get("run_immediately_if_missed", False)),
        ),
        retry_count=int(retry.get("count", 3)),
        retry_interval=float(retry.get("interval_seconds", 0.5)),
        pushplus_token=str(raw.get("pushplus_token", "")),
        session_wait_seconds=int(session_cfg.get("wait_seconds", 120)),
        session_poll_interval=int(session_cfg.get("poll_interval_seconds", 5)),
    )


def load_credentials(secret_key: str) -> list[AccountCredentials]:
    validate_secret_key(secret_key)
    if not CREDENTIALS_PATH.exists():
        return []

    with open(CREDENTIALS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    accounts: list[AccountCredentials] = []
    migrated = False

    for row in data.get("accounts", []):
        token_raw = row["token"]
        uid_raw = str(row["user_id"])
        if not token_raw.startswith(ENC_PREFIX):
            migrated = True
        def _opt_decrypt(key: str, default: str = "") -> str:
            raw = row.get(key, default) or default
            if not raw:
                return default
            if isinstance(raw, str) and raw.startswith(ENC_PREFIX):
                return _decrypt_field(raw, secret_key)
            return str(raw)

        accounts.append(
            AccountCredentials(
                mobile=row["mobile"],
                token=_decrypt_field(token_raw, secret_key),
                user_id=_decrypt_field(uid_raw, secret_key),
                province=row["province"],
                city=row["city"],
                lat=str(row["lat"]),
                lng=str(row["lng"]),
                device_id=row["device_id"],
                end_date=str(row.get("end_date", "99991231")),
                receiver_name=_opt_decrypt("receiver_name"),
                receiver_mobile=row.get("receiver_mobile") or row["mobile"],
                district=row.get("district", ""),
                detail_address=_opt_decrypt("detail_address"),
                pay_password=_opt_decrypt("pay_password"),
            )
        )

    if migrated and accounts:
        save_credentials(accounts, secret_key)

    return accounts


def save_credentials(accounts: list[AccountCredentials], secret_key: str) -> None:
    validate_secret_key(secret_key)
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    def _enc_optional(value: str) -> str:
        if not value:
            return ""
        return _encrypt_field(value, secret_key)

    payload = {
        "version": 3,
        "accounts": [
            {
                "mobile": a.mobile,
                "token": _encrypt_field(a.token, secret_key),
                "user_id": _encrypt_field(a.user_id, secret_key),
                "province": a.province,
                "city": a.city,
                "lat": a.lat,
                "lng": a.lng,
                "device_id": a.device_id,
                "end_date": a.end_date,
                "receiver_name": _enc_optional(a.receiver_name),
                "receiver_mobile": a.receiver_mobile or a.mobile,
                "district": a.district,
                "detail_address": _enc_optional(a.detail_address),
                "pay_password": _enc_optional(a.pay_password),
            }
            for a in accounts
        ],
    }
    with open(CREDENTIALS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.chmod(CREDENTIALS_PATH, 0o600)


def mask_mobile(mobile: str) -> str:
    if len(mobile) >= 11:
        return f"{mobile[:3]}****{mobile[-4:]}"
    return re.sub(r"\d", "*", mobile)
