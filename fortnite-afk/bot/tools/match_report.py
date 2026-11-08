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
confs = [s["action_conf"] for s in steps if "action_conf" in s]
sims = [s["similarity"] for s in steps if s.get("similarity") is not None]
moved = sum(1 for v in sims if v < 0.98)
still = sum(1 for v in sims if v >= 0.98)
interacts = sum(1 for s in steps if s.get("interact"))
jumps = sum(1 for s in steps if s.get("jump"))
attacks = sum(1 for s in steps if "attack" in s.get("plan", ""))
screens: dict[str, int] = {}
for s in steps:
    key = s.get("screen")
    if key:
        screens[key] = screens.get(key, 0) + 1
last_screen = next((s.get("screen") for s in reversed(steps) if s.get("screen")), "-")
conf_ok = sum(1 for c in confs if c >= 0.25)
rows = "".join(
    f"<tr><td>{s['index']}</td><td>{s.get('time', '')}</td>"
    f"<td>{s.get('luma', '')}</td><td>{s.get('api_s', '-')}</td>"
    f"<td>{s.get('screen', '-')}</td>"
    f"<td>{s.get('action_conf', '-')}</td>"
    f"<td>{s.get('similarity', '-')}</td>"
    f"<td><code>{html.escape(s.get('plan', 'black frame'))}</code></td></tr>"
    for s in steps)
median = round(statistics.median(api), 2) if api else 0
doc = f"""<!doctype html><html lang="zh"><meta charset="utf-8">
<title>Match monitor</title>
<style>
body{{background:#0b0f16;color:#e6edf7;font:14px/1.7 "Segoe UI","Microsoft YaHei",sans-serif;padding:30px}}
table{{border-collapse:collapse;width:100%;max-width:1180px}}
th,td{{border-bottom:1px solid #1e2637;padding:7px 10px;text-align:left}}
th{{color:#8b97ad;font-size:11px;text-transform:uppercase;letter-spacing:.06em}}
code{{color:#c7d4ea}} .k{{color:#e8c170;font-weight:700}} .w{{color:#ff8a8a}}
</style>
<h1>对局监控</h1>
<p>{len(steps)} 步 · {len(api)} 次模型决策 · <b>{black}</b> 次黑屏 ·
API 中位 <b>{median}s</b>（最大 {round(max(api), 2) if api else 0}s）</p>
<p>置信度 ≥0.25：<b>{conf_ok}</b> / {len(confs)}（兜底 {fallback} 次）·
画面变化 <b>{moved}</b> 次 · 停滞 {still} 次 ·
交互 {interacts} · 跳跃 {jumps} · 开火 {attacks}</p>
<p>结束时画面：<b>{last_screen}</b> · 各阶段计数：{html.escape(str(screens))}</p>
<table><tr><th>#</th><th>t(s)</th><th>luma</th><th>api(s)</th><th>screen</th>
<th>act conf</th><th>sim</th><th>plan</th></tr>
{rows}</table>
</html>"""
out.write_text(doc, encoding="utf-8")
print(f"report: {out}")
print(f"steps={len(steps)} decisions={len(api)} black={black} median_api={median}s "
      f"conf_ok={conf_ok}/{len(confs)} fallback={fallback} moved={moved} still={still} "
      f"interact={interacts} jump={jumps} attack={attacks} end={last_screen}")
print(f"steps={len(steps)} decisions={len(api)} black={black} "
      f"median_api={median}s fallback={fallback}/{len(api)}")
