---
name: replay-video
description: 用本仓库棋谱阅读器（viewer/）把对局录成 MP4 视频，或起本机静态服务在浏览器查看棋谱与核对出片。需要给某盘或多盘对局出视频、核对编码/音量/画面，或在浏览器看 runs/<tag> 棋谱时加载；修改阅读器实现或版式设计时读 docs/viewer.md，不加载本 skill。
---

# 录棋局视频 / 看棋谱

阅读器读取棋谱文件（`game.pgn`：国际象棋标准 PGN、中国象棋 xqbase PGN），也可播放外部普通棋谱。实现、版式取值与设计取舍见 `docs/viewer.md`（出片看「录屏：脚本出片」，网址参数和快捷键看「做成什么样」）。

## 准备棋谱与依赖

- 已入库对局与本机新跑对局区分处理：
  - 已入库的 179 盘正式对局（含在 git worktree 中，无 `game.jsonl`）：共 73 个正式对局目录，其中 66 个单盘目录（51 个模型互弈 + 15 个单盘模型对引擎 `b1-ch-*` / `b1-xq-*`）直接位于 `runs/<tag>/game.pgn`；7 个多盘批次目录（`b1`、`b1-session`、`b2`、`b3max-ch`、`b3max-xq`、`zc`、`zx`，共 113 盘）顶层只有 `summary.*`，每盘棋位于二级子目录 `runs/<batch>/<game>/game.pgn`（如 `runs/zc/maia-1900-s1-w/game.pgn`）。它们均自带最新导出的完整 `game.pgn`（178 盘另带 `analysis.jsonl`），可直接浏览或录屏，不要检查 `game.jsonl`，也不要运行 `python3 -m agi_chess export`。
  - 本机新跑、含 `game.jsonl` 的对局：只录已下完的棋；先确认 `runs/<tag>/game.jsonl` 最后一行是 `{"type": "end", …}`（没有这一行的可能仍在运行，不要触碰其目录），再按需运行 `python3 -m agi_chess export runs/<tag>` 重写导出文件（`game.pgn`、`record.txt`），不改动 `game.jsonl`。
- 路径支持：录制脚本支持相对仓库根目录的路径或本机任意绝对路径。
- 开发依赖：先在仓库根目录执行 `npm --prefix viewer ci`（安装锁定的 `playwright-core==1.58.2`）。脚本会自动从 `PATH` 与常见路径查找 `ffmpeg` 和 Chromium / Chrome；若本机尚无兼容浏览器，可在仓库根目录执行 `node viewer/node_modules/playwright-core/cli.js install --with-deps chromium` 安装与锁定版本配套的浏览器。

## 录制视频

```sh
node viewer/record.mjs <棋谱或单盘目录> [更多…] -o <输出.mp4> [选项]
node viewer/record.mjs runs/g1-c-opus-sol -o /tmp/g1.mp4
node viewer/record.mjs runs/zc/maia-1900-s1-w -o /tmp/zc-s1w.mp4
node viewer/record.mjs runs/a runs/b -o /tmp/ab.mp4 --gap 1.5 --title   # 连播，每盘前加标题画面，最后一格是总比分
```

