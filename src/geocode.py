"""高德地理编码。"""

import requests


def geocode_address(amap_key: str, address: str) -> list[dict]:
    resp = requests.get(
        "https://restapi.amap.com/v3/geocode/geo",
        params={"key": amap_key, "output": "json", "address": address},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("geocodes", [])
