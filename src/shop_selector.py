"""门店选择：库存优先 / 距离优先。"""

from __future__ import annotations

import math
from typing import Any


def pick_shop_max_inventory(
    shops: list[dict],
    item_code: str,
    city_shop_ids: set[str] | None = None,
) -> str | None:
    """选本市该商品可预约门店中库存（inventory）最大者 — 提高中签概率的常用策略。"""
    best_id: str | None = None
    best_inv = -1
    for shop in shops:
        shop_id = str(shop.get("shopId", ""))
        if city_shop_ids and shop_id not in city_shop_ids:
            continue
        for item in shop.get("items", []):
            if str(item.get("itemId")) != str(item_code):
                continue
            inv = int(item.get("inventory", 0))
            if inv > best_inv:
                best_inv = inv
                best_id = shop_id
    return best_id


def pick_shop_nearest(
    shops: list[dict],
    item_code: str,
    shop_details: dict[str, Any],
    lat: float,
    lng: float,
    city_shop_ids: set[str] | None = None,
) -> str | None:
    best_id: str | None = None
    best_dist = float("inf")
    for shop in shops:
        shop_id = str(shop.get("shopId", ""))
        if city_shop_ids and shop_id not in city_shop_ids:
            continue
        item_ids = [str(i.get("itemId")) for i in shop.get("items", [])]
        if str(item_code) not in item_ids:
            continue
        info = shop_details.get(shop_id) or {}
        slat, slng = float(info.get("lat", 0)), float(info.get("lng", 0))
        dist = math.sqrt((lat - slat) ** 2 + (lng - slng) ** 2)
        if dist < best_dist:
            best_dist = dist
            best_id = shop_id
    return best_id


def select_shop(
    strategy: str,
    shops: list[dict],
    item_code: str,
    shop_details: dict[str, Any],
    province: str,
    city: str,
    province_city_map: dict,
    lat: str,
    lng: str,
) -> str | None:
    city_ids: set[str] | None = None
    prov_map = province_city_map.get(province, {})
    if city in prov_map:
        city_ids = set(prov_map[city])

    if strategy == "nearest":
        return pick_shop_nearest(
            shops, item_code, shop_details, float(lat), float(lng), city_ids
        )
    return pick_shop_max_inventory(shops, item_code, city_ids)
