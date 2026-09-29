# 国际象棋棋谱回放与录屏：候选方案调研

> 2026-09-29。只调研、未实施，没改 llm-chess 仓库。需求取自 `/Users/xhx/repos/llm-chess/docs/viewer-brief.md`。
> 本文是汇总。三份分报告有全部证据、源码位置和实测细节，都在同一目录：
> - 现成平台：`chess-platforms.md`
> - web 开源播放器与棋盘库：`chess-oss-web.md`
> - PGN 直接出 gif/视频的工具，以及自制路线：`chess-gif-video.md`
>
> 证据标注：**实测** 是在本机、无头浏览器或对方接口上跑过；**源码** 是读过代码或官方文档；**推测** 是没验证过的判断。

## 0. 结论

1. **现成平台走不通。** lichess 的自动播放只有 1 秒和 5 秒两档，没有网址参数；匿名导入会把评注整个丢掉（实测）；Study 会删掉所有 `[%…]` 命令（源码）。chess.com 的用户协议明文禁止机器人和自动化访问。几家「PGN 转视频」网站都只做单盘，也不显示自定义元信息。
2. **没有哪个开源项目开箱即用。** 最接近的是 pgn4web（GPL-2.0-or-later，强 copyleft），它能用网址参数设连播和间隔、每步有回调、能读自定义命令（实测）。它缺将军高亮、标题画面和播完信号，代码是 2009 年起的老式全局函数。lichess pgn-viewer 的回放界面最好，但没有自动播放，也不认 Termination。PGN 转 gif 这类工具都做不出标题画面、竖屏、多盘拼接和终局原因。
3. **推荐自己搭一个薄播放页，只用宽松许可的库**：棋盘 cm-chessboard（MIT），PGN 解析 @mliebelt/pgn-parser（Apache-2.0），规则计算 chess.js（BSD-2-Clause）。一个页面分两种模式：回放模式给人看，录屏模式给 Playwright 驱动。录屏时不录实时画面，而是「推一步、等画完、截一张」，最后用 ffmpeg 按固定时长合成。这样不会因为页面卡顿丢步。估计 600–900 行（第 4 节）。
4. **最快的出片办法**：调研时已写了一个 68 行的 Python 原型（python-chess 出 SVG，cairosvg 转 PNG，Pillow 排版，ffmpeg 合成），本机跑通。它出了 1080×1920 竖屏 mp4，有标题画面、双方名字、上一步高亮、将军红光和终局横幅。只用来出视频的话，这是最省事的路。但它不能用来回放，而且它依赖 python-chess（GPL）。
5. **需要维护者拍板的许可事实**：python-chess 是 GPL-3.0-or-later，本项目早已在用。lila-gif 是 AGPL-3.0-or-later。pgn4web、lichess pgn-viewer、chessground、chessops、mliebelt pgn-viewer、gifpgn、c2g 都属 GPL 族。本工具只在本机自用、只录视频、不分发代码，这种情况下这些能不能用，本文不下结论。

## 1. 需求编号

| 编号 | 需求 | 出处 |
|---|---|---|
| R1 | 多盘连播，一盘播完自动接下一盘 | 用户需求 1 |
| R2 | 固定间隔自动走子，默认每步 2–3 秒，可调 | 用户需求 2 |
| R3 | 每步元信息：理由、耗时、思考 token、输出 token、非法重选次数 | 用户需求 3，补充 |
| R4 | 录屏时隐藏元信息，回放时显示 | 用户需求 3 |
| R5 | 用网址参数或脚本进入录屏状态，并能知道何时播完 | 补充 |
| R6 | 节奏稳定，不因加载卡顿丢步 | 补充 |
| R7 | 9:16 和 16:9 的干净画面，高 DPI | 补充 |
| R8 | 每盘开头的标题画面 | 补充 |
| R9 | 双方玩家名和执哪方 | 补充 |
| R10 | 上一步高亮 | 补充 |
| R11 | 被将军提示 | 补充 |
| R12 | 终局结果和结束原因（Termination 头，中文） | 补充 |
| R13 | 暂停、前后单步、跳到任意一步 | 补充 |
| R14 | 数据留在本地 | 补充 |
| R15 | 自定义评注命令不会被吞掉，也不报错；中文和全角字符正常 | 棋谱现状 |

