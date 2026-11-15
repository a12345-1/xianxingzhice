# -*- coding: utf-8 -*-
"""SQLite：建表、灌示例 POI、行程读写。"""
import csv
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH, SEED_DIR, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS poi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT, city TEXT, type TEXT, area TEXT,
  lat REAL, lng REAL, open_hours TEXT, price REAL,
  tags TEXT, stay_min INTEGER,
  intro TEXT, rating REAL, address TEXT,
  need_booking INTEGER DEFAULT 0,
  source TEXT DEFAULT 'seed', fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS trips (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT, raw_text TEXT, people INTEGER DEFAULT 1,
  title TEXT, city TEXT, days INTEGER, start_date TEXT,
  budget_limit REAL, need_json TEXT, status TEXT DEFAULT 'ready',
  saved_at TEXT, adjustments TEXT, tips_note TEXT, plan_info TEXT
);
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trip_id INTEGER, day_index INTEGER, seq INTEGER,
  type TEXT, name TEXT, start_time TEXT,
  duration_min INTEGER, cost REAL DEFAULT 0,
  poi_id INTEGER, area TEXT, tags TEXT, note TEXT,
  source TEXT DEFAULT 'knowledge_base'
);
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY, value TEXT
);
"""


@contextmanager
def conn():
    """用完即关，避免长时间运行后句柄泄漏。"""
    ensure_dirs()
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)
    _migrate()
    _seed_poi()


def _migrate():
    """给老库补列（CREATE TABLE IF NOT EXISTS 不会改已存在的表）。"""
    with conn() as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(poi)").fetchall()}
        for name, ddl in (("source", "TEXT DEFAULT 'seed'"),
                          ("fetched_at", "TEXT"),
                          ("need_booking", "INTEGER DEFAULT 0")):
            if name not in cols:
                c.execute(f"ALTER TABLE poi ADD COLUMN {name} {ddl}")

        tcols = {r["name"] for r in c.execute("PRAGMA table_info(trips)").fetchall()}
        for name, ddl in (("code", "TEXT"), ("raw_text", "TEXT"),
                          ("people", "INTEGER DEFAULT 1"), ("saved_at", "TEXT"),
                          ("adjustments", "TEXT"), ("tips_note", "TEXT"),
                          ("plan_info", "TEXT")):
            if name not in tcols:
                c.execute(f"ALTER TABLE trips ADD COLUMN {name} {ddl}")

        icols = {r["name"] for r in c.execute("PRAGMA table_info(items)").fetchall()}
        if "source" not in icols:
            c.execute("ALTER TABLE items ADD COLUMN source TEXT DEFAULT 'knowledge_base'")


# 主数据：马佳杰的《景点价格参考》+ 高德坐标合并生成（scripts/build_poi.py）
SEED_FILES = ["poi_curated.csv"]


def _seed_poi():
    rows = []
    for name in SEED_FILES:
        path = SEED_DIR / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows.extend(csv.DictReader(f))

    # 用「数据文件指纹」判断要不要重建，而不是数行数：
    # 联网刷新会删掉某城市的种子行，按行数判断会导致每次启动全库重来。
    import hashlib
    sig = f"{len(rows)}:" + hashlib.md5(
        "".join(r["name"] + r["city"] for r in rows).encode("utf-8")).hexdigest()[:10]

    with conn() as c:
        cur = c.execute("SELECT value FROM meta WHERE key='seed_version'").fetchone()
        if cur and cur["value"] == sig:
            return
        # 示例数据变了：整体重建（行程里的 poi_id 会失效，一并清掉以免串城市）
        c.execute("DELETE FROM items")
        c.execute("DELETE FROM trips")
        c.execute("DELETE FROM poi")

        def _intro(r):
            note = (r.get("note") or "").strip()
            if note:
                return note
            kind = {"attraction": "景点", "food": "餐饮", "hotel": "住宿"}.get(r["type"], "地点")
            return f"{r['name']}，位于{r['city']}{r['area']}，属于{kind}，特点：{r['tags'].replace(';', '、')}。"

        def _num(v, default=0.0):
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        booking = {"湖南省博物院", "长沙市博物馆", "岳麓书院", "谢子龙影像艺术馆",
                   "李自健美术馆", "陕西历史博物馆", "浙江省博物馆"}

        c.executemany(
            "INSERT INTO poi(name,city,type,area,lat,lng,open_hours,price,tags,stay_min,"
            "intro,rating,address,need_booking,source) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'seed')",
            [(r["name"], r["city"], r["type"], r["area"], float(r["lat"]), float(r["lng"]),
              r["open_hours"], _num(r["price"]), r["tags"], int(float(r["stay_min"] or 90)),
              _intro(r), _num(r.get("rating"), 4.5) or 4.5,
              (r.get("address") or "").strip() or f"{r['city']}{r['area']}",
              int(_num(r.get("need_booking"), 0)) or (1 if r["name"] in booking else 0))
             for r in rows],
        )
        c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('seed_version',?)", (sig,))


def import_city(city, rows):
    """用联网抓到的 POI 替换该城市的全部数据（示例种子也一并替换，保证口径一致）。"""
    import datetime
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with conn() as c:
        c.execute("DELETE FROM poi WHERE city=?", (city,))
        c.executemany(
            "INSERT INTO poi(name,city,type,area,lat,lng,open_hours,price,tags,stay_min,"
            "intro,rating,address,need_booking,source,fetched_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0,'amap',?)",
            [(r["name"], r["city"], r["type"], r["area"], float(r["lat"]), float(r["lng"]),
              r["open_hours"], float(r["price"]), r["tags"], int(r["stay_min"]),
              f"{r['name']}，来自高德地图，位于{r['city']}{r['area']}。",
              r.get("rating"), r.get("address", ""), stamp) for r in rows],
        )
        return len(rows)


def cities():
    with conn() as c:
        return [r["city"] for r in c.execute("SELECT DISTINCT city FROM poi ORDER BY city")]


def poi_reviews(pid):
    """示例评价：按标签生成，明确标注来源，避免冒充真实点评。"""
    poi = poi_by_id(pid)
    if not poi:
        return []
    tags = (poi.get("tags") or "").split(";")
    out = []
    if "人多" in tags:
        out.append({"user": "匿名", "rating": 4, "text": "周末人很多，建议早上开门就到。"})
    if "排队久" in tags:
        out.append({"user": "匿名", "rating": 3, "text": "排了 40 分钟才进去，错峰会好一些。"})
    if "人少" in tags:
        out.append({"user": "匿名", "rating": 5, "text": "人不多，逛起来很舒服。"})
    if "拍照" in tags:
        out.append({"user": "匿名", "rating": 5, "text": "光线好的时候很出片。"})
    if not out:
        out.append({"user": "匿名", "rating": 4, "text": "整体符合预期，按开放时间安排即可。"})
    return out[:3]


# ---------------------------------------------------------------- poi
def poi_list(city=None, type_=None):
    sql, args = "SELECT * FROM poi WHERE 1=1", []
    if city:
        sql += " AND city=?"
        args.append(city)
    if type_:
        sql += " AND type=?"
        args.append(type_)
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


def poi_by_id(pid):
    with conn() as c:
        r = c.execute("SELECT * FROM poi WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None


# ---------------------------------------------------------------- trip
def trip_create(title, city, days, start_date, budget_limit, need,
                raw_text="", people=1):
    with conn() as c:
        cur = c.execute(
            "INSERT INTO trips(title,city,days,start_date,budget_limit,need_json,raw_text,people)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (title, city, days, start_date, budget_limit,
             json.dumps(need, ensure_ascii=False), raw_text, people),
        )
        tid = cur.lastrowid
        code = f"tr_{(start_date or '00000000').replace('-', '')}_{tid:04d}"
        c.execute("UPDATE trips SET code=? WHERE id=?", (code, tid))
        return tid


def trip_get(tid):
    with conn() as c:
        r = c.execute("SELECT * FROM trips WHERE id=?", (tid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["need"] = json.loads(d.pop("need_json") or "{}")
        d["adjust_list"] = json.loads(d.get("adjustments") or "[]")
        return d


def trip_set_adjustments(tid, items):
    with conn() as c:
        c.execute("UPDATE trips SET adjustments=? WHERE id=?",
                  (json.dumps(items, ensure_ascii=False), tid))


def trip_set_tips_note(tid, note):
    with conn() as c:
        c.execute("UPDATE trips SET tips_note=? WHERE id=?", (note, tid))


def trip_set_plan_info(tid, info):
    with conn() as c:
        c.execute("UPDATE trips SET plan_info=? WHERE id=?",
                  (json.dumps(info or {}, ensure_ascii=False), tid))


def trip_get_plan_info(tid):
    with conn() as c:
        r = c.execute("SELECT plan_info FROM trips WHERE id=?", (tid,)).fetchone()
    if not r or not r["plan_info"]:
        return {}
    try:
        return json.loads(r["plan_info"])
    except (TypeError, ValueError):
        return {}


def trip_by_code(code):
    with conn() as c:
        r = c.execute("SELECT id FROM trips WHERE code=?", (code,)).fetchone()
        return r["id"] if r else None


def trips_recent(limit=3):
    """最近行程（含未保存草稿），带总花费，供 P1「最近行程」用。"""
    with conn() as c:
        rows = c.execute(
            "SELECT t.id, t.code, t.title, t.city, t.days, t.start_date, t.people,"
            " t.budget_limit, t.status, t.saved_at,"
            " (SELECT COALESCE(SUM(cost),0) FROM items WHERE trip_id=t.id) AS total_cost"
            " FROM trips t ORDER BY t.id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def trip_delete(tid):
    with conn() as c:
        c.execute("DELETE FROM items WHERE trip_id=?", (tid,))
        c.execute("DELETE FROM trips WHERE id=?", (tid,))


def trip_clone(tid, code):
    """复制一份行程（含条目），返回新 id。"""
    with conn() as c:
        r = c.execute("SELECT * FROM trips WHERE id=?", (tid,)).fetchone()
        if not r:
            return None
        cur = c.execute(
            "INSERT INTO trips(title,city,days,start_date,budget_limit,need_json,raw_text,"
            "people,status,adjustments,tips_note) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (r["title"] + "（副本）", r["city"], r["days"], r["start_date"], r["budget_limit"],
             r["need_json"], r["raw_text"], r["people"], "draft", r["adjustments"],
             r["tips_note"]),
        )
        new_id = cur.lastrowid
        new_code = code(new_id)
        c.execute("UPDATE trips SET code=? WHERE id=?", (new_code, new_id))
        rows = c.execute("SELECT * FROM items WHERE trip_id=? ORDER BY day_index, seq",
                         (tid,)).fetchall()
        for it in rows:
            c.execute(
                "INSERT INTO items(trip_id,day_index,seq,type,name,start_time,duration_min,"
                "cost,poi_id,area,tags,note,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_id, it["day_index"], it["seq"], it["type"], it["name"], it["start_time"],
                 it["duration_min"], it["cost"], it["poi_id"], it["area"], it["tags"],
                 it["note"], it["source"]),
            )
        return new_id


def trip_save(tid, stamp):
    with conn() as c:
        c.execute("UPDATE trips SET status='saved', saved_at=? WHERE id=?", (stamp, tid))


def trip_set_status(tid, status):
    with conn() as c:
        c.execute("UPDATE trips SET status=? WHERE id=?", (status, tid))


# ---------------------------------------------------------------- items
def items_get(tid):
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM items WHERE trip_id=? ORDER BY day_index, seq", (tid,)
        ).fetchall()
        return [dict(r) for r in rows]


def trips_saved():
    with conn() as c:
        rows = c.execute(
            "SELECT code,title,city,days,start_date,budget_limit,saved_at"
            " FROM trips WHERE status='saved' ORDER BY saved_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def items_replace_day(tid, day, items):
    with conn() as c:
        c.execute("DELETE FROM items WHERE trip_id=? AND day_index=?", (tid, day))
        for i, it in enumerate(items, start=1):
            c.execute(
                "INSERT INTO items(trip_id,day_index,seq,type,name,start_time,duration_min,"
                "cost,poi_id,area,tags,note,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (tid, day, i, it["type"], it["name"], it["start"], it["duration_min"],
                 it.get("cost", 0), it.get("poi_id"), it.get("area", ""),
                 it.get("tags", ""), it.get("note", ""), it.get("source", "knowledge_base")),
            )


def item_add(tid, day, it):
    """往某天末尾追加一条（不动其他条目）。"""
    with conn() as c:
        n = c.execute("SELECT COALESCE(MAX(seq),0) FROM items WHERE trip_id=? AND day_index=?",
                      (tid, day)).fetchone()[0]
        c.execute(
            "INSERT INTO items(trip_id,day_index,seq,type,name,start_time,duration_min,"
            "cost,poi_id,area,tags,note,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tid, day, n + 1, it["type"], it["name"], it["start"], it["duration_min"],
             it.get("cost", 0), it.get("poi_id"), it.get("area", ""),
             it.get("tags", ""), it.get("note", ""), it.get("source", "knowledge_base")),
        )


def item_get(iid):
    with conn() as c:
        r = c.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
        return dict(r) if r else None


def item_update(iid, fields):
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE items SET {keys} WHERE id=?", (*fields.values(), iid))


def item_delete(iid):
    with conn() as c:
        c.execute("DELETE FROM items WHERE id=?", (iid,))


# ---------------------------------------------------------------- members
def members_save(tid, members):
    with conn() as c:
        c.execute("DELETE FROM members WHERE trip_id=?", (tid,))
        for m in members:
            c.execute("INSERT INTO members(trip_id,name,prefs) VALUES(?,?,?)",
                      (tid, m["name"], json.dumps(m["prefs"], ensure_ascii=False)))


def members_get(tid):
    with conn() as c:
        rows = c.execute("SELECT name,prefs FROM members WHERE trip_id=?", (tid,)).fetchall()
        return [{"name": r["name"], "prefs": json.loads(r["prefs"])} for r in rows]

