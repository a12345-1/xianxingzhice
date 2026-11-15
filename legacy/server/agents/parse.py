# -*- coding: utf-8 -*-
"""① 需求解析：自然语言 → 结构化需求。

有模型就用模型，没有就用关键词规则；两条路输出同一个 schema，
前端不需要区分（need["source"] 里会标 local / llm）。
"""
import re
from datetime import date, timedelta

from .. import llm

CITIES = ["长沙", "西安", "成都", "重庆", "杭州", "武汉", "广州", "深圳", "南京",
          "苏州", "厦门", "青岛", "大理", "丽江", "北京", "上海", "张家界", "凤凰"]

INTEREST_WORDS = {
    "自然": ["自然", "风景", "公园", "山", "江", "湖", "湿地"],
    "美食": ["吃", "美食", "小吃", "夜宵", "奶茶", "湘菜"],
    "拍照": ["拍照", "出片", "打卡", "艺术", "文艺"],
    "人文": ["人文", "历史", "博物馆", "书院", "故居", "古镇"],
    "夜景": ["夜景", "夜游", "灯"],
    "购物": ["购物", "逛街", "商场", "买"],
    "亲子": ["亲子", "带娃", "小孩", "老人"],
}

AVOID_WORDS = {
    "爬山": ["爬山", "登山", "爬不动"],
    "人多": ["人多", "拥挤", "排队"],
    "早起": ["早起", "不想早"],
    "长距离步行": ["走不动", "太远", "脚"],
    "商业化": ["商业化", "网红店", "宰客"],
}

NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}

SYSTEM = """你是旅行需求解析器。用户用一句话描述出行计划，你抽取结构化字段。
规则：
1. 只输出 JSON，不要解释；
2. 没说的一律填 null，不要编造；
3. days 没说默认 2；budget 说"不贵/便宜"填 low，"随便"填 null，具体金额填数字；
4. interests 只能从 [自然,美食,拍照,人文,夜景,购物,亲子] 里选，最多 3 个；
5. avoid 只能从 [爬山,人多,早起,长距离步行,商业化] 里选；
6. pace 只能是 slow / normal / fast。
输出：{"city":"","days":2,"start_date":null,"budget":null,"pace":"normal",
"interests":[],"avoid":[],"companions":1,"confidence":0.0}"""


def parse_need(text: str, profile: dict = None) -> dict:
    text = (text or "").strip()
    out = llm.complete_json(SYSTEM, text)
    if out and isinstance(out, dict) and out.get("city") is not None:
        need = _normalize(out, text)
        need["source"] = "llm"
        return need

    need = _heuristic(text)
    need["source"] = "local"
    return need


def _normalize(d: dict, raw: str) -> dict:
    return {
        "city": d.get("city") or _city(raw),
        "days": int(d.get("days") or 2),
        "start_date": d.get("start_date") or _next_weekend(),
        "budget": d.get("budget"),
        "pace": d.get("pace") if d.get("pace") in ("slow", "normal", "fast") else "normal",
        "interests": [x for x in (d.get("interests") or []) if x in INTEREST_WORDS][:3],
        "avoid": [x for x in (d.get("avoid") or []) if x in AVOID_WORDS],
        "companions": int(d.get("companions") or 1),
        "raw": raw,
    }


def _city(text: str) -> str:
    for c in CITIES:
        if c in text:
            return c
    return "长沙"


def _next_weekend() -> str:
    today = date.today()
    delta = (5 - today.weekday()) % 7      # 下个周六
    return (today + timedelta(days=delta)).isoformat()


def _heuristic(text: str) -> dict:
    need = {
        "city": _city(text),
        "days": 2,
        "start_date": _next_weekend(),
        "budget": None,
        "pace": "normal",
        "interests": [],
        "avoid": [],
        "companions": 1,
        "raw": text,
    }

    # 天数
    m = re.search(r"([0-9]{1,2}|[一二两三四五六七])\s*天", text)
    if m:
        v = m.group(1)
        need["days"] = int(v) if v.isdigit() else NUM.get(v, 2)
    elif "周末" in text:
        need["days"] = 2
    elif "小长假" in text or "三天" in text:
        need["days"] = 3
    elif "一天" in text or "一日" in text:
        need["days"] = 1
    need["days"] = max(1, min(need["days"], 5))

    # 预算
    m = re.search(r"预算\s*([0-9]{2,5})", text)
    if not m:
        m = re.search(r"([0-9]{2,5})\s*(元|块)", text)
    if m:
        need["budget"] = int(m.group(1))
    elif any(w in text for w in ("不贵", "便宜", "省钱", "预算有限")):
        need["budget"] = "low"

    # 节奏
    if any(w in text for w in ("慢", "悠闲", "轻松", "躺平", "不赶")):
        need["pace"] = "slow"
    elif any(w in text for w in ("特种兵", "暴走", "紧凑", "多逛", "打卡多")):
        need["pace"] = "fast"

    # 同行人数
    m = re.search(r"([0-9]{1,2}|[一二两三四五])\s*个?人", text)
    if m:
        v = m.group(1)
        need["companions"] = int(v) if v.isdigit() else NUM.get(v, 1)
    elif any(w in text for w in ("和朋友", "闺蜜", "情侣", "对象")):
        need["companions"] = 2

    # 兴趣
    for tag, words in INTEREST_WORDS.items():
        if any(w in text for w in words):
            need["interests"].append(tag)
    need["interests"] = need["interests"][:3]

    # 避雷
    for tag, words in AVOID_WORDS.items():
        if any(w in text for w in words):
            need["avoid"].append(tag)

    return need