## 2. 候选×需求勾选表

图例：✅ 开箱满足；◐ 部分满足，或者要加少量配置、胶水代码；✗ 不支持；? 没查清。

| 候选 | 类别 | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | R11 | R12 | R13 | R14 | R15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lichess 分析板和导入 | 平台 | ✗ | ✗ 只有 1s 和 5s 两档 | ✗ 评注被丢（实测） | ✗ | ✗ | ◐ | ✗ | ✗ | ✅ | ✅ | ◐ | ✅ | ✅ | ✗ 上传 | ✗ |
| lichess Study | 平台 | ◐ 最多 64 章，章与章之间不自动接 | ✗ | ◐ 只剩理由文字 | ✗ | ✗ | ◐ | ✗ | ✗ | ✅ | ✅ | ◐ | ✅ | ✅ | ✗ 上传，要账号 | ✗ `[%…]` 全删 |
| lichess GIF 接口 | 平台 | ✗ | ✗ 固定 0.8s | ✗ | ✅ 本来就不显示 | — | ✅ | ✗ 720×840 | ✗ | ✅ | ✅ | ✅ | ✗ | ✗ | ✗ 先导入成公开棋局 | — |
| chess.com | 平台 | ✗ | ✗ | ? | ? | ✗ 条款禁止 | ? | ? | ✗ | ✅ | ✅ | ? | ? | ✅ | ✗ 上传 | ? |
| chess.video、chessframe 等 | 出片网站 | ✗ | ✅ | ✗ | ✅ | ✗ 有反机器人校验，条款禁批量 | ✅ | ✅ | ◐ 只有 chessframe 有 | ◐ | ◐ | ? | ? | ✗ | ✗ 大多要上传 | ✗ |
| pgn4web | 开源播放器，GPL-2.0+ | ✅ | ✅ 最短 0.5s | ◐ 理由能显示，数字要自己用 API 取 | ✅ 网址参数 | ◐ 网址参数加每步回调，播完要自己判断 | ✅ 实测稳 | ◐ 要自己写版式 | ✗ | ✅ | ✅ | ✗ | ◐ 能读到头 | ✅ | ✅ | ✅ 实测 |
| lichess pgn-viewer | 开源播放器，GPL-3.0+ | ✗ 只读第一盘 | ✗ 没有自动播放 | ◐ 命令原样当文字显示 | ◐ 自己写 CSS | ◐ 有 JS API，没有事件 | ◐ 要外部驱动 | ◐ | ✗ | ✅ | ✅ | ✅ | ◐ 只有结果 | ✅ | ✅ | ◐ |
| mliebelt pgn-viewer | 开源播放器，GPL-3.0+，功能开发已停 | ◐ 要手动下拉选盘 | ✅ | ◐ 只有理由文字 | ◐ | ✗ 没有开播 API，也没有播完信号 | ◐ | ◐ | ✗ | ◐ | ✅ | ◐ | ◐ | ◐ 跳步接口有缺陷 | ✅ | ✅ |
| gifpgn | 出 gif，GPL-3.0+ | ✗ | ✅ | ✅ 不显示 | ✅ | ✅ 命令行 | ✅ | ◐ 方形，事后用 ffmpeg 补边 | ✗ | ✅ 中文缺字 | ◐ 只有箭头 | ◐ 只有箭头 | ✗ | ✗ | ✅ | ✅ 实测 |
| lila-gif（要自己部署） | 出 gif，AGPL-3.0+ | ✗ | ✅ 每帧延时可设 | ✅ 不显示 | ✅ | ✅ HTTP | ✅ | ✗ 宽度固定 720，放大会糊 | ✗ | ✅ 中文缺字 | ✅ | ✅ | ✗ | ✗ | ✅ | ✅ 它不读 PGN |
| **A. 自搭薄页（cm-chessboard + pgn-parser + chess.js）** | 自己写，全宽松许可 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ 逐步截图 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ 实测 pgn-parser 把命令解析成键值 |
| **B. Python 出片（原型已跑通）** | 自己写，依赖 python-chess（GPL）和 cairosvg（LGPL） | ✅ ffmpeg 拼接 | ✅ | ✅ 不显示 | ✅ 只做录屏版 | ✅ 命令行 | ✅ 逐帧 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✗ 不能回放 | ✅ | ✅ 实测 |

