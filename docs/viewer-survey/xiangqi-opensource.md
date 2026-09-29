# 中国象棋棋谱回放：开源候选调研

> 2026-09-29。只调研、未实施。需求对照 `docs/viewer-brief.md`。许可一栏只如实列出 LICENSE 原文判定的 SPDX 名和所属族别，不判断「能不能用」——按仓库 AGENTS.md，强 copyleft 的边界要问维护者。
> 本次新 clone（全部 `--depth 1`，只读）：`~/repos/chessgroundx`、`~/repos/pychess-variants`（sparse，只取 `client/`、`static/images/pieces/` 及 `static/` 顶层文件）、`~/repos/xiangqi.js`、`~/repos/xiangqiboardjs`、`~/repos/xqwlight`、`~/repos/vschess`、`~/repos/python-chinese-chess`、`~/repos/xiangqi-setup`、`~/repos/xiangqi_viewer`。已有的 `~/repos/Fairy-Stockfish` 只读，未改动；没碰 `~/repos/jev-study`。

## 先说结论

- **没有哪个开源项目能直接满足需求**。最接近的是 **vschess（微思象棋播放器）**：中文记谱、自动播放（间隔可调）、评注、上一步高亮、单步/跳转、JS API 都有；但它没有多盘连播，也不会在画面上提示将军（只放一声音效），画面是固定 380×420 的位图棋盘加一大块界面，竖屏高清录制要改样式，放大后还会发虚。许可是 LGPL-3.0（弱 copyleft），仓库里同时放了一份 GPL-3.0 原文，见下。
- 其余候选要么只是**棋盘组件**（chessgroundx：GPL-3.0；xiangqiboardjs：MIT），要么只是**规则库**（ffish.js：GPL-3.0；xiangqi.js：BSD-2-Clause），要么是**出图/出 GIF 的 Python 工具**（python-chinese-chess：GPL-3.0；xiangqi-setup：AGPL-3.0-or-later）。
- **关键观察：回放用不着规则库**。`game.jsonl` 里每步都有 ICCS 坐标、中文记谱和将军标记，终局原因在 `end` 行里。按坐标把子搬过去（目标格上有子就吃掉）就能推出每一步的局面，不用生成着法、也不用判合法性。所以「自己搭一个薄播放页」比想象的小，估算见文末。
- **素材可以不碰 copyleft**：xiangqi-setup 里的棋盘主题和 playok 棋子主题是 CC0-1.0（看过各自的 LICENSE.txt），可以拿来当自绘页的素材；它的代码本身是 AGPL，不用它的代码就行。
- **DhtmlXQ（东萍）**：找不到公开源码仓库，官网页面和 readme 都没有许可声明，按项目政策属于「许可不明」。

---

## 1. vschess（微思象棋播放器）

- 仓库：https://github.com/FastLight126/vschess ，本地 `~/repos/vschess`
- **许可**：
  - 仓库根 `~/repos/vschess/LICENSE` 是 GNU LESSER GENERAL PUBLIC LICENSE Version 3 原文 → **LGPL-3.0**（弱 copyleft）。
  - `~/repos/vschess/vschess/LICENSE` 是 GNU GENERAL PUBLIC LICENSE Version 3 原文。
  - 打包后的源码 `vschess/vschess.js` 文件头写「本程序遵循 LGPL 协议 https://www.gnu.org/licenses/lgpl.html」，没写版本号。
  - LGPLv3 本身就是「GPLv3 + 附加许可」，惯例是两份原文一起放，所以大概率就是 LGPL-3.0。但两份文件并存、文件头又没写版本，**这点要请维护者确认**。
  - 素材：棋盘、棋子 PNG（`vschess/style/{default,fc,mobile}/`）和音效（`vschess/sound/default/*.mp3`）没有单独的许可说明。
