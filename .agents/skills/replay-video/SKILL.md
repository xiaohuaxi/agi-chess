---
name: replay-video
description: 用本仓库的棋谱阅读器（viewer/）把对局录成 mp4，或在浏览器里打开棋谱逐步看。Use when 要给某盘或几盘对局出视频、核对出片，或要手工看 runs/<tag> 的棋谱。只讲怎么用，不讲实现。
---

# 录棋局视频 / 看棋谱

阅读器读的是棋谱文件（`game.pgn`，国际象棋标准 PGN、中国象棋 xqbase PGN），别人的普通棋谱也能播。实现、版式取值、设计取舍都在 `docs/viewer.md`；这里只讲怎么用，遇到下面没写的问题再去翻它（出片看「录屏：脚本出片」，网址参数和快捷键看「做成什么样」）。

## 先备好棋谱

- **只录下完的棋**：`runs/<tag>/game.jsonl` 最后一行是 `{"type": "end", …}` 才算下完。没有这一行的可能正在下，别碰它的目录。
- **用当前代码重导一遍**：`python3 -m llmchess export runs/<tag>`。只重写导出文件（`game.pgn`、`record.txt` 这类），不动 `game.jsonl`。旧代码导出的棋谱可能少思考深度标签，或者中文评注在字中间断行，读回来会多出空格。
- `runs/` 被 git 忽略，只在主检出（`~/repos/llm-chess/runs/`）里有，worktree 里没有。录制脚本认本机任意路径，直接给绝对路径就行。
- 开发依赖：先在 `viewer/` 下跑一次 `npm ci`（只装 playwright-core，版本锁死，配套本机缓存里的 Chromium）。

## 一条命令出片

```
node viewer/record.mjs <棋谱或 runs 目录> [更多…] -o <输出.mp4> [选项]
node viewer/record.mjs ~/repos/llm-chess/runs/g1-c-opus-sol -o /tmp/g1.mp4
node viewer/record.mjs runs/a runs/b -o /tmp/ab.mp4 --gap 1.5 --title   # 连播，每盘前加标题画面，最后一格是总比分
```

- 给目录时读里面的 `game.pgn`。给了多个就按顺序连播，当成一场比赛算比分。
- 常用选项（单位是秒；没给的用页面默认值）：
  - `--gap` 每步停多久（2.5），含走子滑动
  - `--anim` 走子滑动多久（0.3），算在 gap 之内、不拉长视频；`--anim 0` 不要动画
  - `--titlehold` 标题画面（3，配 `--title` 才有）、`--resulthold` 终局横幅（4）、`--summaryhold` 多盘总比分（5）
  - `--title` 每盘开局前加标题画面（写双方名字）；默认不加，开头直接是开局局面（`--no-title` 等同默认，留作兼容）
  - `--aspect 3:4|9:16|16:9`：默认 3:4 出 1080×1440，这是发布用的比例
  - `--scale` 像素倍数（默认 2）
  - `--set 名=值` 再透传一个网址参数；`--set vendor=0` 标题画面名字前不补厂商（「GPT astra」→「astra」）
- 出片时长大约等于「标题 + 步数 × gap + 终局 + 总比分」。默认参数下，出一分钟视频要跑约 6 秒。
- 成功时打印时长、帧数、各类格数；失败时打印中文原因，退出码 1。完整说明看 `node viewer/record.mjs --help`。

## 出片后核对

```
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,profile,pix_fmt,width,height,r_frame_rate:format=duration -of default=nw=1 /tmp/g1.mp4
```

应该是 h264 / High、yuv420p、30/1，尺寸对得上画幅，时长和上面的估算差不到一帧。再抽几帧看一眼，棋子、中文要清楚，终局横幅要在：

```
ffmpeg -v error -y -ss 5 -i /tmp/g1.mp4 -frames:v 1 /tmp/g1-5s.png
```

抽出来的 PNG 直接用 Read 看。

## 手工看棋谱

页面是纯静态文件，但不能用 `file://` 打开，要经本机服务：

```
cd ~/repos/llm-chess && python3 -m http.server --bind 127.0.0.1 8000
```

一定要绑 127.0.0.1，别暴露到局域网。然后打开 `http://127.0.0.1:8000/viewer/`：

- 网址参数：`?files=/runs/a/game.pgn,/runs/b/game.pgn&autoplay=1&gap=1.5`。路径从站点根算起，所以要在同时有 `viewer/` 和 `runs/` 的目录下起服务。静态看某一格用 `game=2&ply=30`（`ply=end` 是终局），多盘总比分用 `summary=1`；`layout=wide` / `layout=compact` 强制宽版或窄版。
- 也可以不带参数打开页面，把 `.pgn` 文件拖进去。多个文件按文件名排序连播。
- 快捷键：← → 单步，空格播放 / 暂停，Home / End 跳到本盘首尾，PgUp / PgDn 换盘。宽版（窗口宽 ≥ 900）右栏可以点着法跳步，看每步的评注、用时、token。

## 常见坑

- **浏览器 / ffmpeg 找不到**：ffmpeg 默认用 `/opt/homebrew/bin/ffmpeg`（Playwright 缓存里那个在本机跑不起来），浏览器默认用 playwright-core 配套的缓存 Chromium。换路径用 `--ffmpeg` / `--chromium`，或者设环境变量 `VIEWER_FFMPEG` / `VIEWER_CHROMIUM`。测试用的 ffprobe 默认和 ffmpeg 在同一个目录，也可以用 `VIEWER_FFPROBE` 指定。
- **给错文件**：一盘带着法的棋都读不出来的文件（不是棋谱）会在开工前报错退出，不会出空片。可是一个多盘文件里夹着的空盘不会被挑出来。
- **停留设成 0**：停 0 秒的那一格根本不截图，比如 `--resulthold 0` 就没有终局横幅。全设成 0 会报「一格画面都没有」。
- **9:16 / 16:9 没专门排版**：只是换了视口尺寸，画面照 3:4 的窄版摆，可能多出空白或显得挤。要发布就用 3:4，另外两种先出一段看看再说。
- **`--set` 传错不报错**：页面不认识的参数名直接忽略，值不合法就退回默认值，所以写错了也照样出片。`rec`、`files` 由脚本自己给，传了会被拒。录制时版式恒为窄版，`--set layout=wide` 不起作用。改时长请用专门的 `--gap` 这类选项，它们会先检查数值。
- **Ctrl-C 中途停**：会杀掉 ffmpeg、关掉浏览器和服务、删掉中间帧和半截输出再退出（退出码 130），不用手工清理。输出先写成同目录的临时文件，成功后才改名，所以不会留下半截 mp4。
- **标题画面上的棋手名**（加了 `--title` 时）：默认前面补上厂商名（「Claude opus」「GPT astra」），`--set vendor=0` 去掉。用户 2026-09-30 定标题画面默认不加，要才用 `--title`。
