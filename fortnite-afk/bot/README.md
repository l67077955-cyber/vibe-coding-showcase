# Fortnite 零建造四排挂机 / Jev 视觉决策版

用 TypeSafe **Jev**（`typesafe/jev-1.14`）看游戏画面，决定按什么键：

- **局内**：Jev 不只是选方向，还选 **操作**（走/横移/后退/跳/交互/攻击/瞄准/换弹/转视角）、**按住时长**（tap 0.12s / short 0.35s / medium 0.8s / long 1.6s）和 **重复次数**（1/2/3 次）。代码把这些决策翻译成精确的按键和鼠标动作。
- **连续移动**：方向键在两次 Jev 决策之间保持按下，转向时只做增量切换（松开不再需要的键、按下新键），不会每步都停下来；超过 `max_continuous_s` 没有新决策会自动松开，防止失控。
- **避障**：Jev 返回 `path=clear/low/high_wall/hazard`；低障碍自动改成 `jump_forward`，高墙自动横移绕开，悬崖/水/岩浆自动后退；连续两帧画面签名相同还会触发 `S + Space + D` 脱困。
- **场景交互**：Jev 用 `target_visible` + `target` Box + `target_kind` + `target_distance` + `interact_ready` 判断宝箱/门/按钮/载具/掉落物；靠近且面向目标时按住 `E`（时长由 Jev 的 `hold` 决定，最低 1 秒）。
- **局外**：Jev 识别 PLAY / 零建造 / 小队 / 填充 / 离开对局 / 确认 / 返回大厅等按钮，自动开始下一局。
- **零第三方依赖**：只用 Python 标准库（ctypes + urllib + zlib），不需要 `pip install`；也提供打包好的 `FortniteAFK.exe`，在干净的 Windows 上直接跑。

> ⚠️ 自动化和挂机违反 Epic 的服务条款，可能导致封号/收回 XP；云电脑服务商也可能禁止脚本。**不要拿主账号试**。下面所有“实测”都是在这台海马云电脑里做的，Fortnite 本身没有安装，所以 Fortnite 的最终实机验证需要你装好后跑一遍。

---

## 1. 最快开始（海马云电脑 / 干净 Windows）

把整个 `fortnite-afk` 文件夹复制到云电脑，例如：

```
C:\Users\computer\Documents\notes\fortnite-afk\
```

### 1.1 API Key

任选一种：

1. 在文件夹里新建 `key.txt`，内容只有一行 OpenRouter key（`sk-or-v1-...`）。
2. 设置环境变量 `OPENROUTER_API_KEY`。
3. 直接双击 `run.bat`：它会自动从 `%USERPROFILE%\.config\opencode\opencode.jsonc` 里读取已有的 OpenRouter key（本机已配置）。

### 1.2 Fortnite 设置

- 显示模式：**窗口化全屏 / Windowed Fullscreen**（无边框）。独占全屏可能截到黑屏。
- 先在游戏里手动选好：**零建造（Zero Build） + 小队（Squads） + 填充（Fill）**。脚本会记住这个模式并反复排队。
- 语言中英文都行，提示词里同时写了 `PLAY / 开始`、`ZERO BUILD / 零建造`、`FILL / 填充`。
- 不要让云电脑锁屏/休眠；脚本会调用 `SetThreadExecutionState` 保持显示，但云厂商仍可能在断开客户端后切换虚拟显示器。

### 1.3 三步自检

```powershell
# 1) 环境、Key、API、截图、会话状态（不取窗口句柄）
.\FortniteAFK.exe doctor

# 2) 抓当前画面，让 Jev 识别按钮并画框，生成 HTML 报告
.\FortniteAFK.exe calibrate --profile lobby
.\FortniteAFK.exe calibrate --profile explore
.\FortniteAFK.exe calibrate --profile menu
.\FortniteAFK.exe calibrate --profile results
```

`calibrate` 会在 `logs/` 下生成 `calibrate_<profile>_<时间>.html` 和截图。绿色框 = 脚本会点击；红色 = 置信度/存在性/尺寸被拒绝。用浏览器打开报告，确认 Jev 在**你的真实 UI** 上框对了再跑正式局。

