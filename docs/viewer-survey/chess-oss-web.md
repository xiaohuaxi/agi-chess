# Web 端开源 PGN 播放器与棋盘库调研（国际象棋）

> 调研日期 2026-09-29。只调研、未改任何已有仓库。
> 源码检出（`git clone --depth 1`，均为新建目录）：`~/repos/{pgn-viewer, pgn-viewer-mliebelt, chessground, cm-chessboard, chessboardjs, chessboard2, react-chessboard, chessboardjsx, chess.js, pgn-parser, chessops, cm-pgn}`。lichess 与 mliebelt 的仓库都叫 `pgn-viewer`，后者只好加了后缀放在 `pgn-viewer-mliebelt`。pgn4web 只有 SourceForge SVN 和 zip 包，zip 解压在 `pgn4web-src/pgn4web-3.09`（没放进 ~/repos）。
> 实测环境：`pgntest/`（npm 包、测试脚本、测试 PGN）。浏览器实测用 playwright-core 加本机缓存的 chromium headless shell，deviceScaleFactor=2；截图在 `shot-*.png`。
> 标注：**实测** = 在 node 或无头浏览器里跑过；**读源码** = 看了对应源文件；**推测** = 没验证。

## 0. 结论先行

- **没有哪个现成播放器开箱就能满足「录屏模式」加「元信息回放」。** 最接近的是 **pgn4web**（GPL-2.0-or-later）：多盘连播、可调间隔、网址参数、每步回调、从评注读自定义命令它都有（实测）。但它是 2009 年起的老式全局函数代码，没有将军高亮，也没有标题画面。**lichess pgn-viewer**（GPL-3.0-or-later）回放界面最好看，但没有自动播放，只认第一盘，`[%think …]` 会原样显示成文字（实测）。**mliebelt pgn-viewer**（GPL-3.0-or-later）有播放按钮和间隔配置，但只能手动开播，没有播完信号，跳步接口只换棋盘、不同步棋谱（读源码）。
- **许可分两派**：lichess 系（pgn-viewer、chessground、chessops）、mliebelt pgn-viewer、pgn4web 都属 GPL 族（强 copyleft）；cm-chessboard（MIT）、chess.js（BSD-2-Clause）、@mliebelt/pgn-parser（Apache-2.0）、cm-pgn（MIT）、chessboard.js（MIT）、chessboard2（ISC）、react-chessboard（MIT）、chessboardjsx（MIT）属宽松许可。本仓库 AGENTS.md「通用开发规范」把 GPL/AGPL 列在「明确不能用」一族，简报又说边界问维护者。本文只列事实，用不用由维护者定。
- **宽松许可路线要自己写一个薄播放层**：解析用 **@mliebelt/pgn-parser**，它把 `[%think 34]` 这类未知命令直接解析成键值（实测，四个解析器里只有它这样做）；棋盘用 **cm-chessboard**（SVG 渲染、零依赖，`setPosition` 返回 Promise、动画结束才 resolve，便于卡节奏）；走子合法性和将军判断用 **chess.js**。标题画面、自动播放、网址参数、`window` 上的控制接口、播完标记、两种显示模式，粗估 400–700 行 JS/CSS（推测）。
- **所有解析器都有一个共同的坑（实测）**：`game.pgn` 把没有空格的中文长串硬切折行，解析器要么保留 `\n`，要么换成空格，渲染出来中文中间都会多一个空格（lichess 和 pgn4web 的截图里都看得见「用来测试 硬切折行」）。不管选哪家，加载时都得把「中日韩字符 + 换行 + 中日韩字符」拼回去，或者改导出端。

## 1. 需求编号（取自 docs/viewer-brief.md）

