# -*- coding: utf-8 -*-
"""业务编排（单人 MVP）：解析 → 生成 → 校验 → 预算 → 贴士 → 规格化输出。"""
import re
import time

from . import db, llm, spec
from .agents import command as command_agent
from .agents import parse as parse_agent
from .agents import plan as plan_agent
from .agents import tips as tips_agent
from .agents import validate as validate_agent


def _now_ms(t0):
    return int((time.perf_counter() - t0) * 1000)


def _hhmm_min(s):
    """'09:30' -> 570；解析失败返回 None。"""
    try:
        h, m = str(s).split(":")
        v = int(h) * 60 + int(m)
        return v if 0 <= v < 24 * 60 else None
    except (ValueError, AttributeError, TypeError):
        return None


def _min_hhmm(v):
    v = max(0, min(int(v), 23 * 60 + 59))
    return "%02d:%02d" % (v // 60, v % 60)


def _enrich(items):
    """补 POI 元数据（营业时间、坐标、标签），供校验与规格化使用。"""
    cache = {}
    for it in items:
        pid = it.get("poi_id")
        if pid and pid not in cache:
            cache[pid] = db.poi_by_id(pid)
        poi = cache.get(pid) or {}
        it["open_hours"] = poi.get("open_hours", "")
        it["lat"] = poi.get("lat")
        it["lng"] = poi.get("lng")
        it["need_booking"] = poi.get("need_booking", 0)
        if not it.get("tags"):
            it["tags"] = poi.get("tags", "")
    return items


# ---------------------------------------------------------------- 自动调整
WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _hours(text):
    """解析营业时间区间。

    高德返回的时间串经常带季节/日期段（如“03-16至04-30 周一至周日 08:00-19:00”）
    或分段营业（“11:00-14:00,16:00-06:00”），这类一律返回 None，表示“不做时间校验”，
    避免把正常安排误判成超时。
    """
    import re

    t = text or ""
    t = re.sub(r"周一至周日|周一至周五|周一至周六|每日", "", t)
    t = re.sub(r"\d{4}-\d{2}-\d{2}至\d{4}-\d{2}-\d{2}", "", t)
    t = re.sub(r"\d{2}-\d{2}至\d{2}-\d{2}", "", t)
    if "至" in t or "," in t or "，" in t or ";" in t or "；" in t:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})\s*[-—~]\s*(\d{1,2}):(\d{2})", t)
    if not m:
        return None
    start = int(m.group(1)) * 60 + int(m.group(2))
    end = int(m.group(3)) * 60 + int(m.group(4))
    if start == 0 and end >= 24 * 60:          # 00:00-24:00 = 全天
        return None
    return start, end