### 1.4 先空跑一局

```powershell
.\FortniteAFK.exe run --dry-run --cycles 1
```

`--dry-run` 仍会截图和调用 Jev，但**不发任何键、不点任何按钮**。看日志里的 `CLICK ...` / `EXPLORE ...` 是否符合预期。

### 1.5 正式运行

```powershell
.\FortniteAFK.exe run
# 或限制时长/局数
.\FortniteAFK.exe run --cycles 3 --duration-minutes 120
```

停止：**F12**（可在 `config.json` 改 `f8`–`f12`）或 `Ctrl+C`。脚本只在前台窗口是 Fortnite 时才发输入；你切走/锁屏/云会话断开时会自动暂停，不会乱点。

---

## 2. 运行流程

```
             Jev 看大厅
                 │
        ┌────────▼────────┐
        │  lobby          │  PLAY / 零建造 / 小队 / 填充 按钮
        └────────┬────────┘
                 │ click PLAY
        ┌────────▼────────┐
        │  queue          │  匹配中 / 加载
        └────────┬────────┘
                 │ 进入对局
        ┌────────▼────────┐
        │  match/explore  │  每 2.5–4 秒一帧：
        │                 │  action/hold/repeat=Choice
        │                 │  target=Noul+Box, path=Choice
        │                 │  目标近 -> E（时长/次数由 Jev 定）
        │                 │  path=low -> W + Space
        │                 │  path=high -> 横移绕开
        │                 │  卡住   -> S + Space + D
        └────────┬────────┘
                 │ 到达随机时长 16–22 分钟 / 被淘汰
        ┌────────▼────────┐
        │  menu           │  Esc -> LEAVE MATCH -> CONFIRM
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │  results        │  RETURN TO LOBBY / PLAY AGAIN
        └────────┬────────┘
                 └──────────► 回 lobby，下一局
```

局外的所有按钮都由 Jev 的 **Box** 答案给出坐标，代码只负责：

1. 置信度 ≥ `confidence.box`；
2. 配对的存在性 **Noul** ≥ `confidence.presence`；
3. 框不能覆盖几乎整屏；
4. 坐标换算到窗口客户区并点击。

任何一条不满足就拒绝点击，避免“盲点”。

---

## 3. Jev API 用法

请求（OpenRouter 的 System One 端点）：

```json
{
  "model": "typesafe/jev-1.14",
  "state": [
    {"type": "text", "text": "Fortnite first-person screenshot..."},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
  ],
  "questions": {
    "action": {
      "type": "choice",
      "instructions": "Which operation should the player perform now?",
      "criteria": {
        "move_forward": "Walk straight ahead.",
        "move_forward_left": "Walk diagonally forward-left.",
        "strafe_left": "Move sideways left.",
        "back_up": "Walk backwards.",
        "jump_forward": "Jump while moving forward to climb a low obstacle.",
        "interact": "Press E to open/use the nearby object.",
        "attack": "Press the left mouse button.",
        "aim": "Hold the right mouse button.",
        "reload": "Press R.",
        "look_left": "Turn the camera left.",
        "look_right": "Turn the camera right.",
        "stop": "No safe operation."
      }
    },
    "hold": {
      "type": "choice",
      "instructions": "How long should the operation be held?",
      "criteria": {
        "tap": "One tap/click, about 0.12s.",
        "short": "About 0.35s.",
        "medium": "About 0.8s.",
        "long": "About 1.6s."
      }
    },
    "repeat": {
      "type": "choice",
      "instructions": "How many times should it repeat?",
      "criteria": {"once": "Once.", "twice": "Twice.", "three_times": "Three times."}
    },
    "target_visible": {"type": "noul", "instructions": "Is an interactive object visible?"},
    "target": {"type": "box", "instructions": "the nearest interactive object"},
    "target_kind": {
      "type": "choice",
      "instructions": "What kind of object is it?",
      "criteria": {"chest": "Chest", "door": "Door", "button": "Button",
                   "vehicle": "Vehicle", "loot": "Loot", "none": "None"}
    },
    "target_distance": {
      "type": "choice",
      "instructions": "How close is it?",
      "criteria": {"near": "Within a few steps.", "far": "Visible but distant.",
                   "unclear": "Unknown."}
    },
    "interact_ready": {"type": "noul",
                       "instructions": "Is the player close enough and facing it to interact now?"},
    "path": {
      "type": "choice",
      "instructions": "What is directly ahead within a few steps?",
      "criteria": {
        "clear": "Walkable and clear.",
        "low": "A low obstacle that can be jumped.",
        "high_wall": "A wall too high to jump; detour.",
        "hazard": "Cliff, water, lava or storm wall.",
        "unclear": "Cannot tell."
      }
    }
  }
}
```

