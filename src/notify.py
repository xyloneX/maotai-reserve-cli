"""消息推送。"""

import logging

import requests

logger = logging.getLogger(__name__)


def push_pushplus(token: str, title: str, content: str) -> None:
    if not token:
        return
    try:
        r = requests.get(
            "http://www.pushplus.plus/send",
            params={"token": token, "title": title, "content": content},
            timeout=15,
        )
        logger.info("PushPlus: %s %s", r.status_code, r.text[:100])
    except Exception as e:
        logger.warning("PushPlus 推送失败: %s", e)