def auto_adjust(tid):
    """闭馆 / 不在营业时间的条目自动处理，并记录原因。

    规则（按优先级）：
    1. 不是最后一天 → 顺延到次日末尾；
    2. 是最后一天 → 就近换成同区域、当天开放的同类地点；
    3. 换不到 → 删掉并记录。
    返回 [{day_index, to_day, item_id, name, message}]
    """
    from datetime import date

    trip = db.trip_get(tid)
    start = trip.get("start_date")
    days = int(trip.get("days") or 1)
    if not start:
        return []
    base = date.fromisoformat(start)
    out = []

    items = db.items_get(tid)
    for it in items:
        poi = db.poi_by_id(it["poi_id"]) if it.get("poi_id") else None
        if not poi:
            continue
        # 只校验景点：餐厅营业时间是分段/夜宵制，酒店是 0 时长，
        # 对这两类做“超时顺延”会得到很怪的结果。
        if it["type"] != "attraction":
            continue
        weekday = (base.weekday() + it["day_index"] - 1) % 7
        doc_index = (weekday + 1) % 7                      # 0=周日
        closed = "周一闭馆" in (poi.get("open_hours") or "") and doc_index == 1
        rng = _hours(poi.get("open_hours") or "")
        start_min = _hhmm(it["start_time"])
        outside = bool(rng) and not (rng[0] <= start_min <= rng[1])
        if not (closed or outside):
            continue

        reason = "闭馆" if closed else "不在营业时间"

        # 1) 顺延到次日
        if it["day_index"] < days:
            next_day = it["day_index"] + 1
            rows = sorted([x for x in db.items_get(tid) if x["day_index"] == next_day],
                          key=lambda y: y["seq"])
            last_end = 9 * 60
            if rows:
                last_end = max(_hhmm(x["start_time"]) + int(x["duration_min"] or 0) for x in rows)
            new_start = max(9 * 60, last_end + 30)
            db.item_update(it["id"], {"day_index": next_day, "seq": len(rows) + 1,
                                      "start_time": f"{new_start // 60:02d}:{new_start % 60:02d}"})
            _renumber(tid, it["day_index"])
            _renumber(tid, next_day)
            out.append({
                "day_index": it["day_index"], "to_day": next_day, "item_id": f"it_{it['id']}",
                "name": it["name"],
                "message": f"{it['name']}{reason}，已顺延到第 {next_day} 天 "
                           f"{new_start // 60:02d}:{new_start % 60:02d}",
            })
            continue

        # 2) 最后一天：换一个当天开放的同类地点
        used = {x["poi_id"] for x in db.items_get(tid) if x.get("poi_id")}
        alt = _find_alt(trip["city"], it, doc_index, used)
        if alt:
            db.item_update(it["id"], {
                "name": alt["name"], "cost": alt["price"], "poi_id": alt["id"],
                "area": alt["area"], "tags": alt["tags"], "duration_min": alt["stay_min"],
            })
            out.append({
                "day_index": it["day_index"], "to_day": it["day_index"], "item_id": f"it_{it['id']}",
                "name": alt["name"],
                "message": f"{it['name']}{reason}，已换成 {alt['name']}",
            })
        else:
            db.item_delete(it["id"])
            _renumber(tid, it["day_index"])
            out.append({
                "day_index": it["day_index"], "to_day": None, "item_id": f"it_{it['id']}",
                "name": it["name"],
                "message": f"{it['name']}{reason}，当天没有可替换的地点，已移除",
            })
    return out


def _find_alt(city, it, doc_index, used):
    """同区域、同类型、当天开放且没用过的地点。"""
    for p in db.poi_list(city):
        if p["id"] in used or p["type"] != it["type"]:
            continue
        if "周一闭馆" in (p.get("open_hours") or "") and doc_index == 1:
            continue
        if it.get("area") and p["area"] != it["area"]:
            continue
        return p
    return None


def parse_text(text):
    return parse_agent.parse_need(text)


class NoCityData(Exception):
    """目的地没有 POI 数据，不允许静默回退到别的城市。"""

    def __init__(self, city, cities):
        self.city = city
        self.cities = cities
        super().__init__(f"no data for {city}")


class UnknownCity(Exception):
    """输入里提到的地方不认识（例如“霍格沃茨”），绝不生成假行程。"""

    def __init__(self, raw_text=""):
        self.raw_text = raw_text
        super().__init__("unknown city")


# 最低可行成本（元）：住宿/晚 + 两顿/天 + 门票交通杂项/天
MIN_HOTEL = 130
MIN_MEAL = 45
MIN_MISC = 40


def min_cost(days: int) -> int:
    days = max(1, int(days))
    nights = max(days - 1, 0)
    return int(MIN_HOTEL * nights + MIN_MEAL * 2 * days + MIN_MISC * days)


class BudgetTooLow(Exception):
    """预算低于最低可行线，返回可执行的建议而不是硬生成。"""

    def __init__(self, city, days, budget, need_min):
        self.city = city
        self.days = days
        self.budget = budget
        self.need_min = need_min
        super().__init__("budget too low")


def _check_budget(city, days, budget, force=False):
    """预算明显不够时提前拦下（TC-04），force=True 可强行生成。"""
    if force:
        return
    try:
        budget = int(float(budget))
    except (TypeError, ValueError):
        return                      # 没给预算 / “不贵”这种模糊值，交给排程正常判断
    if budget <= 0:
        return
    need_min = min_cost(days)
    if budget < need_min:
        raise BudgetTooLow(city, days, budget, need_min)


