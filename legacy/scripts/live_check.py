# -*- coding: utf-8 -*-
"""对运行中的服务做真实 HTTP 冒烟（需要先启动 uvicorn）。

    .venv\\Scripts\\python.exe scripts\\live_check.py
"""
import json
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def show(name, resp):
    ok = 200 <= resp.status_code < 300
    print(f"{'✓' if ok else '✗'} {name}  {resp.status_code}")
    if not ok:
        print(resp.text[:300])
        raise SystemExit(1)
    return resp.json()


def main():
    c = httpx.Client(base_url=BASE, timeout=60)

    print("health:", show("GET /api/health", c.get("/api/health")))

    text = "这周末去长沙两天，两个人，预算 800，不想爬山，想吃美食、拍照"
    need = show("POST /api/parse", c.post("/api/parse", json={"text": text}))
    print("   解析：", {k: need[k] for k in ("city", "days", "budget", "companions", "avoid", "interests")})

    trip = show("POST /api/trips", c.post("/api/trips", json={"need": need}))
    tid = trip["id"]
    print(f"   行程 {tid}：{len(trip['days'])} 天，预算 {trip['budget']['total']}，冲突 {len(trip['conflicts'])}")

    show("GET /api/trips/{id}", c.get(f"/api/trips/{tid}"))

    item = trip["items"][0]
    patched = show("PATCH item", c.patch(f"/api/trips/{tid}/items/{item['id']}", json={"duration_min": 45}))
    assert any(i["id"] == item["id"] and i["duration_min"] == 45 for i in patched["items"])
    print("   改时长 45 分钟 ✓")

    show("POST swap", c.post(f"/api/trips/{tid}/items/{item['id']}/swap"))
    show("POST move", c.post(f"/api/trips/{tid}/items/{trip['items'][1]['id']}/move", json={"direction": "up"}))

    if len(trip["days"]) > 1:
        before = c.get(f"/api/trips/{tid}").json()
        d1 = [(i["id"], i["name"]) for i in before["days"][0]["items"]]
        after = show("POST regenerate day2", c.post(f"/api/trips/{tid}/days/2/regenerate"))
        d1_after = [(i["id"], i["name"]) for i in after["days"][0]["items"]]
        assert d1 == d1_after, "重排第二天却动了第一天"
        print("   第一天未变 ✓")

    merged = show("POST members", c.post(f"/api/trips/{tid}/members", json={"members": [
        {"name": "小明", "prefs": {"interests": ["自然", "拍照"], "avoid": [], "pace": "fast", "budget_level": "mid"}},
        {"name": "小红", "prefs": {"interests": ["美食"], "avoid": ["自然"], "pace": "slow", "budget_level": "low"}},
    ]}))
    print("   共同点：", merged["merge"]["consensus"], " 冲突：", merged["merge"]["conflicts"])

    show("POST regenerate all", c.post(f"/api/trips/{tid}/regenerate", json={"avoid": "自然"}))
    print("share:", show("POST share", c.post(f"/api/trips/{tid}/share")))

    # 静态页
    for path in ("/", "/plan.html", "/trip.html", "/css/app.css", "/js/plan.js"):
        r = c.get(path)
        print(f"{'✓' if r.status_code == 200 else '✗'} GET {path}  {r.status_code}  {len(r.content)} bytes")

    print("\n真实 HTTP 冒烟 OK")


if __name__ == "__main__":
    main()