| 编号 | 需求 |
|---|---|
| R1 | 多盘连播，一盘播完自动接下一盘 |
| R2 | 固定间隔自动走子，默认 2–3 秒，可调 |
| R3 | 每步元信息：理由、耗时、思考 token、输出 token、非法次数 |
| R4 | 录屏时隐藏元信息，回放时显示 |
| R5 | 网址参数或 JS 直接进入录屏状态，并能知道何时播完（Playwright 无头录制） |
| R6 | 节奏稳定，不因加载卡顿丢步 |
| R7 | 9:16 和 16:9 的干净画面，高 DPI |
| R8 | 每盘开头的标题画面 |
| R9 | 双方玩家名（模型名加思考深度）、执哪方 |
| R10 | 上一步高亮 |
| R11 | 被将军提示 |
| R12 | 终局结果和结束原因（Termination 头） |
| R13 | 暂停、前后单步、跳到任意一步 |
| R14 | 数据留在本地 |
| R15 | 能解析 `[%think N]` 这类自定义命令，`%emt` 能识别，全角字符和中文正常 |

## 2. 候选×需求勾选表

✅ 开箱满足　◐ 部分满足或需要少量配置、胶水代码　✗ 不支持，要自己写　— 不适用（纯棋盘或纯解析库，这一项由上层自己写）

| 候选 | 许可 (SPDX) | R1 连播 | R2 间隔 | R3 元信息 | R4 显隐 | R5 自动化/播完 | R6 节奏 | R7 比例/DPI | R8 标题 | R9 玩家 | R10 上步 | R11 将军 | R12 结果原因 | R13 控制 | R14 本地 | R15 解析 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lichess-org/pgn-viewer | GPL-3.0-or-later | ✗ | ✗ | ◐ 原样显示 | ◐ CSS | ◐ 有 JS API，没有播完事件 | ◐ 外部驱动 | ◐ | ✗ | ✅ | ✅ | ✅ | ◐ 只有结果 | ✅ | ✅* | ◐ |
| mliebelt/pgn-viewer | GPL-3.0-or-later | ◐ 下拉选盘 | ✅ timerTime | ◐ 只显示理由文字 | ◐ | ✗ 没有开播 API、没有播完信号 | ◐ | ◐ | ✗ | ◐ | ✅ | ◐ 推测 | ◐ | ◐ 跳步接口有缺陷 | ✅ | ✅ |
| pgn4web | GPL-2.0-or-later | ✅ | ✅（下限 500ms） | ◐ 理由已净化，数字靠 API 取 | ✅ 网址参数 | ◐ 网址参数加每步回调，播完要自己判断 | ✅ 实测稳 | ◐ SVG 棋子可选 | ✗ | ✅ | ✅ | ✗ | ◐ 读头可取 | ✅ | ✅ | ✅ |
| lichess-org/chessground（棋盘） | GPL-3.0-or-later | — | — | — | — | — | ◐ | ✅ | — | — | ✅ | ✅ | — | — | ✅ | — |
| shaack/cm-chessboard（棋盘） | MIT | — | — | — | — | — | ✅ Promise | ✅ SVG | — | — | ◐ markers | ◐ markers | — | — | ✅ | — |
| oakmac/chessboardjs（棋盘） | MIT | — | — | — | — | — | ◐ | ◐ 默认 PNG | — | — | ✗ 自己加 CSS | ✗ | — | — | ✅ | — |
| oakmac/chessboard2（棋盘） | ISC | — | — | — | — | — | ◐ | ◐ | — | — | ◐ | ✗ | — | — | ✅ | — |
| react-chessboard（棋盘） | MIT | — | — | — | — | — | ◐ | ✅ | — | — | ◐ squareStyles | ◐ squareStyles | — | — | ✅ | — |
| willb335/chessboardjsx（棋盘） | MIT | — | — | — | — | — | ◐ | ◐ | — | — | ◐ | ✗ | — | — | ✅ | — |
| jhlywa/chess.js（规则加解析） | BSD-2-Clause | ✗ 一次只载一盘 | — | ◐ 原始评注串 | — | — | — | — | — | ✅ 读头 | ✅ 走法记录 | ✅ isCheck | ✅ 读头 | — | ✅ | ◐ 原样保留 |
| @mliebelt/pgn-parser（解析） | Apache-2.0 | ✅ parseGames | — | ✅ commentDiag 键值 | — | — | — | — | — | ✅ | — | ✅ check 标记 | ✅ | — | ✅ | ✅ |
| chessops（规则加解析） | GPL-3.0-or-later | ✅ | — | ◐ 只识别 emt/clk | — | — | — | — | — | ✅ | ✅ | ✅ | ✅ | — | ✅ | ◐ |
| cm-pgn（解析） | MIT | ✅ PgnList | — | ◐ 原始评注串 | — | — | — | — | — | ✅ | ✅ | ✅ inCheck | ✅ | — | ✅ | ◐ |

