# -*- coding: utf-8 -*-
"""按《接口数据字段说明.md》第九节 checklist 逐条校验。

用法（phase1 目录）：
    ..\\.venv\\Scripts\\python.exe scripts\\check_spec.py
"""
import os
import re
import sys
from pathlib import Path

# 默认强制走本地规则，保证断言可复现；加 --llm 才测模型路径
if "--llm" not in sys.argv:
    os.environ["MOCK_MODE"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient   # noqa: E402

from server.main import app                 # noqa: E402
from server import db                       # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff]")
OK, FAIL = "✓", "✗"
errors = []


def check(cond, msg):
    print(f"{OK if cond else FAIL} {msg}")
    if not cond:
        errors.append(msg)


def main():
    db.init()
    c = TestClient(app)

    # ---------- 生成
    r = c.post("/api/trips/generate", json={
        "raw_text": "五一 3 天 预算 3000 想去杭州，不想太挤",
        "day_count": 3,
        "budget_limit": 3000,
    })
    check(r.status_code == 200, f"POST /generate 200（实际 {r.status_code}）")
    trip = r.json()

    check(trip["status"] in ("ok", "partial"), "status 取值合法")
    check(trip["trip_id"].startswith("tr_"), "trip_id 形如 tr_…")

    # checklist 1：days 长度 == day_count，items 是数组
    check(len(trip["days"]) == trip["request"]["day_count"], "days 长度等于 day_count")
    check(all(isinstance(d["items"], list) for d in trip["days"]), "items 是数组而非 null")

    # checklist 2：cost == breakdown 四项之和
    bad = []
    for d in trip["days"]:
        for it in d["items"]:
            if it["cost"] != sum(it["cost_breakdown"].values()):
                bad.append(it["item_id"])
    check(not bad, f"cost 等于 cost_breakdown 之和（异常 {bad[:3]}）")

    # checklist 3/4/5：预算
    b = trip["budget"]
    check(b["total"] == sum(x["amount"] for x in b["categories"]), "budget.total 等于四类之和")
    check([x["key"] for x in b["categories"]] == ["ticket", "transport", "food", "hotel"],
          "categories 固定四类且顺序正确")
    if b["limit"] is None:
        check(b["over_budget"] is False, "limit 为 null 时 over_budget 恒 false")
    else:
        check(b["remaining"] == b["limit"] - b["total"], "remaining = limit - total")
        check(b["over_budget"] == (b["total"] > b["limit"]), "over_budget 判定正确")
    check(b["per_person"] == b["total"] // trip["request"]["people"], "per_person 向下取整")

    # checklist 6：warnings / suggestions 都是数组
    warns_ok = all(isinstance(it["warnings"], list) for d in trip["days"] for it in d["items"])
    check(warns_ok, "items[].warnings 全是数组")
    check(isinstance(b["suggestions"], list), "budget.suggestions 是数组")

    # 结构字段齐全
    it0 = next((it for d in trip["days"] for it in d["items"]), None)
    check(it0 is not None, "至少生成一条 items")
    for k in ("item_id", "seq", "type", "name", "start_time", "end_time", "duration_min",
              "transport", "cost", "cost_breakdown", "source", "open_hours", "closed_days",
              "warnings"):
        check(k in it0, f"items[] 含字段 {k}")
    check(it0["type"] in ("spot", "food", "hotel", "transport", "rest"), "item.type 取值合法")
    check(it0["transport"]["mode"] in ("walk", "bus", "taxi", "train"), "transport.mode 合法")

    # tips
    t = trip["tips"]
    check(isinstance(t["packing"], list) and 3 <= len(t["packing"]) <= 8,
          f"tips.packing 3—8 条（现在 {len(t['packing'])}）")
    check(all("level" in x for x in t["weather_tips"]), "weather_tips 含 level")
    check(t["source"] in ("weather_api", "knowledge_base", "model", "mixed"), "tips.source 合法")

    # meta
    check(len(trip["meta"]["agents"]) == 5, "meta.agents 记录 5 个智能体")

    # ---------- 编辑（checklist 7：PATCH 回完整 budget）
    target = it0["item_id"]
    r2 = c.patch(f"/api/trips/{trip['trip_id']}/items/{target}",
                 json={"action": "update", "patch": {"duration_min": 45}})
    check(r2.status_code == 200, "PATCH 单条 200")
    p2 = r2.json()
    check("budget" in p2 and p2["budget"]["total"] == sum(x["amount"] for x in p2["budget"]["categories"]),
          "PATCH 回完整且自洽的 budget")
    check(p2["item"]["duration_min"] == 45, "PATCH 生效")

    # 删除
    r3 = c.patch(f"/api/trips/{trip['trip_id']}/items/{target}",
                 json={"action": "delete", "patch": {}})
    check(r3.status_code == 200, "PATCH delete 200")
    check(all(it["item_id"] != target for d in r3.json()["days"] for it in d["items"]),
          "删除后该条不在 days 里")

    # ---------- 保存
    r4 = c.post(f"/api/trips/{trip['trip_id']}/save")
    check(r4.status_code == 200 and r4.json()["status"] == "saved", "保存接口返回 saved")
    check(c.get("/api/trips").json()["trips"], "已保存列表非空")

    # ---------- 错误码
    r5 = c.post("/api/trips/generate", json={"raw_text": "", "day_count": 2})
    check(r5.status_code == 400, "空需求返回 400")
    check(r5.json()["detail"]["code"] == "INSUFFICIENT_INFO", "错误码 INSUFFICIENT_INFO")
    check(bool(CJK.search(r5.json()["detail"]["message"])), "错误 message 是中文")

    r6 = c.get("/api/trips/tr_not_exist_0000")
    check(r6.status_code == 404 and r6.json()["detail"]["code"] == "NOT_FOUND", "不存在的行程 404")

    # 回归：预算留空时前端传 null，不能 422
    r7 = c.post("/api/trips/generate",
                json={"raw_text": "周末去长沙两天", "day_count": 2, "budget_limit": None})
    check(r7.status_code == 200, f"budget_limit 为 null 能生成（实际 {r7.status_code}）")
    check(r7.json()["budget"]["limit"] is None, "未设上限时 limit 为 null")
    check(r7.json()["budget"]["over_budget"] is False, "未设上限时 over_budget 为 false")

    r8 = c.post("/api/trips/generate",
                json={"raw_text": "去长沙两天", "day_count": "abc"})
    check(r8.status_code == 400, "非法 day_count 返回 400 而不是 422")
    check(r8.json()["code"] == "INVALID_INPUT", "非法参数错误码 INVALID_INPUT")

    # TC-04：预算严重不足要给建议，而不是崩溃或硬生成
    low = c.post("/api/trips/generate",
                 json={"raw_text": "去三亚玩5天，预算300，要住海景房", "day_count": 5,
                       "budget_limit": 300})
    check(low.status_code == 400, "TC-04 预算不足返回 400")
    check(low.json()["detail"]["code"] == "BUDGET_TOO_LOW", "错误码 BUDGET_TOO_LOW")
    check(len(low.json()["detail"].get("suggestions") or []) >= 2, "给了至少 2 条平替建议")
    check(low.json()["detail"]["minimum"] > 300, "最低估算大于用户预算")

    forced = c.post("/api/trips/generate",
                    json={"raw_text": "去北京两天", "day_count": 2, "budget_limit": 200,
                          "force": True})
    check(forced.status_code == 200, "force=true 时允许强行生成")
    check(forced.json()["budget"]["over_budget"] is True, "强行生成后标记超支")

    # TC-06：模糊输入要反问，不直接生成
    vague = c.post("/api/chat", json={"raw_text": "我想出去玩", "known": {"days": 2}})
    check(vague.status_code == 200, "TC-06 反问接口可用")
    v = vague.json()
    check(v["ready"] is False, "「我想出去玩」不 ready")
    check({"city", "budget"} <= set(v["missing"]), "缺 city 和 budget 会被问")
    check(all(q.get("slot") for q in v["questions"]), "反问项都带 slot")

    full = c.post("/api/chat", json={"raw_text": "去杭州两天，预算 1000，两个人"}).json()
    check(full["ready"] is True and not full["missing"], "信息齐全时不再反问")

    no_people = c.post("/api/chat", json={"raw_text": "去杭州两天，预算 1000"}).json()
    check("people" in no_people["missing"], "没说几个人会反问人数")

    unknown = c.post("/api/chat", json={"raw_text": "霍格沃茨2天"}).json()
    check("city" in unknown["missing"], "不认识的城市也会触发反问")

    # 反问补全后能直接生成
    r_after = c.post("/api/trips/generate",
                     json={"raw_text": "我想出去玩", "day_count": 2,
                           "budget_limit": None, "city": "杭州"})
    check(r_after.status_code == 200, "补全城市后能生成")
    check(r_after.json()["request"]["destination"] == "杭州", "用的是反问里选的城市")
    names = {}
    for city in ("长沙", "杭州", "西安", "成都"):
        rr = c.post("/api/trips/generate",
                    json={"raw_text": f"去{city}玩两天", "day_count": 2})
        check(rr.status_code == 200, f"{city} 能生成（实际 {rr.status_code}）")
        names[city] = {i["name"] for d in rr.json()["days"] for i in d["items"]}

    for city, got in names.items():
        allow = {p["name"] for p in db.poi_list(city)}
        check(got <= allow, f"{city} 只用了本城市的地点（越界 {sorted(got - allow)[:2]}）")
    check(not (names["长沙"] & names["杭州"]), "长沙与杭州的行程没有重叠")

    r9 = c.post("/api/trips/generate", json={"raw_text": "去三亚玩两天", "day_count": 2})
    check(r9.status_code == 400, "未收录城市返回 400")
    check(r9.json()["detail"]["code"] == "NO_DATA", "错误码 NO_DATA 且不静默回退")

    # TC-05：不认识的地方（霍格沃茨）绝不生成假行程
    for phrase in ("去霍格沃茨玩两天，预算 1000", "霍格沃茨2天", "霍格沃茨玩两天"):
        r10 = c.post("/api/trips/generate", json={"raw_text": phrase, "day_count": 2})
        check(r10.status_code == 400, f"「{phrase}」返回 400 而不是编造行程")
        check(r10.json()["detail"]["code"] == "UNKNOWN_CITY", f"「{phrase}」错误码 UNKNOWN_CITY")

    print()
    if errors:
        print(f"{FAIL} 未通过 {len(errors)} 项：")
        for e in errors:
            print("   -", e)
        sys.exit(1)
    print("清单全部通过 ✅")


if __name__ == "__main__":
    main()
