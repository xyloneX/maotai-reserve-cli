#!/usr/bin/env python3
"""在服务器上写入双管理账号环境变量并重启 API。"""

from __future__ import annotations

import os
import secrets
import sys

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "139.155.134.97")
USER = os.environ.get("DEPLOY_USER", "ubuntu")
PASSWORD = os.environ.get("DEPLOY_PASS", "")
ENV_PATH = "/opt/maotai/deploy/.env"

OWNER_USER = os.environ.get("MT_OWNER_USERNAME", "owner")
OWNER_PASS = os.environ.get("MT_OWNER_PASSWORD") or f"Maotai@Owner{secrets.token_hex(3)}"
CLIENT_USER = os.environ.get("MT_CLIENT_USERNAME", "client")
CLIENT_PASS = os.environ.get("MT_CLIENT_PASSWORD") or f"Maotai@Client{secrets.token_hex(3)}"


def main() -> int:
    if not PASSWORD:
        print("请设置 DEPLOY_PASS", file=sys.stderr)
        return 1

    lines_to_set = {
        "MT_OWNER_USERNAME": OWNER_USER,
        "MT_OWNER_PASSWORD": OWNER_PASS,
        "MT_CLIENT_USERNAME": CLIENT_USER,
        "MT_CLIENT_PASSWORD": CLIENT_PASS,
        "MT_ADMIN_USERNAME": OWNER_USER,
        "MT_ADMIN_PASSWORD": OWNER_PASS,
    }

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    def sudo(cmd: str) -> str:
        i, o, e = c.exec_command(f"sudo -S bash -lc {cmd!r}", get_pty=True)
        i.write(PASSWORD + "\n")
        i.channel.shutdown_write()
        out = o.read().decode(errors="replace")
        if o.channel.recv_exit_status() != 0:
            raise RuntimeError(out + e.read().decode(errors="replace"))
        return out

    sudo(f"touch {ENV_PATH}")
    for key, val in lines_to_set.items():
        esc = val.replace("'", "'\"'\"'")
        sudo(
            f"(grep -q '^{key}=' {ENV_PATH} && "
            f"sed -i 's|^{key}=.*|{key}={esc}|' {ENV_PATH} || "
            f"echo '{key}={esc}' >> {ENV_PATH})"
        )

    sudo("systemctl restart maotai-api")
    import time

    time.sleep(2)
    _, o, _ = c.exec_command("curl -s http://127.0.0.1:8000/api/v1/ping")
    print(o.read().decode())
    c.close()

    print(f"\n✅ 双账号已配置")
    print(f"   最高管理员  {OWNER_USER} / {OWNER_PASS}")
    print(f"   甲方操作员  {CLIENT_USER} / {CLIENT_PASS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
