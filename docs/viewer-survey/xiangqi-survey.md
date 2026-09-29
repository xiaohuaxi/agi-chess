# 中国象棋棋谱回放 + 录屏：候选方案调研

> 2026-09-29。只调研、未实施，未改任何仓库文件。需求依据 `/Users/xhx/repos/llm-chess/docs/viewer-brief.md`。
> 本文是汇总。两份分报告有逐项证据（链接、源码行号、LICENSE 路径）：
> - 现成网站/平台：`xiangqi-platforms.md`（下载的网页原件在同目录 `web/`）
> - 开源项目：`xiangqi-opensource.md`
> - 同目录另有一份录屏技术报告 `recording.md`（不是本单产出，录屏方式的本机实测在那里），本文引用了它的结论。
>
> 本次新 shallow clone 到 `~/repos/`（只读）：chessgroundx、pychess-variants（稀疏）、xiangqi.js、xiangqiboardjs、xqwlight、vschess、python-chinese-chess、xiangqi-setup、xiangqi_viewer。已有仓库一个没动，没碰 jev-study。

## 一句话结论

三档都查过，没有现成的东西能直接用。现成网站没有一家能用网址或脚本同时做到「多盘连播 + 隐藏评注自动播 + 知道播完」；开源项目里最接近的 vschess 差连播、没有画面上的将军提示、棋盘是位图（竖屏高清会发虚）、而且它的 PGN 解析会悄悄删掉我们评注里的内容。**推荐自己搭一个纯 SVG 的薄播放页**：数据直接取 `game.jsonl`，不需要规则库，约 600–900 行，agent 1–2 个工作日，不依赖任何 copyleft 代码；录屏走「逐帧截图 + ffmpeg」。

## 候选 × 需求 勾选表

图例：✅ 满足；◐ 部分满足或要少量包装；❌ 不满足；？ 未核实；— 不适用。

| 候选 | 类型 | 许可（族别） | 用自己的棋谱、数据留本地 | 多盘连播 | 定时自动走子、间隔可调 | 评注录屏藏 / 回放显 | 网址或脚本进录屏态、知道播完 | 画面干净、比例可控、高清 | 上一步 / 将军 / 双方信息 | 中文记谱 | 回放：单步跳转 + 每步元信息 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 东萍 DhtmlXQ（网站或自托管） | 网站 / 脚本 | **许可不明**（无任何声明） | ◐ 粘贴或自托管可不上传 | ❌ | ✅ 8–0.1 秒档，脚本可任意毫秒 | ◐ 可整块藏，无切换开关 | ◐ 无参数；脚本调计时函数、读当前步变量 | ◐ 可只剩棋盘，比例要外层裁；位图 | ？ | ✅ | ◐ 评注是一段文字 |
| pychess.org | 网站 | 站点代码 AGPL-3.0（强） | ❌ 存到它服务器，study 要登录 | ❌ | ❌ | ◐ study 保留评注 | ◐ 只有 embed 地址，靠脚本按键 | ◐ SVG 清晰，比例外层裁 | ✅ | ❌ 只有 WXF / SAN | ◐ |
| xqbase 棋谱页 | 网站 | — | ❌ 不能导入 | ❌ | ❌ | ❌ | ❌ | ？ | ？ | ✅ | ❌ |
| ChessDB / elephantchess / xiangqi.com | 网站 | — | ◐/？ | ❌ | ❌ | ◐/？ | ？ | ？ | ？ | ❌/？ | ？ |
| vschess（微思象棋播放器） | 开源 JS 播放器 | **LGPL-3.0（弱）**；子目录另附 GPL-3.0 原文、源码头只写「LGPL」无版本，待确认 | ✅（关掉它的云端请求后） | ❌ 约 50 行包装 | ✅ 0.1 秒粒度，实时计时 | ◐ 改 CSS 藏标签页 | ✅ JS API + 回调；◐ 播完要自己判断 | ❌ 位图最高 2 倍图，界面很重 | ◐ 上一步有；将军只有音效 | ✅ | ✅ |
| chessgroundx | 棋盘组件 | GPL-3.0（强） | ✅ | ❌ | ❌ | ❌ | ✅ 自己暴露 | ✅ 配 SVG 素材 | ✅ 上一步、将军高亮 | ❌ | ❌ |
| xiangqiboard.js | 棋盘组件 | MIT；素材许可不明 | ✅ | ❌ | ❌ | ❌ | ◐ | ◐ | ◐ | ❌ | ❌ |
| ffish.js / xiangqi.js | 规则库 | GPL-3.0（强）/ BSD-2-Clause | — | — | — | 解析 PGN 时评注整段丢 | — | — | 能判将军 | ❌ | — |
| python-chinese-chess（出 GIF） | Python 库 | GPL-3.0（强） | ✅ | ❌ | ◐ GIF 帧间隔 | ❌ | — | ❌ 只有棋盘 | ✅ | ✅ | ❌ |
| xiangqi-setup | 命令行出 SVG | 代码 AGPL-3.0-or-later（强）；**素材多为 CC0-1.0** | ✅ | — | — | ❌ | — | 素材可复用 | ◐ | ❌ | — |
| XQWLight | 人机对弈 | GPL-2.0-or-later（强） | 不是播放器 | ❌ | ❌ | ❌ | ❌ | ❌ | ◐ | ❌ | ❌ |
| **自搭 SVG 薄播放页（推荐）** | 自己写 | 自有；素材自画或取 CC0 | ✅ | ✅ | ✅ | ✅ 两种模式 | ✅ 网址参数 + JS 接口 + 播完标记 | ✅ SVG 任意分辨率，9:16 / 16:9 两套版式 | ✅ | ✅ 直接用记录里的 | ✅ |