\* lichess pgn-viewer 的菜单里有「分析棋盘 / 和电脑练习」外链，点了会把当前局面 FEN 带到 lichess.org；可以在配置里关掉。

## 3. 维护状态总表

| 候选 | 最后提交 | 最近发布 | npm 周下载 | Stars / 开放 issue | 备注 |
|---|---|---|---|---|---|
| lichess-org/pgn-viewer | 2026-09-19 | v2.6.4（2026-08-19） | @lichess-org/pgn-viewer ≈1.4k；旧包名 lichess-pgn-viewer ≈550 | 153 / 6 | lichess 官方在维护，活跃 |
| mliebelt/pgn-viewer | 2026-09-22（dependabot 合并） | npm 1.6.11（2025-04-21），GitHub release 停在 2020 | ≈90 | 187 / 62 | 最近 20 次提交全是机器人合并的依赖升级，功能开发基本停了 |
| pgn4web | SourceForge 显示 2026-09-18 更新 | 3.09 | —（SF 周下载约 11） | — | 单人长期维护，SVN |
| lichess-org/chessground | 2026-09-29 | v10.4.1（2026-09-29） | @lichess-org/chessground ≈6.2k；旧包名 chessground ≈12.6k | 1371 / 31 | 很活跃 |
| shaack/cm-chessboard | 2026-09-28 | npm 8.15.1（2026-09-28，没有 GitHub release） | ≈3.6k | 305 / 0 | 活跃 |
| oakmac/chessboardjs | 2022-12-09 | npm 1.0.0（2019） | ≈650（加上旧包 chessboardjs ≈500） | 2131 / 109 | README 写明作者转去做 chessboard2，基本停更，依赖 jQuery |
| oakmac/chessboard2 | 2023-05-30 | v0.5.0（2023-05-30） | ≈230 | 112 / 46 | 预发布状态，2023 年后没有提交 |
| Clariity/react-chessboard | 2026-08-16 | v5.12.1（2026-08-16） | ≈48k | 546 / 2 | 活跃，要 React |
| willb335/chessboardjsx | 2021-03-31（最后推送 2022） | v2.4.7（2021） | ≈470 | 270 / 26 | README 第一行就是「UNMAINTAINED」 |
| jhlywa/chess.js | 2026-08-11 | v1.4.0（2025-06-14） | ≈183k | 4414 / 46 | 事实标准，活跃 |
| mliebelt/pgn-parser | 2026-09-29（dependabot） | npm 1.4.19（2025-10-04） | ≈3.5k | 78 / 6 | 以依赖升级为主 |
| niklasf/chessops | 2026-09-10 | npm 0.15.1（2026-07-12） | ≈23k | 172 / 8 | lichess 作者维护，活跃 |
| shaack/cm-pgn | 2026-07-24 | npm 5.0.0（2026-07-23） | ≈410 | 42 / 0 | 活跃，但用户量小 |

## 4. 逐个候选

### 4.1 lichess-org/pgn-viewer

