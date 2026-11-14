[English](viewer-guide.en.md) | [简体中文](viewer-guide.md)

# 棋谱浏览与视频录制

阅读器直接读取 PGN：国际象棋用标准 PGN，中国象棋用 xqbase PGN。可以直接浏览随仓入库的 179 盘正式模型对局（66 个单盘目录 `runs/<tag>/game.pgn` 与 7 个多盘批次子目录 `runs/<batch>/<game>/game.pgn`）、测试样例和自己的棋谱，不需要模型账号或棋类引擎。

阅读器默认中文，网址加 `lang=en` 可切换英文。安装总览见[安装与运行](setup.md)，实现与完整参数说明见[阅读器设计](viewer.md)，素材与工具许可见[依赖说明](dependencies.md)。

## 打开正式对局与仓内样例

在仓库根目录运行本机静态服务：

```sh
node viewer/serve.mjs
# 默认监听 127.0.0.1:8765；无 Node.js 时可用：python3 -m http.server 8765 --bind 127.0.0.1
```

打开下面任一网址（传入对局目录名或 `game.pgn` 会自动伴随加载同目录 `analysis.jsonl` 的恶手标注）：

- [空白阅读器（含 4 盘代表局一键直达入口）](http://127.0.0.1:8765/viewer/)
- [国际象棋巅峰对局（Opus Max vs Astra Max 第 1 局）](http://127.0.0.1:8765/viewer/?files=/runs/g7-c-opus-astra-1)
- [中国象棋巅峰对局（Opus Max vs Astra Max 第 1 局）](http://127.0.0.1:8765/viewer/?files=/runs/g7-x-opus-astra-1)
- [国际象棋 Argon High vs Opus High 第 1 局](http://127.0.0.1:8765/viewer/?files=/runs/argon-vs-agy-opus-high-20261019)
- [国际象棋等级分锚定局（Opus Max vs Maia-1900）](http://127.0.0.1:8765/viewer/?files=/runs/zc/maia-1900-s1-w)
- [国际象棋测试样例](http://127.0.0.1:8765/viewer/?files=/viewer/test/fixtures/chess-sample.pgn)
- [中国象棋测试样例](http://127.0.0.1:8765/viewer/?files=/viewer/test/fixtures/xq-sample.pgn)
- [两种棋样例连播](http://127.0.0.1:8765/viewer/?files=/viewer/test/fixtures/chess-sample.pgn,/viewer/test/fixtures/xq-sample.pgn&autoplay=1)

仓库 `runs/` 目录已包含全部 73 个正式模型对局目录（共 179 盘）的 `game.pgn`：其中 **66 个单盘目录**（51 个模型互弈 + 15 个单盘模型对引擎 `b1-ch-*`/`b1-xq-*`）可直接写成 `/runs/<tag>`（或 `/runs/<tag>/game.pgn`），**7 个多盘批次目录**（`b1`、`b1-session`、`b2`、`b3max-ch`、`b3max-xq`、`zc`、`zx`，共 113 盘）位于二级子目录 `/runs/<batch>/<game>`（如 `/runs/zc/maia-1900-s1-w`）。只需将网址中的 `files=` 改为对应目录或 `.pgn` 路径即可查看对局与每步思考理由；当路径指向 `game.pgn`（或目录简写）时，阅读器会自动尝试请求同目录的 `analysis.jsonl` 并严格校验叠加引擎恶手/失误/不精确徽章（若无则静默忽略，也支持用逗号显式传入多个文件）。服务必须从仓库根目录启动，URL 中的路径相对站点根目录。只绑定 `127.0.0.1`；结束时回终端按 Ctrl-C。8765 被占用时可用 `node viewer/serve.mjs --port 8000` 换一个端口并修改网址。页面使用浏览器模块，不能用 `file://` 直接打开，无需构建，也不用先跑 `npm ci`。

## 浏览自己的棋谱

打开 <http://127.0.0.1:8765/viewer/>，可直接点击页面上的内置代表局，或把自己的 `.pgn` 文件（可连带对应的 `analysis.jsonl`）拖进页面。多个文件按文件名排序连播；若想控制顺序，可以在文件名前加 `01-`、`02-`。

| 操作 | 快捷键 |
| --- | --- |
| 上一步 / 下一步 | ← / → |
| 播放 / 暂停 | 空格 |
| 本盘开头 / 末尾 | Home / End |
| 上一盘 / 下一盘 | PgUp / PgDn |

宽窗口（至少 900 像素）右栏显示着法、评注和棋谱里已有的用时、token 等信息，也可以点着法跳步。窄窗口只显示棋盘和棋手信息。阅读器显示记录中的理由与标注，不自动评估每步优劣；没有写进棋谱的数据不会凭空补齐。

常用网址参数可以用 `&` 接在 `files=...` 后：

| 参数示例 | 效果 |
| --- | --- |
| `autoplay=1&gap=1.5` | 自动播放，每个半回合 1.5 秒 |
| `anim=0` | 关闭走子滑动动画（默认 0.3 秒，已算在 gap 内） |
| `openhold=0.5` | 每盘开局停 0.5 秒再走第一步 |
| `game=1&ply=20` | 静态打开第一盘第 20 个半回合之后的局面 |
| `ply=end` | 打开本盘终局 |
| `summary=1` | 多盘的总比分画面 |
| `layout=wide` / `layout=compact` | 强制宽版 / 窄版 |
| `sound=1&vol=0.5` | 打开音效并调轻；打开后先点页面或按键以允许浏览器发声 |
| `lang=en` | 英文界面；评注原文与象棋汉字棋子保留，象棋着法改显 WXF 记法 |
| `names=opus=Claude Opus,astra=GPT astra` | 覆盖显示名，比分仍按棋谱中的原名归属 |
| `title=1` | 每盘前加标题画面；默认不开 |

`game`、`ply`、`summary` 的静态定位不要和 `autoplay=1` 同用。网页默认静音；普通 PGN 的变着分支会跳过，仅播放主线。中国象棋棋谱须使用阅读器支持的 xqbase 记谱格式，不是任意文本棋谱。

## 准备录制工具

录制由 Node.js 脚本启动无头 Chromium 截图，再用 FFmpeg 拼成 MP4，不需要 Python 规则库，也不会调用模型。准备：

1. **Node.js >= 22** 与 npm（`node --test 'viewer/test/*.test.js'` 的引号通配需要 Node.js 22+；若使用 Node 18/20，可去掉单引号由 shell 展开：`node --test viewer/test/*.test.js`。2026-11-05 实测环境为 Node.js 24.20.0、npm 11.19.0）。
2. 在仓库根目录安装 `viewer/` 锁文件中的开发依赖：

   ```sh
   npm --prefix viewer ci
   ```

3. 可被 Playwright 驱动的 Chromium。`playwright-core` 不会在 `npm ci` 时自动下载浏览器；可通过 `--chromium /绝对路径/Chromium` 或设置 `VIEWER_CHROMIUM` 指定，未指定时脚本依次查找 Playwright 配套的缓存 Chromium（可在仓库根目录执行 `node viewer/node_modules/playwright-core/cli.js install --with-deps chromium` 安装与锁定版本 `1.58.2` 配套的浏览器）以及系统 `PATH` 和常见路径中的 `chromium`、`chromium-browser`、`google-chrome-stable`、`google-chrome`、`/snap/bin/chromium` 与 macOS `/Applications/Google Chrome.app/...`。
4. FFmpeg 可执行文件；用 `--ffmpeg /绝对路径/ffmpeg` 或 `VIEWER_FFMPEG` 指定，未指定时自动从 `PATH` 及常见系统路径（`/usr/bin/ffmpeg`、`/usr/local/bin/ffmpeg`、`/opt/homebrew/bin/ffmpeg`）查找。核对视频还需 `ffprobe`。
5. **Linux 服务器 / 无桌面环境的中文字体**：中国象棋棋盘上的汉字棋子与中文界面使用系统字体渲染；在无桌面 Linux 环境录屏或截图前，请先安装中文字体（如 Ubuntu/Debian：`sudo apt install fonts-noto-cjk fonts-arphic-ukai`），否则中国象棋棋盘上的汉字棋子会显示为方块（tofu）。

页面自己不依赖这些开发工具。`viewer/package-lock.json` 固定了 `playwright-core` 版本；不必为浏览棋谱下载浏览器或安装视频工具。

## 录成 MP4

从仓库根目录运行，输出目录须已存在，使用尚未使用的文件名：

```sh
node viewer/record.mjs viewer/test/fixtures/chess-sample.pgn -o /tmp/chess-sample.mp4 --gap 1.5 --openhold 0.5
```

输出默认 3:4、1080×1440、H.264、30 fps，带走子和终局音效。多个输入按命令行顺序连播，最后加总比分：

```sh
node viewer/record.mjs viewer/test/fixtures/chess-sample.pgn viewer/test/fixtures/xq-sample.pgn -o /tmp/two-samples.mp4 --gap 1.5 --openhold 0.5
```

给目录时自动读取其中的 `game.pgn`（例如直接录制单盘目录 `node viewer/record.mjs runs/g7-c-opus-astra-1 -o /tmp/g7-c-1.mp4 --gap 1.5 --openhold 0.5`，或多盘批次下的单盘子目录 `node viewer/record.mjs runs/zc/maia-1900-s1-w -o /tmp/zc-s1w.mp4`；多盘批次顶层如 `runs/zc` 只含 `summary.*`，须传具体单盘子目录），也支持仓库外的绝对路径。常用选项：`--no-sound` 无声、`--vol 0.5` 调轻、`--anim 0` 关动画、`--title` 加标题；`--resulthold` 调终局停留，`--summaryhold` 调多盘总比分停留。默认不加标题。`--aspect 9:16` 或 `16:9` 只改变视口，没有专门排版，使用前先检查画面。完整选项：

```sh
node viewer/record.mjs --help
```

Ctrl-C 会关闭录制脚本自己的浏览器、服务和 FFmpeg，并清理本次中间产物；成功前输出写入同目录临时文件，成功后才改成目标文件名。

核对编码、尺寸与时长（`ffprobe` 需在 PATH，或写绝对路径）：

```sh
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,profile,pix_fmt,width,height,r_frame_rate:format=duration -of default=nw=1 /tmp/chess-sample.mp4
```

默认应为 H.264 High、yuv420p、1080×1440、30/1。再实际打开视频，检查开头、几步走子、中文和终局横幅；中国象棋使用系统字体，不同机器的中文字形可能不同。

已入库的 66 个单盘目录 `runs/<tag>/game.pgn` 与 7 个多盘批次子目录 `runs/<batch>/<game>/game.pgn` 已是最新导出的完整棋谱，可直接浏览或录制（无需也不可对其运行 `export`，因为体积庞大的底层 `game.jsonl` 未入库）。若录制自己新跑的模型对局，先确认对局已结束（本机 `game.jsonl` 最后一条为 `type=end`），再用 `python -m agi_chess export runs/<tag>` 导出或更新棋谱。

英文录制在原命令后加 `--set lang=en --set "names=opus=Claude Opus,astra=GPT astra"`，也可同时用 `--openhold 0.5`。象棋英文着法为 WXF 显示，输入棋谱仍用 xqbase 格式。
