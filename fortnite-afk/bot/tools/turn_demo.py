#!/usr/bin/env python
"""Show why the turn stopped looking robotic: snap vs eased profile.

The old code did `move_relative(320, random(-20, 20))` once per decision, i.e.
the camera teleports 320 px in a single frame. The new profile splits the same
turn into 50 Hz ticks with a smoothstep speed curve: slow start, fast middle,
slow stop, exact same total displacement.

    python tools/turn_demo.py --px 320 --out logs/turn_demo
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from afk.motion import TurnConfig, plan_turn, smoothstep, turn_duration  # noqa: E402


def svg_chart(dx: int, steps: list[int], cfg: TurnConfig) -> str:
    width, height = 760, 300
    left, top, right, bottom = 56, 24, 24, 44
    plot_w = width - left - right
    plot_h = height - top - bottom
    n = len(steps)
    total_t = max(turn_duration(steps, cfg), 0.001)

    def x_of(t: float) -> float:
        return left + plot_w * (t / total_t)

    def y_of(v: float) -> float:
        return top + plot_h * (1 - v / dx)

    pts = [(x_of(0.0), y_of(0.0))]
    acc = 0
    for i, d in enumerate(steps):
        acc += d
        pts.append((x_of((i + 1) * cfg.tick_s), y_of(acc)))
    eased = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = (f"{left},{top + plot_h} " + eased +
            f" {left + plot_w},{top + plot_h}")

    bars = []
    bar_w = max(1.0, plot_w / max(1, n) * 0.7)
    peak = max(abs(d) for d in steps) or 1
    for i, d in enumerate(steps):
        bx = left + plot_w * (i / max(1, n)) + (plot_w / max(1, n) - bar_w) / 2
        bh = plot_h * 0.42 * (abs(d) / peak)
        by = top + plot_h - bh
        bars.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" '
                    f'height="{bh:.1f}" fill="#2f6df6" opacity="0.30"/>')

    return f"""<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" fill="#0d121b"/>
  <line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}"
        stroke="#2a3446"/>
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#2a3446"/>
  {''.join(bars)}
  <polyline points="{eased}" fill="none" stroke="#3ddc84" stroke-width="2.5"/>
  <polyline points="{left},{top} {left},{top + plot_h}" fill="none"
            stroke="#ff5d5d" stroke-width="2.5" stroke-dasharray="5 4"/>
  <circle cx="{left}" cy="{top}" r="4" fill="#ff5d5d"/>
  <text x="{left}" y="{top - 8}" fill="#ff8a8a" font-size="11" font-family="Consolas">
    old: 0 to {dx}px in one frame</text>
  <text x="{left + plot_w - 8}" y="{top + 12}" fill="#7ee2ab" font-size="11"
        text-anchor="end" font-family="Consolas">new: eased over {turn_duration(steps, cfg):.2f}s
    ({n} ticks)</text>
  <text x="{left - 10}" y="{top + 4}" fill="#6f7d94" font-size="10" text-anchor="end"
        font-family="Consolas">{dx}px</text>
  <text x="{left - 10}" y="{top + plot_h}" fill="#6f7d94" font-size="10" text-anchor="end"
        font-family="Consolas">0</text>
  <text x="{left}" y="{height - 12}" fill="#6f7d94" font-size="10"
        font-family="Consolas">0s</text>
  <text x="{left + plot_w}" y="{height - 12}" fill="#6f7d94" font-size="10"
        text-anchor="end" font-family="Consolas">{total_t:.2f}s</text>
  <text x="{width - 24}" y="{height - 12}" fill="#6f7d94" font-size="10"
        text-anchor="end" font-family="Consolas">cumulative mouse px over time</text>
</svg>"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--px", type=int, default=320)
    p.add_argument("--out", default=str(ROOT / "logs" / "turn_demo"))
    args = p.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

    cfg = TurnConfig()
    steps = plan_turn(args.px, cfg)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"turn {args.px:+d}px")
    print(f"  old : 1 mouse event, {args.px:+d}px, ~0 ms  (camera whip)")
    print(f"  new : {len(steps)} events, {turn_duration(steps, cfg)*1000:.0f} ms, "
          f"max {max(abs(s) for s in steps)}px/tick")
    print(f"  sum : {sum(steps)}px (exact), ease-in/out via smoothstep")
    print("  profile:")
    peak = max(abs(s) for s in steps)
    for i, s in enumerate(steps):
        bar = "#" * max(1, round(abs(s) / peak * 30))
        print(f"    {i:02d} {s:+4d}  {bar}")
    print(f"  smoothstep(0.25)={smoothstep(0.25):.3f} "
          f"smoothstep(0.5)={smoothstep(0.5):.3f} smoothstep(0.75)={smoothstep(0.75):.3f}")

    doc = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>Turn profile — snap vs eased</title>
<style>
body{{margin:0;background:#080b12;color:#e8edf7;
     font:15px/1.6 "Segoe UI","Microsoft YaHei",sans-serif}}
.wrap{{max-width:900px;margin:0 auto;padding:32px 26px 60px}}
h1{{font-size:24px;margin:0 0 4px}} .sub{{color:#8b97ad;font-size:13px;margin-bottom:20px}}
.card{{border:1px solid #1e2637;border-radius:14px;background:#0d121b;padding:18px;margin:16px 0}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
td,th{{padding:6px 10px;border-bottom:1px solid #1b2332;text-align:left}}
th{{color:#7f8ca3;font-size:11px;text-transform:uppercase;letter-spacing:.06em}}
code{{font-family:Consolas,monospace;color:#c7d4ea}}
</style></head><body><div class="wrap">
<h1>转向曲线：从“瞬移”到“缓入缓出”</h1>
<div class="sub">同一次 {args.px}px 转向 · 旧实现 1 帧完成 · 新实现 {len(steps)} 个 20ms tick</div>
<div class="card">{svg_chart(args.px, steps, cfg)}</div>
<div class="card"><table>
<tr><th>指标</th><th>旧</th><th>新</th></tr>
<tr><td>鼠标事件数</td><td><code>1</code></td><td><code>{len(steps)}</code></td></tr>
<tr><td>总位移</td><td><code>{args.px:+d}px</code></td><td><code>{sum(steps):+d}px</code></td></tr>
<tr><td>单帧最大位移</td><td><code>{args.px}px</code>（无上限）</td>
    <td><code>{max(abs(s) for s in steps)}px</code>（≤ {cfg.max_px_per_s:.0f}px/s）</td></tr>
<tr><td>用时</td><td><code>~0ms</code></td><td><code>{turn_duration(steps, cfg)*1000:.0f}ms</code></td></tr>
<tr><td>速度曲线</td><td>阶跃</td><td>smoothstep（慢-快-慢）</td></tr>
</table></div>
</div></body></html>"""
    path = out / "turn_profile.html"
    path.write_text(doc, encoding="utf-8")
    print(f"\nchart: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
