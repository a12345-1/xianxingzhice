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


def plan_days(need: dict, pois: list):
    """返回 (按天的条目列表, 规划说明)。

    先让模型提议（propose.py），再由 _guard 用代码裁决：去重、补足、距离、
    预算、时间。模型不可用或输出不可用时退回本地排程。
    """
    days = int(need.get("days") or 2)
    if llm.available():
        out = _plan_guarded(need, pois, days)
        if out:
            plan, info = out
            if plan:
                return plan, info
    return _plan_local(need, pois, days), {"source": "local", "fixes": [], "note": ""}


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

        if not picks:
            out.append({"day": d, "theme": "自由安排", "items": []})
            continue

        area_foods = [p for p in foods if p["area"] == area and p["id"] not in used] or \
                     [p for p in foods if p["id"] not in used]
        # 离当天第一个景点近的餐馆优先，避免午饭安排在 70 分钟车程外
        anchor = picks[0]
        area_foods = sorted(area_foods, key=lambda p: _km(anchor, p))
        lunch_pool = [p for p in area_foods if open_at(p, 12 * 60)] or area_foods
        dinner_pool = [p for p in area_foods if open_at(p, 18 * 60)]

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
            # 选离当天最后一个点最近的酒店，避免出现“民宿在 250 分钟车程外”
            last_poi = next((p for p in reversed(items) if p.get("poi_id")), None)
            anchor = None
            if last_poi:
                anchor = next((p for p in usable if p["id"] == last_poi["poi_id"]), None)

            def _hotel_score(h):
                if anchor and anchor.get("lat") and h.get("lat"):
                    return _km(anchor, h)
                return 0 if h["area"] == area else 1

            hotel = min(hotels, key=_hotel_score)
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


def _weather_for(need, day):
    """取某一天的天气模板（用于“下雨减少室外活动”这类约束）。"""
    from datetime import date, timedelta
    from . import weather
    start = need.get("start_date")
    if not start:
        return None
    try:
        d = date.fromisoformat(start) + timedelta(days=int(day) - 1)
    except (TypeError, ValueError):
        return None
    return weather.pick("%s-%s" % (need.get("city"), d.isoformat()), day)


def _km(a, b):
    """两点直线距离（公里），用于给酒店排序。"""
    import math
    try:
        lat1, lng1, lat2, lng2 = map(float, (a["lat"], a["lng"], b["lat"], b["lng"]))
    except (TypeError, ValueError, KeyError):
        return 999
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


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

# ---------------------------------------------------------------- 模型提议 + 代码把关
MAX_HOP_KM = 15          # 同一天两点直线距离超过它，视为“来回跑”
LUNCH_T = 11 * 60 + 45
DINNER_T = 17 * 60 + 30
HOTEL_T = 19 * 60