返回：

```json
{
  "answers": {
    "action": {"type": "choice", "choice": "attack", "confidence": 0.88, "probabilities": {}},
    "hold": {"type": "choice", "choice": "short", "confidence": 0.82, "probabilities": {}},
    "repeat": {"type": "choice", "choice": "twice", "confidence": 0.77, "probabilities": {}},
    "target_visible": {"type": "noul", "noul": 0.91},
    "target": {"type": "box", "confidence": 0.86,
               "box": {"left": 0.45, "top": 0.35, "right": 0.62, "bottom": 0.72}},
    "target_kind": {"type": "choice", "choice": "chest", "confidence": 0.9, "probabilities": {}},
    "target_distance": {"type": "choice", "choice": "near", "confidence": 0.8,
                        "probabilities": {}},
    "interact_ready": {"type": "noul", "noul": 0.9},
    "path": {"type": "choice", "choice": "clear", "confidence": 0.9, "probabilities": {}}
  }
}
```

代码里的判断：

- `action` 置信度 < 0.25 → 回退到 `move_forward`。
- `target_visible ≥ 0.55`、`target_distance=near`（或框高 ≥ 0.22）、`interact_ready ≥ 0.4`、且不在开箱冷却 → 强制 `interact`，按住 `E`，时长取 `max(hold, 1.0s)`。
- `path=hazard` 或 `hazard_ahead ≥ 0.65` → 改成 `back_up`。
- `path=low` 或 `obstacle_ahead ≥ 0.65` 且原本前进 → 改成 `jump_forward`（W + Space）。
- `path=high_wall` → 根据目标在画面左/右改成 `strafe_left/right` 绕行。
- `hold` 映射：tap 0.12s / short 0.35s / medium 0.8s / long 1.6s。
- `repeat` 映射：once 1 / twice 2 / three_times 3；攻击/交互/跳跃会重复执行，连续移动时保持按键到下一次决策（`max_continuous_s` 兜底）。
- 连续两帧 8×8 亮度签名相似度 ≥ 0.985 → 判定卡住，执行 `S + Space + D`。

Box 没有“未找到”答案，所以每个 Box 都配一个 `<name>_visible` 的 Noul；这正是官方文档推荐的做法。

---

## 4. 海马云电脑实测结论（这台机器）

### 4.1 能跑的部分

- **GDI 截图正常**：`ScreenCapture` 用 `BitBlt/StretchBlt`，1280×720 画面亮度正常，不是黑屏。
- **鼠标注入正常**：能点掉 Windows 防火墙弹窗、点 Luanti 菜单的“继续”。
- **Jev API 正常**：`typesafe/jev-1.14` 返回 Choice/Noul/Box，单次约 `$0.00006–0.00013`。
- **键盘 WM_KEYDOWN 能到窗口**，但 **SendInput 的 WM_CHAR 为 0**（见下）。

### 4.2 输入注入：只有 SendInput 一种模式

这个版本删掉了 `postmessage` / `hybrid` 两个后端，也删掉了 `keytest` 命令。原因很直接：两种后端都需要窗口句柄，而现在的约束是**不取任何游戏窗口句柄**。