def create_trip(need, raw_text="", budget_limit=None):
    city = need.get("city") or "长沙"
    if city == "__unknown__":
        raise UnknownCity(raw_text)
    days = max(1, min(int(need.get("days") or 2), 15))
    pois = db.poi_list(city)
    if not pois:
        # 没数据时也要先判断预算是否离谱，给的建议才具体
        _check_budget(city, days, budget_limit or need.get("budget"), force=need.get("force"))
        raise NoCityData(city, db.cities())
    _check_budget(city, days, budget_limit or need.get("budget"), force=need.get("force"))

    limit = budget_limit if budget_limit else need.get("budget")
    if isinstance(limit, str):
        limit = None
    people = int(need.get("people") or need.get("companions") or 1)

    # 让把关逻辑知道预算上限（模型提议后代码要用它裁剪）
    plan, plan_info = plan_agent.plan_days(
        {**need, "days": days, "budget_limit": limit}, pois)

    tid = db.trip_create(f"{city} · {days} 天行程", city, days, need.get("start_date"),
                         limit, need, raw_text=raw_text, people=people)
    for d in plan:
        db.items_replace_day(tid, d["day"], d["items"])
    db.trip_set_plan_info(tid, plan_info)
    return tid


# ---------------------------------------------------------------- 生成
def generate(raw_text, day_count, budget_limit, city=None, force=False,
             days_from_ui=False, start_date=None, people=None):
    """跑完整条链，返回（规格化响应, 各智能体耗时）。"""
    timings = []

    t = time.perf_counter()
    need = parse_agent.parse_need(raw_text)
    # 天数：用户没动过步进器时，以文本里写明的天数为准（「5天4晚」不该被界面默认值吃掉）
    if days_from_ui:
        need["days"] = int(day_count)
    else:
        explicit = parse_agent._explicit(raw_text)
        need["days"] = int(explicit.get("days") or day_count)
    if city:                                  # 反问流程里用户选的，优先于文本解析
        need["city"] = city
        need["city_unknown"] = False
        need["city_explicit"] = True
    if budget_limit:
        need["budget"] = budget_limit
    if start_date:
        need["start_date"] = start_date
    if people:
        need["companions"] = int(people)
        need["people"] = int(people)
    need["force"] = bool(force)
    timings.append({"name": "需求解析", "status": "ok", "ms": _now_ms(t)})

    t = time.perf_counter()
    tid = create_trip(need, raw_text, budget_limit)
    timings.append({"name": "路线生成", "status": "ok", "ms": _now_ms(t)})

    t = time.perf_counter()
    adjusts = auto_adjust(tid)
    db.trip_set_adjustments(tid, adjusts)
    data = spec_payload(tid, with_note=True)
    timings.append({"name": "时间校验", "status": "ok", "ms": _now_ms(t)})

    t = time.perf_counter()
    _ = data["budget"]
    timings.append({"name": "预算核算", "status": "ok", "ms": _now_ms(t)})

    t = time.perf_counter()
    _ = data["tips"]
    data["meta"]["model"] = "deepseek-chat" if need.get("source") == "llm" else "local-rules"
    data["meta"]["parse_source"] = need.get("source", "local")
    timings.append({"name": "贴士生成", "status": "ok", "ms": _now_ms(t)})

    return data, timings


def spec_payload(tid, with_note=False):
    trip = db.trip_get(tid)
    if not trip:
        return None
    items = _enrich(db.items_get(tid))
    need = trip.get("need") or {}

    # 数据口径：这个城市到底收录了多少地点，空白天要据此解释
    pool = db.poi_list(trip["city"])
    trip = dict(trip)
    trip["data_note"] = (
        f"{trip['city']} 目前收录 {len(pool)} 个地点"
        f"（景点 {sum(1 for p in pool if p['type'] == 'attraction')}"
        f" / 餐饮 {sum(1 for p in pool if p['type'] == 'food')}"
        f" / 住宿 {sum(1 for p in pool if p['type'] == 'hotel')}）"
    )
    trip["plan_info"] = db.trip_get_plan_info(tid)

    conflicts = validate_agent.validate(items, trip, need)
    tips = tips_agent.make_tips(trip, items)
    if with_note:
        note = tips_agent.polish(trip.get("city"), [
            {"day": d["day_index"], "items": [i["name"] for i in d["items"]]}
            for d in _group_days(items)
        ], tips)
        if note:
            tips["note"] = note
            tips["note_source"] = "model"
            db.trip_set_tips_note(tid, note)
    elif trip.get("tips_note"):                 # 页面刷新时用上次生成的结果，不再调模型
        tips["note"] = trip["tips_note"]
        tips["note_source"] = "model"
    data = spec.build(trip, need, items, conflicts, tips)
    data["trip_id"] = trip.get("code") or data["trip_id"]
    return data