强 copyleft 一族（GPL / AGPL，按仓库政策「明确不能用」）：pychess-variants、chessgroundx、ffish.js、python-chinese-chess、xiangqi-setup 代码、XQWLight、mistboard。弱 copyleft：vschess（LGPL-3.0，待确认版本）。许可不明（按政策视同红线）：DhtmlXQ 播放器脚本与图片、xiangqiboard.js 的素材。本工具只在本机自用录视频、不分发代码时能不能用，本文不下结论，留给维护者定。

## 一、现成网站/平台

**东萍 DhtmlXQ**：最贴合的一家。格式是 `[DhtmlXQ]…[/DhtmlXQ]` 文本块，着法是每步 4 位数字（起点 x,y + 终点 x,y，红方在下、y=9 是红方底线），和我们的 ICCS 一一对应（`h2e2` → `7747`，即「炮二平五」）；每步评注 `[DhtmlXQ_commentN]`，换行写 `||`。自带自动播放（8/5/3/2/1/0.5 秒等档，脚本调 `Autotimer(毫秒)` 可任意间隔），`[DhtmlXQ_zoom]` 能把评注区整块藏掉、只剩棋盘区，全局变量「当前步 = 末步」即播完。缺：不能连播、没有自动播放的网址参数、老式 iframe 小部件（比例要外层裁、位图）、播放器 JS 和图片**没有任何许可声明**。在 dpxq 站内用画面带站点框架；自托管可以不上传，但它的脚本在非本机域名下会回连东萍。条款：只有「版权所有、转载注明出处」的页脚，截录发社交账号没有明文许可也没有明文禁止。

**pychess.org**：现代，SVG 清晰；study 能导入多盘 PGN 并保留 `{}` 评注。但没有自动播放、记谱只有 WXF / SAN（没有「炮二平五」）、建 study 要登录、棋谱存到它服务器（公开对局会留在站上档案）。条款禁止抓取、扫描、干扰服务，没禁截图；无头浏览器反复访问属灰区。适合用户自己带评注翻看，不适合自动录屏。

**xqbase.com**：棋谱页只能手动点、不能导入。它的「中国象棋 PGN 规范」（`[Format "Chinese|WXF|ICCS"]`、`{}` 评注）可作为以后出通行 PGN 的参照。象棋巫师是 Windows 桌面软件，Mac 要 Wine / 虚拟机，录屏代价见 `recording.md`（屏幕录制权限每月确认、锁屏黑帧，全自动脆弱）。

**其它**：ChessDB 云库、elephantchess.io、xiangqi.com 都是分析 / 查询工具，没有棋谱自动回放；mistboard.com（AGPL）的「只显示棋盘」全屏模式还在规划；lichess 不支持象棋。

## 二、开源项目

