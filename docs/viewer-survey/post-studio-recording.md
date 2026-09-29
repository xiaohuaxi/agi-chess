# post-studio 此前录屏方案调研（2026-09-29，只读调研）

## 结论
已发布的两条视频（007 国际象棋、008 象棋）**不是 post-studio 的 agent 录的**，是用户让 **ChatGPT 桌面端（Codex/Work，Computer Use + Chrome 集成）自己下棋、自己录、自己剪**。录屏用 macOS 自带 `screencapture`，剪辑用它自己写的 AVFoundation 脚本。之后 011 才在仓库里做了一套自己的录窗工具（ScreenCaptureKit），但 011 暂停，没有发布视频。

## 1. 内容与文件（视频不进 Git，在被忽略的 local/）
- 007：ChatGPT 对 Jev 下国际象棋。`local/007-jev-chess-match/jev-chess-4x-from20s.mp4`（发布版，截掉开头 20 秒）；`jev-chess-4x.mp4` 是完整转码版。2026-09-22 15:40 微博 / 15:43 小红书发布。
- 008：ChatGPT（执红）对 Jev 下象棋，18 回合将死。`local/008-jev-xiangqi-match/jev-xiangqi-2x.mp4`。2026-09-22 22:07 小红书 / 22:08 微博发布。
- 011（Astra 对 Opus 三局两胜）：只有测试/原片，未发布：`local/011-xiangqi-astra-opus/run-20260924-233957/g1-{raw,cut,test}.mp4`、`match-20260924-232940/g1-test.mp4`。
- 依据：posts/007-jev-chess-match/{README,sources}.md，posts/008-jev-xiangqi-match/{README,sources,production}.md，posts/011-xiangqi-astra-opus/{README,match}.md。

## 2. 录制方式
- 控制 Chrome：ChatGPT 的「Chrome 集成」（画面上的提示条是「"ChatGPT"已开始调试此浏览器」，即 CDP 调试模式，页面里还叠着 agent 光标）。008 的 sources.md 从会话日志（`~/.codex/sessions/`）核实：无引擎，录屏/抽帧/剪辑用 `screencapture` + 自写 AVFoundation 脚本。
- 捕获：`screencapture -v -R<x,y,w,h> out.mov` 录**屏幕固定区域**（只框 Chrome 窗口）。要求 Mac **解锁**、窗口不被遮挡（依据：`.agents/skills/screen-media/references/mac-media.md`）。
- 后期工具：
  - `posts/007-jev-chess-match/tools/{frames,motion,probe,trim}.swift`（AVFoundation 抽帧/找静止/探测/截头变速）；
  - `.agents/skills/screen-media/scripts/media.py`（ffmpeg：probe / idle 找空等 / sheet 联系表 / cut --keep --speed，默认导出 1080×1440 H.264 30fps faststart）+ `SKILL.md` 规范；
  - 011 新做的 `posts/011-xiangqi-astra-opus/tools/recwin.swift`：**ScreenCaptureKit 只录单个 Chrome 窗口**（`list` / `record out.mp4 秒数 --id N --fps 30` / `frame`），窗口被挡也能录、不占用户屏幕；SIGTERM 正常收尾；码率 = 宽×高×4。手册见 `posts/011-.../match.md`。
- 没有用：Playwright、Claude in Chrome 录屏、逐帧截图拼接、浏览器扩展录制。（011 里 Opus 棋手用 `claude -p --chrome` 操作棋盘，但那是棋手，不是录屏。）
- 全部都是 ChatGPT 桌面端整套代劳，用户不需要盯着，但需要 Mac 处于解锁状态。

