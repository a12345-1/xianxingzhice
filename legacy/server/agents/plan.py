# -*- coding: utf-8 -*-
"""② 行程生成：候选 POI → 按天结构化行程。

铁律：模型只能在候选里选，不能新增景点；
本地模式用"按区域 + 按时长"的确定性排法，保证不重叠、不超时。
"""
import json
import re

from .. import llm

PACE_POINTS = {"slow": 2, "normal": 3, "fast": 4}
BUFFER_MIN = 30          # 景点间通勤缓冲
LUNCH_EARLIEST = 11 * 60 + 45
DAY_START = 9 * 60
DAY_END = 21 * 60

SYSTEM = """你是短途行程规划师。基于候选地点生成 {days} 天行程。
硬约束：
1. 只能从候选里选，不得新增；
2. 每天 {n} 个景点 + 午餐 +（可选）晚餐；
3. 上午一个、午餐、下午一到两个，按区域就近安排；
4. 避开 avoid 里的标签；
5. 时间用 24 小时制 HH:MM，duration_min 是分钟。
只输出 JSON：
{{"days":[{{"day":1,"theme":"","items":[{{"name":"","type":"attraction",
"start":"09:30","duration_min":90,"cost":0}}]}}]}}"""


def plan_days(need: dict, pois: list) -> list:
    days = int(need.get("days") or 2)
    if llm.available():
        out = _plan_with_llm(need, pois)
        if out:
            return out
    return _plan_local(need, pois, days)


# ---------------------------------------------------------------- 本地
def _fmt(minutes: int) -> str:
    minutes = max(0, min(minutes, 23 * 60 + 59))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _match(poi: dict, need: dict) -> bool:
    tags = set((poi.get("tags") or "").split(";"))
    if tags & set(need.get("avoid") or []):
        return False
    return True


def parse_hours(text: str):
    """'10:00-21:00' → (600, 1260)；'全天' 或无法解析 → None。"""
    text = (text or "").strip()
    if not text or "全天" in text:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})\s*[-—~]\s*(\d{1,2}):(\d{2})", text)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2)), int(m.group(3)) * 60 + int(m.group(4))


def open_at(poi: dict, minutes: int) -> bool:
    rng = parse_hours(poi.get("open_hours"))
    if not rng:
        return True
    start, end = rng
    if end < start:                      # 跨夜营业
        return minutes >= start or minutes <= end
    return start <= minutes <= end


def earliest(poi: dict) -> int:
    """能开始的最早时间（分钟）。全天/无法解析视为 0。"""
    rng = parse_hours(poi.get("open_hours"))
    return rng[0] if rng else 0


def _score(poi: dict, need: dict) -> int:
    tags = set((poi.get("tags") or "").split(";"))
    return sum(2 for t in need.get("interests") or [] if t in tags)


def _plan_local(need: dict, pois: list, days: int) -> list:
    usable = [p for p in pois if _match(p, need)]
    attractions = [p for p in usable if p["type"] == "attraction"]
    foods = [p for p in usable if p["type"] == "food"]
    hotels = [p for p in usable if p["type"] == "hotel"]

    # 区域排序：兴趣匹配多、景点多的区域优先
    areas = {}
    for p in attractions:
        areas.setdefault(p["area"], []).append(p)
    ranked = sorted(areas.items(), key=lambda kv: sum(_score(p, need) for p in kv[1]), reverse=True)
    if not ranked:
        ranked = [("", [])]

    used, out = set(), []
    n_points = PACE_POINTS.get(need.get("pace", "normal"), 3)

    for d in range(1, days + 1):
        area, cands = ranked[(d - 1) % len(ranked)]
        picks = sorted([p for p in cands if p["id"] not in used],
                       key=lambda p: _score(p, need), reverse=True)[:max(n_points, 2)]
        area_foods = [p for p in foods if p["area"] == area and p["id"] not in used] or \
                     [p for p in foods if p["id"] not in used]
        lunch_pool = [p for p in area_foods if open_at(p, 12 * 60)] or area_foods
        dinner_pool = [p for p in area_foods if open_at(p, 18 * 60)]

        if not picks:
            out.append({"day": d, "theme": "自由安排", "items": []})
            continue

        items, t = [], DAY_START
        t = max(t, earliest(picks[0]))
        items.append(_entry(picks[0], t))
        t += picks[0]["stay_min"] + BUFFER_MIN
        lunch = lunch_pool[0] if lunch_pool else None
        if lunch:
            lt = max(t, LUNCH_EARLIEST, earliest(lunch))
            items.append(_entry(lunch, lt))
            t = lt + lunch["stay_min"] + BUFFER_MIN
        for p in picks[1:]:
            start = max(t, earliest(p))
            if start + p["stay_min"] > 17 * 60 + 30:
                break
            items.append(_entry(p, start))
            t = start + p["stay_min"] + BUFFER_MIN
        dinner = next((p for p in dinner_pool if not lunch or p["id"] != lunch["id"]), None)
        if dinner:
            dt = max(t, 18 * 60, earliest(dinner))
            if dt <= 20 * 60:
                items.append(_entry(dinner, dt))
                t = dt + dinner["stay_min"]

        if d < days and hotels:
            hotel = min(hotels, key=lambda h: 0 if h["area"] == area else 1)
            ht = max(t + BUFFER_MIN, 19 * 60)
            if ht <= DAY_END:
                items.append({"type": "hotel", "name": hotel["name"], "start": _fmt(ht),
                              "duration_min": 0, "cost": hotel["price"], "poi_id": hotel["id"],
                              "area": hotel["area"], "tags": hotel["tags"], "note": "住宿"})
                used.add(hotel["id"])

        for it in items:
            if it["poi_id"]:
                used.add(it["poi_id"])
        out.append({
            "day": d,
            "theme": f"{area or '市区'} · {'、'.join((need.get('interests') or ['经典路线'])[:2])}",
            "items": items,
        })
    return out


def _entry(poi: dict, start_min: int) -> dict:
    return {
        "type": poi["type"],
        "name": poi["name"],
        "start": _fmt(start_min),
        "duration_min": int(poi["stay_min"] or 60),
        "cost": float(poi["price"] or 0),
        "poi_id": poi["id"],
        "area": poi["area"],
        "tags": poi["tags"],
        "note": "",
    }


# ---------------------------------------------------------------- 模型
def _plan_with_llm(need: dict, pois: list):
    cand = [p for p in pois if _match(p, need)]
    brief = [
        {"name": p["name"], "type": p["type"], "area": p["area"],
         "price": p["price"], "stay_min": p["stay_min"], "tags": p["tags"]}
        for p in cand
    ]
    user = json.dumps({"need": need, "candidates": brief}, ensure_ascii=False)
    out = llm.complete_json(
        SYSTEM.format(days=need.get("days", 2), n=PACE_POINTS.get(need.get("pace"), 3)), user
    )
    if not out or "days" not in out:
        return None

    by_name = {p["name"]: p for p in cand}
    days = []
    for d in out["days"]:
        items = []
        for it in d.get("items", []):
            poi = by_name.get(it.get("name"))
            if not poi:
                continue
            items.append({
                "type": poi["type"], "name": poi["name"],
                "start": it.get("start", "09:30"),
                "duration_min": int(it.get("duration_min") or poi["stay_min"]),
                "cost": float(it.get("cost") or poi["price"] or 0),
                "poi_id": poi["id"], "area": poi["area"],
                "tags": poi["tags"], "note": it.get("reason", ""),
            })
        if items:
            days.append({"day": int(d.get("day") or len(days) + 1),
                         "theme": d.get("theme", ""), "items": items})
    return days or None
