# -*- coding: utf-8 -*-
"""闲行智策 v1（单人 MVP）· API

严格按 docs/接口数据字段说明.md 输出：
- POST /api/trips/generate
- PATCH /api/trips/{trip_id}/items/{item_id}
- POST /api/trips/{trip_id}/save
另外提供演示需要：GET 行程、景点详情、突发重规划、多轮补槽。
"""
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, service
from . import amap
from .config import WEB_DIR, use_mock


@asynccontextmanager
async def lifespan(app):
    db.init()
    yield


app = FastAPI(title="闲行智策 API v1", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RequestValidationError)
async def _on_invalid(request, exc):
    """把 Pydantic 的英文 422 变成中文 400，方便前端直接提示。"""
    fields = []
    for e in exc.errors():
        loc = [str(x) for x in e.get("loc", []) if x != "body"]
        fields.append(".".join(loc) or "body")
    return JSONResponse(status_code=400, content={
        "status": "error", "code": "INVALID_INPUT",
        "message": "请求参数不合法：" + ("、".join(fields) or "body"),
    })


# ---------------------------------------------------------------- 请求体
class GenerateIn(BaseModel):
    raw_text: str = ""
    day_count: int = 2
    budget_limit: int | None = None      # 接口文档：int | null
    city: str | None = None              # 反问流程里用户选的城市，优先于文本解析
    force: bool = False                  # 预算不够时仍要生成


class PatchIn(BaseModel):
    action: str = "update"
    patch: dict = {}


class RerouteIn(BaseModel):
    mode: str = "rain"          # rain | late
    item_id: str | None = None
    extra_min: int = 60


class ChatIn(BaseModel):
    raw_text: str = ""
    answers: dict = {}
    known: dict = {}          # 前端已经填好的字段，有值就不再反问


class CommandIn(BaseModel):
    text: str = ""


def _trip_id(trip_id: str) -> int:
    tid = db.trip_by_code(trip_id)
    if tid is None and str(trip_id).isdigit():
        tid = int(trip_id)
    if not tid or not db.trip_get(tid):
        raise HTTPException(404, detail={"status": "error", "code": "NOT_FOUND",
                                         "message": "这份行程已不在了，请重新生成"})
    return tid


