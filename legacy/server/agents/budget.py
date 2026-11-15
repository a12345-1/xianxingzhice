# -*- coding: utf-8 -*-
"""④ 预算核算：纯代码，不调模型。"""
CATEGORY = {"attraction": "门票", "food": "餐饮", "hotel": "住宿", "transit": "交通"}


def calc(items, budget_limit=None, companions=1) -> dict:
    by_cat, total = {}, 0.0
    for it in items:
        cat = CATEGORY.get(it.get("type"), "其他")
        val = float(it.get("cost") or 0)
        by_cat[cat] = round(by_cat.get(cat, 0) + val, 2)
        total += val

    limit = None
    try:
        if budget_limit not in (None, "", "low"):
            limit = float(budget_limit)
    except (TypeError, ValueError):
        limit = None

    over = limit is not None and total > limit
    return {
        "total": round(total, 2),
        "by_category": by_cat,
        "limit": limit,
        "over_budget": over,
        "gap": round(total - limit, 2) if over else 0,
        "per_person": round(total / max(int(companions or 1), 1), 2),
    }
