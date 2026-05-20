"""预约执行核心逻辑，供 main.py 与 CLI 共用。"""

from __future__ import annotations

import logging
from datetime import datetime

from .api import IMaotaiClient, fetch_app_version
from .config_loader import AppConfig, load_config, load_credentials, mask_mobile, validate_secret_key
from .exceptions import ConfigError, SessionNotReadyError, TokenExpiredError
from .notify import push_pushplus
from .scheduler import wait_until_reserve_time

logger = logging.getLogger(__name__)
TODAY = datetime.now().strftime("%Y%m%d")


def reserve_one_item(client, cfg, item_code, item_name, p_c_map, shop_details, label, dry_run):
    from .shop_selector import select_shop

    shops = client.fetch_session_shops(item_code)
    shop_id = select_shop(
        cfg.shop_strategy,
        shops,
        item_code,
        shop_details,
        client.account.province,
        client.account.city,
        p_c_map,
        client.account.lat,
        client.account.lng,
    )
    if not shop_id:
        return False, f"{item_name}: 未找到可预约门店"

    shop_name = shop_details.get(shop_id, {}).get("name", shop_id)

    if dry_run:
        preview = client.preview_reserve(shop_id, item_code)
        return True, (
            f"🔍 [试跑] {label} | {item_name} | {shop_name} | "
            f"session={preview['session_id']} actParam长度={preview['act_param_len']}"
        )

    import time

    last_msg = ""
    for attempt in range(1, cfg.retry_count + 1):
        ok, msg = client.reserve(shop_id, item_code)
        last_msg = msg
        if ok:
            return True, f"✅ {label} | {item_name} | {shop_name} | {msg}"
        logger.warning("预约失败 [%s] 第%d次: %s", item_name, attempt, msg)
        if attempt < cfg.retry_count:
            time.sleep(cfg.retry_interval)

    return False, f"❌ {label} | {item_name} | {shop_name} | {last_msg}"


def prepare_account(client: IMaotaiClient, cfg: AppConfig, dry_run: bool) -> None:
    ok, msg = client.validate_token()
    if not ok:
        raise TokenExpiredError(
            f"{mask_mobile(client.account.mobile)}: {msg}，请重新登录"
        )
    logger.info("Token 校验: %s — %s", mask_mobile(client.account.mobile), msg)

    if dry_run:
        sid = client.refresh_session_id()
        if sid == "0":
            logger.warning("试跑: sessionId=0，仍将演示选店与加密")
        return

    client.ensure_session_id(
        max_wait_seconds=cfg.session_wait_seconds,
        poll_interval=cfg.session_poll_interval,
    )


def run_account(client: IMaotaiClient, cfg: AppConfig, dry_run: bool) -> list[str]:
    results: list[str] = []
    label = mask_mobile(client.account.mobile)
    prepare_account(client, cfg, dry_run)
    p_c_map, shop_details = client.fetch_shop_map()

    if cfg.claim_energy and not dry_run:
        logger.info("小茅运/耐力: %s", client.claim_energy())

    for item in cfg.items:
        ok, line = reserve_one_item(
            client, cfg, item.code, item.name, p_c_map, shop_details, label, dry_run
        )
        results.append(line)
        logger.info(line)
    return results


def execute_reserve(
    *,
    dry_run: bool = False,
    skip_wait: bool = False,
    on_line: callable | None = None,
) -> tuple[bool, list[str]]:
    """
    执行预约流程。
    返回 (是否整体成功, 结果行列表)
    on_line: 可选回调，每完成一行结果时调用
    """
    cfg = load_config()
    validate_secret_key(cfg.secret_key)
    accounts = load_credentials(cfg.secret_key)
    if not accounts:
        raise ConfigError("无账号，请先登录")

    app_ver = fetch_app_version()
    logger.info(
        "模式: %s | App %s | 策略: %s",
        "试跑" if dry_run else "正式",
        app_ver,
        cfg.shop_strategy,
    )

    if not skip_wait and not dry_run:
        wait_until_reserve_time(cfg.schedule)

    all_lines: list[str] = []
    success_any = False

    for acc in accounts:
        if TODAY > acc.end_date:
            line = f"跳过过期账号 {mask_mobile(acc.mobile)}"
            all_lines.append(line)
            if on_line:
                on_line(line)
            continue

        client = IMaotaiClient(acc, app_version=app_ver)
        try:
            for line in run_account(client, cfg, dry_run):
                all_lines.append(line)
                if on_line:
                    on_line(line)
                if line.startswith("✅") or line.startswith("🔍"):
                    success_any = True
        except (TokenExpiredError, SessionNotReadyError) as e:
            line = f"❌ {e}"
            all_lines.append(line)
            if on_line:
                on_line(line)
        except Exception as e:
            line = f"❌ {mask_mobile(acc.mobile)}: {e}"
            logger.exception(line)
            all_lines.append(line)
            if on_line:
                on_line(line)

    title = "i茅台试跑完成" if dry_run else (
        "i茅台预约完成" if success_any else "i茅台预约结果"
    )
    push_pushplus(cfg.pushplus_token, title, "\n".join(all_lines))

    return success_any, all_lines
