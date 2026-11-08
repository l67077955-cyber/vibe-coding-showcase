#!/usr/bin/env python
"""Turn a screen_only_loop decisions.json into a one-page monitor report."""
from __future__ import annotations

import html
import json
import statistics
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

src = Path(sys.argv[1] if len(sys.argv) > 1 else "logs/match_monitor/decisions.json")
out = src.with_name("report.html")
data = json.loads(src.read_text(encoding="utf-8"))
steps = data.get("steps", [])
api = [s["api_s"] for s in steps if "api_s" in s]
black = sum(1 for s in steps if "skipped" in s)
plans = [s.get("plan", "") for s in steps]
fallback = sum(1 for p in plans if "(0.00)" in p)
rows = "".join(
    f"<tr><td>{s['index']}</td><td>{s.get('time', '')}</td>"
    f"<td>{s.get('luma', '')}</td><td>{s.get('api_s', '-')}</td>"
    f"<td>{s.get('screen', '-')}</td>"
    f"<td><code>{html.escape(s.get('plan', 'black frame'))}</code></td></tr>"
    for s in steps)
median = round(statistics.median(api), 2) if api else 0
doc = f"""<!doctype html><html lang="zh"><meta charset="utf-8">
<title>Match monitor</title>
<style>
body{{background:#0b0f16;color:#e6edf7;font:14px/1.7 "Segoe UI","Microsoft YaHei",sans-serif;padding:30px}}
table{{border-collapse:collapse;width:100%;max-width:1040px}}
th,td{{border-bottom:1px solid #1e2637;padding:7px 10px;text-align:left}}
th{{color:#8b97ad;font-size:11px;text-transform:uppercase;letter-spacing:.06em}}
code{{color:#c7d4ea}} .k{{color:#e8c170;font-weight:700}} .w{{color:#ff8a8a}}
</style>
<h1>对局监控</h1>
<p>{len(steps)} 步 · {len(api)} 次模型决策 · <b>{black}</b> 次黑屏 ·
API 中位 <b>{median}s</b>（最大 {round(max(api), 2) if api else 0}s）</p>
<p class="k">{fallback}/{len(api)} 次决策的 action 置信度为 0.00，全部走 move_forward 兜底</p>
<table><tr><th>#</th><th>t(s)</th><th>luma</th><th>api(s)</th><th>screen</th><th>plan</th></tr>
{rows}</table>
<p style="color:#8b97ad">证据：step_01.png（出生岛）、../monitor_now.png（战斗巴士）</p>
</html>"""
out.write_text(doc, encoding="utf-8")
print(f"report: {out}")
print(f"steps={len(steps)} decisions={len(api)} black={black} "
      f"median_api={median}s fallback={fallback}/{len(api)}")
