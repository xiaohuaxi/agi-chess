# 从 PGN 直接出 GIF / 视频的开源工具调研

调研日期 2026-09-29。范围：不走浏览器录屏，直接从 PGN 出 GIF 或视频的现成工具，外加自制路线估算。
只读调研：源码 shallow clone 在 `~/repos/`（新增检出：lila-gif、gifpgn、chess_gif、pgn-to-gif、pgn2gif、c2g、pgn-to-video-converter、chess-animator、python-chess；原有仓库没动）。
试跑用的 venv、产物都在 ``。
测试输入：`runs/g1-c-opus-sol/game.pgn`（95 个半回合，带 `[%emt] [%think]…` 评注，`Termination` 头是中文「将死」）。

## 0. 结论先行（供拍板参考，不下"能不能用"的结论）

- **没有一个现成工具同时满足**：标题画面 + 终局原因 + 竖屏 9:16 + 每步 2–3 秒 + 双方名字 + 将军提示 + 上一步高亮。每个都缺至少三项。
- 单项最接近的是 **gifpgn**（有名字条、可调秒数、箭头标上一步；许可 GPL-3.0-or-later）和 **lila-gif**（名字条、将军高亮、每帧延时、任意局面序列；许可 AGPL-3.0-or-later，本机没有 cargo，未编译）。两个都要再套一层 ffmpeg 补 9:16 和标题、结果画面。
- **自制路线**（python-chess SVG → cairosvg → Pillow 排版 → ffmpeg）我在本机实测跑通，约 70 行做出 9:16 竖屏、标题画面、双方名字、上一步高亮、将军红光、终局横幅、4 分钟 mp4（渲染约 18 秒）。见第 9 节。
- 许可提醒：**python-chess 本身就是 GPL-3.0-or-later**（第 1 节），本项目已在用；lila-gif 是 AGPL，gifpgn、c2g 是 GPL。这些都属于仓库许可政策里「强 copyleft」那一族，边界请问维护者。

## 1. python-chess（本项目已用依赖，先核实）

- 许可：GPL-3.0-or-later。证据：`~/repos/python-chess/LICENSE.txt` 是 GNU GPL Version 3 全文；`setup.py:64` 写 `license="GPL-3.0+"`；`README.rst:372`「licensed under the GPL 3 (or any later version at your option)」；本机 venv 里 `chess 1.11.2` 元数据同为 `GPL-3.0+`。SPDX：`GPL-3.0-or-later`。**强 copyleft（GPL 族）。**
- 维护：最后提交 2026-08-22（`0c6bdac`）；最新 release v1.11.2（2025-02-25）。活跃，星标约 2900。PyPI 上另有个 `python-chess 1.999` 空壳，只是依赖 `chess`，别当成另一个库。
- 相关能力：`chess.svg.board(board, lastmove=, check=, size=, colors=, arrows=, flipped=)` 直接出 SVG，含上一步高亮、将军红光；`node.emt()` 原生解析 `[%emt]`；评注里的 `[%think N]` 等自定义命令按普通文字保留，不影响解析（实测读 g1 棋谱 `errors=[]`）。
- 内置 SVG 棋子的原作者与许可：源码里没写明，我没核实。

## 2. lichess-org/lila-gif（Rust）

- 许可：AGPL-3.0-or-later。`LICENSE` 是 GNU Affero GPL v3 全文（661 行），`Cargo.toml` 写 `license = "AGPL-3.0+"`，README 写 "GNU Affero General Public License, version 3 or any later version"。**强/网络 copyleft（AGPL）。** 附带：字体 Noto Sans 为 Apache-2.0（`theme/font/LICENSE.txt`）；棋子集许可各不相同，`theme/piece/LICENSE.txt` 只指向 lila 的 COPYING.md，未逐个读。
- 维护：最后提交 2026-08-02（dependabot 合并）；仓库 2026-09-01 有推送；星标 115；GitHub 无 release、无 tag（浅克隆看不到全部历史，只知道本地检出为单提交深度）。
- 形态：HTTP 服务，默认 `127.0.0.1:6175`，只吐 GIF。
  - `GET /image.gif`：单个局面。参数 `fen`、`white`、`black`、`comment`、`lastMove`（UCI）、`check`（格子名或 yes）、`orientation`、`theme`（blue/brown/green/ic/pink/purple）、`piece`（约 40 套）、`coordinates`。
  - `POST /game.gif`：JSON，`white`/`black`/`orientation`/`theme`/`piece`/`delay`（默认每帧厘秒）/`coordinates`，`frames[]` 里每帧 `fen`、`delay`（覆盖）、`lastMove`、`check`、`glyph`（!、?、?? 等徽标）、`clock`（白黑各一个数字，做时钟条用）。**能喂任意局面序列，由调用方自己给。**
