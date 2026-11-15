# -*- coding: utf-8 -*-
"""把马佳杰的《景点价格参考》CSV 与高德坐标合并，生成 poi_curated.csv。

用法（phase1 目录）：
    ..\\.venv\\Scripts\\python.exe scripts\\build_poi.py "C:\\Users\\xzk\\Downloads\\deepseek_csv_20261115_35f6e9.txt"

产出：server/seed/poi_curated.csv
- 景点：名称/门票/开放时间/备注 来自 CSV，坐标/评分/行政区 来自高德
- 餐饮、住宿：高德关键词搜索（每个城市取评分最高的几条）
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import amap  # noqa: E402

OUT = ROOT / "server" / "seed" / "poi_curated.csv"

# 高德搜不到时的人工坐标兜底
MANUAL = {
    "山城步道": ("重庆", 106.5730, 29.5570, "渝中区"),
    "李子坝轻轨穿楼": ("重庆", 106.5379, 29.5536, "渝中区"),
    "洪崖洞": ("重庆", 106.5790, 29.5628, "渝中区"),
    "永庆坊": ("广州", 113.2445, 23.1185, "荔湾区"),
    "南锣鼓巷": ("北京", 116.4032, 39.9370, "东城区"),
    "武康路": ("上海", 121.4404, 31.2086, "徐汇区"),
}

# CSV 里的名字和高德不一致时，用别名去搜（输出仍用 CSV 的名字）
ALIAS = {
    "湖南博物院": "湖南省博物馆",
    "李子坝轻轨穿楼": "李子坝单轨穿楼",
    "广州塔(外观)": "广州塔",
    "河坊街/清河坊": "河坊街",
    "西湖风景名胜区": "杭州西湖风景名胜区",
    "灵隐寺(含飞来峰)": "灵隐寺",
    "大雁塔/大慈恩寺": "大慈恩寺",
}

TAG_MAP = [
    ("人文", ["人文", "历史", "博物馆", "书院", "故居", "古镇", "建筑", "书法", "考古", "祈福"]),
    ("自然", ["自然", "山", "湿地", "公园", "江", "湖"]),
    ("美食", ["美食", "小吃", "逛吃"]),
    ("夜景", ["夜景", "地标"]),
    ("拍照", ["拍照", "艺术", "Citywalk", "出片", "奇观", "街区"]),
    ("室内", ["室内", "展厅"]),
]

CLAUSE_KEYS = ["博物馆", "博物院", "美术馆", "祠", "书院", "寺", "宫", "府", "堂", "纪念馆"]
WALK_KEYS = ["山", "湿地", "基地", "城墙", "步道"]


def norm_hours(s):
    """'08:30-17:00(周一闭馆)' → '08:30-17:00 周一闭馆'，保证闭馆日能被识别。"""
    s = (s or "").strip()
    closed = "周一闭馆" if "周一闭馆" in s else ""
    head = s.split("(")[0].split("（")[0].strip()
    if head.startswith("全天") or not head:
        head = "全天"
    return (head + (" " + closed if closed else "")).strip()


def norm_tags(s):
    raw = (s or "").replace("|", ",")
    tags = []
    for tag, keys in TAG_MAP:
        if any(k in raw for k in keys) and tag not in tags:
            tags.append(tag)
    if not tags:
        tags.append("人文")
    return ";".join(tags)


def stay_min(name):
    if any(k in name for k in WALK_KEYS):
        return 150
    if any(k in name for k in CLAUSE_KEYS):
        return 90
    return 90


def best_match(city, name):
    """在高德结果里挑名字最接近的一条。"""
    try:
        data = amap._get_raw(city, name, 10)
    except Exception as e:
        print(f"  ! 查询失败 {name}: {e}")
        return None
    query = name.replace("(外观)", "").replace("（外观）", "")
    best, best_score = None, 0
    for p in data.get("pois", []):
        nm = (p.get("name") or "").strip()
        if not nm:
            continue
        if nm == query:
            score = 3
        elif query in nm or nm in query:
            score = 2
        elif len(set(nm) & set(query)) >= max(2, len(query) // 2):
            score = 1
        else:
            score = 0
        if score > best_score:
            best, best_score = p, score
    return best if best_score >= 2 else None


def main(src):
    rows = list(csv.DictReader(Path(src).open(encoding="utf-8-sig")))
    print(f"读入 {len(rows)} 条景点")

    out = []
    cities = {}
    for r in rows:
        name, city = r["景点名称"].strip(), r["所在城市"].strip()
        cities.setdefault(city, []).append(name)
        hit = best_match(city, ALIAS.get(name, name))
        if hit:
            loc = (hit.get("location") or "").split(",")
            lng, lat = float(loc[0]), float(loc[1])
            area = hit.get("adname") or ""
            rating = (hit.get("biz_ext") or {}).get("rating") or ""
            print(f"  ✓ {name} → {hit['name']} ({lng},{lat})")
        elif name in MANUAL:
            _, lat, lng, area = MANUAL[name]
            rating = ""
            print(f"  ○ {name} → 人工坐标")
        else:
            print(f"  ✗ {name} 未匹配，跳过")
            continue

        note = r.get("单人游玩备注", "").strip()
        out.append({
            "name": name,
            "city": city,
            "type": "attraction",
            "area": area or city,
            "lat": round(lat, 4),
            "lng": round(lng, 4),
            "open_hours": norm_hours(r.get("开放时间")),
            "price": float(r.get("门票参考价(元)") or 0),
            "tags": norm_tags(r.get("景点标签")),
            "stay_min": stay_min(name),
            "note": note,
            "rating": rating,
            "address": f"{city}{area}",
            "need_booking": 1 if "预约" in note else 0,
            "food_price": r.get("单人餐饮参考(元/餐)") or "",
            "hotel_price": r.get("单人住宿参考(元/晚)") or "",
        })

    # 餐饮 / 住宿：用高德拉真实名字；高德不给价格，用 CSV 的单人参考价兜底
    for city in cities:
        ref = next((r for r in rows if r["所在城市"].strip() == city), {})
        food_ref = float(ref.get("单人餐饮参考(元/餐)") or 0)
        hotel_ref = float(ref.get("单人住宿参考(元/晚)") or 0)
        try:
            got = amap.search_city(city)
        except Exception as e:
            print(f"  ! {city} 餐饮住宿拉取失败: {e}")
            got = []
        picks = [p for p in got if p["type"] == "food"][:12] + \
                [p for p in got if p["type"] == "hotel"][:4]
        # 过滤“重庆XX面馆”开在外地这种看着违和的店名
        others = {"北京", "上海", "广州", "成都", "西安", "长沙", "杭州", "重庆"} - {city}
        picks = [p for p in picks if not any(o in p["name"][:5] for o in others)]
        picks = [p for p in picks if p["type"] == "hotel"][:3] + \
                [p for p in picks if p["type"] == "food"][:6]
        for p in picks:
            price = p["price"] or (food_ref if p["type"] == "food" else hotel_ref)
            out.append({
                "name": p["name"], "city": city, "type": p["type"], "area": p["area"],
                "lat": p["lat"], "lng": p["lng"], "open_hours": p["open_hours"],
                "price": round(price, 1), "tags": "美食" if p["type"] == "food" else "住宿",
                "stay_min": p["stay_min"], "note": "", "rating": p.get("rating") or "",
                "address": p.get("address", ""), "need_booking": 0,
                "food_price": "", "hotel_price": "",
            })
        nf = len([p for p in picks if p["type"] == "food"])
        print(f"  + {city}: 餐饮 {nf} / 住宿 {len(picks) - nf}（参考价 餐 {food_ref:.0f} 住 {hotel_ref:.0f}）")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = ["name", "city", "type", "area", "lat", "lng", "open_hours", "price",
            "tags", "stay_min", "note", "rating", "address", "need_booking"]
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in out:
            w.writerow({k: row.get(k, "") for k in cols})
    print(f"\n写出 {len(out)} 条 → {OUT}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/build_poi.py <景点CSV路径>")
        sys.exit(1)
    main(sys.argv[1])