- **许可**：`~/repos/pgn-viewer/LICENSE` 是 GNU GPL v3 原文；package.json 写的是 `GPL-3.0-or-later`；README 专门强调「嵌入网站后组合作品只能按 GPL 分发，必须向网站用户公开源码」。**强 copyleft**。依赖的 chessground、chessops 也都是 GPL-3.0-or-later。
- **维护**：见总表，活跃。
- **能力**（读源码 `src/config.ts`、`src/pgnViewer.ts`、`src/pgn.ts`、`src/view/side.ts`；浏览器实测 `shot-lichess.png`）：
  - 回放 UI 完整：上一步高亮、将军高亮（chessground 的 `check`）、上下方显示玩家名（取 White/Black 头，实测显示 `claude:opus` / `codex:astra`）、棋谱列表里夹着评注、结果（`1-0`）。键盘左右键翻步，还有翻转棋盘。
  - **不认 Termination**，只显示 Result（读源码 `makeMetadata`）。
  - **没有自动播放**，也没有定时器（读源码，全仓库搜不到 timer/autoplay）。
  - **只读第一盘**：`parsePgn(pgn)[0]`（读源码 `pgn.ts`）。要连播就得每盘重新建一个实例。
  - **JS API**：工厂函数返回 `PgnViewer` 实例，有 `goTo('first'|'prev'|'next'|'last')`、`toPath(path)`、`flip()`、`game.mainline[]`（每步带 san/fen/check/comments/emt）、`initialPly` 配置、`canGoTo()`。**没有事件回调、没有网址参数**。播完只能由外部驱动的脚本自己判断（`canGoTo('next') === false`）。
  - **R7**：棋盘由 chessground 用 CSS 背景画 SVG 棋子，高 DPI 清晰（实测 2x 截图）；布局靠 `showMoves: false|'right'|'bottom'|'auto'` 和 CSS 变量，想要干净画面得自己写 CSS 把控件藏掉（`showControls: false`、`showPlayers`）。
- **怎么喂 PGN、评注的命运**（实测 `t_chessops.mjs` 加浏览器 DOM 提取）：
  - `%emt` 被识别并从文字里剥掉，存进 `move.emt`（秒）。但界面上**不显示** emt（读源码：view 里只渲染 clk 时钟）。
  - `[%think 0] [%out 9] … [%illegal 1]` **原样当评注文字显示**，界面上能直接看到 `[%think 34] [%out 47] …`（截图可见）。不报错、不吞掉。
  - 全角 `｛｝％` 和中文正常显示；硬切折行处的 `\n` 被保留，渲染出来多一个空格。
- **要补多少**：连播、自动播放、定时器、播完信号、标题画面、结束原因、元信息的结构化显示（得先改评注，或在喂进去之前预处理），还要把 `[%…]` 从文字里剥掉。改动面大，而且改了就是 GPL 衍生作品。只当「回放模式」用、不改源码的话，可以在喂 PGN 前把评注预处理成易读文字（推测可行）。

### 4.2 mliebelt/pgn-viewer（原 PgnViewerJS）

- **许可**：`~/repos/pgn-viewer-mliebelt/LICENSE` 是 GNU GPL v3 原文；package.json 写 `GPL-3.0-or-later`。**强 copyleft**。依赖 chessground 9.x（GPL-3.0）、@mliebelt/pgn-reader（Apache-2.0），还有 FontAwesome free（图标 CC-BY-4.0 / 代码 MIT，推测，没细查）。
- **维护**：功能开发基本停了（npm 最后一版 2025-04，之后全是依赖机器人），开放 issue 62 个。
- **能力**（读源码 `src/pgnv.ts`、`src/types.ts`、`src/timer.ts`；浏览器实测 `shot-mliebelt.png`）：
  - 有播放按钮和 `timerTime` 配置（默认 700ms，可设 2000–3000）。空格键或点按钮切换播放，定时器是一个 10ms 分辨率的 setTimeout 循环。
  - **开播只能靠点按钮或按空格**：`togglePlay` 是内部函数，公开 API（`jumpToMove`、`stop`、`manualMove`、`getPgn` 等）里没有 play。Playwright 可以 `click` 播放按钮（推测可行）。
  - **播完没有信号**：`nextMove()` 走到末步只是返回 false，定时器还在空转（读源码）。
  - **`jumpToMove(n)` 只改棋盘 FEN**，不更新当前步和棋谱高亮（读源码第 1999 行一带，自己的注释也写着「// Something」）。
  - `manyGames: true` 时顶部出现一个选盘下拉框（实测列出了两盘），**不会自动接下一盘**。
  - 显示玩家头、结果（`showResult`）、上一步高亮（chessground）；`timeAnnotation` 只处理 `%clk`，不处理 `%emt`（读源码第 1144 行一带）。
  - 实测里 `initialPly` 类的参数不起作用（棋盘停在初始局面），版式比较朴素。