- **维护**：最后提交 2025-10-24（V2.6.7），89 star，浅克隆只有 1 个提交（作者每次发版都整包覆盖）。
- **需求逐条**：
  - 多盘连播：**没有**。需要外面包一层：播完一盘后再 `new vschess.load(...)` 或调 `loadData(node, info)` 换下一盘，约 50 行。
  - 定时自动走子：有。`play()` / `pause()`，间隔 `playGap` 以 0.1 秒为单位，可用 `setPlayGap()` 改（默认 5，即 0.5 秒）。计时靠一个每 100ms 触发一次的 `setInterval` 数格子（`function.load.js:88`、`intervalCallback`），属于实时计时，不是确定性的。
  - 评注显示/隐藏：评注在「棋谱注解」标签页的文本框里（`module.comment.js`）。要隐藏就把默认标签切走（`defaultTab`），或用 CSS 把那块藏起来。
  - 上一步高亮：有。`setSelectByStep` 给起点和终点加选中样式。
  - 将军提示：**画面上没有**。只在 `playSoundBySituation` 里播 `check.mp3`（`module.sound.js`）。
  - 中文记谱：有，默认 `moveFormat: "chinese"`，还能切 WXF / ICCS。
  - 单步/跳转：有，`setBoardByStep(n)`、`setBoardByOffset(±k)`，还有快进快退按钮。
- **Playwright 能否控制**：能。全局有 `vschess` 对象，`new vschess.load(sel, options)` 返回实例。可以调 `getCurrentStep()`、`lastSituationIndex()`、`setBoardByStep()`、`play()`、`pause()`、`setAnimationTime()`；回调有 `loadFinish`、`afterAnimate` 等（`main.dom.js:34`）。「播完」没有专门事件，但自动播放到最后一步会自己 `pause()`，可以靠 `afterAnimate` 回调里比较当前步和最后一步来判断。没有网址参数，要自己写一个包装页。
- **吃什么格式**：自动识别东萍 DhtmlXQ、中国象棋 PGN（`[Game "Chinese Chess"]`，支持中文 / WXF / ICCS / 坐标四种着法写法）、XQF、CBR、鹏飞等（`function.dataToNode.js`）。
  - **PGN 解析器会损坏我们的评注**（已读代码确认，`function.dataToNode.js:179` 起）：它先对整段文本执行 `.replace(/\[(.*)\]/g,"")`、`.replace(/\((.*)\)/g,"")`、`.replace(/[0-9]+\./g,"")`、`.replace(/1\-0([\S\s]*)/g,"")` 等，**然后才**把 `{...}` 评注抽出来。后果如下：
    - 同一行里从第一个 `[` 到最后一个 `]` 整段被删，`[%emt …]` 等命令连同夹在中间的文字一起没了；
    - 评注里的括号内容会被删（样例里的「(马二进三)」）；
    - 「数字加点」会被删；
    - 评注里只要出现 `1-0`、`0-1`，后面的整盘棋谱都会被截掉。
    - 不会报错，只会悄悄丢内容。
  - DhtmlXQ 解析是逐行读的，评注写成 `[DhtmlXQ_commentN]…[/DhtmlXQ_commentN]`，`||` 表示换行（`function.dataToNode.js:335`）。只要评注里不出现 `[/DhtmlXQ_`，内容就能原样保留。
  - **转换建议**：从 `game.jsonl` 直接导出 DhtmlXQ。
    - 着法写进 `movelist`，每步 4 位数字：x 取 ICCS 的列（a–i 对应 0–8），y = 9 − ICCS 的行（已按样例 `dhtmlxq.txt` 的 `binit` 核对：红方在下，y=9 是红方底线）。
    - 元信息改写成人能读的一句话（如「用时 5 秒 · 思考 20 token」），跟理由一起放进 `comment{ply}`。
    - 也可以绕过解析，直接用 `loadData(chessNode, chessInfo)` 把节点树塞进去。
    - 转换器约 60 行 Python。
- **渲染与清晰度**：用 DOM 元素加 CSS 背景图（PNG/JPG）。棋盘固定 360×400 加 10px 内边距，棋子 40px；最高只有 2 倍图（`board-dpr-2.png` 是 760×840）。录 1080×1920 时棋盘要放大到约 1000px 宽，已经超过 2 倍图，会发虚。整个组件还带标签页、按钮条、着法列表等大块界面，要干净画面得大改 CSS 或另写样式包（`vschess/style/*`、`vschess/layout/*`）。
- **数据外发**：初始化时会用 JSONP 向 `https://www.xiaxiangqi.com/api/cloud/startfen` 拉一份推荐局面列表（`module.edit.js:17`），这等于加载一段远程脚本，但不上传棋谱。「生成 GIF」「分享」「保存」按钮会把棋谱发到 xiaxiangqi.com（`module.share.js`，`cloudApi.gif` 等）。传 `cloudApi: false` 或把这几个地址置空即可全部关掉。**它的 GIF 导出是云端服务，不是本地生成。**

