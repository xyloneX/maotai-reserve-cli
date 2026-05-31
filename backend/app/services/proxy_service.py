"""代理池配置与健康检测。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import yaml

from ..core.config import settings
from ..core.database import SessionLocal
from ..models.entities import Account

logger = logging.getLogger(__name__)


def load_config_yaml() -> dict:
    path = settings.config_yaml
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config_yaml(raw: dict) -> None:
    with open(settings.config_yaml, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, allow_unicode=True, default_flow_style=False)


def get_proxy_pools() -> dict[str, str]:
    raw = load_config_yaml()
    return {str(k): str(v) for k, v in (raw.get("proxy_pools") or {}).items()}


def set_proxy_pools(pools: dict[str, str]) -> dict[str, str]:
    raw = load_config_yaml()
    cleaned = {k.strip(): v.strip() for k, v in pools.items() if k.strip() and v.strip()}
    raw["proxy_pools"] = cleaned
    save_config_yaml(raw)
    return cleaned


def egress_group_usage() -> list[dict]:
    """各出口组账号数量及是否已配置代理。"""
    pools = get_proxy_pools()
    db = SessionLocal()
    try:
        accounts = db.query(Account).filter(Account.enabled == True).all()  # noqa: E712
        counts: dict[str, int] = {}
        for a in accounts:
            g = (a.egress_group or "").strip() or "_direct"
            counts[g] = counts.get(g, 0) + 1
        return [
            {
                "egress_group": g,
                "account_count": n,
                "has_proxy": g in pools or (g == "_direct" and "_direct" in pools),
                "proxy_url": pools.get(g, pools.get(g.replace("_direct", ""), "")),
            }
            for g, n in sorted(counts.items(), key=lambda x: -x[1])
        ]
    finally:
        db.close()


def sync_proxy_keys_from_accounts() -> dict[str, str]:
    """为尚未配置的空 egress_group 生成占位项（URL 需人工填写）。"""
    pools = get_proxy_pools()
    db = SessionLocal()
    try:
        groups = {
            (a.egress_group or "").strip()
            for a in db.query(Account).filter(Account.enabled == True).all()  # noqa: E712
            if (a.egress_group or "").strip()
        }
    finally:
        db.close()
    added = 0
    for g in sorted(groups):
        if g not in pools:
            pools[g] = ""
            added += 1
    if added:
        set_proxy_pools(pools)
    return {"added": added, "total": len(pools), "pools": pools}


def test_proxy_url(url: str, timeout: float = 8.0) -> dict:
    if not url or not url.strip():
        return {"ok": False, "message": "代理 URL 为空", "latency_ms": 0}
    proxies = {"http": url.strip(), "https": url.strip()}
    try:
        t0 = __import__("time").time()
        r = requests.get(
            "https://www.baidu.com",
            proxies=proxies,
            timeout=timeout,
            allow_redirects=True,
        )
        ms = int((__import__("time").time() - t0) * 1000)
        if r.status_code < 500:
            return {"ok": True, "message": f"HTTP {r.status_code}", "latency_ms": ms}
        return {"ok": False, "message": f"HTTP {r.status_code}", "latency_ms": ms}
    except Exception as e:
        return {"ok": False, "message": str(e)[:200], "latency_ms": 0}


def test_all_proxies(max_workers: int = 8) -> list[dict]:
    pools = get_proxy_pools()
    if not pools:
        return []
    results: list[dict] = []

    def _one(name: str, url: str) -> dict:
        r = test_proxy_url(url)
        return {"name": name, "url": url, **r}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_one, n, u): n for n, u in pools.items()}
        for fut in as_completed(futs):
            results.append(fut.result())
    return sorted(results, key=lambda x: x["name"])
