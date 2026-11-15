# -*- coding: utf-8 -*-
"""③ 行程校验：全部用规则，不调模型。"""
import re
from datetime import date, timedelta


def to_min(hhmm: str) -> int:
    try:
        h, m = str(hhmm).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def _hours(text):
    """'10:00-21:00' → (600, 1260)；全天/无法解析 → None。"""
    text = (text or "").strip()
    if not text or "全天" in text:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})\s*[-—~]\s*(\d{1,2}):(\d{2})", text)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2)), int(m.group(3)) * 60 + int(m.group(4))


def _by_day(items):
    days = {}
    for it in items:
        days.setdefault(it["day_index"], []).append(it)
    for d in days:
        days[d].sort(key=lambda x: x["seq"])
    return days


def validate(items, trip=None, need=None) -> list:
    """返回冲突列表：[{level, day, item_id, reason, fix}]"""
    out = []
    days = _by_day(items)

    for day, lst in days.items():
        # 1. 时间重叠
        for i in range(len(lst) - 1):
            cur, nxt = lst[i], lst[i + 1]
            end = to_min(cur["start_time"]) + int(cur["duration_min"] or 0)
            if end > to_min(nxt["start_time"]):
                out.append({
                    "level": "high", "day": day, "item_id": nxt["id"],
                    "reason": f"第 {day} 天 {cur['name']} 与 {nxt['name']} 时间重叠",
                    "fix": f"把 {nxt['name']} 顺延 {end - to_min(nxt['start_time'])} 分钟",
                })
        # 2. 排得太晚
        if lst:
            last = lst[-1]
            end = to_min(last["start_time"]) + int(last["duration_min"] or 0)
            if end > 21 * 60 + 30:
                out.append({
                    "level": "medium", "day": day, "item_id": last["id"],
                    "reason": f"第 {day} 天排到 {end // 60}:{end % 60:02d}，偏晚",
                    "fix": "去掉最后一个点，或把它挪到第二天",
                })
        # 3. 闭馆日
        if trip and trip.get("start_date"):
            try:
                d0 = date.fromisoformat(trip["start_date"])
                weekday = (d0 + timedelta(days=day - 1)).weekday()
                if weekday == 0:                     # 周一
                    for it in lst:
                        if "周一闭馆" in (it.get("open_hours") or ""):
                            out.append({
                                "level": "high", "day": day, "item_id": it["id"],
                                "reason": f"{it['name']} 周一闭馆",
                                "fix": "换到其他日期，或改去附近的同类地点",
                            })
            except Exception:
                pass

        # 3.5 营业时间：安排到打烊时段
        for it in lst:
            rng = _hours(it.get("open_hours"))
            if not rng:
                continue
            start, end = rng
            t = to_min(it["start_time"])
            inside = (start <= t <= end) if end >= start else (t >= start or t <= end)
            if not inside:
                out.append({
                    "level": "medium", "day": day, "item_id": it["id"],
                    "reason": f"{it['name']} 营业时间 {it['open_hours']}，{it['start_time']} 不在营业时段",
                    "fix": "调整到营业时间内，或换一家同类店",
                })

    # 4. 预算
    if trip and trip.get("budget_limit"):
        total = sum(float(it.get("cost") or 0) for it in items)
        if total > float(trip["budget_limit"]):
            out.append({
                "level": "medium", "day": 0, "item_id": None,
                "reason": f"预计花费 {total:.0f} 元，超出预算 {total - float(trip['budget_limit']):.0f} 元",
                "fix": "去掉 1 个收费景点，或换更便宜的餐馆",
            })

    # 5. 避雷标签
    avoid = set((need or {}).get("avoid") or [])
    if avoid:
        for it in items:
            tags = set((it.get("tags") or "").split(";"))
            hit = tags & avoid
            if hit:
                out.append({
                    "level": "medium", "day": it["day_index"], "item_id": it["id"],
                    "reason": f"{it['name']} 命中你不想去的特点：{'、'.join(hit)}",
                    "fix": "点“换一个”挑同类替代",
                })

    # 6. 排队久
    for it in items:
        if "排队久" in (it.get("tags") or ""):
            out.append({
                "level": "low", "day": it["day_index"], "item_id": it["id"],
                "reason": f"{it['name']} 常有排队（约 30—60 分钟）",
                "fix": "错峰去，或先取号再逛附近",
            })

    out.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["level"], 3))
    return out
