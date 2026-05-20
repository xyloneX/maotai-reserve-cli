"""等待至预约窗口前的最佳提交时刻。"""

from __future__ import annotations

import datetime
import logging
import time

from .config_loader import ScheduleConfig

logger = logging.getLogger(__name__)


def wait_until_reserve_time(cfg: ScheduleConfig) -> None:
    """
    在 target_time 前 advance_seconds 秒触发。
    例如 09:00:00 前 2 秒 → 08:59:58 开始提交，减少过早/过晚。
    """
    now = datetime.datetime.now()
    parts = cfg.target_time.split(":")
    if len(parts) != 3:
        raise ValueError(f"schedule.target_time 格式应为 HH:MM:SS，当前: {cfg.target_time}")

    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    target = now.replace(hour=h, minute=m, second=s, microsecond=0)
    fire_at = target - datetime.timedelta(seconds=cfg.advance_seconds)

    if now >= target and not cfg.run_immediately_if_missed:
        logger.warning(
            "已过今日申购时间 %s，跳过等待。手动测试请设 run_immediately_if_missed: true",
            cfg.target_time,
        )
        return

    if now >= fire_at:
        logger.info("已到触发时刻，立即执行")
        return

    delta = (fire_at - now).total_seconds()
    logger.info("等待 %.1f 秒，将于 %s 发起预约", delta, fire_at.strftime("%H:%M:%S"))
    while datetime.datetime.now() < fire_at:
        remaining = (fire_at - datetime.datetime.now()).total_seconds()
        if remaining > 30:
            time.sleep(min(10, remaining - 5))
        elif remaining > 1:
            time.sleep(0.5)
        else:
            time.sleep(0.05)
