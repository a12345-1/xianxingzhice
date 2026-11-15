# -*- coding: utf-8 -*-
"""把内部行程数据转换成《接口数据字段说明.md》定义的响应结构。

约定（与文档一致）：
- 金额整数元；时间 HH:mm；日期 YYYY-MM-DD
- 拿不到的字段返回 null，不省略 key
- items[].cost == cost_breakdown 四项之和
- budget.total == categories 四项之和
- days 长度 == day_count，items 允许空数组但不为 null
- source=model 的条目，前端要标「推测」
"""
import math
from datetime import date, datetime, timedelta

from .agents.tips import weather_of

WEEKDAY = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
MODE_MIN_PER_KM = {"walk": 13, "bus": 5, "taxi": 3}      # 分钟/公里（含等待的粗估）
TYPE_MAP = {"attraction": "spot", "food": "food", "hotel": "hotel", "transport": "transport"}

# 参考占比：仅用于给分类标黄，不参与超支判定
REF_RATIO = {"ticket": 0.20, "transport": 0.20, "food": 0.35, "hotel": 0.25}
CAT_LABEL = {"ticket": "门票", "transport": "交通", "food": "餐饮", "hotel": "住宿"}


def _hhmm_to_min(s):
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def _min_to_hhmm(m):
    m = max(0, min(int(m), 23 * 60 + 59))
    return f"{m // 60:02d}:{m % 60:02d}"


def _haversine_km(a, b):
    if not a or not b or None in (a[0], a[1], b[0], b[1]):
        return None
    lat1, lng1, lat2, lng2 = map(float, (a[0], a[1], b[0], b[1]))
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _transport(prev, cur):
    """根据两点直线距离粗估耗时；首项为 0。"""
    if not prev:
        return {"mode": "walk", "from_prev_min": 0}
    km = _haversine_km((prev.get("lat"), prev.get("lng")), (cur.get("lat"), cur.get("lng")))
    if km is None:
        return {"mode": "walk", "from_prev_min": 0}
    mode = "walk" if km <= 1.2 else ("bus" if km <= 6 else "taxi")
    minutes = int(round(km * MODE_MIN_PER_KM[mode]))
    return {"mode": mode, "from_prev_min": max(minutes, 5 if mode != "walk" else 0)}


def _breakdown(item, cost):
    if item["type"] == "food":
        return {"ticket": 0, "food": cost, "transport": 0, "hotel": 0}
    if item["type"] == "hotel":
        return {"ticket": 0, "food": 0, "transport": 0, "hotel": cost}
    if item["type"] == "transport":
        return {"ticket": 0, "food": 0, "transport": cost, "hotel": 0}
    return {"ticket": cost, "food": 0, "transport": 0, "hotel": 0}


def _closed_days(item):
    if "周一闭馆" in (item.get("open_hours") or ""):
        return [1]
    return []


def _walk_level(items):
    minutes = sum(int(i.get("duration_min") or 0) for i in items if i["type"] == "attraction")
    if minutes < 180:
        return "light"
    if minutes < 330:
        return "medium"
    return "heavy"


def _day_weather(start_date, day_index):
    if not start_date:
        return None
    d = date.fromisoformat(start_date) + timedelta(days=day_index - 1)
    w = weather_of(d.month)
    return {
        "condition": w["text"],
        "temp_low": w["low"],
        "temp_high": w["high"],
        "rain_prob": w["rain"],
        "source": "model",          # 未接真实天气接口，如实标注
    }


