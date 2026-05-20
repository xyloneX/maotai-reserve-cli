"""i茅台 App API 客户端。"""

from __future__ import annotations

import datetime
import json
import logging
import random
import time
import uuid
from typing import Any

import requests

from .config_loader import AccountCredentials
from .crypto import ActParamEncryptor, request_signature
from .device_util import make_mt_r, make_request_id, normalize_device_id
from .exceptions import AuthError, RateLimitError, SessionNotReadyError

logger = logging.getLogger(__name__)

APP_HOST = "app.moutai519.com.cn"
STATIC_HOST = "static.moutai519.com.cn"
H5_HOST = "h5.moutai519.com.cn"

_encryptor = ActParamEncryptor()


def fetch_app_version() -> str:
    try:
        r = requests.get(
            "https://itunes.apple.com/cn/lookup?id=1600482450",
            timeout=15,
        )
        return r.json()["results"][0]["version"]
    except Exception as e:
        logger.warning("无法从 App Store 获取版本号，使用默认 1.8.0: %s", e)
        return "1.8.0"


class IMaotaiClient:
    def __init__(self, account: AccountCredentials, app_version: str | None = None):
        self.account = account
        self.app_version = app_version or fetch_app_version()
        self.session_id: str | None = None
        self._session = requests.Session()
        self._init_headers()

    def _init_headers(self) -> None:
        device = normalize_device_id(self.account.device_id)
        self.account.device_id = device
        try:
            mt_r = make_mt_r(device)
        except Exception:
            mt_r = "clips_OlU6TmFRag5rCXwbNAQ/Tz1SKlN8THcecBp/HGhHdw=="

        self._headers = {
            "Host": APP_HOST,
            "Accept": "*/*",
            "MT-User-Tag": "0",
            "MT-Network-Type": "WIFI",
            "MT-Token": self.account.token or "",
            "MT-Team-ID": "",
            "MT-Info": "028e7f96f6369cafe1d105579c5b9377",
            "MT-Device-ID": device,
            "MT-Bundle-ID": "com.moutai.mall",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "MT-APP-Version": self.app_version,
            "User-Agent": f"iOS;17.0;Apple;iPhone15,2",
            "MT-R": mt_r,
            "Content-Type": "application/json; charset=UTF-8",
            "Connection": "keep-alive",
            "userId": str(self.account.user_id or "0"),
            "MT-Lat": self.account.lat,
            "MT-Lng": self.account.lng,
            "MT-Request-ID": make_request_id(),
        }

    def _auth_headers(self) -> dict[str, str]:
        """登录 / 发验证码：Token 必须为空，每次新 Request-ID。"""
        h = dict(self._headers)
        h["MT-Token"] = ""
        h["userId"] = "0"
        h["MT-Request-ID"] = make_request_id()
        return h

    @staticmethod
    def _parse_api_message(resp: requests.Response) -> str:
        try:
            body = resp.json()
            return str(body.get("message") or body.get("msg") or body)[:200]
        except Exception:
            return resp.text[:200]

    def _signed_post(
        self,
        path: str,
        params: dict[str, str],
        *,
        for_auth: bool = False,
    ) -> requests.Response:
        md5, ts = request_signature(params)
        body = {**params, "md5": md5, "timestamp": ts, "MT-APP-Version": self.app_version}
        url = f"https://{APP_HOST}{path}"
        headers = self._auth_headers() if for_auth else self._headers
        headers["MT-Request-ID"] = make_request_id()
        return self._session.post(url, json=body, headers=headers, timeout=30)

    def send_vcode(self, mobile: str) -> tuple[bool, str]:
        resp = self._signed_post(
            "/xhr/front/user/register/vcode",
            {"mobile": mobile},
            for_auth=True,
        )
        if resp.status_code == 429:
            return False, "发送过于频繁(429)，请等待 2 分钟后再试"
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code} {self._parse_api_message(resp)}"
        try:
            j = resp.json()
            if j.get("code") not in (2000, 0, "2000", None) and j.get("code") is not None:
                return False, f"发送失败 code={j.get('code')} {j.get('message', '')}"
        except json.JSONDecodeError:
            pass
        return True, "验证码已发送，请查看短信（约 1 分钟内有效）"

    def login(self, mobile: str, vcode: str) -> tuple[str, str]:
        code = (vcode or "").strip()
        if len(code) < 4:
            raise AuthError("验证码不能为空，请输入短信里的 4–6 位数字")

        last_err = ""
        for attempt in range(3):
            resp = self._signed_post(
                "/xhr/front/user/register/login",
                {"mobile": mobile, "vCode": code, "ydToken": "", "ydLogId": ""},
                for_auth=True,
            )

            if resp.status_code == 429:
                wait = 45 * (attempt + 1)
                last_err = f"登录请求过于频繁(429)，请等待 {wait} 秒后重试"
                logger.warning(last_err)
                if attempt < 2:
                    time.sleep(wait)
                    continue
                raise RateLimitError(
                    last_err + "\n建议：稍后再试；勿连续多次发送验证码；可换手机热点。"
                )

            if resp.status_code != 200:
                raise AuthError(
                    f"HTTP {resp.status_code} {self._parse_api_message(resp)}"
                )

            try:
                j = resp.json()
            except json.JSONDecodeError:
                raise AuthError(f"响应无法解析: {resp.text[:120]}")

            api_code = j.get("code")
            if api_code not in (2000, 0, "2000") or not j.get("data"):
                msg = j.get("message") or j.get("msg") or str(j)
                raise AuthError(f"登录失败: {msg}")

            data = j["data"]
            token, user_id = data["token"], str(data["userId"])
            self.account.token = token
            self.account.user_id = user_id
            self._headers["MT-Token"] = token
            self._headers["userId"] = user_id
            return token, user_id

        raise RateLimitError(last_err or "登录失败")

    def refresh_session_id(self) -> str:
        day_ms = int(
            time.mktime(datetime.date.today().timetuple()) * 1000
        )
        url = f"https://{STATIC_HOST}/mt-backend/xhr/front/mall/index/session/get/{day_ms}"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        self.session_id = str(resp.json()["data"]["sessionId"])
        return self.session_id

    def is_session_ready(self) -> bool:
        sid = self.session_id or self.refresh_session_id()
        return bool(sid) and sid != "0"

    def ensure_session_id(
        self,
        max_wait_seconds: int = 120,
        poll_interval: int = 5,
    ) -> str:
        """等待有效 sessionId；仍为 0 则抛出 SessionNotReadyError。"""
        deadline = time.time() + max_wait_seconds
        while time.time() < deadline:
            sid = self.refresh_session_id()
            if sid and sid != "0":
                logger.info("场次 sessionId=%s", sid)
                return sid
            logger.info(
                "sessionId=0（非申购时段或未开放），%ds 后重试…",
                poll_interval,
            )
            time.sleep(poll_interval)
        raise SessionNotReadyError(
            f"在 {max_wait_seconds}s 内未获取到有效 sessionId。"
            "请确认当前为申购时段（通常 9:00–10:00）或稍后重试。"
        )

    def validate_token(self) -> tuple[bool, str]:
        """检查 MT-Token 是否仍有效。"""
        paths = (
            "/xhr/front/user/info",
            "/xhr/front/user/getUserInfo",
        )
        for path in paths:
            url = f"https://{APP_HOST}{path}"
            try:
                resp = self._session.get(url, headers=self._headers, timeout=15)
            except requests.RequestException as e:
                return False, f"网络异常: {e}"

            if resp.status_code == 401:
                return False, "Token 已失效 (HTTP 401)"

            if resp.status_code != 200:
                continue

            try:
                body = resp.json()
            except json.JSONDecodeError:
                return True, "Token 有效"

            code = body.get("code")
            if code in (2000, 0, "2000"):
                return True, "Token 有效"
            if code in (401, 4001, 4030):
                return False, f"Token 无效 code={code}"
            if body.get("data"):
                return True, "Token 有效"

        # 接口路径变更时：有 token 且非空则放行，由预约接口最终校验
        if self.account.token and len(self.account.token) > 10:
            return True, "Token 未校验（接口无响应），将尝试预约"
        return False, "Token 为空"

    def fetch_shop_map(self) -> tuple[dict, dict]:
        """返回 (省市区->门店ID列表, shopId->门店详情)。"""
        url = f"https://{STATIC_HOST}/mt-backend/xhr/front/mall/resource/get"
        h = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
            "Referer": f"https://{H5_HOST}/gux/game/main?appConfig=2_1_2",
            "MT-APP-Version": self.app_version,
            "mt-lat": self.account.lat,
            "mt-lng": self.account.lng,
        }
        res = requests.get(url, headers=h, timeout=30).json()
        shops_url = res["data"]["mtshops_pc"]["url"]
        shops = requests.get(shops_url, timeout=60).json()

        province_city_map: dict[str, dict[str, list[str]]] = {}
        for shop_id, info in shops.items():
            prov = info.get("provinceName", "")
            city = info.get("cityName", "")
            province_city_map.setdefault(prov, {}).setdefault(city, []).append(shop_id)
        return province_city_map, shops

    def fetch_session_shops(self, item_code: str) -> list[dict]:
        if not self.session_id:
            self.refresh_session_id()
        day_ms = int(time.mktime(datetime.date.today().timetuple()) * 1000)
        url = (
            f"https://{STATIC_HOST}/mt-backend/xhr/front/mall/shop/list/slim/v3/"
            f"{self.session_id}/{self.account.province}/{item_code}/{day_ms}"
        )
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json().get("data", {}).get("shops", [])

    def build_reserve_payload(self, shop_id: str, item_id: str) -> dict[str, Any]:
        inner = {
            "itemInfoList": [{"count": 1, "itemId": item_id}],
            "sessionId": int(self.session_id),
            "userId": self.account.user_id,
            "shopId": shop_id,
        }
        return {
            **inner,
            "actParam": _encryptor.encrypt(inner),
        }

    def preview_reserve(self, shop_id: str, item_id: str) -> dict[str, Any]:
        """dry-run：仅生成请求体，不提交。"""
        payload = self.build_reserve_payload(shop_id, item_id)
        public = {k: v for k, v in payload.items() if k != "actParam"}
        return {
            "shop_id": shop_id,
            "item_id": item_id,
            "session_id": self.session_id,
            "payload_keys": list(payload.keys()),
            "act_param_len": len(payload.get("actParam", "")),
            "act_param_preview": str(payload.get("actParam", ""))[:48] + "…",
            "body_preview": public,
        }

    def reserve(self, shop_id: str, item_id: str) -> tuple[bool, str]:
        payload = self.build_reserve_payload(shop_id, item_id)
        payload.pop("userId", None)
        url = f"https://{APP_HOST}/xhr/front/mall/reservation/add"
        resp = self._session.post(url, json=payload, headers=self._headers, timeout=30)
        body = resp.text[:300]
        ok = False
        if resp.status_code == 200:
            try:
                j = resp.json()
                ok = j.get("code") == 2000 or j.get("success") is True
            except json.JSONDecodeError:
                ok = "成功" in body or "success" in body.lower()
        return ok, f"HTTP {resp.status_code} {body}"

    def claim_energy(self) -> str:
        cookies = {
            "MT-Device-ID-Wap": self.account.device_id,
            "MT-Token-Wap": self.account.token,
        }
        url = f"https://{H5_HOST}/game/isolationPage/getUserEnergyAward"
        resp = self._session.post(url, cookies=cookies, headers=self._headers, json={}, timeout=20)
        return f"{resp.status_code} {resp.text[:120]}"


def new_device_id() -> str:
    return str(uuid.uuid4()).upper()