## 2. chessgroundx（chessground 的多棋种分支，pychess 用的棋盘）

- 仓库：https://github.com/gbtami/chessgroundx ，本地 `~/repos/chessgroundx`；npm 包 `chessgroundx` 10.7.5
- **许可**：`~/repos/chessgroundx/LICENSE` 是 GNU GENERAL PUBLIC LICENSE Version 3 原文 → **GPL-3.0**（强 copyleft）。npm 元数据同样写 GPL-3.0。
- **维护**：最后提交 2026-05-12，46 star；上游 lichess chessground 很活跃。
- **定位**：纯棋盘组件（约 4.7k 行 TypeScript），**没有棋谱解析、记谱和播放器**。
- **需求逐条**：
  - 多盘连播、定时播放、评注、中文记谱、单步跳转：全都要自己写。
  - 它提供的是：`set({fen, lastMove, check})`、`move(orig, dest)` 带走子动画（`animation.duration` 可调）、`lastMove` 高亮、`check` 高亮（给 `kingRoles` 里的将帅加样式，`src/board.ts:40`），以及 9×10 棋盘（`dimensions: {width:9, height:10}`）。
- **Playwright 控制**：只要自己的页面把 API 暴露出来就行。组件本身有 `events.move` 回调。
- **格式**：只认 FEN 和坐标。需要把 ICCS 换成它的格子名，这是纯映射，不用规则库。
- **渲染与素材**：
  - 渲染：DOM 元素加 CSS 背景图，箭头等用 SVG。**棋盘和棋子图不在这个仓库里**，要从 pychess-variants 拿，或者自己配。
  - pychess 素材许可（`~/repos/pychess-variants/static/COPYING.md` 的例外表）：
    - `static/images/board/*` 和 `static/images/pieces/xiangqi/*` 默认是 **AGPL-3.0-or-later**；
    - `pieces/xiangqi/playok/*` 是 **CC0-1.0**（该目录有 LICENSE.txt）；
    - `pieces/xiangqi/euro/*` 是 **CC-BY-4.0**（有 LICENSE.json）。
  - 用 SVG 素材时放大不会发虚。
- **工程代价**：TypeScript，要 npm 安装加打包。基本用法是 `Chessground(el, config)`。

## 3. pychess-variants 前端（及 pychess.org 网站）

- 仓库：https://github.com/gbtami/pychess-variants ，本地 `~/repos/pychess-variants`（sparse）
- **许可**：`~/repos/pychess-variants/LICENSE` 是 GNU AFFERO GENERAL PUBLIC LICENSE Version 3 原文 → **AGPL-3.0**（强/网络 copyleft）。素材的例外见上一节。
- **维护**：非常活跃（最后提交 2026-09-29），311 star。
- **需求**：
  - 前端和后端（Python aiohttp + MongoDB + websocket）绑得很紧，**不能单独当静态回放页用**。
  - 导入棋谱（`client/paste.ts`）的流程是：浏览器里用 ffish 逐步解析 PGN，**只把着法和标签 POST 到服务器 `/import`**，评注整段丢掉。
  - 象棋记谱用 WXF（`cg.Notation.XIANGQI_ARBNUM` 对应 `ffish.Notation.XIANGQI_WXF`，`client/cgCtrl.ts:203`），**没有中文记谱**。
- **作为现成网站（pychess.org）**：能导入并回放，但不显示评注、没有中文记谱、没有多盘连播，而且棋谱会上传成公开对局。
- 结论：只适合当 chessgroundx 的用法参考和素材来源。

## 4. ffish.js（Fairy-Stockfish 的 wasm 绑定）