def build(trip, need, items, conflicts, tips=None, agents=None, elapsed_ms=None):
    """items: 已 join 过 POI 的条目（含 open_hours/lat/lng/tags）"""
    start = trip.get("start_date")
    days_n = int(trip.get("days") or 1)
    people = int(need.get("people") or need.get("companions") or 1)

    # 按天分组
    by_day = {}
    for it in items:
        by_day.setdefault(it["day_index"], []).append(it)
    for d in by_day:
        by_day[d].sort(key=lambda x: x["seq"])

    warn_map = {}
    for c in conflicts or []:
        if c.get("item_id"):
            warn_map.setdefault(c["item_id"], []).append(c)

    days = []
    total = 0
    for d in range(1, days_n + 1):
        lst = by_day.get(d, [])
        weather = _day_weather(start, d)
        day_items, prev, day_cost = [], None, 0
        for idx, it in enumerate(lst, start=1):
            cost = int(round(float(it.get("cost") or 0)))
            tr = _transport(prev, it)
            start_min = _hhmm_to_min(it.get("start_time"))
            end_min = start_min + int(it.get("duration_min") or 0)

            warns = []
            for c in warn_map.get(it["id"], []):
                warns.append({
                    "code": "TIME_CONFLICT" if "重叠" in c.get("reason", "") else "INFO",
                    "message": c.get("reason", ""),
                })
            if "排队久" in (it.get("tags") or "") and not any("排队" in w["message"] for w in warns):
                warns.append({"code": "QUEUE", "message": f"{it['name']} 常需排队（30—60 分钟）"})
            if weather and weather["rain_prob"] >= 50 and it["type"] == "attraction":
                warns.append({"code": "RAIN_SLIP", "message": "雨天路面湿滑，注意防滑"})

            labels = []
            if cost == 0:
                labels.append("免费")
            if it.get("need_booking"):
                labels.append("需预约")
            _tags = (it.get("tags") or "").split(";")
            if "排队久" in _tags or "人多" in _tags:
                labels.append("人多")
            if it["type"] == "hotel":
                labels.append("住宿")
            src = it.get("source") or "knowledge_base"
            if src == "user":
                labels.append("已改")

            day_items.append({
                "item_id": f"it_{it['id']}",
                "seq": idx,
                "type": TYPE_MAP.get(it["type"], "spot"),
                "name": it["name"],
                "start_time": _min_to_hhmm(start_min),
                "end_time": _min_to_hhmm(end_min),
                "duration_min": int(it.get("duration_min") or 0),
                "transport": tr,
                "cost": cost,
                "cost_breakdown": _breakdown(it, cost),
                "source": "model" if src == "model" else ("user" if src == "user" else "knowledge_base"),
                "open_hours": it.get("open_hours") or None,
                "closed_days": _closed_days(it),
                "warnings": warns,
                "labels": labels,
            })
            day_cost += cost
            total += cost
            prev = it

        days.append({
            "day_index": d,
            "date": (date.fromisoformat(start) + timedelta(days=d - 1)).isoformat() if start else None,
            "weekday": WEEKDAY[(date.fromisoformat(start) + timedelta(days=d - 1)).weekday()] if start else None,
            "weather": weather,
            "walk_level": _walk_level(lst),
            "day_cost": day_cost,
            "items": day_items,
        })

    budget = _budget(items, total, trip.get("budget_limit"), people)
    tips_obj = _tips(trip, days, items, tips)

    return {
        "status": "ok" if all(d["items"] for d in days) else "partial",
        "trip_id": trip.get("code") or f"tr_{trip['id']:04d}",
        "request": {
            "raw_text": trip.get("raw_text") or need.get("raw") or "",
            "destination": trip.get("city"),
            "day_count": days_n,
            "people": people,
            "budget_limit": int(float(trip["budget_limit"])) if trip.get("budget_limit") else None,
            "start_date": start,
        },
        "summary": {
            "title": f"{trip.get('city')} {days_n} 日",
            "start_date": start,
            "end_date": (date.fromisoformat(start) + timedelta(days=days_n - 1)).isoformat() if start else None,
            "people": people,
            "day_count": days_n,
            "item_count": sum(len(d["items"]) for d in days),
            "total_cost": total,
            "budget_limit": budget["limit"],
            "over_budget": budget["over_budget"],
        },
        "days": days,
        "budget": budget,
        "tips": tips_obj,
        "meta": {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "elapsed_ms": int(elapsed_ms or 0),
            "model": "local-rules",
            "agents": agents or [],
            "adjustments": trip.get("adjust_list") or [],
        },
    }