def _group_days(items):
    out = {}
    for it in items:
        out.setdefault(it["day_index"], []).append(it)
    return [{"day_index": k, "items": v} for k, v in sorted(out.items())]


def spec_item(tid, item_id):
    data = spec_payload(tid)
    for d in data["days"]:
        for it in d["items"]:
            if it["item_id"] == item_id:
                return it
    return None


# ---------------------------------------------------------------- item_id 解析
def _locate(tid, item_id):
    """item_id 形如 it_42，直接对应 items 表主键，增删后不漂移。"""
    try:
        return int(str(item_id).split("_")[1])
    except Exception:
        return None


def _db_item(tid, item_id):
    iid = _locate(tid, item_id)
    if not iid:
        return None
    it = db.item_get(iid)
    return it if it and it["trip_id"] == tid else None


def _renumber(tid, day):
    rows = [x for x in db.items_get(tid) if x["day_index"] == day]
    for i, x in enumerate(sorted(rows, key=lambda y: y["seq"]), start=1):
        db.item_update(x["id"], {"seq": i})


# 重排后的时间基准：与排程器一致的粗规则（30 分钟机动、午饭不早于 11:45、晚饭不早于 17:30）
DAY_START = 9 * 60
BUFFER_MIN = 30
LUNCH_MIN = 11 * 60 + 45
DINNER_MIN = 17 * 60 + 30


def _retime(tid, day):
    """按当天顺序重算开始时间（换顺序 / 加地点 / 删地点后都要调）。

    规则：景点和餐饮按顺序累计，餐饮不早于午饭 11:45 / 晚饭 17:30；
    住宿不参与时间链，固定排在最后一个非住宿条目之后（不早于 19:00）。
    """
    rows = sorted([x for x in db.items_get(tid) if x["day_index"] == day],
                  key=lambda y: y["seq"])
    t = DAY_START
    for it in rows:
        if it["type"] == "hotel":
            continue
        dur = int(it["duration_min"] or 0)
        if it["type"] == "food":
            t = max(t, LUNCH_MIN if t < 13 * 60 else DINNER_MIN)
        t = min(t, 23 * 60 + 30)
        db.item_update(it["id"], {"start_time": f"{t // 60:02d}:{t % 60:02d}"})
        t += dur + BUFFER_MIN

    for it in rows:
        if it["type"] == "hotel":
            ht = max(t, 19 * 60)
            ht = min(ht, 23 * 60 + 30)
            db.item_update(it["id"], {"start_time": f"{ht // 60:02d}:{ht % 60:02d}"})


def add_item(tid, day, poi_id):
    """往某天末尾加一个地点（同区域候选），并把当天时间重排。"""
    trip = db.trip_get(tid)
    poi = db.poi_by_id(poi_id)
    if not trip or not poi:
        return False
    rows = [x for x in db.items_get(tid) if x["day_index"] == day]
    if any(x.get("poi_id") == poi_id for x in rows):
        return False
    db.item_add(tid, day, {
        "type": poi["type"], "name": poi["name"], "start": "12:00",
        "duration_min": poi["stay_min"], "cost": poi["price"], "poi_id": poi["id"],
        "area": poi["area"], "tags": poi["tags"], "note": "对话新增", "source": "user",
    })
    _retime(tid, day)
    return True