- 源码：`~/repos/Fairy-Stockfish/src/ffishjs.cpp`，包装在 `~/repos/Fairy-Stockfish/tests/js/`；npm 包 `ffish` / `ffish-es6` 0.7.10（2026-08 更新）
- **许可**：`~/repos/Fairy-Stockfish/Copying.txt` 是 GNU GENERAL PUBLIC LICENSE Version 3 原文；`tests/js/package.json` 里 `"license": "GPL-3.0"` → **GPL-3.0**（强 copyleft）。
- **维护**：Fairy-Stockfish 很活跃（本地检出最后提交 2026-09-21）；独立的 wasm 仓库 fairy-stockfish/fairy-stockfish.wasm 有 41 star，最后提交 2026-09-28。
- **定位**：规则库。提供 `Board.push(uci)`、`isCheck()`、`result()`、`gameResult`、`sanMove(uci, Notation.XIANGQI_WXF)`、`readGamePGN()`。
- **限制**：
  - 记谱只有 WXF，**没有中文记谱**（`ffish.d.ts` 的 `Notation` 枚举）。
  - 坐标用 UCI 写法，行号是 1–10：ICCS `h2e2` 要写成 `h3e3`。
  - `readGamePGN` 遇到 `{…}` 直接找下一个 `}` 跳过（`skip_comment`，`ffishjs.cpp:553`），**评注全部丢弃，不报错**；而且只认 SAN/WXF 着法，喂中文记谱不行。
- **结论**：我们回放用不着它，`game.jsonl` 已经有将军标记和终局信息。只有想在浏览器里复核合法性时才有用，另外 wasm 包本身有几 MB。

## 5. xiangqi.js（lengyanyu258）

- 仓库：https://github.com/lengyanyu258/xiangqi.js ，本地 `~/repos/xiangqi.js`
- **许可**：`~/repos/xiangqi.js/LICENSE` 是两条款 BSD 原文（Jeff Hlywa 2017；lengyanyu258 2019–2023）→ **BSD-2-Clause**（宽松）。
- **维护**：最后提交 2025-08-17，44 star；是 chess.js 的象棋移植，1515 行。
- **定位**：规则库。提供 `move`、`in_check`、`in_checkmate`、`load_pgn`、`history`，着法格式是 ICCS（`h2e2` 这种，和我们的写法一样）。
- **限制**：
  - **没有中文记谱**。
  - `load_pgn` 用 `/({[^}]+})+?/g` 把评注整段删掉（`xiangqi.js:1323`），不报错。
  - 本身没有界面，要配 xiangqiboardjs。
- **结论**：许可最宽松的规则库，但回放同样用不着。

## 6. xiangqiboard.js（lengyanyu258）

- 仓库：https://github.com/lengyanyu258/xiangqiboardjs ，本地 `~/repos/xiangqiboardjs`
- **许可**：`~/repos/xiangqiboardjs/LICENSE.md` 是 MIT 原文（Chris Oakman 2013；lengyanyu258 2018–2020）→ **MIT**（宽松）。
- **维护**：最后提交 2020-04-30，59 star，**已停更**；是 chessboard.js 的移植，依赖 jQuery。
- **需求**：
  - 纯棋盘：`position(fen)`、`move('h2-e2')` 带动画（`moveSpeed`），有 `onMoveEnd` 回调；
  - 没有高亮 API（只有内部的 highlight 样式类），要自己加 CSS；
  - 没有评注、记谱、播放功能。
- **素材**：SVG 棋子和棋盘在 `docs/img/xiangqipieces/{wikimedia,wikipedia,...}`、`docs/img/xiangqiboards/wikimedia`，**仓库里没有单独的素材许可说明**。名字标着来自维基共享资源，那边的许可要逐个文件到 Commons 核实，不能按 MIT 算。

## 7. xiangqi-setup（hartwork）

- 仓库：https://github.com/hartwork/xiangqi-setup ，本地 `~/repos/xiangqi-setup`
- **许可**：
  - **仓库没有顶层 LICENSE 文件**；`setup.py` 第 3 行和各源文件头写的是「GNU Affero General Public License version 3.0 or later」→ 代码是 **AGPL-3.0-or-later**（强/网络 copyleft）。
  - **主题素材各自带 LICENSE.txt / LICENSE.json**：
    - 棋盘主题 16 个里 14 个 CC0-1.0，2 个 public-domain；
    - 棋子主题 `playok_2014_chinese`、`retro_simple`、`ccbridge_…` 是 **CC0-1.0**；
    - `euro_xiangqi_js` 是 CC-BY-4.0；
    - `commons_xiangqi_pieces_print_2010` 是 FDL-1.2+ / CC-BY-SA-4.0；
    - `latex_xqlarge_*` 是 **non-commercial**（不能商用）。
    - 证据：`~/repos/xiangqi-setup/README.md:120` 起的列表，以及例如 `xiangqi_setup/themes/pieces/playok_2014_chinese/LICENSE.txt`、`xiangqi_setup/themes/board/clean_beta/LICENSE.txt`。
  - 注意：playok 棋子 SVG 里的字是 `<text>`，字体写的是 WenQuanYi Micro Hei，没转成路径，所以显示效果取决于本机有没有这个字体。