def _plan_guarded(need: dict, pois: list, days: int):
    """模型挑点 -> 代码校验修复 -> 生成带时间的条目。

    返回 (plan, info)；模型不可用返回 None。
    info = {"source": "llm+guard", "note": ..., "fixes": [...]}
    """
    from . import propose

    cand = [p for p in pois if _match(p, need)]
    if not cand:
        return None
    raw, note = propose.propose(need, cand)
    if not raw:
        return None

    fixes = []
    by_name = {p["name"]: p for p in cand}

    def lookup(name):
        name = (name or "").strip()
        if not name:
            return None
        if name in by_name:
            return by_name[name]
        for p in cand:
            if name in p["name"] or p["name"] in name:
                return p
        return None

    used = set()
    picked = []
    for idx in range(1, days + 1):
        d = next((x for x in raw["days"] if int(x.get("day_index") or 0) == idx), None)
        if d is None and idx - 1 < len(raw["days"]):
            d = raw["days"][idx - 1]
        d = d or {}

        spots, foods, hotel = [], [], None
        for name in (d.get("spots") or [])[:3]:
            poi = lookup(name)
            if not poi:
                if name:
                    fixes.append("模型提到的「%s」不在候选库，已忽略" % name)
                continue
            if poi["type"] != "attraction":
                continue
            if poi["id"] in used:
                fixes.append("「%s」被重复安排，只保留第一次" % poi["name"])
                continue
            spots.append(poi)
            used.add(poi["id"])

        for name in (d.get("foods") or [])[:2]:
            poi = lookup(name)
            if not poi or poi["type"] != "food" or poi["id"] in used:
                continue
            foods.append(poi)
            used.add(poi["id"])

        h = lookup(d.get("hotel"))
        if h and h["type"] == "hotel" and h["id"] not in used:
            hotel = h
            used.add(h["id"])

        # 住宿别选太远的：离最后一个景点超过 15 公里就换最近的
        if hotel and spots:
            far = _km(spots[-1], hotel)
            if far > MAX_HOP_KM:
                closer = [x for x in cand if x["type"] == "hotel" and x["id"] != hotel["id"]]
                closer.sort(key=lambda x: _km(spots[-1], x))
                if closer and _km(spots[-1], closer[0]) < far:
                    fixes.append("住宿「%s」离当天最后一个点约 %.0f 公里，换成「%s」"
                                 % (hotel["name"], far, closer[0]["name"]))
                    used.discard(hotel["id"])
                    hotel = closer[0]
                    used.add(hotel["id"])

        picked.append({"day": idx, "spots": spots, "foods": foods, "hotel": hotel})

    # 天气约束：下雨/高温这类模板下，减少室外活动（优先室内，最多留 1 个室外）
    from . import weather as weather_agent
    for p in picked:
        tpl = _weather_for(need, p["day"])
        p["weather"] = tpl
        if not tpl or not tpl.get("indoor"):
            continue
        indoor = [x for x in p["spots"] if weather_agent.is_indoor(x)]
        outdoor = [x for x in p["spots"] if not weather_agent.is_indoor(x)]
        if outdoor and len(outdoor) > 1:
            keep = outdoor[0]
            dropped = outdoor[1:]
            for x in dropped:
                p["spots"].remove(x)
                used.discard(x["id"])
            fixes.append("第 %d 天%s（降雨 %d%%），减少室外活动，去掉「%s」"
                         % (p["day"], tpl["text"], tpl["rain"],
                            "」「".join(x["name"] for x in dropped)))

    # 补足：每天至少 2 个景点（下雨天只补室内的，宁可不补也不违背天气约束）
    for p in picked:
        tpl = p.get("weather") or {}
        pool = [x for x in cand if x["type"] == "attraction" and x["id"] not in used]
        if tpl.get("indoor"):
            pool = [x for x in pool if weather_agent.is_indoor(x)]
        pool.sort(key=lambda x: _score(x, need), reverse=True)
        while len(p["spots"]) < 2 and pool:
            extra = pool.pop(0)
            p["spots"].append(extra)
            used.add(extra["id"])
            why = "景点不足" if not tpl.get("indoor") else "下雨，补一个室内点"
            fixes.append("第 %d 天%s，补了「%s」" % (p["day"], why, extra["name"]))

    # 距离：同一天相邻两点太远就换近的，换不到就删
    for p in picked:
        i = 0
        while i < len(p["spots"]) - 1:
            a, b = p["spots"][i], p["spots"][i + 1]
            km = _km(a, b)
            if km <= MAX_HOP_KM:
                i += 1
                continue
            pool = [x for x in cand if x["type"] == "attraction" and x["id"] not in used]
            pool.sort(key=lambda x: _km(a, x))
            if pool and _km(a, pool[0]) < km:
                new = pool[0]
                fixes.append("「%s」到「%s」约 %.0f 公里，把后者换成「%s」"
                             % (a["name"], b["name"], km, new["name"]))
                p["spots"][i + 1] = new
                used.add(new["id"])
            else:
                fixes.append("「%s」到「%s」约 %.0f 公里且无更近替代，删掉后者"
                             % (a["name"], b["name"], km))
                p["spots"].pop(i + 1)
            i += 1

    # 预算：超支先砍最贵的收费景点，再降住宿
    limit = need.get("budget_limit")
    try:
        limit = int(limit) if limit not in (None, "", "low") else None
    except (TypeError, ValueError):
        limit = None

    def total_of(ps):
        s = 0.0
        for p in ps:
            for x in p["spots"] + p["foods"] + ([p["hotel"]] if p["hotel"] else []):
                s += float(x["price"] or 0)
        return s

    if limit:
        guard = 0
        while total_of(picked) > limit and guard < 6:
            paid = [(p["day"], x) for p in picked for x in p["spots"] if float(x["price"] or 0) > 0]
            if paid:
                day_i, worst = max(paid, key=lambda t: float(t[1]["price"] or 0))
                for p in picked:
                    if p["day"] == day_i and worst in p["spots"]:
                        p["spots"].remove(worst)
                        fixes.append("超出预算，去掉最贵的「%s」（¥%d）"
                                     % (worst["name"], int(worst["price"])))
                        break
            else:
                hotels = [p for p in picked if p["hotel"]]
                if not hotels:
                    break
                p0 = hotels[0]
                old = p0["hotel"]
                old_price = float(old.get("price") or 0)
                # 只能往更便宜的方向走，否则会来回换、死循环
                cheaper = [x for x in cand if x["type"] == "hotel"
                           and x["id"] not in used
                           and float(x["price"] or 0) < old_price]
                cheaper.sort(key=lambda x: float(x["price"] or 0))
                if not cheaper:
                    break
                used.discard(old["id"])
                p0["hotel"] = cheaper[0]
                used.add(cheaper[0]["id"])
                fixes.append("超出预算，住宿从「%s」降为「%s」" % (old["name"], cheaper[0]["name"]))
            guard += 1

    # 生成条目并排时间
    plan = []
    for p in picked:
        items, t = [], DAY_START
        for idx, poi in enumerate(p["spots"]):
            t = max(t, earliest(poi))
            items.append(_entry(poi, t))
            t += int(poi["stay_min"] or 60) + BUFFER_MIN
        if p["foods"]:
            food = p["foods"][0]
            lunch = max(t, LUNCH_T if t < 13 * 60 else DINNER_T)
            items.append(_entry(food, lunch))
            t = lunch + int(food["stay_min"] or 60)
        if len(p["foods"]) > 1:
            food2 = p["foods"][1]
            dinner = max(t, DINNER_T)
            if dinner <= 20 * 60:
                items.append(_entry(food2, dinner))
                t = dinner + int(food2["stay_min"] or 60)
        if p["hotel"] and p["day"] < days:
            items.append({
                "type": "hotel", "name": p["hotel"]["name"], "start": _fmt(max(t, HOTEL_T)),
                "duration_min": 0, "cost": p["hotel"]["price"], "poi_id": p["hotel"]["id"],
                "area": p["hotel"]["area"], "tags": p["hotel"]["tags"], "note": "住宿",
            })
        plan.append({"day": p["day"],
                     "theme": (p["spots"][0]["area"] if p["spots"] else "市区"),
                     "items": items})

    # 用最终条目重算一次总额，超了要如实说
    if limit:
        real = sum(float(i.get("cost") or 0) for d in plan for i in d["items"])
        if real > limit:
            fixes.append("预算 ¥%d 仍压不到 ¥%d 以内（约 ¥%d），建议加预算或减少天数"
                         % (int(real), limit, int(real)))

    return plan, {"source": "llm+guard", "note": note, "fixes": fixes}
