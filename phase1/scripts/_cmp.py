# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

texts = [
    "去杭州玩两天，预算别超过八百，不想太赶",
    "长沙周边，大概一千块两个人，想看山但是别爬山",
    "成都三天，学生党，越便宜越好，不介意住青旅",
]

mode = sys.argv[1] if len(sys.argv) > 1 else "local"
os.environ["MOCK_MODE"] = "1" if mode == "local" else "0"

from server.agents.parse import parse_need  # noqa: E402

print("=== 模式:", mode, "===")
for t in texts:
    n = parse_need(t)
    print(t)
    print("   ->", {k: n.get(k) for k in ("city", "days", "budget", "pace", "interests", "avoid")},
          "| source:", n.get("source"))