- 对本项目：
  - 必须有调用方脚本：用 python-chess 把 PGN 展开成 FEN、UCI、check 的 JSON（约 30 行）。评注怎么写都不影响，因为它根本不读 PGN。
  - 画面尺寸写死：棋盘 90px × 8 = 720 宽，有名字条时 720×840（`src/theme.rs` 的 `SQUARE = 90`，README 表格 720×840）。想要 1080×1920 只能事后用 ffmpeg 缩放加黑边，棋子是预渲染的位图精灵，放大会糊。
  - 没有标题画面、没有步数、没有终局原因文字。名字条字体是 Noto Sans Regular，不含中文；名字如 `claude:opus` 这种 ASCII 没问题，中文会缺字。
  - 每帧延时精度 1 厘秒（u16），2.5 秒即 `delay: 250`。GIF 色板最多 255 色。
- 本机能不能跑：`which cargo rustc` 均无（`~/.cargo` 也没有）；`docker` 客户端在，但 `docker info` 只有 Client 段、没有 Server，判断 daemon 没起。**没有编译**。仓库自带 `Dockerfile`（rust:1-trixie 多阶段），需要 Docker daemon 或装 rustup 后 `cargo build --release`。依赖 crate 约 15 个（axum、tokio、shakmaty、gift 等），源码共约 1800 行。

## 3. prozn/gifpgn（Python，PyPI `gifpgn`）

- 许可：GPL-3.0-or-later。`LICENSE` 是 GPL v3 全文（674 行），`pyproject.toml` 写 `license = "GPL-3.0-or-later"`，本机安装后元数据同。**强 copyleft（GPL 族）。** 依赖 `chess==1.11.2`（精确锁版本，正好等于本机版本）和 `pillow>=12.3.0,<13`（本机系统 Pillow 是 11.3，得单独 venv）；要求 Python ≥3.10（系统 3.9.6 装不了，我用 `python3.13` venv 试的）。附带字体 Carlito（源码目录 `gifpgn/fonts/Carlito-Regular.ttf`，没读其许可）。
- 维护：最后提交 2026-09-03，v1.2.1 发布于 2026-09-03，星标 9，创建于 2021-06。近期活跃，用户少。
- 用法：`CreateGifFromPGN(game).generate("x.gif")`，属性 `board_size`（自动取 8 的倍数）、`frame_duration`（秒，浮点）、`add_headers(height)`（上下两条：名字、被吃子、有 `[%clk]` 时显示时钟）、`enable_arrows()`（蓝箭头标上一步，将军时红箭头指向王）、`reverse_board()`、`piece_theme`、`square_colors`。评估条、评估图、NAG 徽标需要每步有 `[%eval]`，本项目棋谱没有，不用。
- 我实测：`board_size=720, frame_duration=2.5, add_headers(48), enable_arrows()` → 720×816 GIF，96 帧，1.6 秒生成，748KB；名字条显示 `claude:opus` / `codex:sol`（截图已看）。用 ffmpeg 转 9:16 mp4 也跑通：`scale=1080:-2:flags=neighbor,pad=1080:1920`，见 `gifpgn_916.mp4`。
- 坑：
  - 末帧被硬编码复制 20 份（`gifpgn.py` `for _ in range(20)`），每份都是 `frame_duration`，2.5 秒时结尾停 52.5 秒（实测末帧 52500ms）。要么后处理裁掉，要么把 `frame_duration` 设小再自己拉长（后者会破坏节奏），实际得用 ffmpeg `-t` 裁。
  - 没有「上一步」方格高亮，只有箭头；将军只画红箭头，不亮王的格子。
  - 没有标题画面、终局原因、步数；字体 Carlito 不含中文。
  - 一次只能一盘，多盘要自己再拼。