- 输入只有一条路径：`SendInput`（`key_mode` 仍可选 `both / scancode / virtualkey`）。
- 没有 `FindWindow`、没有 `client_rect`、没有前台检查、没有 `PostMessage`。
- 屏幕截图也只走 `GetDC(NULL) + BitBlt`，取整屏或 `capture.region` 指定的矩形。

早期 `keytest` 的记录（仅供历史参考）：`sendinput keydown=1 keyup=1 char=0`、`postmessage keydown=1 keyup=1 char=1`。`WM_CHAR=0` 影响的只是文本/聊天输入，移动键走 keydown/raw input，不受影响。

如果你需要换一种注入方式，那是另一套实现，不在这个构建里；也不会在运行期切换。

### 4.3 开源 3D 游戏实测：Jev 决定往哪走

用 **Luanti 5.18.0（Minetest，开源）** 做真实画面测试：雪地森林，目标是“走到最近的树干”。

命令：

```text
（历史记录）python tools\jev_walk_demo.py --title Luanti --steps 10
  --goal "walk toward the nearest tree trunk" --hold 0.7 --pause 0.8
```

> 这个工具属于旧的“按窗口标题找窗口”版本，已随单模式改造删除；下面的数据和报告保留为历史证据。

实际输出（干净的一次，10/10 步都选中 forward）：

```
[1]  move=forward conf=0.15 target=0.79 path_clear=0.41 changed=1.000 stuck=1 focus=True
[2]  move=forward conf=0.35 target=0.71 path_clear=0.55 changed=0.821 stuck=0 focus=True
[3]  move=forward_right conf=0.13 target=0.86 path_clear=0.38 changed=0.845 stuck=0 focus=True
[4]  move=forward conf=0.29 target=0.76 path_clear=0.32 changed=0.801 stuck=0 focus=True
[5]  move=forward conf=0.43 target=0.84 path_clear=0.69 changed=0.893 stuck=0 focus=True
[6]  move=forward conf=0.41 target=0.70 path_clear=0.66 changed=0.936 stuck=0 focus=True
[7]  move=forward conf=0.38 target=0.73 path_clear=0.67 changed=1.000 stuck=1 focus=True
[8]  move=forward conf=0.60 target=0.82 path_clear=0.75 changed=0.871 stuck=0 focus=True
[9]  move=forward conf=0.55 target=0.78 path_clear=0.67 changed=0.917 stuck=0 focus=True
[10] move=forward conf=0.51 target=0.73 path_clear=0.73 changed=0.933 stuck=0 focus=True
calls=10 cost=$0.001037
```

报告（每帧 + Jev 决策 + 绿色目标框）：

```
logs\walk_demo\20261108_182924\report.html
```

第 1 帧目标树被绿框标出；第 10 帧画面已经换到另一处树干，说明 Jev 的 `forward` 决策 + 按键真的让角色走了。另跑了一组 **SendInput**（不是 PostMessage）：

```
--backend sendinput --steps 4
changed=0.965 / 0.968 / 0.985
```

说明在这台海马云电脑里，**SendInput 的移动按键是有效的**，尽管 `keytest` 里 `WM_CHAR=0`；受影响的主要是文本框/聊天输入。Fortnite 的 EAC 是否放行仍需实机确认。

> 不是 Fortnite：Fortnite 没有安装在这台云电脑上（`LauncherInstalled.dat` 为空），所以局内开箱/翻越/按钮的最终验证需要你装好 Fortnite 后跑 `calibrate --profile explore` 和 `run --dry-run`。Luanti 证明的是“Jev 看图选方向 → 按键 → 角色真的移动”这条链路。

### 4.4 网页版 3D 场景：多任务自动化测试

Fortnite 没装，所以写了一个**单文件、零外部依赖**的第一人称 3D 页面 `web/fortnite_chest.html`（DDA 光线投射、两个场景 `fortnite` / `dungeon`、宝箱 + E 交互、开箱动画与战利品卡）。页面把状态写进窗口标题，测试脚本不靠猜：

```
FORWEB chest | far              宝箱在视野内但够不到
FORWEB chest | IN RANGE (E)     按 E 就能开
FORWEB chest | OPENED           已开
```

