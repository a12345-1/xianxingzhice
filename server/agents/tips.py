# -*- coding: utf-8 -*-
"""⑥ 出行贴士：天气 + 行程标签 → 模板化建议（不烧模型）。"""
from datetime import date

# 示例气候（未接天气接口时使用）：月份 -> (天气, 最低温, 最高温, 降雨概率%)
CLIMATE = {
    1: ("多云", 2, 9, 35), 2: ("小雨", 4, 11, 45), 3: ("阴", 8, 16, 50),
    4: ("多云", 14, 22, 45), 5: ("阵雨", 19, 27, 55), 6: ("雨", 23, 30, 60),
    7: ("晴", 27, 35, 35), 8: ("晴", 27, 35, 30), 9: ("多云", 22, 30, 35),
    10: ("晴", 16, 24, 30), 11: ("阴", 10, 18, 40), 12: ("多云", 4, 11, 35),
}


def weather_of(month: int) -> dict:
    text, low, high, rain = CLIMATE.get(month, ("多云", 15, 24, 35))
    return {"text": text, "low": low, "high": high, "rain": rain}


def make_tips(trip: dict, items: list) -> dict:
    start = trip.get("start_date")
    try:
        month = date.fromisoformat(start).month if start else date.today().month
    except ValueError:
        month = date.today().month

    w = weather_of(month)
    tags = set()
    for it in items:
        tags |= set((it.get("tags") or "").split(";"))
        if "住宿" in (it.get("tags") or ""):
            tags.add("过夜")

    clothing = f"{w['low']}—{w['high']}℃，{'短袖 + 薄外套' if w['high'] >= 26 else '长袖 + 外套' if w['high'] >= 18 else '毛衣 + 厚外套'}"
    tips = {
        "weather": w,
        "clothing": clothing,
        "packing": ["身份证", "充电宝", "纸巾湿巾", "常用药"],
        "pitfalls": [],
        "updated": f"第 {month} 月参考气候（示例数据，出行前请再看预报）",
    }

    if w["rain"] >= 45:
        tips["packing"].append("折叠伞")
        tips["pitfalls"].append("降雨概率较高，室内景点优先，户外点留出机动时间")
    if w["high"] >= 30:
        tips["packing"] += ["防晒霜", "遮阳帽"]
        tips["pitfalls"].append("正午 12:00—14:00 尽量安排室内（博物馆/商场）")
    if "爬山" in tags:
        tips["packing"].append("运动鞋")
        tips["pitfalls"].append("有爬山安排，穿防滑鞋，带足水")
    if "排队久" in tags:
        tips["pitfalls"].append("热门店排队久，建议 11:00 前到或先取号")
    if "过夜" in tags:
        tips["packing"].append("洗漱包")
        tips["pitfalls"].append("入住前确认能否寄存行李，退房时间通常 12:00")

    return tips
