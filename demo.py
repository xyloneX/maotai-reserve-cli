#!/usr/bin/env python3
"""
演示模式：无需登录即可查看工具能力与公开接口是否正常。
用法: python demo.py
"""

from __future__ import annotations

import datetime
import json
import sys
import time

from src.api import fetch_app_version
from src.config_loader import (
    CONFIG_PATH,
    CREDENTIALS_PATH,
    load_config,
    load_credentials,
    validate_secret_key,
)
from src.crypto import ActParamEncryptor, request_signature


def line(char: str = "─", width: int = 52) -> None:
    print(char * width)


def section(title: str) -> None:
    print()
    line("═")
    print(f"  {title}")
    line("═")


def step_ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def step_info(msg: str) -> None:
    print(f"    {msg}")


def step_warn(msg: str) -> None:
    print(f"  ⚠ {msg}")


def demo_public_apis() -> dict:
    """调用无需 Token 的公开接口。"""
    section("1. 公开接口探测（无需登录）")

    version = fetch_app_version()
    step_ok(f"i茅台 App Store 最新版本: {version}")

    day_ms = int(time.mktime(datetime.date.today().timetuple()) * 1000)
    import requests

    session_url = (
        f"https://static.moutai519.com.cn/mt-backend/xhr/front/mall/"
        f"index/session/get/{day_ms}"
    )
    r = requests.get(session_url, timeout=15)
    session_id = None
    if r.status_code == 200:
        session_id = r.json().get("data", {}).get("sessionId")
        step_ok(f"今日场次 sessionId: {session_id}")
        step_info(f"申购窗口请以 App 为准，通常 9:00–10:00")
    else:
        step_warn(f"场次接口异常 HTTP {r.status_code}")

    res_url = "https://static.moutai519.com.cn/mt-backend/xhr/front/mall/resource/get"
    r2 = requests.get(
        res_url,
        headers={"User-Agent": "iPhone"},
        timeout=15,
    )
    shop_count = 0
    if r2.status_code == 200:
        shops_link = r2.json().get("data", {}).get("mtshops_pc", {}).get("url", "")
        if shops_link:
            shops = requests.get(shops_link, timeout=30).json()
            shop_count = len(shops)
            step_ok(f"全国门店数据已拉取: {shop_count} 家")
    else:
        step_warn("门店列表接口异常")

    return {"version": version, "session_id": session_id, "shop_count": shop_count}


def demo_crypto() -> None:
    section("2. 加密 / 签名演示（与 App 协议一致）")

    params = {"mobile": "13800000000"}
    md5, ts = request_signature(params, "1700000000000")
    step_ok(f"登录签名 md5: {md5[:16]}…")
    step_info(f"timestamp: {ts}")

    enc = ActParamEncryptor()
    sample = {
        "itemInfoList": [{"count": 1, "itemId": "10941"}],
        "sessionId": 12345,
        "userId": "10001",
        "shopId": "151510100019",
    }
    act = enc.encrypt(sample)
    step_ok(f"预约 actParam 已生成（长度 {len(act)}）")
    step_info(f"片段: {act[:48]}…")


def demo_config() -> None:
    section("3. 本地配置检查")

    step_info(f"配置文件: {CONFIG_PATH}")
    step_info(f"账号文件: {CREDENTIALS_PATH}")

    cfg = None
    try:
        cfg = load_config()
        step_ok(f"商品数: {len(cfg.items)}")
        for it in cfg.items:
            step_info(f"  · {it.code} {it.name}")
        step_ok(f"门店策略: {cfg.shop_strategy}")
        step_ok(
            f"定时: {cfg.schedule.target_time} 前 {cfg.schedule.advance_seconds}s 提交"
        )

        try:
            validate_secret_key(cfg.secret_key)
            step_ok("secret_key 已配置")
        except Exception as e:
            step_warn(str(e))

        if not cfg.amap_key:
            step_warn("amap_key 未填，login.py 需要高德 Key")
        else:
            step_ok("amap_key 已配置")

    except FileNotFoundError as e:
        step_warn(str(e))

    accounts = []
    if cfg:
        try:
            validate_secret_key(cfg.secret_key)
            accounts = load_credentials(cfg.secret_key)
        except Exception:
            pass
    if accounts:
        step_ok(f"已保存账号: {len(accounts)} 个")
        for a in accounts:
            step_info(
                f"  · {a.mobile[:3]}****{a.mobile[-4:]} | "
                f"{a.province}{a.city} | 至 {a.end_date}"
            )
    else:
        step_warn("尚无账号，完成配置后运行: python login.py")


def demo_flow_simulation(session_id) -> None:
    section("4. 预约流程模拟（演示，未真实提交）")

    steps = [
        "等待至 08:59:58（schedule）",
        "刷新 sessionId",
        "拉取门店列表 → 按库存选店",
        "AES 加密 actParam",
        "POST /xhr/front/mall/reservation/add",
        "PushPlus 推送结果",
    ]
    for i, s in enumerate(steps, 1):
        print(f"  [{i}/{len(steps)}] {s}")
        time.sleep(0.35)

    print()
    step_ok("模拟完成（演示模式未调用预约接口）")
    if session_id:
        step_info(f"真实预约将使用 sessionId={session_id}")


def main() -> None:
    print()
    line("═")
    print("  i茅台自动预约 · 演示模式")
    print("  项目路径: 茅台抢单软件/")
    line("═")

    info = demo_public_apis()
    demo_crypto()
    demo_config()
    demo_flow_simulation(info.get("session_id"))

    section("下一步")
    print("  1. 编辑 config.yaml（secret_key、amap_key、商品 ID）")
    print("  2. python login.py          # 首次登录")
    print("  3. python check.py          # 自检")
    print("  4. python main.py --dry-run # 试跑")
    print("  5. python main.py           # 正式预约")
    print()
    line()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
