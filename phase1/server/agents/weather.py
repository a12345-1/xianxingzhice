# -*- coding: utf-8 -*-
"""天气模板：每次规划按天随机抽一个，用来约束路线并生成注意事项。

刻意不含下雪与极端天气（大风/台风/暴雨预警），只保留常见出行场景。
模板字段：
  key      模板标识
  text     天气描述
  rain     降雨概率（%）
  indoor   是否建议减少室外活动
  outfit   穿衣建议
  actions  出行动作（带伞 / 防晒 / 防风…）
  note     写进贴士的一句话
"""
import random
from datetime import date, timedelta

TEMPLATES = [
    {"key": "sunny", "text": "晴", "rain": 5, "indoor": False,
     "outfit": "短袖 + 薄外套", "actions": ["防晒", "墨镜"],
     "note": "天气晴，室外行程可以放心排，注意防晒补水"},
    {"key": "cloudy", "text": "多云", "rain": 15, "indoor": False,
     "outfit": "长袖 + 外套", "actions": ["薄外套"],
     "note": "多云，体感舒适，适合长时间在户外走"},
    {"key": "overcast", "text": "阴", "rain": 30, "indoor": False,
     "outfit": "长袖 + 外套", "actions": ["带件外套"],
     "note": "阴天光线柔和，拍照好看，但要注意保暖"},
    {"key": "drizzle", "text": "小雨", "rain": 60, "indoor": True,
     "outfit": "防水外套 + 防滑鞋", "actions": ["带伞", "防滑鞋"],
     "note": "有小雨，建议减少室外活动，伞要随身带"},
    {"key": "rain", "text": "中雨", "rain": 80, "indoor": True,
     "outfit": "防水外套 + 防滑鞋", "actions": ["带伞", "防滑鞋", "备一件干上衣"],
     "note": "有中雨，室外活动要压缩，优先室内（博物馆、艺术馆）"},
    {"key": "windy", "text": "多云有风", "rain": 20, "indoor": False,
     "outfit": "防风外套", "actions": ["防风外套"],
     "note": "风比较大，登高和骑行注意安全"},
    {"key": "hot", "text": "晴热", "rain": 5, "indoor": True,
     "outfit": "速干短袖 + 遮阳帽", "actions": ["防晒", "补水"],
     "note": "气温偏高，正午尽量安排室内，避免长时间暴晒"},
    {"key": "cool", "text": "凉爽", "rain": 20, "indoor": False,
     "outfit": "长袖 + 薄外套", "actions": ["薄外套"],
     "note": "凉爽，走路舒服，适合把室外景点排满"},
]

# 室内优先的地点特征
INDOOR_KEYS = ("博物馆", "博物院", "美术馆", "艺术馆", "纪念馆", "展览馆")


def pick(seed_text: str, day_index: int) -> dict:
    """按城市+日期+天序号确定性地抽一个模板（同一天结果稳定，不同天不同）。"""
    rnd = random.Random(f"{seed_text}-{day_index}")
    t = dict(rnd.choice(TEMPLATES))
    t["low"], t["high"] = _temps(rnd, t)
    t["source"] = "template"          # 不是真实天气接口
    return t


def _temps(rnd, tpl):
    key = tpl["key"]
    if key == "hot":
        return 27 + rnd.randint(0, 3), 33 + rnd.randint(0, 3)
    if key == "cool":
        return 8 + rnd.randint(0, 4), 17 + rnd.randint(0, 4)
    if key in ("rain", "drizzle"):
        return 12 + rnd.randint(0, 4), 18 + rnd.randint(0, 4)
    return 16 + rnd.randint(0, 5), 23 + rnd.randint(0, 5)


def is_indoor(poi: dict) -> bool:
    name = poi.get("name") or ""
    tags = poi.get("tags") or ""
    return any(k in name for k in INDOOR_KEYS) or "室内" in tags


def rain_note(day_index: int, tpl: dict) -> str:
    return f"第 {day_index} 天{tpl['text']}（降雨概率 {tpl['rain']}%），已把室外安排压到最少，伞记得带"