- 输入与连播：传入目录时只读该目录下一层的 `game.pgn`（多盘批次须指到二级单盘子目录如 `runs/zc/maia-1900-s1-w` 或通配 `runs/zc/*/game.pgn`，直接传 `runs/zc` 会报「目录里没有 game.pgn」）。传入多个时按顺序连播，作为同一场比赛累计比分。
- 常用选项（时长单位为秒；未传的取页面默认值）：
  - `--gap`：每步停留时长（默认 `1.8`，含 `0.3` 秒走子滑动，落定后停 `1.5` 秒）。
  - `--openhold`：每盘开局局面停留时长，之后再走第一步（默认同 `gap`）。发布用视频传 `--openhold 0.5`，避免片头静止约 2 秒让观众误以为卡住（用户 2026-10-04 定）。每盘开局均按此停留；加 `--title` 时开局那格换成标题画面，本项不生效。
  - `--anim`：走子滑动时长（默认 `0.3`），计入 `gap` 之内、不拉长视频；`--anim 0` 关闭动画。
  - `--titlehold` / `--resulthold` / `--summaryhold`：标题画面停留（默认 `3`，配合 `--title` 生效）、终局横幅停留（默认 `4`）、多盘总比分停留（默认 `5`）。
  - `--title`：每盘开局前加标题画面（显示双方棋手名）；默认不加，片头直接为开局局面（`--no-title` 等同默认，留作兼容）。
  - `--aspect 3:4|9:16|16:9`：默认 `3:4` 输出 `1080×1440`（发布用比例）。
  - `--scale`：像素倍数（默认 `2`）。
  - `--set 名=值`：向页面透传一个网址参数；`--set vendor=0` 在标题画面名字前不补厂商（「GPT astra」→「astra」）。
  - 英文界面与显示名覆盖：`--set lang=en` 切英文界面（默认中文）。棋手显示名用 `--set 'names=claude:opus=Claude Opus,codex:astra=GPT astra'`，按逗号分隔「棋谱里的名字=显示名」：等号左边写 PGN 标签原样（`claude:opus`）或简称（`opus`）均可，不区分大小写；右边显示名原样输出、不补厂商，思考深度仍从棋谱读取并接在后面（`Claude Opus+max`）；值含空格时整段加引号，显示名内不能有逗号。中英文界面均识别；中国象棋英文界面下着法显示为 WXF（`C2.5`），棋子仍用汉字。细节见 `docs/viewer.md`「英文界面」。
  - 声音：默认带走子音效（落子 / 吃子声在棋子落地瞬间触发，终局横幅出现时再响一声）；`--vol <倍数>` 调整整体音量（默认 `1`，`0.5` 约轻 `6 dB`），`--no-sound` 输出无声片。
- 时长与耗时：出片时长约等于「每盘（开局 + 步数 × gap + 终局）+ 总比分」，开局那格为 `openhold`（加 `--title` 时为标题画面）。默认参数下生成 1 分钟视频约耗时 25–35 秒（2026-10-02 实测：83 秒国际象棋片 32 秒、89 秒象棋片 48 秒；加入滑动动画后每步逐帧截取 9 张动画画面，因此慢于早期无动画时的约 6 秒）。
- 输出与退出码：成功时打印时长、帧数、截图张数、各类格数、音效和用时；失败时打印中文原因，退出码 `1`。完整说明见 `node viewer/record.mjs --help`。

## 出片后核对

```sh
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,profile,pix_fmt,width,height,r_frame_rate:format=duration -of default=nw=1 /tmp/g1.mp4
```

视频流应为 `h264` / `High`、`yuv420p`、`30/1`，尺寸匹配画幅，时长与上述估算误差不到一帧。有声片另有一路 AAC 音轨（`48000 Hz`、单声道），时长与画面一致；检查音量：

```sh
ffmpeg -hide_banner -nostats -i /tmp/g1.mp4 -vn -af ebur128=peak=sample -f null - 2>&1 | tail -12
```

默认音量下峰值约 `−6 dBFS`（终局音效），落子、吃子各约 `−10 dBFS`。抽帧检查棋子、中文清晰度及终局横幅：

```sh
ffmpeg -v error -y -ss 5 -i /tmp/g1.mp4 -frames:v 1 /tmp/g1-5s.png
```

导出的 PNG 可直接用读文件工具（如 `Read`）查看。

## 浏览器看棋谱

页面为纯静态文件，不能用 `file://` 直接打开，须在仓库根目录下启动本机服务：

```sh
node viewer/serve.mjs
# 默认监听 127.0.0.1:8765；无 Node.js 时可用：python3 -m http.server 8765 --bind 127.0.0.1
```

服务只绑定 `127.0.0.1`，不要暴露到局域网。打开 `http://127.0.0.1:8765/viewer/`：