## 3. 实测规格（ffprobe）
| 文件 | 分辨率 | 帧率 | 编码 | 码率 | 时长 | 大小 |
|---|---|---|---|---|---|---|
| 007 发布版 jev-chess-4x-from20s | 1058×1918 | 30 | H.264 yuv420p | ~1.4 Mbps | 98.2 s（原片 7分53，4×） | 17 MB |
| 008 发布版 jev-xiangqi-2x | 1116×1984（=558×992 点@2x，9:16） | 30 | H.264 | ~2.3 Mbps | 107.7 s（2×） | 31 MB |
| 011 g1-cut（recwin 录制） | 1560×2080（780×1040 点@2x，3:4） | 600 fps 标记（时间戳异常，非真实帧率；需转 30fps 恒定） | H.264 | ~3.2 Mbps | 160 s | 65 MB |
| 011 g1-raw | 同上 | 同上 | H.264 | ~1.6 Mbps | 1351 s | 276 MB |
- 清晰度（抽帧目测 008、011）：Retina 2× 原生像素，棋盘、汉字、按钮边缘清楚，文字可读；带浏览器标签栏/地址栏/「已开始调试此浏览器」提示条。
- 注意 011 的 recwin 输出帧率是 VFR（时间戳按事件到达，静止时几乎不出帧），发布前必须重编码成 30fps CFR（media.py 的 cut 会做）。

## 4. 遇到的问题
- **锁屏录成保护画面**（008 第一盘）：Mac 锁着屏，录了 585 秒全是「ChatGPT is Using Your Mac」锁屏壁纸，App 截图却看得到棋盘。→ 规定开录前先试录 3–5 秒并打开成片核实（screen-media SKILL.md）；第二盘先录 probe 再开局。
- **手机端显得窄**（007，1058×1918）：小红书 App 把 9:16 放大铺满、左右各裁约 4.5%，用户手机上「显得变窄」。→ 实测比例（docs/platform-data.md，刻度尺视频 local/video-ratio-test/），最终定**统一 3:4、导出 1080×1440**（docs/decisions.md）。
- **窗口按窄屏调整后只剩棋盘**，候选/概率信息要靠终局截图补（008）。
- **agent 光标与提示叠加**：录棋手操作的标签页时，棋子消失、叠着两个 agent 的光标和提示框（011）→ 改为单独开一个「录像窗口」只显示棋局、自己轮询更新，不点它。
- **011 首场正式赛两度中断**：录像窗口被关；对局质量差被叫停。用户 2026-09-25 决定不再用网页录屏展示对弈，改做无界面的 llm-chess。
- 长时间空等（思考 9 秒静止）→ 靠 2×/4× 变速和截头处理。
- 011 手册里：窗口最小化或切到别的桌面空间就录不到；用户同时在用 Mac，所以只录窗口不录全屏。
- 007/008 保留了浏览器外框、127.0.0.1 网址和调试提示条（用户要真实感）；011 要求整窗录入、出片前抽查标签页/账号/本机路径。

## 5. 窄屏/竖屏做法
- 没有设备模拟，也没用 CDP 的 Emulation：**直接把真实 Chrome 窗口拖窄**，让页面自然响应式重排（SKILL.md 的原则），再调高度到目标比例。
- 007：窗口约 529×959 点（视频 1058×1918，接近 9:16）；008：558×992 点（1116×1984，9:16）；011：780×1040 点（3:4，整窗含标签栏和地址栏，不裁切）。
- 录制区域要扣掉/或整窗；后期不横向拉伸，比例不符加黑边（`--fit pad`）。
- 当前结论：发布用 3:4、1080×1440；内容区优先（不含浏览器外框），除非用户要整窗。

## 对棋谱阅读器的启示（供参考）
- 想全自动、无人盯：用 `recwin.swift`（ScreenCaptureKit 单窗口）+ `media.py` 后期，比 `screencapture -R` 更稳（不怕遮挡，不录用户桌面）；但要 Screen Recording 权限，且窗口不能最小化/换 Space。
- 棋谱阅读器是自播动画的页面，可以不依赖 agent 操作：开一个 780×1040 点的 Chrome 窗口跑它，录 recwin，再 media.py 转 1080×1440 30fps；不需要 CDP 调试提示条（用普通打开方式，或 Playwright 录视频则完全没有浏览器外框）。
- 无现成的 Playwright/CDP screencast 方案可复用。