## 4. tomasfarias/c2g（Rust CLI）

- 许可：GPL-3.0-or-later。`LICENSE` 是 GPL v3 全文，`Cargo.toml` 写 `GPL-3.0+`；README 列了例外：`svgs/cburnett/*.svg` GPLv2+、roboto Apache-2.0、oswald OFL。**强 copyleft（GPL 族）。**
- 维护：最后提交 2024-09-01，最新 release v0.9.0（2024-05-09），星标 3。**约一年没动；releases 页没有附二进制**（`gh api …/releases/latest` 的 assets 为 0），得自己 `cargo build --release`。本机无 cargo，未编译。
- 用法：`cat game.pgn | c2g --size 640 --delay 2500 --first-frame-delay … --last-frame-delay … --flip --output x.gif`；有名字条（读 White/Black 头，含 Elo）、将军时王格发光、终局在王上画圈（读 `Termination` 头，认不出就当「认输」）。棋盘是正方形，尺寸可调，但只出 GIF。
- 对本项目的两个雷（读源码 `src/giffer.rs` 得出，没编译验证）：
  - 评注里凡是像 `h:mm:ss` 的都被当成时钟（正则 `\d{1,2}:\d{2}:(\d{2}.\d{1}|\d{2})`）。我们的 `[%emt 0:00:04]` 会被显示成对方的「时钟」。要规避得先把 PGN 里的 `%emt` 改写掉。
  - `TimeControl` 头解析用 `.unwrap()`，头格式不对会 panic（本项目棋谱没有此头，暂不触发）。
- 没有上一步高亮（`draw_move` 只画棋子、不涂格）；没有标题画面；中文终局原因无法识别。

## 5. afozk95/pgn-to-gif（Python，PyPI `pgn-to-gif`，命令 `pgn2gif`）

- 许可：MIT。`LICENSE` 是标准 MIT 全文（Copyright 2021 Ahmed Furkan Özkalay），`setup.py` 写 `MIT`。依赖 python-chess（GPL）、cairosvg（LGPL-3.0-or-later，本机 venv 元数据）、imageio（BSD-2-Clause）。**自身 MIT，但运行时链接 GPL 的 python-chess 和 LGPL 的 cairosvg，组合后的义务别自己断。**
- 维护：最后提交 2021-06-03，v0.0.3，星标 2。**已停更四年。**
- 用法：`pgn2gif --pgn-path x.pgn --gif-path y.gif --size 720 --fps 0.4`（我实测出 720×720 GIF，96 帧，6.5 秒；需要 `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` 让 cairosvg 找到 Homebrew 的 cairo）。
  - 上一步高亮：有（`chess.svg` 的 lastmove，截图已看，黄绿格）。
  - 将军：**没有**（源码 `board_to_svg` 不传 `check`）。名字、标题、终局：**没有**。
  - 帧延时坑：CLI 同时传 `--duration 2.5` 和默认 `--fps 1.0` 时，实际 1000ms（`fps` 压过 `duration`），我实测帧延时集合 `{1000}`；要用 `--fps 0.4` 才是 2.5 秒。默认色板 16 色（CLI 默认 64），画质一般。
  - 解析：用 python-chess 读，评注不影响。
- 价值主要是「示范 python-chess SVG + cairosvg + imageio 这条路」，本身太薄。

## 6. fork52/chess_gif（Python，PyPI `chess-gif`）

- 许可：MIT。`LICENSE` 标准 MIT 全文（Copyright 2020 Mrunank Mistry），`setup.cfg` 写 MIT。依赖 python-chess（GPL）、pyvips（要装 libvips）、imageio、pygifsicle（外部程序 gifsicle，macOS 装时走 brew；gifsicle 许可我没读）、Pillow。
- 维护：最后提交 2024-07-14（release 1.2.0），星标 16，无 GitHub release。
- 功能：只出棋盘 GIF，参数 `colors`、`piece_theme`、`side`（格子像素）、`h_margin/v_margin`、`delay`（毫秒）。源码（`create_frame.py`、`gif_maker.py`）里没有名字、上一步高亮、将军、标题、终局任何处理。未安装试跑（依赖 libvips，收益低）。

## 7. dn1z/pgn2gif（Python，另一个同名 `pgn2gif`）