# ---------------------------------------------------------------- 编辑
def apply_patch(tid, item_id, action, patch):
    it = _db_item(tid, item_id)
    if not it:
        return False

    if action == "delete":
        day = it["day_index"]
        db.item_delete(it["id"])
        _renumber(tid, day)
        _retime(tid, day)          # 少了一个点，后面的时间往前收
        return True

    if action == "update":
        fields = {"source": "user"}
        for k in ("start_time", "duration_min", "cost", "name", "note"):
            if k in patch and patch[k] is not None:
                fields[k] = patch[k]

        # 手改时间：把后面几条一起顺延，不要改完又被重算覆盖
        if "start_time" in fields:
            old_m = _hhmm_min(it.get("start_time"))
            new_m = _hhmm_min(fields["start_time"])
            if old_m is not None and new_m is not None and new_m != old_m:
                delta = new_m - old_m
                for x in sorted([y for y in db.items_get(tid)
                                 if y["day_index"] == it["day_index"] and y["seq"] > it["seq"]],
                                key=lambda y: y["seq"]):
                    m = _hhmm_min(x.get("start_time"))
                    if m is not None:
                        db.item_update(x["id"], {"start_time": _min_hhmm(m + delta)})
        db.item_update(it["id"], fields)
        return True

    if action == "reorder":
        target = int(patch.get("seq") or 1)
        day_rows = sorted([x for x in db.items_get(tid) if x["day_index"] == it["day_index"]],
                          key=lambda y: y["seq"])
        target = max(1, min(target, len(day_rows)))
        cur = next(i for i, x in enumerate(day_rows) if x["id"] == it["id"])
        if target - 1 != cur:
            day_rows.insert(target - 1, day_rows.pop(cur))
        for i, x in enumerate(day_rows, start=1):
            db.item_update(x["id"], {"seq": i})
        _retime(tid, it["day_index"])      # 顺序变了，时间必须重算
        return {"ok": True, "moved": target - 1 != cur}

    if action == "insert":
        new = patch.get("item") or {}
        name = new.get("name") or "新增地点"
        db.items_replace_day(tid, it["day_index"], [{
            "type": new.get("type", "attraction"), "name": name,
            "start": new.get("start_time", "12:00"),
            "duration_min": int(new.get("duration_min") or 60),
            "cost": float(new.get("cost") or 0), "poi_id": None,
            "area": it.get("area"), "tags": "", "note": "",
        }])
        return True

    return False


def day_candidates(tid, day, type_="attraction", limit=6):
    """加一个地点：按天给出同城、指定类型、当天还没用过的候选（同区域优先）。"""
    trip = db.trip_get(tid)
    if not trip:
        return []
    day_items = [x for x in db.items_get(tid) if x["day_index"] == int(day)]
    used = {x["poi_id"] for x in db.items_get(tid) if x.get("poi_id")}
    area = day_items[0].get("area") if day_items else ""

    poolid = [p for p in db.poi_list(trip["city"]) if p["id"] not in used]
    if type_:
        want = [p for p in poolid if p["type"] == type_]
        if want:
            poolid = want
    poolid.sort(key=lambda p: (0 if p["area"] == area else 1, p["name"]))
    return [{
        "poi_id": p["id"], "name": p["name"], "type": p["type"], "area": p["area"],
        "price": int(float(p["price"] or 0)), "stay_min": p["stay_min"],
        "open_hours": p.get("open_hours"),
    } for p in poolid[:limit]]


def candidates(tid, item_id, limit=4):
    """换一个：同城市、同类型、同区域优先，排除已用。"""
    it = _db_item(tid, item_id)
    trip = db.trip_get(tid)
    if not it or not trip:
        return []
    used = {x["poi_id"] for x in db.items_get(tid) if x.get("poi_id")}
    pool = [p for p in db.poi_list(trip["city"])
            if p["id"] not in used and p["type"] == it["type"]]
    pool.sort(key=lambda p: (0 if p["area"] == (it.get("area") or "") else 1, p["name"]))
    return [{
        "poi_id": p["id"], "name": p["name"], "area": p["area"],
        "price": int(float(p["price"] or 0)), "stay_min": p["stay_min"],
        "open_hours": p.get("open_hours"),
    } for p in pool[:limit]]


def replace_item(tid, item_id, poi_id):
    it = _db_item(tid, item_id)
    if not it:
        return None
    poi = db.poi_by_id(poi_id)
    if not poi:
        return None
    db.item_update(it["id"], {
        "name": poi["name"], "poi_id": poi["id"], "cost": poi["price"],
        "duration_min": poi["stay_min"], "area": poi["area"], "tags": poi["tags"],
        "source": "user",
    })
    return {"ok": True, "action": "replace", "message": f"已换成「{poi['name']}」"}


