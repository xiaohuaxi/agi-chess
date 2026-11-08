# 中国象棋棋谱回放：现成网站/平台调研

> 调研日期 2026-09-29。只调研、未改任何仓库文件。需求依据 `docs/viewer-brief.md`。
> 证据来源：网页实际抓取（WebFetch/curl）与 pychess-variants 源码（`~/repos/pychess-variants`，HEAD `0d06f16`，2026-09-29；该检出是已存在的稀疏检出，只用 `git show` 读，未改动）。下载的网页原件在 `web/`。
> 约 33 次网页访问。

## 一句话结论

没有哪个现成网站能原样满足「多盘连播 + 隐藏评注自动播 + 能知道播完」的录屏需求；最接近的是**东萍 DhtmlXQ 动态棋盘**（中文记谱、逐步评注、自带自动播放含 2 秒/3 秒档、评注区可藏），但它是老式 iframe 小部件、无多盘连播、JS 没有许可声明；**pychess.org** 现代、能把多盘 PGN 连评注导进 study，但没有自动播放、不显示中文记谱、要登录、条款禁止抓取/自动化。结论偏向：第三方平台最多「借来用一部分」，录屏主力要走选型第 2/3 档（开源项目或自做）。

---

## 1. 东萍象棋网 dpxq.com — DhtmlXQ 动态棋盘

证据：
- 演示与格式说明页：http://www.dpxq.com/hldcg/dhtmlxq/DhtmlXQ_show.htm （本地 `web/show.htm.u8`）
- 代码生成器（打谱器）：http://www.dpxq.com/hldcg/dhtmlxq/ → `frame.htm` → `upfile.htm` + `upfile.js`
- 播放器脚本：http://www.dpxq.com/DhtmlXQ_www_dpxq_com/DhtmlXQ_www_dpxq_com.js （本地 `web/dhtmlxq.js`）

**格式（已核实，演示页原文）**：UBB 文本块 `[DhtmlXQ] … [/DhtmlXQ]`，常用标签：`DhtmlXQ_title / event / date / red / black / result / endtype / binit / movelist / commentN / firstnum / zoom / hidemove`。
- 着法 `movelist`：每步 4 位数字「起点 x,y + 终点 x,y」，棋盘左上角 (0,0)、右下角 (8,9)（黑方在上）。原文例子：「炮二平五」记作 `7747`。换算：ICCS `h2e2` → x=列(a=0…i=8)、y=9−行 → `7747`，与我们记录末尾的 ICCS 串一一对应，转换器很简单。
- 评注：`[DhtmlXQ_commentN]…[/DhtmlXQ_commentN]`，N 是第几步（comment0 = 开局前），换行写成 `||`。可承载「耗时/token/理由」整段文字。
- `zoom`：`[DhtmlXQ_zoom]1.40.500[/DhtmlXQ_zoom]`，前段放大倍数 1.00–2.20；后段 500=全部显示、350=不显示变着注解区、240=只显示左侧基本棋盘区（原文）。
- `hidemove`：打开时隐藏着法列表；`firstnum`：打开后自动走到第 N 步。