- 许可：MIT。`LICENSE`「Copyright (c) 2018 M. Deniz Kızılırmak」标准 MIT。依赖只有 Pillow，没有 python-chess。
- 维护：最后提交 2021-01-24，星标 108，无 release；**已停更**。
- 特点：**自己写的 PGN 解析**（`chess.py`，用正则把 `{…}` 和 `[…]` 整段删掉再逐步解 SAN，靠自己写的走法判定）。我实测跑 g1 棋谱成功，96 帧，`-d 2.5` 每帧 2500ms，棋盘固定 480×480（`_BOARD_SIZE = 480` 硬编码）。
- 没有名字、上一步高亮、将军、标题、终局。自写规则解析不如 python-chess 可信，遇到升变、歧义着法未逐条验证。价值低。

## 8. 其他两个值得记一笔的

- **boneyland/chess-animator**（Python + Manim，MIT，`LICENSE.txt` 为标准 MIT，Copyright 2026 David Joyner）：创建于 2026-09-23、最后提交 2026-09-29，星标 1，**极新**。能直接出 720p 视频，画面是固定横屏 16:9 布局（左棋盘，右侧步表、评注、Stockfish 分析、评估条、评估曲线），每步约 1.6 秒，评注会显示。需要 Python 3.12+、manim、manim-chess（MIT）、**Stockfish 二进制**做分析（其 README 称 82 步要 4 分 50 秒），依赖大（cairo/pango 要编译）。有玩家条、将军发光。对我们：布局固定横屏、不能竖屏、评注是必显的（不符合「录屏版不显示评注」）、强依赖引擎分析；不匹配。本机没装 manim，未试跑。
- **shaack/pgn-to-video-converter**（JS，浏览器网页，用 canvas + MediaRecorder 录制成视频）：`package.json` 写 MIT，**但仓库里没有 LICENSE 文件**（GitHub 也识别为无许可）；2025-01-11 最后提交，星标 1。本质上还是「浏览器录屏」，只是把录制内置到页面里，出的是浏览器编码的视频（webm/mp4 取决于浏览器），不属于本次要的 CLI 路线，也没有名字、标题、终局。未试跑。
- 另有 erayzeki/chess-to-video（PGN → AVI，GitHub 识别无许可，2021 最后更新）、crebro/ChessPGN-GIF（无许可，2021）、mzfr/pgn2gif（已归档），都太旧或无许可，没细看。
- 在线服务（chess.rodeo、violetcrownchess.com 等）不在本次范围。

## 9. 候选 × 需求 勾选表

图例：✅ 满足；◐ 部分或要变通；❌ 不满足；？ 未验证。「实测」指我在本机跑出来看过截图或元数据。

