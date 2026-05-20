"""设备标识：与 i茅台 App 一致的 MT-R 生成。"""

import base64
import uuid


def make_mt_r(device_id: str) -> str:
    """由 MT-Device-ID 生成 MT-R（开源协议逆向）。"""
    buf: list[str] = []
    xor_val = 72
    for ch in device_id:
        xor_val ^= ord(ch)
        buf.append(chr(xor_val))
    raw = "".join(buf)
    return "clips_" + base64.b64encode(raw.encode("latin-1")).decode("ascii")


def make_request_id() -> str:
    return str(uuid.uuid4())


def normalize_device_id(device_id: str) -> str:
    device_id = device_id.strip().upper()
    if not device_id:
        return str(uuid.uuid4()).upper()
    return device_id