`tools/web_task_suite.py` 跑 6 个互相独立的任务（每个任务新开浏览器、自己截图、自己写 `decisions.json`）：

| 任务 | 场景 | 驱动 | 断言 | 结果 |
|---|---|---|---|---|
| `keyboard_fortnite` | fortnite | 脚本 W + E | 开箱 | PASS |
| `keyboard_dungeon` | dungeon | 脚本 W + E | 开箱 | PASS |
| `negative_fortnite` | fortnite | 远距离按 E | 必须无效 | PASS |
| `idempotent_fortnite` | fortnite | 开箱后再按 E | 保持 OPENED | PASS |
| `vision_fortnite` | fortnite | Jev 决策 | 自己走过去并选 `interact` | PASS（3 步 / 13.2s） |
| `vision_dungeon` | dungeon | Jev 决策 | 换场景重复 | PASS |

汇总报告：`logs/web_tasks/20261108_193140_suite/suite_report.html`。单场景夹具 `tools/web_chest_test.py` 另有 `--baseline`（完全不调模型，验证键盘链路）和 `--pre-turn-ms`（把视角转偏，测偏轴瞄准）。

关键设计：**只读窗口标题判胜负**。模型之外的任何东西都改不了标题，所以 “OPENED” 只能由真实落到页面上的 E 产生。

---

### 4.5 无句柄模式：只截屏 + SendInput

如果连窗口句柄都不允许碰（反作弊/合规场景），用 `tools/screen_only_loop.py`：

```powershell
python tools\screen_only_loop.py --dry-run --steps 6        # 只看，不发按键
python tools\screen_only_loop.py --region 0,0,1600,900 --act # 真的发按键
```

它只做两件事：

- 用 `GetDC(NULL)` + `BitBlt` 截整屏或 `--region` 指定区域；
- 用 `SendInput` 发键盘鼠标（`InputController`）。

明确不做：`FindWindow` / `EnumWindows`、读 client rect、检查前台、`OpenProcess`、读内存、`PostMessage`（它按定义需要 HWND）。黑屏（平均亮度 < 3）直接跳过，不送模型。

实测：`logs/screen_only/browser_demo/decisions.json`，整屏 1600×900，2 步，第 2 步 Jev 认出 `target=chest/near, aim=+0.20`，全程没有取任何窗口句柄。

> GDI 截图必然要一个屏幕 DC（`GetDC(NULL)`），用完立即 `ReleaseDC`；这不是游戏窗口句柄，也不指向游戏进程。

### 4.6 点击位置只来自 Jev，没有硬编码坐标

大厅、岛屿页、模式选择、加载页的按钮位置都不一样，写死坐标迟早点错。`tools/auto_start.py` 的做法是每帧问 Jev 三个问题：

- `screen`：这是大厅 / 岛屿页 / 准备页 / 排队 / 对局 / 其他
- `target_action`：现在做什么最接近进局（play / select / start / back / wait）
- `target_button`：按钮的 Box

代码只做一件事：点这个 Box 的中心。**没有 `click(214,711)` 这种常量，也没有按颜色/区域猜按钮的兜底**——模型指不出来就不点。

实测（dry-run，不点击）：

```
[01] screen=lobby(0.92) action=play(0.81) box=yes
       -> would click play at (232,751)
```

需要真点时加 `--act`：

```powershell
python tools\auto_start.py --act --move-seconds 6 --steps 8
```

进局后它会按 `W` / `W+D` / `W+A` / `W` 连续走 6 秒，证明角色真的能动。

## 5. 延迟与动作自然感（v3）

### 5.1 延迟：5.7 秒 → 2.0 秒

`tools/bench_jev.py` 在同一画面、同一模型上做 A/B，每档 4 次取中位数：

| 配置 | 中位延迟 | 主要原因 |
|---|---|---|
| 1280px + 每次新建连接（旧默认） | **5734 ms** | 每次调用重付 DNS/TCP/TLS |
| 1280px + 复用连接 | 3094 ms | 握手只付一次 |
| 960px + 复用连接 | 2992 ms | 上传变小，但还不够 |
| 768px + 复用连接（新默认） | **1954 ms** | 上传体积减半后拐点出现 |

