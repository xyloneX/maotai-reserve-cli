import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...core.config import settings
from ...core.response import ok
from ...services.imaotai_service import health_items
from ..deps import AuthUser, CurrentUser, SuperAdmin

router = APIRouter(prefix="/settings", tags=["设置"])


class SettingsUpdate(BaseModel):
    schedule_target_time: str | None = None
    schedule_advance_seconds: int | None = None
    shop_strategy_default: str | None = None
    claim_energy_default: bool | None = None
    retry_count: int | None = None
    retry_interval_seconds: float | None = None
    session_wait_seconds: int | None = None
    pushplus_token: str | None = None
    reserve_parallel_by_egress: bool | None = None
    reserve_max_workers: int | None = None
    reserve_shard_size: int | None = None


class ProxyPoolsUpdate(BaseModel):
    pools: dict[str, str]


def _load_yaml() -> dict:
    if not settings.config_yaml.exists():
        return {}
    with open(settings.config_yaml, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _settings_view(raw: dict) -> dict:
    sched = raw.get("schedule", {}) or {}
    retry = raw.get("retry", {}) or {}
    session = raw.get("session", {}) or {}
    reserve = raw.get("reserve", {}) or {}
    pools = raw.get("proxy_pools") or {}
    return {
        "schedule_target_time": sched.get("target_time", "09:00:00"),
        "schedule_advance_seconds": sched.get("advance_seconds", 2),
        "shop_strategy_default": raw.get("shop_strategy", "max_inventory"),
        "claim_energy_default": raw.get("claim_energy", True),
        "retry_count": retry.get("count", 3),
        "retry_interval_seconds": retry.get("interval_seconds", 0.5),
        "session_wait_seconds": session.get("wait_seconds", 120),
        "pushplus_token": "***" if raw.get("pushplus_token") else "",
        "amap_key": "***" if raw.get("amap_key") else "",
        "reserve_parallel_by_egress": reserve.get("parallel_by_egress", True),
        "reserve_max_workers": reserve.get("max_workers", 32),
        "reserve_shard_size": reserve.get("shard_size", 50),
        "proxy_pool_count": len(pools),
    }


@router.get("")
def get_settings(_: CurrentUser = AuthUser):
    return ok(_settings_view(_load_yaml()))


@router.put("")
def put_settings(body: SettingsUpdate, _: CurrentUser = SuperAdmin):
    raw = _load_yaml()
    if body.schedule_target_time is not None or body.schedule_advance_seconds is not None:
        raw.setdefault("schedule", {})
        if body.schedule_target_time is not None:
            raw["schedule"]["target_time"] = body.schedule_target_time
        if body.schedule_advance_seconds is not None:
            raw["schedule"]["advance_seconds"] = body.schedule_advance_seconds
    if body.shop_strategy_default is not None:
        raw["shop_strategy"] = body.shop_strategy_default
    if body.claim_energy_default is not None:
        raw["claim_energy"] = body.claim_energy_default
    if body.retry_count is not None or body.retry_interval_seconds is not None:
        raw.setdefault("retry", {})
        if body.retry_count is not None:
            raw["retry"]["count"] = body.retry_count
        if body.retry_interval_seconds is not None:
            raw["retry"]["interval_seconds"] = body.retry_interval_seconds
    if body.session_wait_seconds is not None:
        raw.setdefault("session", {})["wait_seconds"] = body.session_wait_seconds
    if body.pushplus_token is not None:
        raw["pushplus_token"] = body.pushplus_token
    if (
        body.reserve_parallel_by_egress is not None
        or body.reserve_max_workers is not None
        or body.reserve_shard_size is not None
    ):
        raw.setdefault("reserve", {})
        if body.reserve_parallel_by_egress is not None:
            raw["reserve"]["parallel_by_egress"] = body.reserve_parallel_by_egress
        if body.reserve_max_workers is not None:
            raw["reserve"]["max_workers"] = body.reserve_max_workers
        if body.reserve_shard_size is not None:
            raw["reserve"]["shard_size"] = body.reserve_shard_size
    with open(settings.config_yaml, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, allow_unicode=True, default_flow_style=False)
    return ok(_settings_view(raw))


@router.get("/proxy-pools")
def get_proxy_pools(_: CurrentUser = AuthUser):
    from ...services.proxy_service import egress_group_usage, get_proxy_pools

    return ok(
        {
            "pools": get_proxy_pools(),
            "usage": egress_group_usage(),
        }
    )


@router.put("/proxy-pools")
def put_proxy_pools(body: ProxyPoolsUpdate, _: CurrentUser = SuperAdmin):
    from ...services.proxy_service import set_proxy_pools

    pools = set_proxy_pools(body.pools)
    return ok({"pools": pools, "count": len(pools)})


@router.post("/proxy-pools/sync-from-accounts")
def sync_proxy_from_accounts(_: CurrentUser = SuperAdmin):
    from ...services.proxy_service import sync_proxy_keys_from_accounts

    return ok(sync_proxy_keys_from_accounts())


@router.post("/proxy-pools/test")
def test_proxy_pools(_: CurrentUser = AuthUser):
    from ...services.proxy_service import test_all_proxies

    results = test_all_proxies()
    ok_count = sum(1 for r in results if r.get("ok"))
    return ok(
        {
            "total": len(results),
            "ok_count": ok_count,
            "items": results,
        }
    )


@router.get("/health")
def settings_health(_: CurrentUser = AuthUser):
    return ok({"items": health_items()})


@router.get("/scheduler")
def get_scheduler(_: CurrentUser = AuthUser):
    from ...services.scheduler_service import scheduler_status

    return ok(scheduler_status())
