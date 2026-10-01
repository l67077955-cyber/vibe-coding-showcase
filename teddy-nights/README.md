# 玩具熊的午夜后宫 · Teddy Nights

A browser fan game inspired by *Five Nights at Freddy's*: survive from 12 AM to 6 AM in the security office with limited power.

**Live**: https://l67077955-cyber.github.io/vibe-coding-showcase/teddy-nights/

## 里面有什么

- **核心机制**：左右门、门灯、11 路监控（厨房仅音频）、电量与用电量、停电后弗莱迪伴着八音盒登场
- **四个角色各有路线**：邦尼走西侧、奇卡走东侧、弗莱迪只在你不看它时移动、福克斯在海盗湾探头后冲向左门（关门挡住会扣电）
- **5 夜 + 第 6 夜 + 自定义之夜**（四角色 AI 0–20 可调），进度存在浏览器 localStorage
- 每晚开场有中文电话录音字幕，可静音

## 操作

| 操作 | 键位 |
|---|---|
| 左 / 右门 | A / D（或点门边红按钮） |
| 左 / 右门灯 | Q / E（或点白按钮） |
| 监控 | 空格，或鼠标划过底部「监控」条 |
| 转头 | 鼠标移到屏幕两侧，或 ← → |
| 返回菜单 | Esc |

支持触屏点按。

## 技术说明

- 单文件 `index.html`，零依赖、零外部资源，离线可玩
- 所有画面（角色、房间、监控噪点、扫描线）都是 Canvas 2D 程序化绘制，没有一张位图
- 所有音效（风扇、关门、静电、尖叫、6 AM 钟声）都是 WebAudio 实时合成；停电八音盒旋律为比才《斗牛士之歌》（公有领域）
- AI 采用原作的"移动机会"模型：每个角色按固定间隔掷 1–20，点数不超过当前 AI 等级即移动，AI 等级随夜晚和时刻递增

## 免责声明

非官方粉丝作品，仅供学习交流，与原作无关联。*Five Nights at Freddy's* © Scott Cawthon。本作未使用任何原作素材。