# ---------------------------------------------------------------- 详情
def item_detail(tid, item_id):
    it = _db_item(tid, item_id)
    if not it:
        return None
    poi = db.poi_by_id(it["poi_id"]) if it.get("poi_id") else {}
    reviews = db.poi_reviews(it["poi_id"]) if it.get("poi_id") else []
    return {
        "item_id": item_id,
        "name": it["name"],
        "type": it["type"],
        "area": it.get("area"),
        "start_time": it["start_time"],
        "duration_min": it["duration_min"],
        "cost": int(float(it.get("cost") or 0)),
        "open_hours": (poi or {}).get("open_hours"),
        "intro": (poi or {}).get("intro") or "暂无简介（示例数据）",
        "rating": (poi or {}).get("rating"),
        "address": (poi or {}).get("address") or it.get("area") or "",
        "lat": (poi or {}).get("lat"),
        "lng": (poi or {}).get("lng"),
        "reviews": reviews,
        "reviews_source": "示例评价（知识库）",
    }


# ---------------------------------------------------------------- 突发重规划
def _hhmm(s):
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def reroute(tid, mode, item_id=None, extra_min=60):
    trip = db.trip_get(tid)
    items = db.items_get(tid)
    if not items:
        return False

    if item_id:
        it = _db_item(tid, item_id)
        day = it["day_index"] if it else 1
        start_seq = it["seq"] if it else 1
    else:
        day, start_seq = 1, 1

    day_rows = sorted([x for x in items if x["day_index"] == day], key=lambda y: y["seq"])

    if mode == "rain":
        kept = [x for x in day_rows if x["seq"] <= start_seq]
        rest = [x for x in day_rows if x["seq"] > start_seq]
        for x in rest:
            db.item_delete(x["id"])
        if rest:
            db.items_replace_day(tid, day, [{
                "type": "attraction", "name": "就近避雨：附近商场 / 咖啡馆", "start": "15:00",
                "duration_min": 60, "cost": 30, "poi_id": None,
                "area": (kept[-1].get("area") if kept else ""), "tags": "室内", "note": "雨天备选",
            }])
            rows = sorted([x for x in db.items_get(tid) if x["day_index"] == day],
                          key=lambda y: y["seq"])
            for i, x in enumerate(rows, start=1):
                db.item_update(x["id"], {"seq": i})
        _renumber(tid, day)
        return True

    if mode == "late":
        for x in day_rows:
            if x["seq"] <= start_seq:
                continue
            start_min = _hhmm(x["start_time"]) + extra_min
            if start_min > 21 * 60 + 30:
                db.item_delete(x["id"])
            else:
                db.item_update(x["id"], {"start_time": f"{start_min // 60:02d}:{start_min % 60:02d}"})
        _renumber(tid, day)
        return True

    return False


# ---------------------------------------------------------------- 多轮补槽
SLOT_QUESTIONS = {
    "city": {
        "question": "请问想去哪个城市？",
        "hint": "直接选一个，或在输入框里写明城市",
    },
    "days": {
        "question": "请问打算玩几天？",
        "hint": "1—15 天，周末一般 2 天",
    },
    "people": {
        "question": "请问一共几个人去？",
        "hint": "1—10 人，门票餐饮按人数算、住宿按房间算",
    },
    "budget": {
        "question": "请问您的预算大概是多少？（可以留空表示不限）",
        "hint": "含吃住行的打包总预算，单位元",
    },
}


def clarify(raw_text, answers=None, known=None):
    """输入检测 → 缺什么补什么（TC-06 的反问三连）。

    known 是前端已经填好的字段（天数输入框、预算输入框），有值就不再问。
    """
    answers = answers or {}
    known = known or {}
    text = (raw_text or "").strip()
    need = parse_agent.parse_need(text)
    need.update({k: v for k, v in answers.items() if v not in (None, "", [])})

    missing, questions = [], []

    def ask(slot, extra=None):
        missing.append(slot)
        q = dict(SLOT_QUESTIONS[slot], slot=slot)
        if extra:
            q["message"] = extra
        questions.append(q)

    # 人数：文本没写、用户也没填，就要问
    if not known.get("people") and not answers.get("people"):
        ppl = need.get("companions") or 0
        m_ppl = re.search(r"[0-9一二三四五六七八九十两]\s*个?人|独自|一个人|情侣|闺蜜|一家三口|我和", text)
        if not m_ppl and int(ppl) <= 1:
            ask("people", "从输入里没看出几个人去")

    # 城市
    city = need.get("city")
    if need.get("city_unknown"):
        token = ""
        m = re.search(r"去\s*([\u4e00-\u9fff]{2,5})", text) or \
            re.search(r"([\u4e00-\u9fff]{2,6}?)(?=\d?\s*[天日])", text)
        if m and parse_agent._looks_like_place(m.group(1)):
            token = m.group(1)
        ask("city", f"「{token}」我这边暂时没有景点数据" if token else "没认出目的地城市")
    elif not need.get("city_explicit") and not known.get("city") and not answers.get("city"):
        ask("city", "从输入里没看出目的地")

    # 天数：输入框有值就不问
    if not known.get("days") and not re.search(r"[0-9一二两三四五六七八九十]\s*[天日]", text):
        ask("days")

    # 预算：输入框有值、文本里有数字、或明确说“不限”，就不问
    if not known.get("budget") and need.get("budget") is None \
            and not any(w in text for w in ("不限", "随意", "看着来", "没预算")):
        ask("budget")

    return {
        "need": need,
        "missing": missing,
        "questions": questions,
        "ready": not missing,
        "supported_cities": db.cities(),
    }