- **评注的命运**（实测，它用的 pgn-parser 同 4.11）：`[%…]` 命令被解析进 `commentDiag`，界面上只显示剩下的理由文字（实测 DOM：「控制中心，开放象和后的出路。」）。自定义数字不显示，要显示得改源码。
- **要补多少**：开播 API、播完事件、跳步修复、自动接下一盘、标题画面、元信息面板，都得动源码（GPL 衍生）。

### 4.3 pgn4web（附加候选，值得看）

- **许可**：`pgn4web-3.09/README.txt` 第 520 行起写「GNU General Public License … either version 2 of the License, or (at your option) any later version」，随包附 `license-gpl-2.0.txt`，即 **GPL-2.0-or-later，强 copyleft**。包内资源许可各不相同：jscolor 是 LGPL（弱 copyleft）；SVG 棋子来自 Wikimedia（GFDL / CC-BY-SA-3.0 / GPL 任选），或 openclipart（CC0）；PNG 棋子是 CC-BY-4.0；字体派生自 Liberation Sans（GPL）。
- **维护**：SourceForge 显示 2026-09-18 更新，版本 3.09，SVN 仓库，单人长期维护。GitHub 上只有多年前的旧镜像。
- **能力**（读源码 `pgn4web.js`、`board.html`；浏览器实测 `run2.mjs`、`shot-pgn4web2.png`）：
  - **网址参数非常多**（`board.html` 用 `gup()` 读取，70 多个）：`pgnData=文件`、`autoplayMode=game|loop|none`（缩写 `am=g|l|n`）、`delay=毫秒`、`initialGame`、`initialHalfmove`、`showComments`、`commentsDisplay`、`pieceFont=svgchess`、`squareSize`、`headerDisplay`、`movesDisplay`、`highlightMode`，各种颜色、字号等等。
  - **多盘连播**：`SetAutoplayNextGame(true)`，或网址 `am=loop`。实测两盘按顺序播完后又绕回第一盘（loop 模式是无限循环）。
  - **间隔**：`SetAutoplayDelay(ms)`，限制在 `minAutoplayDelay=500` 到最大值之间（读源码）。实测设 300ms 被抬到 500ms，12 步的间隔稳定在 501–504ms（样本小，只能看方向）。
  - **JS API 和回调**：`GoToMove(ply, var)`、`MoveForward(n)`、`SetAutoPlay(bool)`、`Init(game)`；全局变量 `currentGame`、`numberOfGames`、`CurrentPly`、`StartPly`、`PlyNumber`；钩子 `customFunctionOnMove()`、`customFunctionOnPgnGameLoad()`（实测 customFunctionOnMove 每步都触发）。**「播完」没有现成事件**，要在 onMove 里判断「最后一盘、最后一步」，然后关掉自动播放、打标记（实测能拿到判断所需的全部状态）。
  - **读自定义命令**：`customPgnCommentTag('think', elementId, ply)` 能读任意 `[%名 值]`（实测第 2 步读出 `34`，`emt` 读出 `0:00:11`）；`customPgnHeaderTag('Termination')` 读出 `将死`（实测）。
  - **显示**：评注里的 `[%…]` 在显示时被全部剥掉（读源码 `strippedMoveComment`，实测输出干净的中文理由）。全角字符和中文正常；硬切折行处同样多一个空格（实测）。
  - 上一步高亮有；**棋盘上没有将军高亮**（源码只在合法性检查里用 IsCheck，推测没有显示用途）；没有标题画面。
  - 默认 PNG 棋子在 2x 屏上发糊（实测截图）。改 `pieceFont=svgchess` 就清晰了（实测）。
- **要补多少**：播完标记、元信息面板、将军提示、标题画面、9:16 版式，要写一个自定义 HTML 页面加几十到一两百行胶水（推测）。代码是 ES5 全局函数加 `document.write`，扩展起来别扭。
- **数据本地**：纯静态文件，从同源的 `pgnData` 读，不上传（读源码，推测没有外发请求，没抓包验证）。

### 4.4 lichess-org/chessground（棋盘）