**vschess**（https://github.com/FastLight126/vschess ，`~/repos/vschess`；最后提交 2025-10，89 star）
- 许可：仓库根 `LICENSE` 是 LGPL-3.0 原文；`vschess/LICENSE` 是 GPL-3.0 原文；打包源码头写「遵循 LGPL 协议」无版本。LGPLv3 惯例就是两份原文并放，大概率是 LGPL-3.0，但要维护者确认。棋盘棋子 PNG、音效无单独许可说明。
- 满足：中文记谱（还能切 WXF / ICCS）、自动播放 `play()/pause()/setPlayGap()`、评注页、上一步高亮、`setBoardByStep(n)` 跳转、全局 `vschess` 对象和 `afterAnimate` 等回调，Playwright 可控。
- 缺：不能连播（外包一层换盘，约 50 行）；将军只放音效、画面无提示；固定 380×420 位图棋盘，最高 2 倍图，录 1080×1920 会发虚；自带标签页、按钮条、着法列表，要干净画面得逆着它的布局大改 CSS；计时是每 100ms 的 `setInterval` 实时计数，录屏节奏不确定。
- **会吞评注**：它读 PGN 时先对全文做 `.replace(/\[(.*)\]/g,"")`、删 `(…)`、删「数字.」、遇到 `1-0` 截掉后面全部，**然后**才抽 `{}` 评注——`[%emt …]` 到行内最后一个 `]` 之间的文字全没、理由里的「(马二进三)」被删、理由里出现「1-0」会截断整盘，都不报错。读 DhtmlXQ 则逐行解析、能原样保留（评注里不出现 `[/DhtmlXQ_` 即可）。所以要喂它就转 DhtmlXQ，别转 PGN。
- 数据外发：初始化会 JSONP 拉 xiaxiangqi.com 的一段远程脚本（不传棋谱）；「生成 GIF / 分享 / 保存」会把棋谱发到 xiaxiangqi.com，GIF 是云端生成。传 `cloudApi: false` 可全关。

**chessgroundx**（GPL-3.0，2026-05，46 star）：pychess 用的棋盘组件，有走子动画、上一步和将军高亮、9×10 棋盘；没有记谱、评注、播放器，要 npm + 打包，素材要另配（pychess 默认素材 AGPL，只有 playok 套是 CC0、euro 套是 CC-BY-4.0）。只省掉自搭方案里约 100–150 行，许可却变成 GPL-3.0，不划算。

**pychess-variants 前端**（AGPL-3.0，很活跃）：前后端绑死，离不开服务器；导入时评注被丢，记谱只有 WXF。只当参考。

**规则库 ffish.js（GPL-3.0）/ xiangqi.js（BSD-2-Clause）**：都没有中文记谱；读 PGN 时 `{}` 评注整段跳过 / 删掉，不报错。**回放根本用不着规则库**：`game.jsonl` 每步已有坐标、中文记谱、将军标记，终局原因在 `end` 行，按坐标搬子（目标格有子就吃掉）就能推出每个局面。

**出 GIF / 图片的工具**：python-chinese-chess（GPL-3.0）能出带上一步和将军标记的棋盘 GIF，但只有棋盘，没有双方信息、标题、连播，依赖缺一个就静默什么都不出；xiangqi-setup（代码 AGPL-3.0-or-later）命令行逐局面出 SVG，**它的棋盘主题 14/16 个是 CC0-1.0、playok 等棋子主题是 CC0-1.0**（逐个看过各主题的 LICENSE.txt；注意 `latex_xqlarge_*` 是非商用、`commons_*` 是 FDL / CC-BY-SA），素材可单独拿来用（playok 棋子的字是 `<text>`，字体依赖本机）。

**其它**：XQWLight（GPL-2.0-or-later）是人机对弈小程序，不是播放器；DhtmlXQ 找不到公开源码仓库、无许可声明；xiangqiboard.js（MIT，2020 停更，jQuery，素材来自维基共享资源、许可要逐文件核）；jshou/xiangqi_viewer（MIT，玩具级）。

## 三、我们的记录怎么转

- **推荐直接读 `game.jsonl`，不经过 record.txt**。已核实：`config` 行 `cfg.players`（如 `claude:opus` / `codex:sol`）和 `cfg.sides.<w|b>.effort`（如 `xhigh`）给出双方与思考深度；`move` 行有 `move`（ICCS）、`text`（中文记谱）、`check`、`stat`（尝试次数、非法、用时等）、`opening`；`end` 行有胜方与原因。每步理由与 token 合计，仓库里 `records.move_meta` 已经从 `attempt` 回复切好（字段 `why`、`emt`、`think`、`out` 等，缺省项为 None），转换器复用它即可，不必重新解析文本。
- 自搭页：转换器输出每盘一个 JSON + 一份连播清单，约 80–120 行 Python，放本仓库。
- 若要喂 vschess 或 DhtmlXQ：导出 DhtmlXQ，`movelist` 每步 `x=列(a..i→0..8)`、`y=9−行`，元信息改写成人读得懂的一句话（「用时 5 秒 · 思考 20 token」）和理由一起放 `commentN`，约 60 行。**不要走 PGN**（vschess 会删评注内容，ffish / xiangqi.js / pychess 会丢评注）。
- 以后要出通行 PGN：照 xqbase 规范，`[Game "Chinese Chess"]`、`[Format "Chinese"]`，评注原样搬；自定义的 `[%…]` 命令在已查的解析器里都不被识别，其中 vschess 会破坏内容。

