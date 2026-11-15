# -*- coding: utf-8 -*-
"""不依赖 FastAPI 的端到端自检：解析 → 生成 → 校验 → 预算 → 贴士。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import db, service  # noqa: E402


def show(tag, obj):
    print(f"\n== {tag} ==")
    print(json.dumps(obj, ensure_ascii=False, indent=2)[:1200])


def main():
    db.init()
    print("POI 数量：", len(db.poi_list()))

    text = "这周末去长沙两天，两个人，预算 800，不想爬山，想吃美食、拍照"
    need = service.parse_text(text)
    show("need", need)

    tid = service.create_trip(need)
    p = service.payload(tid)
    print("\n行程 ID：", tid)

    for d in p["days"]:
        print(f"\n第 {d['day']} 天 · {d['theme']}")
        for it in d["items"]:
            print(f"  {it['start_time']}  {it['name']:<14} {it['duration_min']:>3}min  ￥{it['cost']:.0f}  [{it['type']}]")

    show("budget", p["budget"])
    show("conflicts", p["conflicts"])
    show("tips", p["tips"])

    # 换一个
    first = p["items"][0]
    ok = service.swap_item(tid, first["id"])
    print("\n换一个：", ok)

    # 只重排第二天
    p2 = service.payload(tid)
    if len(p2["days"]) > 1:
        service.regenerate_day(tid, 2)
        p3 = service.payload(tid)
        print("第二天条目数：", len(p3["days"][1]["items"]), "（第一天未变：",
              len(p3["days"][0]["items"]) == len(p2["days"][0]["items"]), "）")

    # 结伴
    merged = service.save_members(tid, [
        {"name": "小明", "prefs": {"interests": ["自然", "拍照"], "avoid": [], "pace": "fast", "budget_level": "mid"}},
        {"name": "小红", "prefs": {"interests": ["美食"], "avoid": ["自然"], "pace": "slow", "budget_level": "low"}},
    ])
    show("merge", merged)

    print("\nOK")


if __name__ == "__main__":
    main()
