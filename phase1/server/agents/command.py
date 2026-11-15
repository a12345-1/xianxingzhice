# -*- coding: utf-8 -*-
"""⑦ 修改指令理解（模型）：把“把第二天下午删掉”翻译成结构化动作。

只做“语言 → 动作”，真正的增删改由 service 用代码执行，模型不直接写数据。
"""
import json

from .. import llm

SYSTEM = """你是行程修改助手。用户给你当前行程 JSON 和一句修改要求，你只输出 JSON，不要解释。

格式：
{"action":"replace|delete|move|insert|info",
 "day_index": 1,
 "target": "要改的条目名称（必须与行程里的 name 完全一致）",
 "replacement": "替换成的地点名（仅 replace/insert 用，可为 null）",
 "start_time": "HH:mm 或 null",
 "message": "一句中文说明你改了什么"}

规则：
1. 只能操作给定行程里存在的条目，禁止编造不存在的地点；
2. target 必须与行程里的 name 一字不差；
3. 用户说的条目不在指定那天、但在行程其他天 → 就按它实际所在那天处理，并在 message 里说明；
4. 用户说“删掉某天的下午/后半段”，就对该天最后一个条目返回 delete；
5. 用户说的替换目标已经在行程里 → 照样替换，并在 message 里提醒重复；
6. 只有 target 在整份行程里都找不到时，才返回 action=info 说明找不到。"""


def parse(text: str, trip: dict, days: list):
    """返回动作 dict，失败返回 None（调用方降级成“没听懂”）。"""
    ctx = {
        "city": trip.get("city"),
        "days": [
            {
                "day_index": d["day_index"],
                "items": [{"name": i["name"], "start": i["start_time"], "type": i["type"]}
                          for i in d["items"]],
            }
            for d in days
        ],
    }
    out = llm.complete_json(SYSTEM, "行程：" + json.dumps(ctx, ensure_ascii=False) +
                            "\n修改要求：" + text)
    if not isinstance(out, dict) or not out.get("action"):
        return None
    return out
