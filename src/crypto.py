"""i茅台请求签名与 actParam AES 加密。"""

import base64
import hashlib
import json
import time
from typing import Any

from Crypto.Cipher import AES

# 开源社区逆向所得，App 大版本升级后可能失效，需自行更新
AES_KEY = "qbhajinldepmucsonaaaccgypwuvcjaa"
AES_IV = "2018534749963515"
SALT = "2af72f100c356273d46284f6fd1dfc08"


class ActParamEncryptor:
    def __init__(self, key: str = AES_KEY, iv: str = AES_IV):
        self._key = key.encode("utf-8")
        self._iv = iv.encode("utf-8")

    def _pkcs7_pad(self, text: str) -> str:
        bs = 16
        padding = bs - len(text.encode("utf-8")) % bs
        return text + chr(padding) * padding

    def encrypt(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, separators=(",", ":"))
        cipher = AES.new(self._key, AES.MODE_CBC, self._iv)
        encrypted = cipher.encrypt(self._pkcs7_pad(raw).encode("utf-8"))
        return base64.b64encode(encrypted).decode("utf-8")


def request_signature(params: dict[str, str], timestamp_ms: str | None = None) -> tuple[str, str]:
    """返回 (md5, timestamp_ms)。"""
    ts = timestamp_ms or str(int(time.time() * 1000))
    ordered = "".join(params[k] for k in sorted(params.keys()))
    digest = hashlib.md5((SALT + ordered + ts).encode("utf-8")).hexdigest()
    return digest, ts


def local_credentials_key(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def encrypt_local(plain: str, secret: str) -> str:
    from Crypto.Util.Padding import pad

    key = local_credentials_key(secret)
    cipher = AES.new(key, AES.MODE_ECB)
    return base64.b64encode(cipher.encrypt(pad(plain.encode(), AES.block_size))).decode()


def decrypt_local(cipher_b64: str, secret: str) -> str:
    from Crypto.Util.Padding import unpad

    key = local_credentials_key(secret)
    cipher = AES.new(key, AES.MODE_ECB)
    return unpad(cipher.decrypt(base64.b64decode(cipher_b64)), AES.block_size).decode()