| 需求 | lila-gif | gifpgn | c2g | pgn-to-gif (afozk95) | chess_gif | pgn2gif (dn1z) | chess-animator | 自制 |
|---|---|---|---|---|---|---|---|---|
| 许可类别 | AGPL-3.0+ | GPL-3.0+ | GPL-3.0+ | MIT（依赖 GPL/LGPL） | MIT（依赖 GPL） | MIT | MIT（依赖 GPL；要 Stockfish） | 依赖 python-chess GPL、cairosvg LGPL |
| 直接读 PGN | ❌ 要脚本展开成 FEN | ✅ | ✅ | ✅ | ✅ | ✅（自写解析） | ✅ | ✅ |
| 自定义评注不致解析失败 | ✅（不读 PGN） | ✅ 实测 | ◐ `%emt` 被误当时钟 | ✅ 实测 | ？未试 | ✅ 实测 | ◐ 评注会显示成解说 | ✅ 实测 |
| 每帧延时可调（2–3 秒） | ✅ 每帧 `delay` 厘秒 | ✅ `frame_duration` | ✅ `--delay` 毫秒 | ◐ 要用 `--fps`，`--duration` 被压 | ✅ `delay` 毫秒 | ✅ `-d` 秒 | ❌ 固定约 1.6 秒 | ✅ |
| 画面比例 9:16 / 16:9 | ❌ 固定 720 宽，事后 ffmpeg 补边 | ❌ 方形加条，事后补边（实测 OK） | ❌ 方形，事后补边 | ❌ 方形 | ❌ 方形 | ❌ 固定 480 方形 | ◐ 仅横屏 16:9 | ✅ 任意 |
| 清晰度（高 DPI） | ❌ 位图精灵放大糊 | ✅ 棋盘尺寸可设大 | ✅ SVG 渲染，尺寸可设 | ✅ SVG | ✅ | ❌ 480 | ✅ 720p 起 | ✅ SVG 矢量 |
| 双方名字 | ✅ 名字条（ASCII 行，中文缺字） | ✅ 头部条（无中文字体） | ✅ 名字条（读头） | ❌ | ❌ | ❌ | ✅ | ✅ |
| 上一步高亮 | ✅ `lastMove` | ◐ 蓝箭头，无格子高亮 | ❌ | ✅ 黄绿格 | ❌ | ❌ | ✅（配 NAG 色） | ✅ |
| 将军提示 | ✅ `check` | ◐ 红箭头 | ✅ 王发光 | ❌ | ❌ | ❌ | ✅ | ✅ 红光 |
| 标题帧 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ◐ 有开头卡但布局固定 | ✅ |
| 终局原因（含中文） | ❌ | ❌ | ◐ 王上画圈，中文原因识别不了 | ❌ | ❌ | ❌ | ◐ 末尾有引擎信息卡 | ✅ 自己写 |
| 多盘拼接 | ❌ 一次一盘 | ❌ | ❌ | ❌ | ❌ | ◐ CLI 可传多个 pgn，各出各的 gif | ◐ `--game N` 选一盘，不拼 | ✅ ffmpeg concat |
| 隐藏评注（录屏版） | ✅ 不显示 | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ 评注必显 | ✅ 自控 |
| 输出直接是视频 | ❌ GIF（要 ffmpeg 转） | ❌ GIF（实测转 mp4 可） | ❌ GIF | ❌ GIF | ❌ GIF | ❌ GIF | ✅ mp4 | ✅ mp4 |
| 维护状态 | 2026-08 活跃，无 release | 2026-09 活跃 | 2024-09 停更一年，无二进制 | 2021 停更 | 2024-07 | 2021 停更 | 2026-09 极新 | 无 |
| 本机实测 | 未编译（无 cargo） | 跑通 | 未编译 | 跑通 | 未装 | 跑通 | 未装 | 跑通 |

要点：**所有候选都不出标题帧、终局原因、竖屏，没有一个能拼多盘**；这四项凡要就得自己写 ffmpeg 外壳，此时「现成工具」只剩画棋盘那一段，而 python-chess 的 `chess.svg` 已经把这一段做完了（含上一步高亮和将军红光）。

## 10. 自制路线：python-chess 出 SVG 帧 → PNG → ffmpeg 合成

我在 `chess-prototype-render.py` 写了个原型（68 行），实测：

- 输入 g1 棋谱，输出 1080×1920 mp4，标题 3 秒 + 初始局面 + 95 步 × 2.5 秒 + 终局横幅 4 秒，总长 248.5 秒；渲染约 18 秒（cairosvg 出 96 张 PNG，多核）；文件 2.3MB。
- 已含：标题画面（对局名、双方名字大字）、上下名字条（含「白/黑」中文字样）、步数、上一步两格黄绿高亮、被将军王的红色光晕（`chess.svg` 的 `check=` 自带）、终局横幅（读 `Termination` 头，「将死 Checkmate 1-0」）。截图已看，效果可用。
- 全程用本机 `ffmpeg 9.0.2`（concat demuxer 的 `duration` 控制每帧时长，再 `fps=30` 输出）。

**估算行数**（在原型基础上做成能用的成品）：

| 部分 | 行数 |
|---|---|
| 单盘：PGN → 帧（含 9:16 与 16:9 两种布局） | 约 100 |
| 标题帧和终局帧的版式、终局原因映射（将死、和棋各类、认输、超时、非法过多等，词表以本项目记录格式为准） | 约 40–60 |
| 多盘拼接：每盘各出一段 mp4，再 `ffmpeg -f concat -c copy`（各段编码参数一致即可无损拼） | 约 20 |
| 命令行、参数（每步秒数、比例、输出路径、批量目录） | 约 30–40 |
| 合计 | 约 200–250 行 Python，一个文件 |

**难点与我的发现**：

