"""`calibrate`: run the real question set on one frame and produce a visual report."""
from __future__ import annotations

import html
import logging
import shutil
from datetime import datetime
from pathlib import Path

from .capture import Frame, ScreenCapture
from .config import APP_DIR, Config
from .geometry import Rect, box_center_screen
from .jev import JevClient, Observation
from .png import draw_rect
from .screens import questions_for
from .win32 import client_rect as get_client_rect
from .screen_target import ScreenTarget

log = logging.getLogger(__name__)


def _resolve_dir(cfg: Config) -> Path:
    directory = Path(cfg.logging.dir)
    if not directory.is_absolute():
        directory = APP_DIR / directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _status(obs: Observation, name: str, cfg: Config) -> tuple[bool, str]:
    box = obs.usable_box(
        name,
        min_confidence=cfg.confidence.box,
        min_presence=cfg.confidence.presence,
        allow_null=cfg.confidence.allow_null,
        null_value=cfg.confidence.null_value,
        max_side=cfg.confidence.max_box_side,
    )
    if box is not None:
        return True, "OK"
    _, conf = obs.raw_box(name)
    if conf != conf:
        return False, "rejected (null confidence)"
    if conf < cfg.confidence.box:
        return False, f"rejected (conf {conf:.2f} < {cfg.confidence.box:.2f})"
    return False, "rejected (presence/size)"


def calibrate(cfg: Config, profile: str, image: str | None = None) -> Path:
    if image:
        frame = Frame.from_png_file(image)
        source = f"image {image}"
    else:
        # Screen-only build: no window lookup, just the configured rectangle
        # (or the whole screen).
        target = ScreenTarget(cfg)
        rect = target.client_rect()
        capture = ScreenCapture(
            cfg.capture.max_width, cfg.capture.inset_left, cfg.capture.inset_top,
            cfg.capture.inset_right, cfg.capture.inset_bottom,
        )
        frame = capture.grab(rect)
        source = f"screen rect={rect}"

    client = JevClient(cfg)
    questions = questions_for(profile)
    obs = client.ask(frame, questions, context=f"Calibration frame for the '{profile}' profile.")
    client.close()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = _resolve_dir(cfg)
    base = f"calibrate_{profile}_{stamp}"
    png_path = out_dir / f"{base}.png"
    html_path = out_dir / f"{base}.html"

    if frame.rgb is not None:
        rgb = bytearray(frame.rgb)
        for name, answer in obs.answers.items():
            if answer.get("type") != "box":
                continue
            from .geometry import parse_box

            box = parse_box(answer.get("box"))
            if box is None:
                continue
            ok, _ = _status(obs, name, cfg)
            draw_rect(rgb, frame.width, frame.height, box,
                      color=(40, 220, 120) if ok else (255, 70, 70), thickness=3)
        from .capture import Frame as FrameCls

        out_frame = FrameCls(frame.width, frame.height, rgb, frame.rect, frame.scale,
                             frame.captured_at)
        out_frame.save_png(png_path)
    else:
        shutil.copyfile(image, png_path)

    rows = []
    overlays = []
    for name, answer in obs.answers.items():
        kind = answer.get("type")
        detail = ""
        if kind == "box":
            box = answer.get("box") or {}
            conf = answer.get("confidence")
            ok, why = _status(obs, name, cfg)
            detail = (f"({box.get('left', 0):.2f},{box.get('top', 0):.2f})-"
                      f"({box.get('right', 0):.2f},{box.get('bottom', 0):.2f}) conf={conf} {why}")
            left = float(box.get("left", 0)) * 100
            top = float(box.get("top", 0)) * 100
            width = (float(box.get("right", 0)) - float(box.get("left", 0))) * 100
            height = (float(box.get("bottom", 0)) - float(box.get("top", 0))) * 100
            color = "#28dc78" if ok else "#ff4646"
            overlays.append(
                f'<div class="box" style="left:{left:.2f}%;top:{top:.2f}%;'
                f'width:{width:.2f}%;height:{height:.2f}%;border-color:{color}">'
                f'<span>{html.escape(name)} {conf}</span></div>'
            )
        elif kind == "choice":
            detail = f"{answer.get('choice')} conf={answer.get('confidence')}"
        elif kind == "noul":
            detail = f"{answer.get('noul'):.3f}"
        rows.append(
            f"<tr><td>{html.escape(name)}</td><td>{html.escape(str(kind))}</td>"
            f"<td>{html.escape(detail)}</td></tr>"
        )

    page = f"""<!doctype html>
<meta charset="utf-8">
<title>Fortnite AFK calibration - {html.escape(profile)}</title>
<style>
 body {{ background:#141821; color:#e8edf5; font:14px/1.5 "Segoe UI",Arial,sans-serif; margin:24px; }}
 h1 {{ font-size:20px; font-weight:600; }}
 .meta {{ color:#93a1b5; margin-bottom:16px; }}
 .frame {{ position:relative; display:inline-block; max-width:100%; border:1px solid #2b3444; }}
 .frame img {{ display:block; max-width:100%; height:auto; }}
 .box {{ position:absolute; border:2px solid #28dc78; box-sizing:border-box; }}
 .box span {{ position:absolute; left:0; top:-20px; background:#000c; color:#fff;
             font:12px/18px Consolas,monospace; padding:0 5px; white-space:nowrap; }}
 table {{ border-collapse:collapse; margin-top:18px; min-width:680px; }}
 th,td {{ text-align:left; padding:5px 12px; border-bottom:1px solid #263041; }}
 th {{ color:#93a1b5; font-weight:600; }}
 .note {{ margin-top:14px; color:#93a1b5; }}
</style>
<h1>Fortnite AFK calibration &mdash; {html.escape(profile)}</h1>
<div class="meta">model={html.escape(obs.model)} &middot; source={html.escape(source)}
 &middot; frame={frame.width}x{frame.height} &middot; screen={html.escape(obs.screen)}
 ({obs.screen_confidence:.2f}) &middot; cost=${client.total_cost:.6f}</div>
<div class="frame"><img src="{html.escape(png_path.name)}" alt="calibration frame">{''.join(overlays)}</div>
<table><tr><th>question</th><th>type</th><th>answer</th></tr>{''.join(rows)}</table>
<div class="note">Green = the script would click this box; red = rejected by confidence/presence/size.
Tune <code>confidence.box</code> and <code>confidence.presence</code> in config.json if a real
button is rejected, or lower <code>capture.max_width</code> if small labels are missed.</div>
"""
    html_path.write_text(page, encoding="utf-8")

    print(f"profile={profile} source={source} frame={frame.width}x{frame.height}")
    print(f"screen={obs.screen} conf={obs.screen_confidence:.3f}")
    for name, answer in obs.answers.items():
        kind = answer.get("type")
        if kind == "box":
            ok, why = _status(obs, name, cfg)
            box = answer.get("box") or {}
            print(f"  {name:24s} box  conf={answer.get('confidence')}  {why}")
            if ok and frame.rgb is not None:
                from .geometry import parse_box

                parsed = parse_box(box)
                if parsed:
                    x, y = box_center_screen(parsed, frame.rect)
                    print(f"  {'':24s} click point: ({x}, {y})")
        elif kind == "choice":
            print(f"  {name:24s} choice={answer.get('choice')} conf={answer.get('confidence')}")
        elif kind == "noul":
            print(f"  {name:24s} noul={answer.get('noul'):.3f}")
    print(f"report: {html_path}")
    print(f"image:  {png_path}")
    return html_path