- **许可**：`~/repos/chessground/LICENSE` 是 GPL v3 原文，package.json `GPL-3.0-or-later`，**强 copyleft**。
- **能力**（读 `src/config.ts`）：`fen`、`lastMove`、`check`（加 `highlight.lastMove/check`）、`animation.{enabled,duration}`、`coordinates`、`viewOnly`、`orientation`、drawable 箭头。棋子用 CSS 背景（assets 带 cburnett SVG），高 DPI 清晰。**只是棋盘**，播放、解析、UI 都要自己写；`set()` 同步返回，动画结束没有 Promise（推测，没细看）。
- **可控性**：纯 JS API，没有网址参数。

### 4.5 shaack/cm-chessboard（棋盘）

- **许可**：`~/repos/cm-chessboard/LICENSE` 是 MIT 原文。宽松许可。
- **能力**（读 `src/Chessboard.js`、`src/extensions/markers/Markers.js`）：零依赖 ES6 模块，**SVG 渲染**（高 DPI 清晰，推测，没截图）；`responsive`、`style.aspectRatio`、`borderType`、`showCoordinates`、`animationDuration`（默认 300ms，0 关动画）；`setPosition(fen, animated)` **返回 Promise，动画队列结束后才 resolve**，适合「等这步画完再计时」，对 R6 有利；Markers 扩展有 `frame / square / circleDanger / circleDangerFilled` 等，可以用来画上一步（square/frame）和将军（circleDanger）；还有 Arrows、HtmlLayer 扩展（能在棋盘上叠 HTML，比如终局横幅）。
- 维护活跃，npm 周下载约 3.6k。
- 要自己写：解析、播放控制、全部 UI。

### 4.6 oakmac/chessboardjs 与 chessboard2（棋盘）

- **许可**：chessboardjs 是 `~/repos/chessboardjs/LICENSE.md`（MIT 原文，Copyright 2019 Chris Oakman）；chessboard2 是 `~/repos/chessboard2/LICENSE.md`（ISC 原文）。都是宽松许可。
- chessboardjs：依赖 jQuery；默认棋子是 wikipedia PNG（仓库 `website/img/chesspieces/wikipedia` 里也有 SVG，配置 `pieceTheme` 可以换）；有 `moveSpeed/appearSpeed`、`position(fen, useAnimation)`；**没有内置高亮**，上一步和将军要自己加 CSS 类。README 写明作者重心已转去 chessboard2，基本停更（最后提交 2022-12）。
- chessboard2：零依赖，ClojureScript 编写，v0.5.0 预发布，2023-05 后没有提交，开放 issue 46 个。
- 两者都只是棋盘，其余全部自己写。

### 4.7 react-chessboard / willb335/chessboardjsx（React 棋盘）

- **许可**：react-chessboard 是 `~/repos/react-chessboard/LICENSE`（MIT 原文，2022 Ryan Gregory）；chessboardjsx 是 `~/repos/chessboardjsx/LICENSE`（MIT 原文，2018 William J. Bashelor）。
- react-chessboard v5：`position`、`squareStyles`（可用来做上一步和将军高亮）、`arrows`、`animationDurationInMs`、`showNotation`（读 `src/ChessboardProvider.tsx`）。活跃，周下载约 48k。要引入 React 和打包链。
- chessboardjsx：README 首行「UNMAINTAINED」，2021 年后没有发布。**不建议再看**。
- 都只是棋盘。

### 4.8 jhlywa/chess.js（规则加 PGN）

- **许可**：`~/repos/chess.js/LICENSE` 是 BSD 2-Clause 原文（Copyright 2025 Jeff Hlywa），package.json `BSD-2-Clause`。宽松许可。
- **实测**（`t_chessjs.mjs`、`t_real.mjs`、`t_edge.mjs`）：
  - 真实的 `g1-c-opus-sol/game.pgn` 载入成功，95 个半回合，`isCheckmate()` 为 true。
  - 读头正常（`Termination: 将死`）。
  - `getComments()` 返回原始评注串，`[%emt …] [%think …]` 原样保留，**不解析任何命令**；换行被压成空格（中文硬切处多一个空格）。
  - **多盘 PGN 直接报错**（`Expected end of input … but "[" found`），得先自己切开。
  - 评注里出现 `[a]`、`]`、引号、反斜杠、`;`、`(`、`$1`、`1-0` 都没问题。