逐项：
1. **导入**：是。生成器能粘贴文本（按钮「中文棋谱 / WebCchess / 象棋演播室 / 象棋桥」，`upfile.js` 里有 `TXTtoDhtmlXQ`、`getpgn_TXT`、`getwxf_TXT`、`WXFtoCHN` 等，看函数名是在浏览器里转换 PGN/WXF/中文文本，未逐行核实）；或选硬盘文件上传到 `upfile.asp` 转换。官方列的可导入格式：弈天、MXQ、MCJ、PGN、FEN、TXT、XQF、CHN/XQI、CCM、CHE 等（搜索结果摘要，未逐个试）。也可以直接手写 UBB（我们自己转换最稳）。
2. **多盘连播**：否。一个 UBB 就是一个棋盘；「同一帖子里可以发多个棋盘」只是一页并排多个，没有播完接下一盘。要连播得外部脚本换棋谱。
3. **自动播放/间隔**：是。「自动」按钮弹出档位 8/5/3/2/1/0.5/0.2/0.1 秒（`dhtmlxq.js` 里 `Autotimer(8000)…Autotimer(100)`）；手机版固定 1 秒。`Autotimer(ms)` 是全局函数，脚本可传任意毫秒（如 2500）。计时用 `setInterval`，没有防卡顿补偿。
4. **评注显示/隐藏**：部分。评注在固定的 textarea 注解区；用 `zoom` 后段 350/240 可把注解区整块藏掉，但界面上没有随时切换评注的开关（着法列表有「隐藏/显示」链接）。
5. **网址参数/脚本进录屏态、得知播完**：部分。没有自动播放的 URL 参数（JS 只读 UBB 标签，URL 上只认直播用的 `live=yes/room=yes`）。能做的：UBB 里写 `zoom …240` 藏评注，页面加载后脚本调 `Autotimer(2500)`；播放器状态在全局变量 `nnum`（当前步）/`lnum`（末步），`nnum==lnum` 即播完，`StopPlay()` 会自己停表。前提是能碰到它所在 iframe（同源，即自己托管页面时）。
6. **上传/登录**：粘贴文本转换在浏览器内（按函数判断，未抓包核实）；选文件转换会上传文件到 dpxq；存进「棋谱仓库」要账号（仓库页有登录/VIP 入口，具体规则未核实）。若把 JS 与图片支持包下载到本地自托管（官方提供下载：http://www.dpxq.com/hldcg/share/soft/ ），可以完全不上传。注意 JS 里 `SURL` 在非 localhost 时指向 www.dpxq.com，搜索等功能会回连东萍。
7. **条款/版权**：未见专门的使用条款。页脚原文：「本站原创文章版权归作者和东萍象棋网共同拥有，文章可自由转载……转载文章时请注明作者和出处」「Copyright 2004 东萍象棋网 版权所有」。播放器 JS 与棋子图片**没有任何许可声明**——按本仓库许可政策，「许可不明」按红线处理，自托管/改用前要问维护者（或东萍）。截录画面发社交账号：无明文限制，也无明文许可（未核实）。
8. **画面**：部分。`zoom …240` 只剩棋盘区（仍带按钮条），放大最高 2.20 倍；棋盘外形固定，不能直接出 9:16/16:9，要外层页面自己排版裁切；老式 DHTML 绝对定位，高 DPI 表现未核实。

## 2. 象棋百科全书 xqbase.com（棋谱仓库页、PGN 规范、象棋巫师/小巫师）

证据：
- 棋谱页样例：https://www.xqbase.com/xqbase/?gameid=1 ；播放脚本 https://www.xqbase.com/js/board.js （本地 `web/xqb_board.js`，约 6KB）
- PGN 规范：https://www.xqbase.com/protocol/cchess_pgn.htm
- 象棋巫师：https://www.xqbase.com/xqwizard/xqwizard.htm 、棋谱编辑手册 https://www.xqbase.com/xqwizard/help_edit.htm ；小巫师 https://www.xqbase.com/xqwizard/xqwlight.htm

**PGN 规范（已核实）**：标签 Event/Site/Date/Red/Black/Result/Format/FEN 等；`[Format "Chinese|WXF|ICCS"]`，默认中文；评注用 `{}`，变着用 `()`。这是中国象棋 PGN 的通行参照，我们的转换器若要出「标准」格式，应照它。

**网页棋谱查看器**：只是仓库自己的对局展示。页面内嵌 `jsboard("", "H2-E2 B9-C7 …", 0)`，`board.js` 只有 起点/上一步/下一步/后十步/终点 等函数，没有自动播放、没有评注、没有上传入口。

**象棋巫师**：Windows 桌面软件（有自动播放/演示、评注、能读 XQF/PGN/ICCS/WXF 等，见手册），不是网站；Mac 上要 Wine/虚拟机，不在本单范围。**象棋小巫师 XQWLight**：人机对弈小程序（iOS/Android/Java），不是回放器；页面未给开源地址与许可（网上另有 xqbase 的 GitHub 项目，本单未核实）。

逐项：导入 否；多盘 否；自动播放 否；评注 否；录屏自动化 否（可脚本连点「下一步」，但棋谱须在它库里）；上传/登录 不适用（不能传）；条款：页脚「© 2026 象棋巫师全部版权」，无专门条款；画面：小棋盘嵌在老式表格页里，未核实能否干净截取。

## 3. pychess.org（pychess-variants）

