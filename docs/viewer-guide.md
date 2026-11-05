# 棋谱浏览与视频录制

阅读器直接读取 PGN：国际象棋用标准 PGN，中国象棋用 xqbase PGN。可以浏览仓内样例和自己的棋谱，不需要模型账号，也不需要作者本机的原始实验记录。

本指南对应 `main` 中的中文界面。安装总览见[安装与运行](setup.md)，实现与完整参数说明见[阅读器设计](viewer.md)，素材与工具许可见[依赖说明](dependencies.md)。

## 打开仓内样例

在仓库根目录运行本机静态服务：

```sh
python3 -m http.server --bind 127.0.0.1 8000
```

打开下面任一网址：

- [国际象棋样例](http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/chess-sample.pgn)
- [中国象棋样例](http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/xq-sample.pgn)
- [两种棋连播](http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/chess-sample.pgn,/viewer/test/fixtures/xq-sample.pgn&autoplay=1)

服务必须从仓库根目录启动，URL 中的路径相对站点根目录。只绑定 `127.0.0.1`；结束时回终端按 Ctrl-C。8000 被占用时换一个端口并修改网址。页面使用浏览器模块，不能用 `file://` 直接打开，无需构建，也不用先跑 `npm ci`。

## 浏览自己的棋谱

打开 <http://127.0.0.1:8000/viewer/>，把 `.pgn` 文件拖进页面。多个文件按文件名排序连播；若想控制顺序，可以在文件名前加 `01-`、`02-`。

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
| `title=1` | 每盘前加标题画面；默认不开 |

`game`、`ply`、`summary` 的静态定位不要和 `autoplay=1` 同用。网页默认静音；普通 PGN 的变着分支会跳过，仅播放主线。中国象棋棋谱须使用阅读器支持的 xqbase 记谱格式，不是任意文本棋谱。

## 准备录制工具

录制由 Node.js 脚本启动无头 Chromium 截图，再用 FFmpeg 拼成 MP4，不需要 Python 规则库，也不会调用模型。准备：

1. Node.js 与 npm；2026-11-05 核实时本机为 Node.js 24.20.0、npm 11.19.0，仅记录实测环境，不构成最低版本要求。
2. 在 `viewer/` 安装锁文件中的开发依赖：

   ```sh
   cd viewer
   npm ci
   cd ..
   ```

3. 可被 Playwright 驱动的 Chromium。`playwright-core` 不会自动下载浏览器；已有兼容浏览器可通过 `--chromium /绝对路径/Chromium` 指定，或设置 `VIEWER_CHROMIUM`。未指定时脚本查找 Playwright 配套的缓存 Chromium；没有缓存仍会失败。
4. FFmpeg 可执行文件；用 `--ffmpeg /绝对路径/ffmpeg` 或 `VIEWER_FFMPEG` 指定。未指定时默认尝试 `/opt/homebrew/bin/ffmpeg`，这不是各平台通用路径。核对视频还需 FFprobe。

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

给目录时读取其中的 `game.pgn`，也支持仓库外的绝对路径。常用选项：`--no-sound` 无声、`--vol 0.5` 调轻、`--anim 0` 关动画、`--title` 加标题；`--resulthold` 调终局停留，`--summaryhold` 调多盘总比分停留。默认不加标题。`--aspect 9:16` 或 `16:9` 只改变视口，没有专门排版，使用前先检查画面。完整选项：

```sh
node viewer/record.mjs --help
```

Ctrl-C 会关闭录制脚本自己的浏览器、服务和 FFmpeg，并清理本次中间产物；成功前输出写入同目录临时文件，成功后才改成目标文件名。

核对编码、尺寸与时长（`ffprobe` 需在 PATH，或写绝对路径）：

```sh
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,profile,pix_fmt,width,height,r_frame_rate:format=duration -of default=nw=1 /tmp/chess-sample.mp4
```

默认应为 H.264 High、yuv420p、1080×1440、30/1。再实际打开视频，检查开头、几步走子、中文和终局横幅；中国象棋使用系统字体，不同机器的中文字形可能不同。

若录自己的模型对局，先确认对局已结束，再用 `python -m llmchess export runs/<tag>` 重导棋谱；该操作会重写导出文件，应只针对自己要处理的已结束记录。`game.jsonl` 最后一条为 `type=end` 才算结束，正在运行的目录不要处理。新克隆没有作者本机的 `runs/`，直接用上面的仓内样例即可。