# ---------------------------------------------------------------- 生成
@app.post("/api/trips/generate")
def generate(body: GenerateIn):
    text = (body.raw_text or "").strip()
    if not text:
        raise HTTPException(400, detail={"status": "error", "code": "INSUFFICIENT_INFO",
                                         "message": "先说说想去哪、玩几天", "missing": ["raw_text"]})
    if not (1 <= int(body.day_count) <= 15):
        raise HTTPException(400, detail={"status": "error", "code": "INSUFFICIENT_INFO",
                                         "message": "天数需要在 1—15 天之间", "missing": ["day_count"]})

    t0 = time.perf_counter()
    try:
        data, timings = service.generate(text, int(body.day_count), body.budget_limit,
                                         city=(body.city or None), force=bool(body.force))
    except service.BudgetTooLow as e:
        per_day = max(1, round(e.need_min / max(e.days, 1)))
        fit_days = max(1, min(e.days - 1, e.budget // per_day)) if e.days > 1 else 0
        suggestions = [f"把预算加到 ¥{e.need_min} 以上（当前 ¥{e.budget}）"]
        if fit_days:
            suggestions.append(f"把天数减到 {fit_days} 天左右")
        suggestions.append("换一个周边低成本目的地")
        raise HTTPException(400, detail={
            "status": "error", "code": "BUDGET_TOO_LOW",
            "message": f"预算 ¥{e.budget} 无法满足 {e.city} {e.days} 天的行程"
                       f"（按最低标准约需 ¥{e.need_min}）",
            "budget": e.budget, "days": e.days, "minimum": e.need_min,
            "suggestions": suggestions, "allow_force": True,
        })
    except service.UnknownCity:
        raise HTTPException(400, detail={
            "status": "error", "code": "UNKNOWN_CITY",
            "message": "没太理解要去哪。可以直接说「去杭州两天」「北京三日游」；"
                       f"目前收录：{'、'.join(db.cities())}",
            "supported": db.cities(),
        })
    except service.NoCityData as e:
        raise HTTPException(400, detail={
            "status": "error", "code": "NO_DATA",
            "message": f"目前只收录了 {('、'.join(e.cities))} 的景点数据，{e.city} 还在补充",
            "supported": e.cities,
        })
    data["meta"]["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    data["meta"]["agents"] = timings
    return data


# ---------------------------------------------------------------- 读
@app.get("/api/trips/{trip_id}")
def get_trip(trip_id: str):
    return service.spec_payload(_trip_id(trip_id))


# ---------------------------------------------------------------- 编辑
@app.patch("/api/trips/{trip_id}/items/{item_id}")
def patch_item(trip_id: str, item_id: str, body: PatchIn):
    tid = _trip_id(trip_id)
    ok = service.apply_patch(tid, item_id, body.action, body.patch or {})
    if not ok:
        raise HTTPException(404, detail={"status": "error", "code": "NOT_FOUND",
                                         "message": "这条安排已经不在了"})
    data = service.spec_payload(tid)
    data["item"] = service.spec_item(tid, item_id)
    data["day_cost"] = next((d["day_cost"] for d in data["days"]
                             if any(i["item_id"] == item_id for i in d["items"])), 0)
    return data


# ---------------------------------------------------------------- 保存
@app.post("/api/trips/{trip_id}/save")
def save_trip(trip_id: str):
    tid = _trip_id(trip_id)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    db.trip_save(tid, stamp)
    return {"trip_id": trip_id, "saved_at": stamp, "status": "saved"}


@app.get("/api/trips")
def list_trips():
    return {"trips": db.trips_saved()}


# ---------------------------------------------------------------- 景点详情
@app.get("/api/trips/{trip_id}/items/{item_id}")
def item_detail(trip_id: str, item_id: str):
    tid = _trip_id(trip_id)
    detail = service.item_detail(tid, item_id)
    if not detail:
        raise HTTPException(404, detail={"status": "error", "code": "NOT_FOUND",
                                         "message": "找不到这个地点"})
    return detail


# ---------------------------------------------------------------- 突发重规划
@app.post("/api/trips/{trip_id}/reroute")
def reroute(trip_id: str, body: RerouteIn):
    tid = _trip_id(trip_id)
    service.reroute(tid, body.mode, body.item_id, int(body.extra_min or 60))
    return service.spec_payload(tid)


# ---------------------------------------------------------------- 多轮补槽
@app.post("/api/chat")
def chat(body: ChatIn):
    return service.clarify(body.raw_text or "", body.answers or {}, body.known or {})


@app.post("/api/trips/{trip_id}/command")
def command(trip_id: str, body: CommandIn):
    """一句话改行程：模型理解 → 代码执行。"""
    tid = _trip_id(trip_id)
    if not (body.text or "").strip():
        raise HTTPException(400, detail={"status": "error", "code": "INVALID_INPUT",
                                         "message": "说说要改什么，例如「把第二天下午删掉」"})
    try:
        result = service.apply_command(tid, body.text)
    except service.NoModel:
        raise HTTPException(400, detail={
            "status": "error", "code": "NO_MODEL",
            "message": "没配模型 Key，一句话改行程用不了；可以先手动改条目",
        })
    data = service.spec_payload(tid)
    data["command"] = result
    return data


# ---------------------------------------------------------------- 城市数据
@app.get("/api/cities")
def list_cities():
    return {"cities": db.cities()}


@app.post("/api/cities/{city}/refresh")
def refresh_city(city: str):
    """联网从高德拉取该城市的 POI，写入本地库（source=amap）。"""
    if not amap.enabled():
        raise HTTPException(400, detail={
            "status": "error", "code": "NO_AMAP_KEY",
            "message": "还没配置高德 Key：在 phase1/.env 里加一行 AMAP_KEY=你的Key，然后重启服务",
        })
    try:
        rows = amap.search_city(city)
    except amap.AmapError as e:
        raise HTTPException(502, detail={"status": "error", "code": "AMAP_FAILED",
                                         "message": str(e)})
    if not rows:
        raise HTTPException(404, detail={"status": "error", "code": "NO_RESULT",
                                         "message": f"高德没有返回「{city}」的地点，换个城市名试试"})
    n = db.import_city(city, rows)
    return {"city": city, "imported": n, "source": "amap"}


# ---------------------------------------------------------------- 静态页
app.mount("/css", StaticFiles(directory=str(WEB_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(WEB_DIR / "js")), name="js")


@app.get("/")
def index():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/plan.html")
def plan_page():
    return FileResponse(str(WEB_DIR / "plan.html"))


@app.get("/budget.html")
def budget_page():
    return FileResponse(str(WEB_DIR / "budget.html"))


@app.get("/tips.html")
def tips_page():
    return FileResponse(str(WEB_DIR / "tips.html"))


@app.get("/saved.html")
def saved_page():
    return FileResponse(str(WEB_DIR / "saved.html"))


@app.get("/api/health")
def health():
    with db.conn() as c:
        trips = len(c.execute("SELECT id FROM trips").fetchall())
    return {"ok": True, "mock": use_mock(), "poi": len(db.poi_list()), "trips": trips,
            "version": "v1-single", "cities": db.cities()}