def _budget(items, total, limit, people):
    amounts = {"ticket": 0, "transport": 0, "food": 0, "hotel": 0}
    for it in items:
        cost = int(round(float(it.get("cost") or 0)))
        key = {"food": "food", "hotel": "hotel", "transport": "transport"}.get(it["type"], "ticket")
        amounts[key] += cost

    lim = None
    try:
        if limit:
            lim = int(float(limit))
    except (TypeError, ValueError):
        lim = None

    over = lim is not None and total > lim
    cats = []
    for key in ("ticket", "transport", "food", "hotel"):
        amt = amounts[key]
        cats.append({
            "key": key,
            "label": CAT_LABEL[key],
            "amount": amt,
            "ratio": round(amt / total, 3) if total else 0,
            "over": bool(total) and (amt / total) > REF_RATIO[key],
        })

    suggestions = []
    if over:
        # 规则 1：换掉最贵的收费景点
        spots = [i for i in items if i["type"] == "attraction" and float(i.get("cost") or 0) > 0]
        if spots:
            top = max(spots, key=lambda x: float(x["cost"]))
            suggestions.append({
                "code": "SWAP_SPOT",
                "message": f"把「{top['name']}」换成免费景点，可省 {int(top['cost'])} 元",
                "save_amount": int(top["cost"]),
                "target": {"day_index": top["day_index"], "item_id": f"it_{top['id']}"},
            })

        # 规则 2：降住宿档次（按住宿费的三成估）
        hotels = [i for i in items if i["type"] == "hotel" and float(i.get("cost") or 0) > 0]
        if hotels:
            save = int(sum(float(h.get("cost") or 0) for h in hotels) * 0.3)
            if save > 0:
                suggestions.append({
                    "code": "DOWNGRADE_HOTEL",
                    "message": f"降到经济型/青旅单间，住宿可省约 {save} 元",
                    "save_amount": save,
                    "target": {"day_index": hotels[0]["day_index"], "item_id": f"it_{hotels[0]['id']}"},
                })

        # 规则 3：少玩一天
        days = len({i["day_index"] for i in items})
        if days >= 2 and total:
            per_day = int(round(total / days))
            if per_day > 0 and per_day >= (total - lim):
                suggestions.append({
                    "code": "CUT_DAY",
                    "message": f"砍掉一天约省 {per_day} 元（当前 {days} 天）",
                    "save_amount": per_day,
                    "target": {"day_index": days, "item_id": None},
                })

    return {
        "limit": lim,
        "total": total,
        "remaining": (lim - total) if lim is not None else None,
        "over_budget": over,
        "over_amount": (total - lim) if over else 0,
        "per_person": total // max(people, 1),
        "categories": cats,
        "suggestions": suggestions,
    }


def _tips(trip, days, items, tips):
    base = tips or {}
    packing = list(base.get("packing") or [])
    weather_tips, spot_notes = [], []

    for d in days:
        w = d.get("weather")
        if not w:
            continue
        level = "warn" if w["rain_prob"] >= 50 or w["temp_high"] >= 32 else "info"
        actions = []
        if w["rain_prob"] >= 50:
            actions.append("带伞")
            actions.append("防滑鞋")
        if w["temp_high"] >= 30:
            actions.append("防晒")
        msg = f"{w['condition']} {w['temp_low']}—{w['temp_high']}℃"
        if actions:
            msg += "，" + "、".join(actions)
        weather_tips.append({
            "day_index": d["day_index"], "date": d["date"], "level": level,
            "condition": w["condition"], "message": msg, "actions": actions,
        })

    for d in days:
        for it in d["items"]:
            for w in it["warnings"]:
                spot_notes.append({
                    "name": it["name"], "day_index": d["day_index"], "item_id": it["item_id"],
                    "level": "warn" if w["code"] in ("RAIN_SLIP", "TIME_CONFLICT") else "info",
                    "message": w["message"], "source": "knowledge_base",
                })

    return {
        "source": "mixed",
        "packing": packing[:8],
        "weather_tips": weather_tips,
        "spot_notes": spot_notes,
        "season_notes": base.get("pitfalls") and [
            {"message": m, "level": "info", "source": "knowledge_base"} for m in base["pitfalls"]
        ] or [],
        "note": base.get("note"),
        "note_source": base.get("note_source"),
    }