A 和 B 两行是「写完以后能满足」，不是现成就有。

## 3. 各候选：许可、维护、录屏怎么自动化、PGN 要不要转换

「强 copyleft」这一列标出 GPL、AGPL、SSPL 一族，弱 copyleft 标出 LGPL、MPL、EPL。许可都是读仓库里 LICENSE 原文确认的，文件路径见分报告。

| 候选 | 许可（SPDX） | 强/弱 copyleft | 维护状态 | 录屏自动化方式 | PGN 要不要转换 |
|---|---|---|---|---|---|
| lichess（分析板、Study、GIF） | 服务条款：允许个人和商业使用，限速由 lichess 决定；上传的内容授予 lichess 使用许可 | — | 活跃 | 没有网址参数，也没有播完信号，只能让脚本去点按钮；GIF 接口会拦截爬虫 UA | 必须上传。导入会丢评注；Study 保留理由文字，但删掉所有 `[%…]` |
| chess.com | 用户协议 2026-03-25 版明文禁止机器人和自动化访问，另有 AI 工具条款 | — | — | 条款禁止，所以没有做任何自动化测试 | 要上传 |
| chess.video、chessframe、chess.rodeo、plychess | chess.video 禁止脚本批量调用，plychess 禁止给服务造成负担，chessframe 没有条款页 | — | 商业或个人站点 | 不适用，它们直接出成片（chess.video 有反机器人校验） | 要上传（plychess、chess.rodeo 自称在浏览器本地渲染） |
| pgn4web | GPL-2.0-or-later；附带的 jscolor 是 LGPL，棋子和字体资源各有许可 | **强** | 单人长期维护，SourceForge 2026-09 有更新，版本 3.09 | 网址参数 `am=loop&delay=…`；`customFunctionOnMove` 回调里判断播完；也能用 `MoveForward` 从外部驱动 | 不用转换。显示时会剥掉命令；`customPgnCommentTag('think')` 能读出数值。要把中文折行拼回去 |
| lichess pgn-viewer | GPL-3.0-or-later（依赖的 chessground、chessops 也是） | **强** | 活跃，v2.6.4（2026-08） | 从外部调 `goTo('next')`，用 `canGoTo('next')` 判断播完；没有网址参数 | 能识别 `%emt`，但别的命令会原样当文字显示，要先预处理评注；每盘建一个实例 |
| mliebelt pgn-viewer | GPL-3.0-or-later | **强** | 功能开发停了，只剩依赖机器人的提交，62 个 open issue | 只能点播放按钮开播，播完没有信号 | 命令会被解析掉，不显示数值 |
| lichess chessground（只是棋盘） | GPL-3.0-or-later | **强** | 很活跃 | JS API | — |
| chessops（解析库） | GPL-3.0-or-later | **强** | 活跃 | — | 只识别 emt、clk 等标准命令，其余留在文字里 |
| **cm-chessboard（棋盘）** | MIT | 否 | 活跃，npm 8.15.1（2026-09） | `setPosition` 返回 Promise，动画画完才兑现，便于卡节奏；Markers 扩展能标上一步和将军 | — |
| **@mliebelt/pgn-parser（解析库）** | Apache-2.0 | 否 | 以依赖升级为主，npm 1.4.19（2025-10） | — | 实测能直接喂：`[%think 34]` 这类命令解析成 `commentDiag` 键值，理由文字单独取出；支持多盘 |
| **chess.js（规则库）** | BSD-2-Clause | 否 | 事实标准，活跃 | — | 能读单盘（多盘会报错，要先切开）；评注原样保留；能算将军和将死 |
| cm-pgn（解析库） | MIT；它依赖的 chess.mjs，包信息写 BSD、LICENSE 文件却是 MIT，两处对不上 | 否 | 活跃，用户少 | — | 能切多盘，每步给出 FEN 和是否将军；评注是原始字符串 |
| chessboard.js、chessboard2、react-chessboard、chessboardjsx | MIT、ISC、MIT、MIT | 否 | chessboard.js 和 chessboard2 已停，chessboardjsx 标了「不再维护」；react-chessboard 活跃但要 React | — | — |
| python-chess（本项目已在用） | GPL-3.0-or-later | **强** | 活跃 | — | 直接读，自定义命令不影响解析（实测）；原生支持 `%emt` |
| lila-gif | AGPL-3.0-or-later | **强，网络 copyleft** | 2026-08 有提交，没有 release | 自己部署 HTTP 服务，POST 逐帧 JSON（本机没有 cargo，没编译过） | 要用脚本把 PGN 展开成逐帧 FEN |
| gifpgn | GPL-3.0-or-later | **强** | 2026-09 发布 v1.2.1，用户很少 | 命令行或 Python 调用 | 直接读（实测）。坑：最后一帧被写死重复 20 次，要用 ffmpeg 裁掉 |
| c2g | GPL-3.0-or-later | **强** | 已停一年，没有预编译二进制 | 命令行 | 会把 `%emt` 当成时钟画出来，得先改写 |
| afozk95/pgn-to-gif、fork52/chess_gif、dn1z/pgn2gif | 都是 MIT（前两个运行时依赖 GPL 的 python-chess） | 自身不是 | 2021–2024 年就停了 | 命令行 | 直接读；功能都太薄 |
| cairosvg（B 路线要用） | LGPL-3.0-or-later | **弱** | — | — | — |