证据：源码 `~/repos/pychess-variants`（AGPL-3.0）；条款 https://www.pychess.org/terms ；记谱说明 https://www.pychess.org/variants/xiangqi

逐项：
1. **导入**：是。
   - `/paste`：粘贴单盘 PGN（`[Variant "Xiangqi"]` + 可选 `[FEN]`），着法按 Fairy-Stockfish 的 SAN 解析（`client/pgn.ts` 的 `resolvePgnMove`）。**只提交标签和主线着法，评注丢弃**（`client/paste.ts` 只 `FD.append` 标签、`moves`、`final_fen`）。导入后成为站上的一盘公开对局，页面 `/{gameId}`。
   - **Study**：可导入多盘 PGN，逐盘成章节，**保留 `{}` 评注**（`client/study/studyPgnImport.ts` 的 `commentsFromPgn`）。
   - 我们需要把 ICCS 转成 Fairy-Stockfish SAN（本仓库已有 pyffish，可生成），不是中文记谱。
2. **多盘连播**：否（study 多章节，但要手动切章）。
3. **自动播放**：否。客户端没有 autoplay 代码（全仓 grep 无），只能脚本按「下一步」/方向键模拟。
4. **评注显示/隐藏**：部分。study 里有评注区；无一键隐藏开关（未核实 UI 设置）。
5. **录屏自动化**：部分/偏否。只有 `/embed/{gameId}?ply=N`、`/study/embed/{studyId}/{chapterId}`、`/analysis/xiangqi/{fen}` 这类地址，没有自动播放或隐藏评注参数；步进与判断播完都得靠页面脚本/按键模拟。
6. **上传/登录**：导入的对局存到 pychess 服务器、公开；study 创建**要登录**（`server/views/study.py`：`if user.anon: raise HTTPFound("/login")`）；study 可设私有/不公开（`/study/private` 路由存在）。
7. **条款**：条款原文：「Games, moves, results … may be public and may remain available as part of the site's chess archive」；「You must not attack, overload, scan, scrape, or disrupt the service」；「Do not use … automation, bots, scripts … in games where this is not allowed」。未明文禁止截图/录屏。无头浏览器打开几页录屏属灰区（不是对局作弊，也不算抓取，但要克制访问量）。棋子图片各套有自己的许可（如 `xiangqi/euro` 为 CC-BY-4.0、`playok` 自带许可），录屏发布最好选许可明确的棋子套并署名。
8. **画面**：部分。embed 页只有棋盘+工具栏（`static/embed.css` 网格布局），棋盘可缩放、SVG 清晰；记谱只有 SAN 与 WXF（`client/cgCtrl.ts`：`XIANGQI_ARBNUM → XIANGQI_WXF`），**不显示「炮二平五」这类中文记谱**；9:16 要外层自己裁。

## 4. ChessDB 云库 chessdb.cn

证据：https://www.chessdb.cn/query/
- 是开局/局面查询工具：可「输入FEN」、逐步走子，页面有「自动走红/自动走黑」（让云库替一方应着，**不是回放棋谱**）和「设置URL」入口（参数格式未核实）。
- 逐项：导入整盘棋谱 未核实（未见粘贴整盘着法入口）；多盘 否；自动回放 否；评注 否；录屏自动化 未核实；上传：查询会把局面发到云库服务器、无需登录；条款：只见备案号，无条款页；画面 未核实。不适合做回放器。

## 5. elephantchess.io

证据：https://elephantchess.io/analysis
- 英文象棋站的分析板：记谱可选 WXF、PGN（`Che2`）、代数（`h2e3`），有「Annotation」输入框（0/2000 字），游客会话 30 天，注册可跨设备。
- 逐项：导入 部分（搜索结果称可导入 PGN/UCI 着法，页面抓取未见入口，未核实）；多盘 否；自动播放 否（页面无）；评注 部分（可写单步注解）；录屏自动化 未核实；上传 是（在它服务器上，游客可用）；条款 未核实；画面 未核实；无中文记谱选项。

## 6. xiangqi.com（play.xiangqi.com）

证据：https://www.xiangqi.com/help/analysis 、条款链接 https://www.xiangqi.com/terms （未打开）
- 分析板可逐步输入着法、看引擎评估，复盘针对自己在站上下的棋；帮助页未提 PGN/FEN 导入、评注、自动播放、嵌入。
- 逐项：导入 未核实（帮助页没写）；多盘 否；自动播放 未核实（帮助页没写）；评注 未核实；录屏自动化 未核实；登录 部分（完整功能要登录）；条款 未核实；画面 未核实。