# ---------------------------------------------------------------- 一句话改行程
class NoModel(Exception):
    """没配模型 Key，指令理解用不了。"""


def _find_item(tid, name, day_index=None):
    rows = db.items_get(tid)
    if day_index:
        rows = [x for x in rows if x["day_index"] == int(day_index)]
    for x in rows:
        if x["name"] == name:
            return x
    for x in rows:                                  # 退一步：包含匹配
        if name and (name in x["name"] or x["name"] in name):
            return x
    return None


def _find_poi(city, name):
    if not name:
        return None
    pool = db.poi_list(city)
    for p in pool:
        if p["name"] == name:
            return p
    for p in pool:
        if name in p["name"] or p["name"] in name:
            return p
    return None


def apply_command(tid, text):
    """模型理解指令 → 代码执行。返回 {ok, action, message}。"""
    if not llm.available():
        raise NoModel()

    trip = db.trip_get(tid)
    data = spec_payload(tid)
    act = command_agent.parse(text, trip, data["days"])
    if not act:
        return {"ok": False, "action": None, "message": "这句没听懂，换个说法试试"}

    action = act.get("action")
    msg = (act.get("message") or "").strip()
    target = (act.get("target") or "").strip()
    item = _find_item(tid, target, act.get("day_index"))

    if action == "info" or not item:
        return {"ok": False, "action": action,
                "message": msg or f"没在行程里找到「{target}」，可以手动改"}

    if action == "delete":
        db.item_delete(item["id"])
        _renumber(tid, item["day_index"])
        return {"ok": True, "action": "delete",
                "message": msg or f"已删掉「{item['name']}」"}

    if action == "move":
        start = act.get("start_time") or ""
        if not re.fullmatch(r"\d{1,2}:\d{2}", start):
            return {"ok": False, "action": "move", "message": "没给具体时间，可以手动改"}
        db.item_update(item["id"], {"start_time": start})
        return {"ok": True, "action": "move",
                "message": msg or f"已把「{item['name']}」挪到 {start}"}

    if action in ("replace", "insert"):
        replacement = (act.get("replacement") or "").strip()
        poi = _find_poi(trip["city"], replacement)
        if not poi:
            return {"ok": False, "action": action,
                    "message": f"资料库里没有「{replacement}」，可以手动改"}
        if action == "replace":
            db.item_update(item["id"], {
                "name": poi["name"], "poi_id": poi["id"], "cost": poi["price"],
                "duration_min": poi["stay_min"], "area": poi["area"], "tags": poi["tags"],
            })
            return {"ok": True, "action": "replace",
                    "message": msg or f"已把「{item['name']}」换成「{poi['name']}」"}
        rows = [x for x in db.items_get(tid) if x["day_index"] == item["day_index"]]
        db.item_add(tid, item["day_index"], {
            "type": poi["type"], "name": poi["name"], "start": "15:00",
            "duration_min": poi["stay_min"], "cost": poi["price"], "poi_id": poi["id"],
            "area": poi["area"], "tags": poi["tags"], "note": "对话新增",
        })
        return {"ok": True, "action": "insert",
                "message": msg or f"已加上「{poi['name']}」"}

    return {"ok": False, "action": action,
            "message": msg or f"暂不支持「{action}」，可以手动改"}