## 4. 推荐：自搭薄播放页（A）

### 为什么选它
- **两个模式、一套画面**：回放模式要逐步看理由和 token，本来就只有网页做得好。录屏模式用同一个页面、同样的棋盘，画面风格统一。以后中国象棋照这个结构再做一套也容易。
- **全宽松许可**：MIT、Apache-2.0、BSD-2-Clause，许可问题不用拍板就能往下走。
- **解析最省事**：四个解析器里，只有 @mliebelt/pgn-parser 把自定义命令直接解析成数值（实测），棋谱不用改格式。
- **录屏稳**：所有现成播放器都靠页面里的定时器，无头录制时页面一卡就会抖。自搭可以让 Playwright 当节拍器：调 `step()`，等 cm-chessboard 的动画 Promise 兑现、页面置好就绪标记，截一张 2x 截图；最后用 ffmpeg 的 concat 按每张 2.5 秒合成。这样节奏和播完信号都由脚本掌控，不会丢步，比例也只是换一下视口尺寸。想要走子滑动动画的话，可以在每步动画期间多截几帧，也可以改用 Playwright 实时录像，但实时录像就要接受抖动的风险。

### 要做的事和行数估计（推测）
| 部分 | 行数 |
|---|---|
| 加载：从本地同源目录读一份或多份 PGN，用 pgn-parser 解析，逐步交给 chess.js 算 FEN、上一步、将军；把中文硬切折行拼回去 | 80–120 |
| 棋盘：cm-chessboard 加 Markers，标上一步和将军；终局横幅 | 60–100 |
| 回放模式：棋谱列表、跳步、单步、暂停、键盘操作；每步面板显示理由、耗时、思考、输出、非法次数 | 150–250 |
| 录屏模式：网址参数（`mode=record&ratio=9x16&delay=2500&games=…`），标题画面，隐藏元信息，9:16 和 16:9 两套 CSS 版式；在 `window` 上挂 `step()`、`ready`、`done` | 120–180 |
| Playwright 录制脚本：逐步截图，调 ffmpeg 合成，支持多盘 | 80–120 |
| 其他：样式、上传原型所需的零散处理 | 100 左右 |
| **合计** | **约 600–900 行 JS、CSS 和少量 Python 或 Node** |