## 7. mistboard.com（新兴开源站，顺带）

证据：https://github.com/brianhliou/mistboard （AGPL-3.0-or-later）、issue #454（2026-09-25，开放）
- 面向国际象棋玩家的英文象棋站；有赛事直播、棋局库、对局复盘、PGN/JSON 导出、study 与嵌入；#454 在规划「只显示棋盘的全屏模式、PNG/GIF 导出」等创作者工具，尚未做完。有汉字棋子选项（#398）。
- 导入自己的棋谱、自动播放、评注开关、条款：均未核实。值得在开源项目那一轮再看它的嵌入与导出代码。

## 8. 其它（一句话）

- **lichess.org**：不支持中国象棋（lichess 论坛多帖确认，官方态度是只做国际象棋近亲变体）。例：https://lichess.org/forum/lichess-feedback/chinese-chess-on-lichess
- **天天象棋**（腾讯）：官网 https://xiangqi.qq.com/ 是游戏下载与活动页，复盘打谱在 App 里，未见网页版导入/回放（未深查）。
- **象棋谱 xqipu.com、象棋桥、象棋演播室**：前者是棋谱站（未核实能否上传）；后两者是 Windows 桌面软件，不在本单范围。

---

## 汇总表

值：是 / 否 / 部分 / 未核实。「—」= 不适用。

| 平台 | 1 导入自己棋谱 | 2 多盘连播 | 3 自动播放且间隔可调 | 4 评注显示/隐藏 | 5 网址/脚本进录屏态、知道播完 | 6 无需上传/登录 | 7 条款允许截录发布（有明文） | 8 干净棋盘、比例可控 |
|---|---|---|---|---|---|---|---|---|
| 东萍 DhtmlXQ | 是（UBB/文本/多种文件） | 否 | 是（8–0.1 秒档，脚本可任意毫秒） | 部分（参数可整块藏，无切换开关） | 部分（无参数；脚本调 `Autotimer`、读 `nnum/lnum`） | 部分（粘贴或自托管可不上传；JS 许可不明） | 未核实（无条款，仅版权声明） | 部分（可只剩棋盘，比例需外层裁） |
| xqbase 棋谱页 | 否 | 否 | 否 | 否 | 否 | — | 未核实 | 未核实 |
| pychess.org | 是（PGN；study 保留评注） | 否 | 否 | 部分 | 部分（只有 embed/ply 地址，靠脚本步进） | 否（存到站上；study 要登录） | 部分（条款不禁截图，禁抓取/自动化扰动；棋子图各有许可） | 部分（embed 较干净，无中文记谱） |
| ChessDB 云库 | 未核实 | 否 | 否 | 否 | 未核实 | 部分（免登录，局面发到服务器） | 未核实 | 未核实 |
| elephantchess.io | 部分 | 否 | 否 | 部分 | 未核实 | 部分（游客可用，数据在站上） | 未核实 | 未核实 |
| xiangqi.com | 未核实 | 否 | 未核实 | 未核实 | 未核实 | 部分（完整功能要登录） | 未核实 | 未核实 |
| mistboard.com | 未核实 | 未核实 | 未核实 | 未核实 | 未核实 | 未核实 | 未核实 | 部分（全屏棋盘模式在规划中） |
| lichess.org | 否（不支持象棋） | — | — | — | — | — | — | — |

## 对下一步的提示

- 若要借第三方：DhtmlXQ 格式最贴合（中文记谱、逐步评注、坐标与 ICCS 直接互换），可以在本地页面里放 DhtmlXQ 播放器、外层写连播与录屏脚本——但它的 JS/图片**许可不明**，按仓库政策需先问维护者；在 dpxq 站内用则画面带站点框架、难以自动化。
- pychess 适合「用户自己带评注回放」（study 多章节），不适合自动录屏，且记谱不是中文、要登录、内容上第三方。
- 录屏主线大概率要走开源项目或自做：可顺手比较 mistboard、pychess 的棋盘组件（都是 AGPL，按仓库许可政策属「明确不能用」一族，能否拿来参考请问维护者）以及宽松许可的棋盘库（本单未调研）。