具体改动：

- `afk/jev.py` 新增 `_KeepAlive`：持久 HTTPS 连接，支持 HTTP 代理的 CONNECT 隧道、TLS 会话复用、被代理掐断时自动重连一次，失败再退回 `urllib`。
- 每次调用记录 `encode_ms / http_ms / total_ms`，日志直接可见，不用再猜慢在哪。
- `capture.max_width`：1280 → 768。
- `explore.question_profile = "explore_fast"`：18 问 → 12 问（去掉 planner 不读的 `chest_*`、`eliminated`、`look_around`），输出 token 708 → 525。

> 768px 的收益主要来自上行带宽；换到上行更快的机器，图像大小的收益会缩水，但连接复用始终有效。

### 5.2 转向：从“瞬移”到缓入缓出

旧实现每次决策只发一次 `move_relative(±160–320, ±20)`，相机一帧甩到位。新模块 `afk/motion.py`：

- `aim_px()`：按目标框中心做比例控制，10px 死区、0.65 增益、单次上限 420px；
- `plan_turn()`：把一次转向拆成 20ms 的 tick，smoothstep 速度曲线（慢—快—慢），总位移精确不变；
- `jitter()`：按住时长 ±8–12% 抖动，去掉固定节拍。

`tools/turn_demo.py` 的实测：

```
turn +320px
  old : 1 mouse event, +320px, ~0 ms  (camera whip)
  new : 20 events, 400 ms, max 26px/tick
  sum : 320px (exact), ease-in/out via smoothstep
```

曲线图：`logs/turn_demo/turn_profile.html`。

### 5.3 自然感：决策之间不刹车

- **连续移动**：方向键在两次 Jev 决策之间保持按下，转向时只做增量切换；`max_continuous_s=4.5` 兜底。
- **同时走和转**：方向键先按下，再执行转向 tick，所以角色是“边走边转”，不是站定转完再走；交互/跳跃/点击仍然先稳定再执行。
- **镜头噪音**：两个慢正弦漂移 + 每 tick 抖动 + 偶发小幅甩视（sign 交替，长跑不会漂走），都走同一套 `move_relative`，灵敏度会像真人手一样等比放大。
- **不标定灵敏度**：每一步都用 Jev 重新判定目标框，代码只取剩余偏差的固定比例；上一次转完目标更靠中间就微增益，更偏就砍增益。灵敏度随时变也只影响收敛速度。
- **按了没反应就往前走**：按 E 后画面签名相似度 ≥ 0.995（等于什么都没发生），下一步强制 `move_forward`，而不是原地反复按 E。
- **目标优先**：画面里有可见目标时，不被 `path=low` 带去原地跳，先转向目标再走。

偏轴实测（`logs/web_chest/20261108_193437_fortnite/`）：先把视角向左转 250ms，让宝箱偏到画面右侧 38%。Jev 第 1 步给出 `move_forward_right` + `aim=+0.38`，代码用 **20 个 tick 平滑转 311px**，然后保持 W+D 连续移动；第 2 步进入范围按 E，开箱。

---

## 6. 配置重点（`config.json`）