开源播放器那份分报告只估了播放层，是 400–700 行；这里多算了录制脚本和两种版式。

### 这个方案的前提
| 前提 | 状态 | 证据 |
|---|---|---|
| pgn-parser 能把自定义命令解析成键值，不丢理由文字 | 已核实 | 实测，见 chess-oss-web.md §4.9 |
| chess.js 能读真实棋谱，并算出将军和将死 | 已核实 | 实测 g1 棋谱 95 个半回合，最后是将死 |
| cm-chessboard 的 `setPosition` 在动画画完后才兑现 | 读源码，没实测 | chess-oss-web.md §4.5 |
| cm-chessboard 的 SVG 棋子在 2x 截图下清晰 | 待验证 | 推测，没截图 |
| 本机能跑 Playwright 无头浏览器并按 2x 截图 | 已核实 | 调研时用 playwright-core 加本机缓存的 chromium 截过图 |
| 本机 ffmpeg 能用 concat 按每帧时长合成 | 已核实 | B 路线原型实测 |
| 棋谱里的中文硬切折行在加载时能可靠拼回去 | 待验证 | 所有解析器都会在中间多出一个空格（实测）；拼接规则要试，或者改导出端不折中文 |
| cm-chessboard 自带棋子图集的许可 | 待验证 | 没逐个读 |

有待验证项，所以状态是「待验证」，不是「可以直接实施」。最大的风险是中文折行，这条对任何方案都成立。

### 备选
- **只要尽快出视频**：直接把 B 的原型做成成品，约 200–250 行 Python。回放仍然要一个页面，但那个页面就不用管录屏了。代价是画面有两套实现，而且依赖 python-chess（GPL，本项目已在用）。
- **维护者接受本机自用 GPL 的话**：pgn4web 靠网址参数就能先录出一版（没有将军高亮和标题画面），lichess pgn-viewer 可以当回放器（喂进去之前把 `[%…]` 预处理成易读文字）。两者都不适合做长期方案。
- **不建议**：chess.com（条款禁止）；lichess 导入或 Study（丢元信息，还要上传）；各种 gif 工具（缺标题画面、竖屏、多盘和终局原因，补齐这些就等于自己写了）。

## 5. 顺带发现的问题（没修）

- **PGN 导出把中文长句硬切折行**：所有解析器读回来，断开的地方都会多一个空格。lichess pgn-viewer 和 pgn4web 的截图里都能看到。选哪条路都要处理：要么改导出端，让中文不在字中间折行；要么加载时把「中文+换行+中文」拼回去。
- **python-chess 本身是 GPL-3.0-or-later**：本项目早已在用。这和仓库许可政策里「GPL 明确不能用于出货产物」字面上冲突，请维护者知悉。
- 调研的副作用：
  - 平台调研向 lichess 匿名上传了两盘 3 步的玩具棋（`lichess.org/LQIyyzJc`、`lichess.org/hibmRoIg`），不含真实棋谱，公开可见，匿名上传的删不掉。
  - `~/repos/` 下新建了若干浅克隆，都是新目录，没动已有仓库：pgn-viewer、pgn-viewer-mliebelt、chessground、cm-chessboard、chessboardjs、chessboard2、react-chessboard、chessboardjsx、chess.js、pgn-parser、chessops、cm-pgn、lichess-api、lichess-lila-gif、lichess-lila（稀疏）、lila-gif、gifpgn、chess_gif、pgn-to-gif、pgn2gif、c2g、pgn-to-video-converter、chess-animator、python-chess。
  - Python 原型存为同目录 `chess-prototype-render.py`；试跑产物和截图在临时目录，没留。

## 6. 没验证的
- lichess Study 的真实界面：要账号，没测。
- chess.com 怎么处理自定义命令：条款禁止，没测。
- chessframe、chess.rodeo 的实际输出：没提交 PGN。
- lila-gif、c2g：本机没有 cargo，没编译。
- 用 cm-chessboard 搭页面后的实际截图效果：没做，这是实施阶段第一步要验证的。
