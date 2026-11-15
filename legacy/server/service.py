# -*- coding: utf-8 -*-
"""业务编排：解析结果 → 行程 → 校验 → 预算 → 贴士。"""
from . import db
from .agents import budget as budget_agent
from .agents import merge as merge_agent
from .agents import parse as parse_agent
from .agents import plan as plan_agent
from .agents import tips as tips_agent
from .agents import validate as validate_agent


def create_trip(need: dict) -> int:
    city = need.get("city") or "长沙"
    days = max(1, min(int(need.get("days") or 2), 5))
    pois = db.poi_list(city) or db.poi_list()

    plan = plan_agent.plan_days({**need, "days": days}, pois)
    title = f"{city} · {days} 天行程"
    tid = db.trip_create(title, city, days, need.get("start_date"),
                         need.get("budget") if isinstance(need.get("budget"), (int, float)) else None,
                         need)
    for d in plan:
        db.items_replace_day(tid, d["day"], d["items"])
    return tid


def _enrich(items):
    """补上 POI 的营业时间，供闭馆校验使用。"""
    cache = {}
    for it in items:
        pid = it.get("poi_id")
        if pid and pid not in cache:
            cache[pid] = db.poi_by_id(pid)
        poi = cache.get(pid) or {}
        it["open_hours"] = poi.get("open_hours", "")
        it["lat"] = poi.get("lat")
        it["lng"] = poi.get("lng")
    return items


def payload(tid: int) -> dict:
    trip = db.trip_get(tid)
    if not trip:
        return None

    items = _enrich(db.items_get(tid))
    need = trip.get("need") or {}
    companions = int(need.get("companions") or 1)

    days = {}
    for it in items:
        days.setdefault(it["day_index"], []).append(it)
    day_list = []
    for d in sorted(days):
        lst = sorted(days[d], key=lambda x: x["seq"])
        area = next((x.get("area") for x in lst if x.get("area")), "")
        day_list.append({
            "day": d,
            "theme": area,
            "items": lst,
        })

    budget = budget_agent.calc(items, trip.get("budget_limit"), companions)
    conflicts = validate_agent.validate(items, trip, need)
    tips = tips_agent.make_tips(trip, items)

    return {
        "trip": trip,
        "need": need,
        "days": day_list,
        "items": items,
        "budget": budget,
        "conflicts": conflicts,
        "tips": tips,
    }


def swap_item(tid: int, item_id: int) -> bool:
    it = db.item_get(item_id)
    if not it:
        return False
    used = {x["poi_id"] for x in db.items_get(tid) if x.get("poi_id")}
    cands = [p for p in db.poi_list() if p["type"] == it["type"]
             and p["id"] not in used and p["area"] == it.get("area")]
    if not cands:
        cands = [p for p in db.poi_list() if p["type"] == it["type"] and p["id"] not in used]
    if not cands:
        return False
    p = cands[0]
    db.item_update(item_id, {
        "name": p["name"], "cost": p["price"], "poi_id": p["id"],
        "area": p["area"], "tags": p["tags"], "duration_min": p["stay_min"],
    })
    return True


def move_item(tid: int, item_id: int, direction: str) -> bool:
    """同一天内上移/下移，交换 seq。"""
    items = db.items_get(tid)
    target = next((x for x in items if x["id"] == item_id), None)
    if not target:
        return False
    same = sorted([x for x in items if x["day_index"] == target["day_index"]],
                  key=lambda x: x["seq"])
    idx = same.index(next(x for x in same if x["id"] == item_id))
    new_idx = idx - 1 if direction == "up" else idx + 1
    if not (0 <= new_idx < len(same)):
        return False
    a, b = same[idx], same[new_idx]
    db.item_update(a["id"], {"seq": b["seq"]})
    db.item_update(b["id"], {"seq": a["seq"]})
    return True


def regenerate_day(tid: int, day: int, avoid=None) -> bool:
    trip = db.trip_get(tid)
    if not trip:
        return False
    all_items = db.items_get(tid)
    others = [x for x in all_items if x["day_index"] != day]
    used = {x["poi_id"] for x in others if x.get("poi_id")}

    need = dict(trip.get("need") or {})
    need["avoid"] = list(dict.fromkeys((need.get("avoid") or []) + list(avoid or [])))
    need["days"] = 1

    pois = [p for p in (db.poi_list(trip["city"]) or db.poi_list()) if p["id"] not in used]
    plan = plan_agent.plan_days(need, pois)
    items = plan[0]["items"] if plan else []
    db.items_replace_day(tid, day, items)
    return True


def regenerate_all(tid: int, avoid=None) -> bool:
    trip = db.trip_get(tid)
    if not trip:
        return False
    need = dict(trip.get("need") or {})
    if avoid:
        need["avoid"] = list(dict.fromkeys((need.get("avoid") or []) + [avoid]))
    days = int(trip.get("days") or 2)
    pois = db.poi_list(trip["city"]) or db.poi_list()
    plan = plan_agent.plan_days(need, pois)
    for d in plan:
        db.items_replace_day(tid, d["day"], d["items"])
    return True


def parse_text(text: str) -> dict:
    return parse_agent.parse_need(text)


def save_members(tid: int, members) -> dict:
    db.members_save(tid, members)
    return merge_agent.merge(members)
