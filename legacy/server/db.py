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
  tags TEXT, stay_min INTEGER
);
CREATE TABLE IF NOT EXISTS trips (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT, city TEXT, days INTEGER, start_date TEXT,
  budget_limit REAL, need_json TEXT, status TEXT DEFAULT 'ready'
);
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trip_id INTEGER, day_index INTEGER, seq INTEGER,
  type TEXT, name TEXT, start_time TEXT,
  duration_min INTEGER, cost REAL DEFAULT 0,
  poi_id INTEGER, area TEXT, tags TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS members (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trip_id INTEGER, name TEXT, prefs TEXT
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
    _seed_poi_if_empty()


def _seed_poi_if_empty():
    with conn() as c:
        n = c.execute("SELECT COUNT(*) FROM poi").fetchone()[0]
        if n:
            return
        path = SEED_DIR / "poi_changsha.csv"
        if not path.exists():
            return
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        c.executemany(
            "INSERT INTO poi(name,city,type,area,lat,lng,open_hours,price,tags,stay_min)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            [(r["name"], r["city"], r["type"], r["area"], float(r["lat"]), float(r["lng"]),
              r["open_hours"], float(r["price"]), r["tags"], int(r["stay_min"])) for r in rows],
        )


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
def trip_create(title, city, days, start_date, budget_limit, need):
    with conn() as c:
        cur = c.execute(
            "INSERT INTO trips(title,city,days,start_date,budget_limit,need_json) VALUES(?,?,?,?,?,?)",
            (title, city, days, start_date, budget_limit, json.dumps(need, ensure_ascii=False)),
        )
        return cur.lastrowid


def trip_get(tid):
    with conn() as c:
        r = c.execute("SELECT * FROM trips WHERE id=?", (tid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["need"] = json.loads(d.pop("need_json") or "{}")
        return d


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


def items_replace_day(tid, day, items):
    with conn() as c:
        c.execute("DELETE FROM items WHERE trip_id=? AND day_index=?", (tid, day))
        for i, it in enumerate(items, start=1):
            c.execute(
                "INSERT INTO items(trip_id,day_index,seq,type,name,start_time,duration_min,"
                "cost,poi_id,area,tags,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (tid, day, i, it["type"], it["name"], it["start"], it["duration_min"],
                 it.get("cost", 0), it.get("poi_id"), it.get("area", ""),
                 it.get("tags", ""), it.get("note", "")),
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
