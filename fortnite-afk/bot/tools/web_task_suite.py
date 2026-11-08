#!/usr/bin/env python
"""Multi-task 3D game suite against the local browser stand-in.

The Fortnite pipeline cannot be tested on this machine (the game is not
installed), so the suite drives a real Chromium window showing a first-person
3D page whose window title encodes the game state:

    FORWEB chest | far            chest out of reach
    FORWEB chest | IN RANGE (E)   pressing E opens it
    FORWEB chest | OPENED         it is open

Each task is a self-contained scenario with its own pass/fail assertion, its
own browser instance and its own artifact folder. Tasks are deliberately of
different kinds, because "the loop ran" is not evidence:

    keyboard     scripted W + E          -> does the page/input path work?
    negative     press E out of range    -> does the game refuse the action?
    idempotent   press E twice           -> is the opened state stable?
    vision       Jev decides each step   -> can the model actually do it?
    transfer     same, second scene      -> does it generalise past one look?

Usage:
    python tools/web_task_suite.py --browser edge
    python tools/web_task_suite.py --only keyboard_fortnite,negative_fortnite
    python tools/web_task_suite.py --skip-jev

Exit codes: 0 = every selected task passed, 2 = at least one failed,
            3 = setup error (browser/page missing).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:  # Windows consoles default to cp936; screenshots and models emit UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
for entry in (str(ROOT), str(TOOLS)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import web_chest_test as harness  # noqa: E402
from afk.capture import ScreenCapture  # noqa: E402
from afk.config import load_config  # noqa: E402
from afk.win32 import enable_dpi_awareness, is_foreground, make_input, window_title  # noqa: E402

OUT_ROOT = ROOT / "logs" / "web_tasks"
PAGE = ROOT / "web" / "fortnite_chest.html"


@dataclass
class Task:
    name: str
    scene: str
    driver: str          # keyboard | negative | idempotent | vision
    goal: str
    needs_jev: bool = False


TASKS: list[Task] = [
    Task("keyboard_fortnite", "fortnite", "keyboard",
         "Hold W until the chest is in range, press E once, chest opens."),
    Task("keyboard_dungeon", "dungeon", "keyboard",
         "Same scripted walk + E in the dark dungeon scene.",),
    Task("negative_fortnite", "fortnite", "negative",
         "Press E while still out of range; the chest must stay closed."),
    Task("idempotent_fortnite", "fortnite", "idempotent",
         "Open the chest, press E again; it must stay OPENED and not reset."),
    Task("vision_fortnite", "fortnite", "vision",
         "Jev reads the frame, walks forward, then chooses interact to open the chest.",
         needs_jev=True),
    Task("vision_dungeon", "dungeon", "vision",
         "Jev repeats the task in a completely different scene (transfer test).",
         needs_jev=True),
]


@dataclass
class TaskResult:
    name: str
    scene: str
    driver: str
    goal: str
    passed: bool = False
    detail: str = ""
    seconds: float = 0.0
    steps: list[dict] = field(default_factory=list)
    out_dir: str = ""
    first_png: str = ""
    last_png: str = ""
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name, "scene": self.scene, "driver": self.driver,
            "goal": self.goal, "passed": self.passed, "detail": self.detail,
            "seconds": round(self.seconds, 2), "steps": self.steps,
            "out_dir": self.out_dir, "first_png": self.first_png,
            "last_png": self.last_png, "error": self.error,
        }


class Ctx:
    def __init__(self, hwnd, inputs, capture, out_dir, log, cfg, args, t0):
        self.hwnd = hwnd
        self.inputs = inputs
        self.capture = capture
        self.out_dir = out_dir
        self.log = log
        self.cfg = cfg
        self.args = args
        self.t0 = t0
        self.steps: list[dict] = []

    def snap(self, label: str, plan_line: str = "", reason: str = "") -> str:
        index = len(self.steps) + 1
        _frame, png = harness.grab_step(self.capture, self.hwnd, self.out_dir, index)
        title = window_title(self.hwnd)
        self.steps.append({
            "index": index,
            "time": harness.mmss(time.monotonic() - self.t0),
            "title": title,
            "plan_line": plan_line or label,
            "reason": reason or label,
            "png": png,
        })
        self.log(f"[{index}] {harness.mmss(time.monotonic() - self.t0)} "
                 f"title={title!r} | {plan_line or label}")
        return title


def task_keyboard(ctx: Ctx) -> tuple[bool, str]:
    return harness.run_baseline(ctx.hwnd, ctx.inputs, ctx.capture, ctx.out_dir,
                                ctx.log, ctx.steps, ctx.t0)


def task_negative(ctx: Ctx) -> tuple[bool, str]:
    """E out of range must be a no-op: the page refuses instead of opening."""
    title = ctx.snap("spawn")
    if "OPENED" in title:
        return False, "chest was already open at spawn; the negative test is meaningless"
    if "IN RANGE" in title:
        return False, ("player already spawns in range, so pressing E proves nothing; "
                       "move the spawn further away")
    if not harness.ensure_focus(ctx.hwnd, ctx.log):
        return False, "lost foreground focus before pressing E"
    ctx.log("[negative] pressing E while the title says 'far'")
    ctx.inputs.press("e", 0.12)
    time.sleep(1.2)
    title = ctx.snap("pressed E out of range")
    ctx.steps[-1]["plan_line"] = "press E while far (expected: no-op)"
    if "OPENED" in title:
        return False, f"E opened the chest from out of range; title={title!r}"
    if "IN RANGE" in title:
        return False, f"player drifted into range during the test; title={title!r}"
    return True, f"E out of range was ignored; title stayed {title!r}"


def task_idempotent(ctx: Ctx) -> tuple[bool, str]:
    """Open via the keyboard path, then press E again and confirm stability."""
    ok, detail = harness.run_baseline(ctx.hwnd, ctx.inputs, ctx.capture, ctx.out_dir,
                                      ctx.log, ctx.steps, ctx.t0)
    if not ok:
        return False, f"could not open the chest first: {detail}"
    time.sleep(0.4)
    if not harness.ensure_focus(ctx.hwnd, ctx.log):
        return False, "lost foreground focus before the second E"
    ctx.log("[idempotent] pressing E again on an opened chest")
    ctx.inputs.press("e", 0.12)
    time.sleep(1.0)
    title = ctx.snap("second E on opened chest")
    ctx.steps[-1]["plan_line"] = "press E again (expected: stays OPENED)"
    if "OPENED" not in title:
        return False, f"second E changed the state; title={title!r}"
    return True, "chest stayed OPENED after a second E (no reset, no crash)"


def task_vision(ctx: Ctx) -> tuple[bool, str]:
    state: dict = {}
    ok, detail = harness.run_jev(ctx.hwnd, ctx.inputs, ctx.capture, ctx.cfg, ctx.out_dir,
                                 ctx.log, ctx.steps, ctx.t0, ctx.args, state)
    if state:
        ctx.log(f"[vision] calls={state.get('calls')} cost=${state.get('cost', 0):.6f}")
    return ok, detail


RUNNERS = {
    "keyboard": task_keyboard,
    "negative": task_negative,
    "idempotent": task_idempotent,
    "vision": task_vision,
}


def run_one(task: Task, args) -> TaskResult:
    result = TaskResult(name=task.name, scene=task.scene, driver=task.driver, goal=task.goal)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUT_ROOT / f"{stamp}_{task.name}"
    out_dir.mkdir(parents=True, exist_ok=True)
    result.out_dir = str(out_dir)
    log = harness.Reporter(out_dir)
    t0 = time.monotonic()
    hwnd = None
    proc = None
    profile = None
    stderr_file = None
    capture = None

    log("=" * 78)
    log(f"TASK {task.name}  scene={task.scene}  driver={task.driver}")
    log(f"GOAL {task.goal}")
    log("=" * 78)

    try:
        exe = harness.find_browser(args.browser)
        proc, profile, stderr_file = harness.launch_browser(exe, task.scene, out_dir, log)
        hwnd, _cls, _title = harness.locate_window(proc.pid, log)
        harness.fit_window(hwnd, log)
        time.sleep(0.8)

        cfg = load_config(ROOT / "config.json")
        capture = ScreenCapture(max_width=cfg.capture.max_width)
        inputs = make_input(cfg, hwnd, random.Random())

        ctx = Ctx(hwnd, inputs, capture, out_dir, log, cfg, args, t0)
        passed, detail = RUNNERS[task.driver](ctx)
        result.passed = bool(passed)
        result.detail = detail
        result.steps = ctx.steps
        pngs = [s["png"] for s in ctx.steps if s.get("png")]
        result.first_png = pngs[0] if pngs else ""
        result.last_png = pngs[-1] if pngs else ""
    except harness.SetupError as exc:
        result.error = f"setup: {exc}"
        result.detail = result.error
        log(f"[setup-error] {exc}")
    except Exception as exc:  # noqa: BLE001 - a suite must survive one bad task
        result.error = f"{type(exc).__name__}: {exc}"
        result.detail = result.error
        log(f"[error] {result.error}")
        log(traceback.format_exc())
    finally:
        result.seconds = time.monotonic() - t0
        if capture is not None:
            capture.close()
        harness.force_close(hwnd, proc)
        if stderr_file is not None:
            try:
                stderr_file.close()
            except Exception:
                pass
        harness.remove_profile(profile, log)
        log(f"VERDICT: {'PASS' if result.passed else 'FAIL'} ({result.seconds:.1f}s) {result.detail}")
        try:
            (out_dir / "decisions.json").write_text(
                json.dumps({"task": task.name, "scene": task.scene,
                            "driver": task.driver, "passed": result.passed,
                            "detail": result.detail, "steps": result.steps},
                           ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            log(f"[warn] could not write decisions.json: {exc}")
        log.flush()
    return result


def _rel(path: str, base: Path) -> str:
    if not path:
        return ""
    try:
        return Path(path).relative_to(base).as_posix()
    except ValueError:
        return Path(path).as_posix()


def build_suite_report(out_dir: Path, results: list[TaskResult], args, browser: str) -> Path:
    base = out_dir
    rows = []
    cards = []
    for res in results:
        verdict = "PASS" if res.passed else "FAIL"
        colour = "#3ddc84" if res.passed else "#ff5d5d"
        detail = (res.detail or res.error or "").replace("<", "&lt;").replace(">", "&gt;")
        shots = []
        for step in res.steps[:1] + res.steps[-1:]:
            rel = _rel(step.get("png", ""), base)
            if rel:
                shots.append(
                    f'<figure><img src="{rel}" alt="step"><figcaption>'
                    f'#{step["index"]} {step["title"]}</figcaption></figure>')
        steps_html = "".join(
            f'<tr><td>{s["index"]}</td><td>{s["time"]}</td>'
            f'<td><code>{s["title"]}</code></td>'
            f'<td><code>{s["plan_line"]}</code></td>'
            f'<td>{s["reason"]}</td></tr>'
            for s in res.steps
        )
        cards.append(f"""
    <section class="task {'ok' if res.passed else 'bad'}">
      <header>
        <h2>{res.name}</h2>
        <span class="badge" style="background:{colour}">{verdict}</span>
        <span class="meta">scene={res.scene} · driver={res.driver} · {res.seconds:.1f}s</span>
      </header>
      <p class="goal">{res.goal}</p>
      <p class="detail">{detail}</p>
      <div class="shots">{''.join(shots)}</div>
      <details><summary>steps ({len(res.steps)})</summary>
        <table><thead><tr><th>#</th><th>time</th><th>window title</th>
        <th>action</th><th>reason</th></tr></thead><tbody>{steps_html}</tbody></table>
      </details>
    </section>""")
        rows.append(
            f'<tr class="{"ok" if res.passed else "bad"}"><td>{res.name}</td>'
            f'<td>{res.scene}</td><td>{res.driver}</td>'
            f'<td class="v">{verdict}</td><td>{detail}</td>'
            f'<td>{res.seconds:.1f}s</td></tr>')

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    overall = "ALL TASKS PASSED" if passed == total else f"{total - passed} TASK(S) FAILED"
    colour = "#3ddc84" if passed == total else "#ff5d5d"
    doc = f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>Web 3D task suite — {overall}</title>
<style>
:root{{color-scheme:dark}}
body{{margin:0;background:#080b12;color:#e8edf7;font:15px/1.6 "Segoe UI","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:34px 26px 70px}}
h1{{font-size:30px;margin:0 0 6px}}
.sub{{color:#8b97ad;font-size:13px;margin-bottom:26px}}
.hero{{border:1px solid #1e2637;background:linear-gradient(160deg,#111826,#0b1018);border-radius:16px;padding:22px 24px;margin-bottom:26px}}
.hero .big{{font-size:26px;font-weight:700;color:{colour};margin-bottom:6px}}
.hero .stat{{color:#9fb0c9;font-size:14px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid #1b2332;vertical-align:top}}
th{{color:#7f8ca3;font-weight:600;text-transform:uppercase;letter-spacing:.06em;font-size:11px}}
td.v{{font-weight:700}}
tr.ok td.v{{color:#3ddc84}} tr.bad td.v{{color:#ff5d5d}}
code{{font-family:Consolas,"Cascadia Mono",monospace;font-size:12px;color:#c7d4ea}}
.task{{border:1px solid #1e2637;border-radius:16px;padding:20px 22px;margin:18px 0;background:#0d121b}}
.task.ok{{border-left:4px solid #3ddc84}} .task.bad{{border-left:4px solid #ff5d5d}}
.task h2{{font-size:19px;margin:0;display:inline-block;margin-right:12px}}
.badge{{display:inline-block;color:#06110a;font-weight:800;font-size:11px;letter-spacing:.08em;
padding:3px 9px;border-radius:999px;vertical-align:2px}}
.meta{{color:#7f8ca3;font-size:12px;margin-left:10px}}
.goal{{color:#9fb0c9;margin:8px 0 4px}}
.detail{{margin:4px 0 14px;font-family:Consolas,monospace;font-size:13px;color:#d7e2f4}}
.shots{{display:flex;gap:14px;flex-wrap:wrap;margin:12px 0}}
figure{{margin:0;flex:1 1 420px;max-width:560px}}
figure img{{width:100%;border-radius:10px;border:1px solid #243049;display:block}}
figcaption{{color:#7f8ca3;font-size:11px;margin-top:6px}}
details summary{{cursor:pointer;color:#8fa4c4;font-size:13px;margin-top:8px}}
</style></head><body><div class="wrap">
  <h1>多任务 3D 游戏测试</h1>
  <div class="sub">本地 first-person 3D 页面 · 真实 Chromium 窗口 · SendInput 注入 ·
  状态以窗口标题为准 · {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
  <div class="hero">
    <div class="big">{overall}</div>
    <div class="stat">{passed}/{total} passed · browser={browser} ·
    page=web/fortnite_chest.html · command:
    <code>python tools/web_task_suite.py {' '.join(args.argv)}</code></div>
  </div>
  <table><thead><tr><th>task</th><th>scene</th><th>driver</th><th>verdict</th>
  <th>detail</th><th>time</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
  {''.join(cards)}
</div></body></html>"""
    path = out_dir / "suite_report.html"
    path.write_text(doc, encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--browser", choices=["edge", "chrome"], default="edge")
    p.add_argument("--only", default="", help="comma separated task names")
    p.add_argument("--skip-jev", action="store_true", help="skip tasks that need the model")
    p.add_argument("--steps", type=int, default=12, help="max Jev decisions per vision task")
    p.add_argument("--show", action="store_true", help="keep the last browser open")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.argv = list(argv) if argv is not None else sys.argv[1:]
    enable_dpi_awareness()

    if not PAGE.exists():
        print(f"page missing: {PAGE}", file=sys.stderr)
        return 3

    selected = TASKS
    if args.only:
        wanted = {name.strip() for name in args.only.split(",") if name.strip()}
        selected = [t for t in selected if t.name in wanted]
        missing = wanted - {t.name for t in selected}
        if missing:
            print(f"unknown task(s): {', '.join(sorted(missing))}", file=sys.stderr)
            return 3
    if args.skip_jev:
        selected = [t for t in selected if not t.needs_jev]

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suite_dir = OUT_ROOT / f"{stamp}_suite"
    suite_dir.mkdir(parents=True, exist_ok=True)

    print(f"suite: {len(selected)} task(s) -> {suite_dir}")
    results: list[TaskResult] = []
    for task in selected:
        results.append(run_one(task, args))

    payload = {
        "started": stamp,
        "browser": args.browser,
        "page": str(PAGE),
        "tasks": [r.as_dict() for r in results],
        "passed": sum(1 for r in results if r.passed),
        "total": len(results),
    }
    (suite_dir / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report = build_suite_report(suite_dir, results, args, args.browser)

    print()
    print(f"{'task':<24}{'scene':<11}{'driver':<12}verdict")
    print("-" * 58)
    for res in results:
        print(f"{res.name:<24}{res.scene:<11}{res.driver:<12}"
              f"{'PASS' if res.passed else 'FAIL'}  {res.detail}")
    print("-" * 58)
    print(f"{payload['passed']}/{payload['total']} passed")
    print(f"report: {report}")
    return 0 if payload["passed"] == payload["total"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