- **维护**：最后提交 2026-09-28，34 star。
- **定位**：命令行工具，把局面（WXF / FEN）渲染成 SVG，可以用 `--moves N` 走到第 N 步，用 `--annotate-last-move` 标出上一步。逐步调用就能出逐帧 SVG，再拼成视频。没有评注、中文记谱、将军提示。
- **价值**：**CC0 的棋盘和棋子 SVG，是自绘方案最合适的现成素材**。

## 8. python-chinese-chess（windshadow233，`cchess` 包）

- 仓库：https://github.com/windshadow233/python-chinese-chess ，本地 `~/repos/python-chinese-chess`
- **许可**：`~/repos/python-chinese-chess/LICENSE` 是 GNU GENERAL PUBLIC LICENSE Version 3 原文 → **GPL-3.0**（强 copyleft）。
- **维护**：最后提交 2025-11-14，63 star。
- **定位**：模仿 python-chess 的象棋库。
  - `cchess.svg.board(..., lastmove=, checkers=)` 出 SVG，上一步和将军都会标出来；
  - `cchess.svg.to_gif(board, ...)` 用 cairosvg + imageio 出 GIF，帧间隔可调（`cchess/svg.py:315`）；
  - 另有 `to_html` 出简单的逐步页；
  - `Board.to_pgn(format="Chinese")` 能生成中文记谱。
  - 棋子字形直接写成 SVG 路径（`cchess/svg.py` 的 `PIECES`），来源没说明。
- **限制**：
  - GIF 只有棋盘，没有双方信息、评注、标题画面，也不能多盘连播；
  - 出 GIF 要装 cairosvg、numpy、PIL、imageio、tqdm，缺一个就**静默 return**、什么也不出。
- **结论**：出「纯棋盘 GIF」最快，但达不到社交视频要的画面信息。另一个 Python 库 walker8088/cchess 同为 GPL-3.0（73 star），没有细看。

## 9. xqbase（象棋巫师）开源代码：XQWLight

- 仓库：https://github.com/xqbase/xqwlight ，本地 `~/repos/xqwlight`
- **许可**：`~/repos/xqwlight/LICENSE` 是 GNU GPL Version 2 原文；`JavaScript/position.js` 等文件头写「version 2 of the License, or (at your option) any later version」→ **GPL-2.0-or-later**（强 copyleft）。
- **维护**：最后提交 2025-05-14，244 star。xqbase 的其他仓库：eleeye 引擎是 LGPL-2.1，其余是 Java 工具库（Apache-2.0）。
- **定位**：`JavaScript/` 是**人机对弈小程序**（搜索、开局库、GIF 棋子），不是棋谱播放器；没有 PGN 解析、评注和播放功能。
- **结论**：不符合需求。xqbase 网站本身的棋谱播放页不在这些开源仓库里。

## 10. DhtmlXQ（东萍动态棋盘）

- 官网：http://www.dpxq.com/hldcg/dhtmlxq/frame_big5.htm ，下载包 `DhtmlXQ_www_dpxq_com.rar`，readme 在 http://www.dpxq.com/DhtmlXQ_www_dpxq_com/readme.htm
- **许可**：官网页面和 readme 里**都没有找到任何许可或版权条款**，GitHub 上也搜不到官方源码仓库 → **许可不明**（按项目政策视同红线）。
- **格式价值**：DhtmlXQ 是通行的棋谱交换格式，vschess 等都能读，可以当我们的导出目标格式之一。

## 11. 其他顺带看过的

- **jshou/xiangqi_viewer**（https://github.com/jshou/xiangqi_viewer ，本地 `~/repos/xiangqi_viewer`）：
  - `LICENSE.md` 是 MIT；自带的 snap.svg 0.2.0 是 Apache-2.0。
  - 7 star，最后提交 2022。
  - 633 行，用 SVG（Snap.svg）画棋盘，按坐标手工 `place` 棋子，带一个简单的步进界面；没有格式解析、中文记谱和播放功能。玩具级，只能参考。
- **conglt10/xiangqi**（React + Pikafish 的分析界面）：0 star，**GitHub 上没有许可**，不考虑。
- **maksimKorzh/wukong-xiangqi**：MIT，49 star，2021 年起停更，主体是教学引擎加 PGN 工具，没有细看。

