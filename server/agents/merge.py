# -*- coding: utf-8 -*-
"""⑤ 多人偏好融合：算法合并 + 把冲突摆出来，不替人裁决。"""
TAGS = ["自然", "美食", "拍照", "人文", "夜景", "购物", "亲子"]
PACE = {"slow": 0, "normal": 1, "fast": 2}
BUDGET = {"low": 0, "mid": 1, "high": 2}


def merge(members) -> dict:
    """members: [{"name": "小明", "prefs": {...}}, ...]"""
    if not members:
        return {"merged": {}, "conflicts": [], "pace": "normal",
                "budget_level": "mid", "consensus": []}

    score = {t: 0.0 for t in TAGS}
    likes = {t: 0 for t in TAGS}
    dislikes = {t: 0 for t in TAGS}

    for m in members:
        p = m.get("prefs") or {}
        for t in p.get("interests") or []:
            if t in score:
                score[t] += 1.0
                likes[t] += 1
        for t in p.get("avoid") or []:
            if t in score:
                score[t] -= 1.5          # “讨厌”的权重要比“喜欢”重
                dislikes[t] += 1

    n = max(len(members), 1)
    merged = {t: round(v / n, 2) for t, v in score.items()}
    conflicts = [t for t in TAGS if likes[t] >= 1 and dislikes[t] >= 1]
    consensus = [t for t in TAGS if merged[t] > 0.3 and t not in conflicts]

    return {
        "merged": merged,
        "consensus": consensus[:3],
        "conflicts": conflicts,
        "pace": _avg(members, "pace", PACE, "normal"),
        "budget_level": _avg(members, "budget_level", BUDGET, "mid"),
        "names": [m.get("name", "") for m in members],
    }


def _avg(members, key, table, default):
    vals = []
    for m in members:
        v = (m.get("prefs") or {}).get(key, default)
        vals.append(table.get(v, table[default]))
    return list(table)[round(sum(vals) / max(len(vals), 1))]