- 适合当「走法、FEN、将军、上一步」的计算层；元信息要自己从评注串里用正则取。

### 4.9 @mliebelt/pgn-parser（解析，附加候选，最合适）

- **许可**：`~/repos/pgn-parser/LICENSE` 是 Apache License 2.0 原文，package.json `Apache-2.0`。宽松许可（出货时要带 NOTICE 和署名）。
- **实测**（`t_mliebelt.mjs`、`t_real.mjs`、`t_edge.mjs`）：
  - `parseGames()` 支持多盘（测试文件两盘、真实文件拼两份都正确）。
  - **未知命令被解析成键值**：`commentDiag = {emt:"0:00:11", think:"34", out:"47", in:"2313", cacheread:"0", cachewrite:"0", illegal:"1", comment:"理由文字"}`，`commentAfter` 只剩理由文字。
  - 中文头（`Termination: 将死`）、全角 `｛｝％`、`[a]`、`]` 等都正常；硬切折行处保留 `\n`。
  - `notation.check` 字段在测试里是 null（它读的是 SAN 里的 `+`，测试着法没带 +，推测对 `Qd5+` 会置位）。
- 它只解析、不下棋；要算 FEN 得配 chess.js（它的姊妹包 @mliebelt/pgn-reader 也是 Apache-2.0，会给每步算 FEN，没实测）。

### 4.10 niklasf/chessops（附加候选）

- **许可**：`~/repos/chessops/LICENSE.txt` 是 GPL v3 原文，package.json `GPL-3.0-or-later`，**强 copyleft**。
- **实测**：`parsePgn` 多盘正常；`parseComment` 只识别 `emt/clk/csl/cal/eval`，**其余 `[%…]` 留在 text 里**（读源码 `pgn.ts` 第 815 行起，实测输出一致）；保留 `\n`。lichess pgn-viewer 就是用它解析的。

### 4.11 shaack/cm-pgn（附加候选）

- **许可**：`~/repos/cm-pgn/LICENSE` 是 MIT 原文。依赖 chess.mjs（shaack 的 chess.js ES 模块版），它的 package.json 写 `BSD-2-Clause`，LICENSE 文件却是 MIT 文本，两处不一致，出货前要核一下。
- **实测**：`PgnList.splitPgns` 能切多盘（真实文件拼两份也行），每步给出 `fen/uci/inCheck/inCheckmate/comments`；评注是原始串，**不解析命令**（5.0 改成了「lichess 式评注模型」）。

## 5. 对 Playwright 录屏的补充观察

- **节奏（R6）**：所有现成播放器都用页面内的 setTimeout 计时。无头录屏时，页面负载一高，计时和录下来的帧都可能抖。更稳的做法是「外部驱动」：页面暴露 `step()` 或 `goTo(n)`，并在棋子动画的 Promise 结束后置一个就绪标记；录制脚本按固定节拍逐步推进（或逐步截图后用 ffmpeg 按固定帧率合成）。cm-chessboard 的 Promise 接口和 lichess pgn-viewer 的 `goTo` 都适合这样驱动；pgn4web 有 `MoveForward` 加 `customFunctionOnMove`，也行。（推测，没做录屏实测）
- **播完信号（R5）**：三个现成播放器都没有「全部播完」事件。pgn4web 可以在回调里自己判断，lichess 可以由外部驱动判断，mliebelt 只能轮询内部状态或改源码。
- **R7 高 DPI**：Playwright 的 `deviceScaleFactor` 对 SVG 棋子（chessground、cm-chessboard、pgn4web 的 svgchess）有效，PNG 棋子会糊（pgn4web 默认棋子实测发糊）。

## 6. 没纳入或只简单看过的

- **ChessBase 网页播放器**：不开源，这里不评。
- **shaack/chess-console**：GitHub 许可显示 NOASSERTION（没识别出），没细看。
- **ornicar/pgn4web 等 GitHub 镜像**：2011–2019 年的旧快照，以 SourceForge 为准。