---

## 候选 × 需求 对照表

图例：✅ 有；◐ 部分有或要少量包装；❌ 没有，要自己写；— 不适用。

| 候选 | 许可（族别） | 最近提交 / star | 多盘连播 | 定时自动走子 | 评注显隐 | 上一步高亮 | 将军提示 | 中文记谱 | 单步/跳转 | Playwright 可控 / 知道播完 | 吃的格式；评注里的 `[%…]` | 渲染 / 高清 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vschess | LGPL-3.0（弱）；子目录另附 GPL-3.0 原文，待确认 | 2025-10 / 89 | ❌（约 50 行包装） | ✅ 0.1 秒粒度，实时计时 | ◐ 标签页，要改 CSS | ✅ | ❌ 只有音效 | ✅ | ✅ | ✅ JS API + 回调；◐ 播完要自己判断 | DhtmlXQ / PGN / XQF…；**PGN 解析会删掉 `[…]`、`(…)`、`数字.`，遇到 `1-0` 会截断**；DhtmlXQ 能保留 | PNG，最高 2 倍图，竖屏放大会虚；界面很重 |
| chessgroundx | GPL-3.0（强） | 2026-05 / 46 | ❌ | ❌ | ❌ | ✅ | ✅ 高亮将帅 | ❌ | ❌ | ✅（自己暴露） | 只认 FEN 和坐标 | DOM + 背景图，配 SVG 素材不虚 |
| pychess-variants | AGPL-3.0（强/网络） | 2026-09 / 311 | ❌ | ◐ | ❌ 导入时丢评注 | ✅ | ✅ | ❌ 只有 WXF | ✅ | ❌ 离不开服务器 | PGN（SAN/WXF），评注丢弃 | 同 chessgroundx |
| ffish.js | GPL-3.0（强） | 2026-09 / 41 | — | — | — | — | ✅ `isCheck` | ❌ 只有 WXF | — | — | UCI（行号 1–10）；PGN 评注直接跳过 | 无界面 |
| xiangqi.js | BSD-2-Clause（宽松） | 2025-08 / 44 | — | — | — | — | ✅ `in_check` | ❌ | — | — | ICCS；PGN 评注直接删 | 无界面 |
| xiangqiboard.js | MIT（宽松）；素材许可不明 | 2020-04 / 59 | ❌ | ❌ | ❌ | ◐ 要写 CSS | ❌ | ❌ | ❌ | ◐ `onMoveEnd` | FEN / 坐标 | SVG 或图片素材，依赖 jQuery |
| xiangqi-setup | 代码 AGPL-3.0-or-later；素材多为 CC0-1.0 | 2026-09 / 34 | — | — | ❌ | ◐ 标注 | ❌ | ❌ | ◐ `--moves N` | 命令行 | WXF / FEN | SVG，**CC0 素材可复用** |
| python-chinese-chess | GPL-3.0（强） | 2025-11 / 63 | ❌ | ◐ GIF 帧间隔 | ❌ | ✅ | ✅ | ✅（PGN 导出） | ❌ | — Python | 自带 PGN 读写 | SVG 转 PNG 转 GIF |
| XQWLight | GPL-2.0-or-later（强） | 2025-05 / 244 | ❌ | ❌ | ❌ | ◐ | ◐ | ❌ | ❌ | ❌ | 无 | GIF 图片，人机对弈 |
| DhtmlXQ | **许可不明** | — | ？ | ✅（官方演示） | ✅ | ？ | ？ | ✅ | ✅ | 未知 | 自家格式 | 位图 |
| jshou/xiangqi_viewer | MIT（宽松） | 2022 / 7 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ◐ | ◐ | 手工放子 | SVG（Snap.svg） |

---

## 自己搭的工作量估算

### 前提（都已核实）