## 四、自搭薄播放页的工作量

- **棋盘 SVG 自画**：9×10 线、楚河汉界、九宫斜线、炮位兵位折角、圆形棋子写汉字，约 100–150 行；改用 xiangqi-setup 的 CC0 棋盘 / 棋子 SVG 可降到约 30 行加载代码。`viewBox` 保证任意分辨率清晰。
- **播放逻辑**约 250–400 行：搬子吃子、走子动画（CSS transition，便于逐帧 seek）、上一步标记、将军时将帅泛红并出「将军」字样、顶栏（双方 + 思考深度、第几步、中文记谱）、片头标题画面和片尾结果画面、评注面板（理由、耗时、思考 / 输出 token、非法重选）、暂停 / 单步 / 拖动跳转、多盘连播。
- **给 Playwright 的接口**：网址参数如 `?list=…&mode=record|review&gap=2500&aspect=9x16`；全局 `window.player = {step(n), play(), pause(), state()}`；播完置 `window.__done = true`。录制按 `recording.md` 的本机实测结论：Playwright 自带录像只到 CSS 像素、25fps 低码率 VP8、按墙钟实时录，不适合发布；改为页面按「第 N 步 + 动画进度 t」确定性渲染，逐帧截图（DSF 2 出 1080×1920 / 1920×1080），静止段只截一张用 ffmpeg 拉长，libx264 编码——节奏绝对稳、不因卡顿丢步。录制脚本加 ffmpeg 约 80–150 行。
- **合计约 600–900 行，agent 1–2 个工作日**（含调竖屏 / 横屏两套版式）。没有运行时依赖（Playwright 是 Apache-2.0 的开发期工具，ffmpeg 本机已装）。

## 五、推荐与理由

**推荐：自搭纯 SVG 薄播放页，一个页面两种模式（录屏 / 回放），数据直接取 `game.jsonl`。**

- 只有它能一次满足全部需求，尤其是连播、确定性录屏、高清竖屏、中文记谱、将军提示、回放时看每步 token 和非法次数——这几项在现成网站和 vschess 上都要改或做不到。
- 规模小：回放不需要规则库，最难的「合法性、将军判定」对局程序已经做完写进记录了。
- 许可最干净：不引入 copyleft 代码；素材自画，或只取 CC0 素材。不用等维护者对 GPL / LGPL / 许可不明的裁定。
- 数据不出本机，没有第三方条款问题。
- 国际象棋那边若另有方案可以分开；这个页面的外壳（连播、评注面板、录屏接口）以后也能换一块棋盘复用。

**备选**（如果想先马上有个能看的）：把几盘导成 DhtmlXQ，本机用 vschess 打开，满足「用户自己逐步翻看理由」这一半，约 60 行转换器。它是 LGPL-3.0（版本待确认），且要关掉 xiaxiangqi.com 的云端请求；录屏不建议用它。

## 前提清单

| 前提 | 状态 | 证据 |
|---|---|---|
| `move` 行有 ICCS、中文记谱、将军标记、本步统计 | 已核实 | 抽看 `runs/g1-x-opus-sol/game.jsonl` |
| `end` 行有胜方与终局原因 | 已核实 | 同上，`end.end = {winner, reason}` |
| `config` 有双方模型和思考深度 | 已核实 | `cfg.players`、`cfg.sides.w.effort` |
| 每步理由与 token 合计可直接拿到 | 已核实 | `llmchess/records.py` 的 `move_meta`（`why` 取自落定那次回复） |
| ICCS → DhtmlXQ 坐标 `y = 9 − 行` | 已核实 | 东萍演示页「炮二平五 = 7747」、vschess 样例 `binit` |
| vschess PGN 解析会删评注内容 | 已核实（读源码） | `vschess` 源码 `function.dataToNode.js:179` 起 |
| 逐帧截图 + ffmpeg 节奏确定、可出高清 | 已核实（本机小实验，非本单） | `recording.md` 第一、二节 |
| 走子动画能被逐帧 seek | 部分核实 | `recording.md`：CSS transition / Web Animations 可 seek，rAF 手写动画不行——实现时须用前者 |
| 汉字棋子在无头浏览器里的字体效果 | 待验证 | 取决于本机字体；自画时可指定系统中文字体或把字转成路径 |
| 各社交平台上传规格（码率、帧率） | 待验证 | 未查 |
