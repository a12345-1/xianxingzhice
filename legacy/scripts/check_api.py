# -*- coding: utf-8 -*-
"""不装 FastAPI 也能验证接口层：用最小桩替换 fastapi / pydantic，直接调用路由函数。

用途：在没网/没装依赖的电脑上，确认请求体、返回结构、错误分支都对。
（真正的 HTTP 行为仍需 `uvicorn` 起来后用浏览器或 /docs 验证）
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------- 最小桩
class HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class BaseModel:
    def __init__(self, **kw):
        ann = getattr(type(self), "__annotations__", {})
        for name in ann:
            setattr(self, name, kw.get(name, getattr(type(self), name, None)))
        for k, v in kw.items():
            setattr(self, k, v)

    def dict(self):
        return {k: getattr(self, k) for k in getattr(type(self), "__annotations__", {})}


class FastAPI:
    def __init__(self, **kwargs):
        self.routes = {}

    def _route(self, method):
        def deco(path):
            def wrap(fn):
                self.routes[(method, path)] = fn
                return fn
            return wrap
        return deco

    def get(self, path): return self._route("GET")(path)
    def post(self, path): return self._route("POST")(path)
    def patch(self, path): return self._route("PATCH")(path)
    def delete(self, path): return self._route("DELETE")(path)

    def mount(self, *a, **k): pass
    def add_middleware(self, *a, **k): pass


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


class _Any:
    """接受任意参数的占位类（FileResponse / StaticFiles / CORSMiddleware）。"""

    def __init__(self, *a, **k):
        pass


_stub("fastapi", FastAPI=FastAPI, HTTPException=HTTPException)
_stub("fastapi.responses", FileResponse=_Any)
_stub("fastapi.staticfiles", StaticFiles=_Any)
_stub("fastapi.middleware")
_stub("fastapi.middleware.cors", CORSMiddleware=_Any)
_stub("pydantic", BaseModel=BaseModel)


# ---------------------------------------------------------------- 测试
def main():
    from server import db, main as api

    db.init()

    # 1. 健康检查
    h = api.health()
    assert h["ok"] and h["poi"] >= 30, h
    print("health:", h)

    # 2. 解析
    text = "这周末去长沙两天，两个人，预算 800，不想爬山，想吃美食"
    need = api.api_parse(api.ParseIn(text=text))
    assert need["city"] == "长沙" and need["days"] == 2, need
    print("parse:", {k: need[k] for k in ("city", "days", "budget", "companions", "avoid")})

    # 3. 空输入应报错
    try:
        api.api_parse(api.ParseIn(text="  "))
    except HTTPException as e:
        assert e.status_code == 400
        print("空输入 -> 400 ✓")
    else:
        raise AssertionError("空输入没有报错")

    # 4. 建行程
    data = api.api_create_trip(api.TripIn(need=need))
    tid = data["id"]
    assert data["days"] and data["budget"]["total"] > 0, data["budget"]
    print("trip:", tid, "天:", [d["day"] for d in data["days"]],
          "预算:", data["budget"]["total"], "冲突:", len(data["conflicts"]))

    # 5. 取行程
    again = api.api_get_trip(tid)
    assert again["id"] == tid and len(again["items"]) == len(data["items"])

    # 6. 改一项（时长）
    first = data["items"][0]
    patched = api.api_patch_item(tid, first["id"], api.ItemPatch(duration_min=45))
    assert next(i for i in patched["items"] if i["id"] == first["id"])["duration_min"] == 45
    print("patch 时长 -> 45 ✓")

    # 7. 换一个
    swapped = api.api_swap(tid, first["id"])
    assert len(swapped["items"]) == len(patched["items"])
    print("swap ✓")

    # 8. 上移下移
    second = data["items"][1] if len(data["items"]) > 1 else first
    api.api_move(tid, second["id"], api.MoveIn(direction="up"))
    print("move ✓")

    # 9. 只重排第二天（先快照第一天，重排后必须一模一样）
    if len(data["days"]) > 1:
        before = api.api_get_trip(tid)
        day1_before = [(i["id"], i["name"], i["start_time"]) for i in before["days"][0]["items"]]
        after = api.api_regen_day(tid, 2)
        day1_after = [(i["id"], i["name"], i["start_time"]) for i in after["days"][0]["items"]]
        assert day1_before == day1_after, f"重排第二天却动了第一天：{day1_before} != {day1_after}"
        print("regen day2：第一天未变 ✓")

    # 10. 删除
    victim = data["items"][-1]
    deleted = api.api_delete_item(tid, victim["id"])
    assert all(i["id"] != victim["id"] for i in deleted["items"])
    print("delete ✓")

    # 11. 结伴融合
    merged = api.api_members(tid, api.MembersIn(members=[
        {"name": "小明", "prefs": {"interests": ["自然", "拍照"], "avoid": [], "pace": "fast", "budget_level": "mid"}},
        {"name": "小红", "prefs": {"interests": ["美食"], "avoid": ["自然"], "pace": "slow", "budget_level": "low"}},
    ]))
    assert "自然" in merged["merge"]["conflicts"], merged["merge"]
    print("merge 冲突:", merged["merge"]["conflicts"], "共同点:", merged["merge"]["consensus"])

    # 12. 全量重排带避雷
    applied = api.api_regen_all(tid, api.RegenIn(avoid="自然"))
    assert applied["days"], "重排后没有行程"
    print("regen all(avoid=自然) ✓")

    # 13. 分享
    share = api.api_share(tid)
    assert share["url"].startswith("/plan.html?trip=")
    print("share:", share["url"])

    print("\nAPI 层 OK")


if __name__ == "__main__":
    main()