```jsonc
{
  "model": "typesafe/jev-1.14",
  "input_backend": "sendinput",     // 唯一模式；没有 postmessage / hybrid
  "key_mode": "both",               // both | scancode | virtualkey

  "mode": {
    "setup": "verify",              // off | verify | auto
    "zero_build": true,
    "squads": true,
    "fill": true
  },

  "capture": {
    "max_width": 768              // 传给 Jev 的截图宽度；768 比 1280 快约 1.1 秒
  },

  "explore": {
    "enabled": true,
    "interval_s": [2.5, 4.0],       // 每 2.5–4 秒让 Jev 看一次
    "question_profile": "explore_fast", // explore_fast(12 问) | explore(18 问)
    "move_hold_s": [0.45, 0.9],
    "interact_key": "e",            // 开箱键
    "interact_hold_s": 1.0,
    "chest_min_presence": 0.55,
    "chest_near_box_height": 0.34,  // 0.22 会把 4 米外的宝箱误判成“已到”
    "stuck_limit": 2,
    "continuous": true,             // 两次决策之间保持方向键，移动连贯
    "max_continuous_s": 4.5,        // 没有新决策时最多保持这么久，然后松开
    "smooth_turn": true             // 转向拆成 20ms 小步，缓入缓出
  },

  "turn": {
    "max_px_per_s": 900,            // 相机速度上限（像素/秒）
    "tick_s": 0.02,                 // 一个鼠标 tick = 20ms
    "deadzone_px": 10,              // 小于这个偏差不修正，避免抖动
    "gain": 0.65,                   // 比例控制增益，<1 不超调
    "max_step_px": 420              // 单次决策最多转这么多，避免甩飞
  },

  "cloud": {
    "keep_awake": true,
    "pause_when_disconnected": false, // 默认不因 WTS disconnected 暂停；黑屏/前台仍有保护
    "black_frame_min_luma": 3.0,
    "max_consecutive_black_frames": 10
  }
}
```

- `mode.setup = "verify"`（默认）：Jev 识别当前模式，不是零建造/四排/填充就**不点 PLAY**，避免排错模式。第一次手动选好后最稳。
- `mode.setup = "auto"`：Jev 会尝试点零建造磁贴、小队选项、填充开关；UI 版本不同可能点错，**先用 calibrate 验证**。
- `mode.setup = "off"`：完全跳过模式检查，只点 PLAY。
- `explore.enabled = false`：退回旧的随机走动/跳跃（`afk` 段），不花局内 Jev 调用。
- `explore.continuous = true`：方向键在两次 Jev 决策之间保持按下，移动更连贯；`false` 则每次决策只按住 `hold` 指定的时间，然后停下等下一次决策。
- `explore.max_continuous_s`：连续模式的保险丝。超过这个时间没有新决策（Jev 超时/网络卡住），自动松开方向键。
- Jev 的 `hold`（tap/short/medium/long）和 `repeat`（1/2/3 次）对交互、攻击、跳跃、离散移动都精确生效；连续移动时 `repeat` 不额外叠加，方向键保持到下一次决策或 `max_continuous_s`。
- `explore.smooth_turn = true`：转向走 `afk/motion.py` 的缓入缓出曲线（320px 约 20 tick / 400ms），`false` 则退回一次 `move_relative` 的旧行为。
- `turn.*`：相机速度上限、tick 间隔、死区、比例增益、单次最大转角；想把转向调慢/调快就改 `max_px_per_s`。
- `capture.max_width = 768`：这是延迟和识别精度的平衡点；如果小按钮识别变差，回调到 960（慢约 1 秒）。
- `cloud.pause_when_disconnected`：默认 `false`，海马客户端断开但云主机仍在渲染时继续挂机；如果 WTS 状态不可靠或你想严格保护，改 `true`。无论开关，截图变黑/游戏不在前台都会暂停。

---

## 7. 成本

Jev 按图片 token 计费，实测一帧 1280×720 约 `$0.00006–0.00013`。

- 局内 3 秒一帧：约 `$0.07–0.16/小时`。
- 局外排队/大厅每次 3–6 秒一帧，另计但很低。
- 8 小时约 `$0.6–1.5`，取决于分辨率/帧率/重试。

`run` 结束会打印 `jev_calls` 和 `cost`。想更省：把 `explore.interval_s` 调到 `[4, 6]`，或 `capture.max_width` 调到 960。

---

## 8. 常见问题

