# -*- coding: utf-8 -*-
"""FastAPI 入口：接口 + 静态页面。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, service
from .config import WEB_DIR, use_mock


@asynccontextmanager
async def lifespan(app):
    db.init()
    yield


app = FastAPI(title="闲行智策 API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ---------------------------------------------------------------- 请求体
class ParseIn(BaseModel):
    text: str


class TripIn(BaseModel):
    need: dict


class ItemPatch(BaseModel):
    start_time: str = None
    duration_min: int = None
    seq: int = None
    note: str = None


class MoveIn(BaseModel):
    direction: str = "down"      # up / down


class RegenIn(BaseModel):
    avoid: str = None


class MemberIn(BaseModel):
    name: str
    prefs: dict


class MembersIn(BaseModel):
    members: list


# ---------------------------------------------------------------- 接口
@app.get("/api/health")
def health():
    with db.conn() as c:
        trips = len(c.execute("SELECT id FROM trips").fetchall())
    return {
        "ok": True,
        "mock": use_mock(),
        "poi": len(db.poi_list()),
        "trips": trips,
    }


@app.post("/api/parse")
def api_parse(body: ParseIn):
    if not body.text.strip():
        raise HTTPException(400, "说一句话再试，例如：这周末去长沙两天，预算 800")
    return service.parse_text(body.text)


@app.post("/api/trips")
def api_create_trip(body: TripIn):
    need = body.need or {}
    if not need.get("city"):
        raise HTTPException(400, "缺少目的地")
    tid = service.create_trip(need)
    data = service.payload(tid)
    data["id"] = tid
    return data


@app.get("/api/trips/{tid}")
def api_get_trip(tid: int):
    data = service.payload(tid)
    if not data:
        raise HTTPException(404, "行程不存在")
    data["id"] = tid
    return data


@app.patch("/api/trips/{tid}/items/{iid}")
def api_patch_item(tid: int, iid: int, body: ItemPatch):
    fields = {k: v for k, v in body.dict().items() if v is not None}
    db.item_update(iid, fields)
    data = service.payload(tid)
    data["id"] = tid
    return data


@app.delete("/api/trips/{tid}/items/{iid}")
def api_delete_item(tid: int, iid: int):
    db.item_delete(iid)
    data = service.payload(tid)
    data["id"] = tid
    return data


@app.post("/api/trips/{tid}/items/{iid}/swap")
def api_swap(tid: int, iid: int):
    if not service.swap_item(tid, iid):
        raise HTTPException(400, "附近没有可替换的同类地点")
    data = service.payload(tid)
    data["id"] = tid
    return data


@app.post("/api/trips/{tid}/items/{iid}/move")
def api_move(tid: int, iid: int, body: MoveIn):
    service.move_item(tid, iid, body.direction)
    data = service.payload(tid)
    data["id"] = tid
    return data


@app.post("/api/trips/{tid}/days/{day}/regenerate")
def api_regen_day(tid: int, day: int):
    service.regenerate_day(tid, day)
    data = service.payload(tid)
    data["id"] = tid
    return data


@app.post("/api/trips/{tid}/regenerate")
def api_regen_all(tid: int, body: RegenIn = None):
    avoid = body.avoid if body else None
    service.regenerate_all(tid, avoid)
    data = service.payload(tid)
    data["id"] = tid
    return data


@app.post("/api/trips/{tid}/members")
def api_members(tid: int, body: MembersIn):
    merged = service.save_members(tid, body.members)
    data = service.payload(tid)
    data["id"] = tid
    data["merge"] = merged
    return data


@app.post("/api/trips/{tid}/share")
def api_share(tid: int):
    db.trip_set_status(tid, "shared")
    return {"url": f"/plan.html?trip={tid}&share=1", "status": "shared"}


# ---------------------------------------------------------------- 静态页
app.mount("/css", StaticFiles(directory=str(WEB_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(WEB_DIR / "js")), name="js")


@app.get("/")
def index():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/plan.html")
def plan_page():
    return FileResponse(str(WEB_DIR / "plan.html"))


@app.get("/trip.html")
def trip_page():
    return FileResponse(str(WEB_DIR / "trip.html"))