- 网址参数：`?files=/runs/g7-c-opus-astra-1` 或 `?files=/runs/a/game.pgn,/runs/b/game.pgn&autoplay=1&gap=1.5`。支持单盘目录简写自动补 `/game.pgn`，多盘批次需写二级子目录（如 `/runs/zc/maia-1900-s1-w`）；路径指向 `game.pgn` 或目录简写时，阅读器会自动尝试加载同目录的 `analysis.jsonl` 叠加引擎恶手/失误/不精确徽章，也支持逗号显式传多文件。路径从站点根算起，须在同时有 `viewer/` 和 `runs/` 的目录下起服务。静态看单格用 `game=2&ply=30`（`ply=end` 为终局），多盘总比分用 `summary=1`；`layout=wide` / `layout=compact` 强制宽版或窄版。
- 内置样例与拖拽加载：不带参数打开页面时，可直接点击页面上的内置代表局，或把 `.pgn` 文件（可连带对应的 `analysis.jsonl`）拖入页面；多个文件按文件名排序连播。
- 声音：默认关闭，网址加 `sound=1` 开启（`vol=0.5` 调轻）。浏览器要求页面有过点击或按键才允许发声，`autoplay=1&sound=1` 打开后需先点一下页面。
- 快捷键与宽版侧栏：`←` / `→` 单步，`空格` 播放 / 暂停，`Home` / `End` 跳到本盘首尾，`PgUp` / `PgDn` 换盘；修改样式或脚本后可在浏览器硬刷新（macOS：`Cmd+Shift+R` / Linux & Windows：`Ctrl+Shift+R`）。宽版（窗口宽 `≥ 900`）右栏可点击着法跳步，查看每步的评注、用时、token。

## 常见问题与边界

- 浏览器 / ffmpeg 查找：脚本优先读取 `--ffmpeg` / `--chromium` 或环境变量 `VIEWER_FFMPEG` / `VIEWER_CHROMIUM`（显式指定不存在的名称或路径会直接报错，不会静默回退）。未指定时自动从 `PATH` 及常见系统路径查找 `ffmpeg`（如 `/usr/bin/ffmpeg`、`/usr/local/bin/ffmpeg`、`/opt/homebrew/bin/ffmpeg`）与浏览器（先查 `playwright-core` 配套缓存 Chromium，再查 `PATH` 与系统中的 `chromium`、`chromium-browser`、`google-chrome-stable`、`google-chrome`、`/snap/bin/chromium` 及 macOS `/Applications/Google Chrome.app/...`），也可通过 `node viewer/node_modules/playwright-core/cli.js install --with-deps chromium` 安装与锁定版本配套的浏览器。测试用的 `ffprobe` 优先读 `VIEWER_FFPROBE`，再查与 `ffmpeg` 同目录及 `PATH`。
- 输出覆盖保护：`-o <输出.mp4>` 目标文件若已存在，脚本默认报错退出以防误覆盖；确认要覆盖时加 `-f` / `--force`。
- 非法或空棋谱：连一盘带着法的棋都读不出来的文件（不是棋谱）会在录制前报错退出，不会生成空片；但多盘文件里夹带的空盘不会被单独剔除。
- 停留时长设为 0：停 `0` 秒的那一格不会截图（如 `--resulthold 0` 不会出现终局横幅）；全部设为 `0` 会报「一格画面都没有」。
- `9:16` / `16:9` 画幅：仅改变视口尺寸，画面仍按 `3:4` 窄版布局，可能多出空白或显挤；正式发布用 `3:4`，其余两种先试录一段确认画面。
- `--set` 参数静默回退：页面不认识的参数名直接忽略，值不合法则退回默认值，写错仍会照常出片（`lang=en` 写错就是中文片，`names=` 左边未匹配则保留原名）；出英文片或改显示名后应抽帧确认终局横幅或中局画面。`rec`、`files` 由脚本内部注入，手动传入会被拒绝；录制时版式恒为窄版，`--set layout=wide` 不生效；调整时长请用 `--gap` 等专用选项（会先校验数值）。
- `Ctrl-C` 中途停止：自动终止 `ffmpeg`、关闭浏览器与服务、删除中间帧与半截输出后退出（退出码 `130`），无需手动清理。输出先写入同目录临时文件，成功后才改名，不会留下半截 MP4。
- 标题画面棋手名（加 `--title` 时）：默认前置厂商名（「Claude opus」「GPT astra」），传 `--set vendor=0` 去掉。用户 2026-09-30 定标题画面默认不加，按需传 `--title`。