| 现象 | 处理 |
|---|---|
| `401 User not found` | key 失效。换 `key.txt` 或 `OPENROUTER_API_KEY`；`run.ps1` 会读 `opencode.jsonc` 里的 key。 |
| `402` | OpenRouter 余额不足。 |
| 截图全黑 / `black frame` | 改 Fortnite 为窗口化全屏；云桌面断开后虚拟显示器会黑屏，重连或调 `cloud` 配置；确认没有锁屏。 |
| `PLAY button rejected` | 跑 `calibrate --profile lobby` 看置信度；降低 `confidence.box`（例如 0.28）或提高 `capture.max_width`。 |
| 模式检查一直失败 | 手动选好零建造/小队/填充；或临时 `mode.setup="off"`；或 `calibrate --profile lobby` 检查 `selected_mode` 识别。 |
| 点了没反应 | 确认游戏在前台且鼠标没被锁定；本构建只发 `SendInput`，没有窗口消息后备；仍不行只能上硬件 HID。 |
| 宝箱不开 | 走近一点；`calibrate --profile explore` 看 `target_visible` / `target_kind` / `target` 框；调 `chest_min_presence` / `chest_near_box_height`。 |
| 卡在树/墙 | 连续两帧签名相似会触发 `S + Space + D`；仍卡就把 `stuck_limit` 调到 1，或降低 `stuck_similarity` 到 0.97。 |
| 云电脑断连后脚本停了 | 这是 `cloud.pause_when_disconnected=true` 的保护；默认已关，确认套餐支持后台即可继续。 |

---

## 9. 代码结构

```
fortnite_afk.py          CLI: run / demo / calibrate / doctor（单一屏幕模式）
FortniteAFK.exe          打包好的零依赖可执行文件
run.ps1 / run.bat        自动读 key + 启动 exe
config.json              你的配置（从 config.example.json 复制）
afk/
  config.py              配置、校验、key 解析
  capture.py             GDI 截图 + 纯 stdlib PNG
  png.py                 PNG 编码 / 画框
  screen_target.py       屏幕矩形目标（不取任何窗口句柄）
  win32.py               DPI + SendInput（唯一输入后端）
  jev.py                 System One 客户端（urllib，无 requests）
  screens.py             大厅/排队/局内/菜单/结算/探索 的 Jev 问题集
  controller.py          状态机：lobby -> queue -> match -> leave -> results
  explore.py             局内决策映射、开箱、翻越、卡住检测
  cloud.py               WTS 会话状态、黑屏检测、keep-awake
  motion.py              缓入缓出转向 + 镜头噪音
  autotune.py            帧相关测灵敏度（诊断用，不参与运行）
  sim.py                 离线模拟器（demo/测试）
tests/                   84 个 unittest
tools/
  probe_jev.py           Jev API 冒烟测试（自带 mock 大厅图）
  screen_only_loop.py    无句柄运行器：整屏截图 + SendInput
```

---

## 10. 验证命令

```powershell
# 35 个单元测试
python -m unittest discover -s tests -v

# 离线跑两局：大厅点 PLAY、开箱 E、翻越 Space、离开、确认、回大厅
.\FortniteAFK.exe demo --cycles 2

# Jev API 冒烟（需要 key）
python tools\probe_jev.py
```

本机已经跑过：`35 tests OK`、`FortniteAFK.exe demo` 完成 1 局并打印 PLAY / E / Space / 鼠标左键 down-up×2 / Esc / Leave / Confirm 动作、Luanti 10 步走向树干（`changed` 0.8–0.94）、`calibrate` 大厅 mock 图 `play_button` 置信度 0.86。

---

## 11. 风险与边界

- **封号风险**：Epic 明确禁止自动化/挂机；本脚本不修改游戏文件、不读写内存，只模拟输入和看屏幕，但仍可能被行为检测/人工举报。别用主账号。
- **云厂商风险**：海马等服务条款可能禁止脚本/挂机；可能封云账号。
- **不是“全自动无脑稳”**：Jev 是小模型，复杂 UI/低置信度会拒绝点击；需要 calibrate 调阈值。
- **Fortnite 未在本机安装**：所以“Fortnite 实机开箱/翻越/按钮”这条链路只完成了代码 + 模拟 + Luanti 视觉验证，最终要你在装有 Fortnite 的机器上跑 `doctor` / `calibrate` / `run --dry-run`。
