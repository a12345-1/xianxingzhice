# -*- coding: utf-8 -*-
"""模型提议 + 代码把关：模型只选“去哪几个点”，时间/去重/距离/预算全部由代码裁决。

设计原则：
1. 模型输出只允许引用给定候选名单里的名字，编造的名字直接丢弃；
2. 每一条被代码改动的地方都记进 fixes，答辩时可以展示“守门员做了什么”；
3. 任何异常（超时、JSON 坏掉）都退回本地排程，不阻塞出方案。
"""
import json

from .. import llm

SYSTEM = """你是行程规划助手。只从给定的 candidates 里挑地点，禁止编造名单外的地方。

要求：
1. 按天分配，每天 2—3 个景点（type=attraction），1—2 个餐饮（type=food），第 1 天起每晚住宿 1 个（type=hotel）；
2. 同一天的地点尽量在同一个 area，避免来回跑；
3. 全程不能重复使用同一个地点；
4. 不要输出时间、不要输出价格，只输出名字。

只输出 JSON：
{"days":[{"day_index":1,"spots":["景点名1","景点名2"],"foods":["餐厅名"],"hotel":"酒店名"}],
 "reason":"一句话说明你这样排的思路"}"""


def propose(need, cand):
    """让模型按天挑点；返回 (plan_dict, note) 或 (None, None)。"""
    brief = [
        {"name": p["name"], "type": p["type"], "area": p["area"],
         "price": p["price"], "stay_min": p["stay_min"], "tags": p["tags"]}
        for p in cand
    ]
    payload = {"days": int(need.get("days") or 2), "city": need.get("city"),
               "pace": need.get("pace"), "interests": need.get("interests"),
               "avoid": need.get("avoid"), "candidates": brief}
    out = llm.complete_json(SYSTEM, json.dumps(payload, ensure_ascii=False))
    if not isinstance(out, dict) or not isinstance(out.get("days"), list):
        return None, None
    return out, (out.get("reason") or "").strip()
