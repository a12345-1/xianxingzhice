# -*- coding: utf-8 -*-
"""高德 POI 搜索（Web 服务 API）。

没有配置 AMAP_KEY 时 enabled() 为 False，调用方走本地示例库，不做任何网络请求。
Key 申请：https://lbs.amap.com → 应用管理 → 添加 Key → 服务平台必须选「Web服务」。
"""
import re
import time

from .config import AMAP_KEY, AMAP_TIMEOUT

# 高德分类编码：风景名胜 / 餐饮服务 / 住宿服务
TYPES = {"attraction": "110000", "food": "050000", "hotel": "100000"}
DEFAULT_STAY = {"attraction": 90, "food": 60, "hotel": 0}

# 只用分类编码会拉回“村口小广场”，关键词搜索质量高得多
QUERIES = {
    "attraction": ["景区", "博物馆", "步行街", "公园"],
    "food": ["美食街", "小吃"],
    "hotel": ["酒店"],
}
CAP = {"attraction": 14, "food": 8, "hotel": 4}
MIN_RATING = 4.2

# 明显不是“可游览地点”的名字，直接过滤
BAD_WORDS = ("停车场", "地铁站", "公交站", "售票处", "服务中心", "加油站",
             "公共厕所", "充电站", "便利店")


class AmapError(Exception):
    pass


def enabled():
    return bool(AMAP_KEY)


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _tags(poi_type, name):
    """从高德分类字符串推断标签，够排程用即可。"""
    t = poi_type or ""
    tags = []
    if "风景" in t or "公园" in t or "自然" in t:
        tags.append("自然")
    if "博物馆" in t or "寺庙" in t or "古迹" in t or "历史" in t:
        tags.append("人文")
    if "餐饮" in t or "美食" in t or "小吃" in t:
        tags.append("美食")
    if "购物" in t or "商场" in t:
        tags.append("购物")
    if "住宿" in t or "酒店" in t or "宾馆" in t:
        tags.append("住宿")
    if not tags:
        tags.append("人文" if "景点" in t else "美食" if "餐" in t else "自然")
    if "博物馆" in name or "博物院" in name or "纪念馆" in name:
        if "人文" not in tags:
            tags.append("人文")
    return tags


def _open_hours(biz):
    for k in ("opentime2", "opentime", "open_time"):
        v = biz.get(k)
        if v and isinstance(v, str) and re.search(r"\d", v):
            return v.strip()[:30]
    return "全天"


def _to_row(p, city, type_, city_fallback=""):
    loc = (p.get("location") or "").split(",")
    if len(loc) != 2:
        return None
    lng, lat = _num(loc[0]), _num(loc[1])
    if not lat or not lng:
        return None
    biz = p.get("biz_ext") or {}
    if isinstance(biz, list):
        biz = biz[0] if biz else {}
    name = (p.get("name") or "").strip()
    if not name:
        return None
    return {
        "name": name,
        "city": city,
        "type": type_,
        "area": p.get("adname") or city_fallback or city,
        "lat": round(lat, 4),
        "lng": round(lng, 4),
        "open_hours": _open_hours(biz),
        "price": _num(biz.get("cost"), 0.0),
        "tags": ";".join(_tags(p.get("type"), name)),
        "stay_min": DEFAULT_STAY[type_],
        "rating": _num(biz.get("rating"), 0.0) or None,
        "address": (p.get("address") or "") if isinstance(p.get("address"), str) else "",
        "amap_id": p.get("id") or "",
    }


def search_city(city, per_type=20):
    """按城市拉景点/餐饮/住宿。

    只用分类编码会返回一堆“村口小广场”，所以改成关键词搜索 + 评分过滤：
    景点的关键词是 景区/博物馆/步行街/公园，餐饮是 美食街/小吃，住宿是 酒店。
    失败抛 AmapError（调用方决定是否降级）。
    """
    if not AMAP_KEY:
        raise AmapError("未配置 AMAP_KEY")

    import httpx

    rows = []
    try:
        with httpx.Client(timeout=AMAP_TIMEOUT) as c:
            for type_, keywords in QUERIES.items():
                bucket, seen = [], set()
                for kw in keywords:
                    data = _get(c, city, TYPES[type_], kw, min(per_type, 25))
                    for p in data.get("pois", []):
                        row = _to_row(p, city, type_)
                        if not row or row["name"] in seen:
                            continue
                        if any(w in row["name"] for w in BAD_WORDS):
                            continue
                        if (row.get("rating") or 0) < MIN_RATING:
                            continue
                        seen.add(row["name"])
                        bucket.append(row)
                bucket.sort(key=lambda r: r.get("rating") or 0, reverse=True)
                rows.extend(bucket[:CAP[type_]])
    except AmapError:
        raise
    except Exception as e:                      # 网络/解析异常统一成 AmapError
        raise AmapError(f"请求高德失败：{e}")
    return rows


def _get_raw(city, keyword, offset=10, types=None):
    """给建库脚本用：按关键词查一次，返回原始 JSON。"""
    import httpx

    if not AMAP_KEY:
        raise AmapError("未配置 AMAP_KEY")
    params = {
        "key": AMAP_KEY, "city": city, "citylimit": "true",
        "keywords": keyword, "offset": min(offset, 25), "page": 1, "extensions": "all",
    }
    if types:
        params["types"] = types
    try:
        data = httpx.get("https://restapi.amap.com/v3/place/text",
                         params=params, timeout=AMAP_TIMEOUT).json()
    except Exception as e:
        raise AmapError(f"请求高德失败：{e}")
    if str(data.get("status")) != "1":
        raise AmapError(f"高德返回 {data.get('info')}（{data.get('infocode')}）")
    return data


def _get(client, city, types, keyword, offset):
    r = client.get("https://restapi.amap.com/v3/place/text", params={
        "key": AMAP_KEY, "city": city, "citylimit": "true",
        "types": types, "keywords": keyword,
        "offset": offset, "page": 1, "extensions": "all",
    })
    data = r.json()
    if str(data.get("status")) != "1":
        raise AmapError(f"高德返回 {data.get('info')}（{data.get('infocode')}）")
    return data