| 前提 | 状态 | 证据 |
|---|---|---|
| `game.jsonl` 的 `move` 行有 ICCS 坐标、中文记谱、将军标记、本步统计 | 已核实 | 抽样看过 `runs/g1-x-opus-sol/game.jsonl`：字段有 `move`、`text`、`check`、`stat`、`side`、`ply` |
| `end` 行有胜方和终局原因 | 已核实 | 同上 `end.end = {winner, reason}` |
| `config` 行有双方模型和思考深度 | 待验证 | 只看到 `cfg` 字段，没展开里面的键 |
| 理由文字能从 `game.jsonl` 拿到 | 待验证 | 看过 `record.txt` 的评注里有理由；`jsonl` 里理由是从 `attempt` 回复里切出来的还是 `move` 行直接带着，没核实；最差也可以复用 `records.meta_comment` 的现成逻辑 |
| ICCS 坐标到 DhtmlXQ 坐标的换算：y = 9 − 行号 | 已核实 | vschess 样例 `binit` 中红车在 `09` |

### 方案 A：纯 SVG 自绘薄播放页（推荐作为保底，许可最干净）

- **转换器**（Python，放本仓库）：`game.jsonl` → 每盘一个 JSON（起始局面、每步坐标、中文记谱、是否将军、理由和元信息、双方、结果），再生成一个清单文件列出要连播的几盘。约 **80–120 行**。
- **棋盘 SVG 自绘**，约 **100–150 行 JS/CSS**，包括：
  - 9×10 交叉线、河界「楚河 汉界」、两个九宫斜线；
  - 兵卒和炮位的「炮台」小折角（这部分最琐碎，约 30 行）；
  - 圆形棋子：外圆、内圈，字用 `<text>` 写汉字。红黑两方用不同的字（帅/将、仕/士、相/象、兵/卒、炮/砲 可选）；
  - 用 SVG 的 `viewBox` 做到任意分辨率都清晰。
  - 也可以不自画，直接用 xiangqi-setup 的 CC0 棋盘和棋子 SVG，这部分就降到约 30 行加载代码。
- **播放逻辑**，约 **250–400 行**：
  - 按坐标搬子，带吃子；
  - 走子动画（CSS transform 过渡）；
  - 上一步起点和终点的标记、将军时将帅泛红光并出「将军」字样；
  - 顶栏写双方和思考深度、第几步、中文记谱；
  - 片头标题画面、片尾结果画面；
  - 评注面板：理由、耗时、思考/输出 token、非法重选次数；
  - 回放控件：暂停、前后单步、拖动条跳到任意一步；
  - 多盘连播。
- **给 Playwright 的接口**：
  - 网址参数 `?list=…&mode=record|review&gap=2500&aspect=9x16`；
  - 全局 `window.player = {step(n), play(), pause(), state()}`；
  - 播完时设置 `window.__done = true`，同时 `console.log('DONE')`。
  - **录屏要稳，建议不用浏览器实时计时**，改成「帧驱动」：页面提供 `renderAt(毫秒)`，脚本逐帧调用、截图，再用 ffmpeg 合成。这样加载卡顿不会丢步，节奏也完全确定。Playwright 自带的 recordVideo 是实时录制，可能掉帧。
- **录制脚本**（Node 或 Python 的 Playwright）加 ffmpeg 命令：约 **80–150 行**。
- **合计**：约 **600–900 行**。agent 大约 **1–2 个工作日**（含调样式和出竖屏/横屏两套版式）。不依赖任何 copyleft 代码。

### 方案 B：chessgroundx 加自写外壳

- 省掉的只有「画棋子、走子动画、上一步和将军高亮」这部分，约 100–150 行。
- 代价：
  - 要搭 npm 打包（TypeScript/rollup 或 esbuild）；
  - 棋盘和棋子素材要另配，pychess 的默认素材是 AGPL，得换成 CC0 的 playok 或自己画；
  - 许可变成 GPL-3.0。
- 其余外壳（记谱、评注、连播、录屏接口）和方案 A 一样多，合计约 **500–750 行加构建配置**。
- 性价比不如方案 A。
- **ffish.js 在两个方案里都用不着**：着法合法性对局程序已经保证过了，将军标记也已经在记录里。

### 方案 C：vschess 加包装

- 包括：DhtmlXQ 转换器约 60 行、连播和录制包装页约 100 行、竖屏干净画面的样式包约 150–250 行 CSS、关掉云端请求、自己补「将军」提示约 30 行。
- 合计约 **350–450 行**，比方案 A 少，但有三个硬伤：
  - 位图棋盘高清放大会发虚；
  - 实时计时不适合确定性录屏；
  - 界面很重，改成干净画面要逆着它的布局来。
- 适合「用户自己回放阅读」这一半需求：只要转成 DhtmlXQ，就能直接用它的完整打谱界面看评注。
