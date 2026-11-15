# -*- coding: utf-8 -*-
"""静态检查：JS 里用到的元素 id 是否都在对应 HTML 中存在。"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"

PAIRS = [("index.html", "index.js"), ("plan.html", "plan.js"), ("trip.html", "trip.js")]

ok = True
for html_name, js_name in PAIRS:
    html = (WEB / html_name).read_text(encoding="utf-8")
    js = (WEB / "js" / js_name).read_text(encoding="utf-8")

    html_ids = set(re.findall(r'id="([^"]+)"', html))
    js_ids = set(re.findall(r'getElementById\("([^"]+)"\)', js))

    missing = sorted(js_ids - html_ids)
    unused = sorted(html_ids - js_ids)
    print(f"{html_name}: HTML id {len(html_ids)}，JS 引用 {len(js_ids)}")
    if missing:
        ok = False
        print("  ✗ JS 引用了不存在的 id:", missing)
    if unused:
        print("  · HTML 里未被 JS 引用（可能正常）:", unused)

print("\nOK" if ok else "\nFAILED")
raise SystemExit(0 if ok else 1)