1. **中文字体**：Pillow 画字要给字体文件。本机可用 `/System/Library/Fonts/Hiragino Sans GB.ttc`（原型用的，中英混排正常），但字体路径依赖 macOS，换机器要改；要打包就得选可再分发的开源 CJK 字体（如 Noto Sans CJK 系，许可我没核实）。`chess.svg` 本身不含文字，坐标标签可以关（`coordinates=False`）。
2. **cairosvg 需要系统 cairo**：本机 Homebrew 有 `cairo`，但 Python 找不到，要设 `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`。另外系统 Python 3.9.6 没装 cairosvg，我用 `python3.13` venv 装的。规避办法：用 `chess.svg` 出 SVG 后交给 `rsvg-convert`/`resvg`（本机都没装），或在 Pillow 里自己画格子加贴图（不用 SVG，但要自备棋子图）。
3. **本机 ffmpeg 没有 drawtext 和 libfreetype**（`ffmpeg -filters` 里没有）：所以文字必须在 Pillow 里画好再交给 ffmpeg，不能靠 ffmpeg 加字幕。反过来这样更稳，版式全在一处。
4. **标题画面、竖屏布局**：难度不大，全是 Pillow 排版；要做得好看（字号、留白、渐变）是设计活，不是技术活。竖屏时 1080 宽下棋盘 1040 见方，上下各留名字条，没问题。
5. **将军高亮**：`chess.svg.board(check=王格)` 一行搞定（径向红光），cairosvg 渲染正常。上一步高亮 `lastmove=` 同理。
6. **升变、吃过路兵、王车易位的动画**：不需要——本方案是逐步定格切换（每步一张静态图，符合「每步 2–3 秒」），没有走子动画；要做走子滑动动画才要插值帧，行数会翻倍以上。
7. **速度**：每帧一次 SVG→PNG（约 0.05–0.2 秒/帧），一盘 100 步几十秒以内；多盘可多进程并行。
8. **变更点**：每步元信息不画（录屏版无评注），所以不需要处理评注里的全角字符、超长文字换行；将来若要做「回放版」带评注，这条路就得加文字排版，不划算，回放版更适合网页。
9. **中国象棋**：这套办法**不适用**。`chess.svg` 只管国际象棋；中国象棋棋盘、棋子图、九宫、河界要自己画或另找资源（已有 `cchess` 包在本机，我没查它有无渲染），需另行评估，不在本次范围。

**与「GIF 工具 + ffmpeg」对比**：GIF 工具省的是「画棋盘」这一段（几十行），代价是尺寸/色板/末帧停留时间等被工具写死，且 GPL/AGPL 组件多带进来；自制的画面自由度高，依赖只有 python-chess（已在用）、cairosvg（LGPL）、Pillow（MIT-CMU）、ffmpeg（本机 Homebrew 版编译带 `--enable-gpl`，属于外部程序调用）。

## 11. 关于「GIF 转视频」这一步（所有 GIF 类工具共用）

- 实测可行：`ffmpeg -i x.gif -vf "scale=1080:-2:flags=neighbor,pad=1080:1920:0:(oh-ih)/2:color=0x181820,fps=30,format=yuv420p" -t <秒数> -c:v libx264 -crf 20 out.mp4`，尊重 GIF 里每帧不同的延时。gifpgn 的 240 秒 GIF 转出 240.0 秒 mp4，耗时约 16 秒，2.7MB。
- 缺陷：GIF 最多 256 色，抗锯齿边缘略脏；`flags=neighbor` 放大会更锐但有锯齿。
- 标题画面、终局横幅得另做 PNG 用 ffmpeg 前后拼上（本机 ffmpeg 有 `concat`、`overlay`、`xfade`，没有 `drawtext`）。

## 12. 未完成、未核实项

- lila-gif、c2g 本机无 cargo，**没有编译、没有运行**；关于它们输出的画面细节（尺寸、字体、发光效果）来自源码和 README，未看实图。要试的话最快的路径是装 rustup（改动系统环境，需你同意）或起 Docker daemon 用它自带的 Dockerfile。
- chess_gif、chess-animator、shaack 未安装试跑。
- 各棋子图集（cburnett 等）的具体许可没有逐个读原文。
- 没有对任何候选做「一盘以上、几百步」的压力测试。
