# -*- coding: utf-8 -*-
import os

os.environ["MOCK_MODE"] = "1"
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from server.main import app  # noqa: E402
from server import db  # noqa: E402

db.init()
c = TestClient(app)

r = c.post("/api/trips/generate", json={"raw_text": "去杭州两天", "day_count": 2})
d = r.json()
tid = d["trip_id"]
it = d["days"][0]["items"][0]["item_id"]
print("gen", r.status_code, tid)

cands = c.get("/api/trips/%s/items/%s/candidates" % (tid, it)).json()["candidates"]
print("cand", [(x["name"], x["price"]) for x in cands[:2]])

rep = c.patch("/api/trips/%s/items/%s" % (tid, it),
              json={"action": "replace", "patch": {"poi_id": cands[0]["poi_id"]}})
print("replace", rep.status_code, rep.json()["item"]["name"])

dup = c.post("/api/trips/%s/duplicate" % tid).json()
print("dup", dup)

lst = c.get("/api/trips?limit=3").json()["trips"]
print("list", [(t["trip_id"], t["total_cost"], t["status"]) for t in lst])

print("del", c.delete("/api/trips/%s" % dup["trip_id"]).status_code)
print("after del", len(c.get("/api/trips?limit=10").json()["trips"]))
