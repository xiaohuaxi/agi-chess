# 棋谱回放：现成网站/平台调研（国际象棋）

调研日期 2026-09-29。范围：现成的网站和平台（开源库归别的调研）。
标注约定：**[实测]** = 我亲手请求或渲染过；**[源码]** = 读过官方仓库源码或文档；**[文档]** = 只看了站点自己的页面或搜索结果；**[推测]** = 没有证据的判断。

## 0. 先说结论

1. 没有任何一个现成平台同时满足「多盘连播 + 2–3 秒可调自动走子 + 录屏时隐藏、回放时显示评注 + 自定义元信息 + 网址参数进录屏状态 + 知道何时播完」。核心缺口是同一个：**这些平台都没有网址参数进入自动播放，也没有播完信号**。
2. lichess 最接近「回放器」，但它的自动播放只有「快 1 秒 / 慢 5 秒」两档（或按走子耗时实时重放），不可调、没有网址参数。导入棋局（/paste、/api/import）**会把评注整个丢掉**（实测），Study 会保留理由文字、但把所有 `[%…]` 命令（含 think/out/illegal）删掉（源码）。
3. 「PGN 直接出视频」类站点（chess.video、chessframe、chess.rodeo、plychess）能出 9:16 / 16:9 的成片，带玩家名、上一步高亮；但都是单盘、看不到自定义元信息、也无法让 agent 无头录屏（有的站有反机器人校验）。它们只适合「临时出一条粗糙成片」，不适合做我们的回放器。
4. chess.com 服务条款明文禁止机器人和自动化访问，还专门写了 AI 工具条款；用它做自动录屏风险最高，我没有对它做任何自动化访问。
5. 建议：平台路线基本走不通，进入「次选：开源项目 / 自己做」。lichess 的 lila-gif（AGPL，归开源库那份调研评估）可以逐帧指定延时、玩家名、上一步和将军高亮，是唯一「逐帧可控」的现成组件，但只出 GIF、画面比例固定。

## 1. 本次我实际发出的请求与上传的数据（透明记录）

- 向 lichess 匿名上传了 **两盘 3 步玩具棋**，仅此两盘，没有任何真实棋谱：
  - `POST https://lichess.org/api/import`，内容 `pgn=1.e4 e5 2.Nf3`，得到 `https://lichess.org/LQIyyzJc`。
  - 同一接口再传一盘带评注的 3 步玩具棋（玩家名 `claude:opus` / `codex:sol`，评注里放了 `[%emt] [%think] [%out] [%in] [%cacheread] [%cachewrite] [%illegal]` 和「这是理由文字」之类的假理由），得到 `https://lichess.org/hibmRoIg`。这两盘匿名上传的棋局没法由我删除，公开可访问。
- 无头 Chrome 各加载一次：`https://lichess.org/analysis/pgn/<上面第二盘玩具 PGN>`（分析板），截图确认。
- 各 GET 一次：`/game/export/hibmRoIg?comments=1&clocks=1`、`/game/export/gif/white/hibmRoIg.gif`（第一次用默认 curl UA，被 404；第二次换了浏览器样子的 UA 才拿到。这只是一次性诊断，**正式录屏不该伪装 UA**，见 §2 末尾）。
- lichess ToS 页面、chess.com 用户协议页面、chess.video 与 plychess 的 terms/privacy 页面各 GET 一次；chess.video 首页和它的前端脚本各 GET 一次（只读了里面的接口名）。
- 没有注册任何账号、没有用任何凭据，没有对 chess.com 做任何自动化访问（条款禁止），没有对第三方视频站提交任何 PGN。
- 本地新增：`~/repos/lichess-api`、`~/repos/lichess-lila-gif`（浅克隆），`~/repos/lichess-lila`（稀疏浅克隆，只取 modules/tree、study、game、importer 和 app/controllers）。没有改 llm-chess 仓库任何文件。临时文件在 `/tmp/lcx/`。

## 2. lichess

### 2.1 分析板：/analysis、/paste（粘贴导入）、/analysis/pgn/…

| 项 | 结论 |
|---|---|
| 导入 PGN | 能。`/paste` 页面粘贴；`/analysis/pgn/<url编码的PGN>` 网址直接带 PGN（文档说「多数标准标签支持」）[源码]。 |
| 多盘连播 | 不能。一次只能一盘（/api/import 明写「只能含一盘」）[源码]。 |
| 自动播放与间隔 | 有，但只有菜单里的固定档：**快 1000ms、慢 5000ms**，另有「按走子耗时实时重放」（棋局里有走子耗时才出现）和「按评分变化」[源码 ui/analyse/src/autoplay.ts、actionMenu.ts]。**没有 2–3 秒档，也没有任何网址参数控制**（analyse 前端只读 `engine`、`evals=0` 两个 query 参数，[源码 ctrl.ts]）。要走 2–3 秒得让脚本每隔几秒点「下一步」按钮/按方向键，那就等于自己写调度。一盘播到底会自己停（`move()` 找不到下一步就 `stop()`），页面上可以从「自动播放按钮状态」判断，但不是官方信号 [源码，推测可用]。 |
| 评注：隐藏/显示 | **匿名分析板里评注整个不显示**。[实测] 我把带评注的玩具 PGN 放进 `/analysis/pgn/`，右侧只有 `e4 e5 Nf3`，页面上的 PGN 框只有 `1. e4 e5 2. Nf3`（评注、标签全被抹掉）。 |
| 自定义元信息显示 | 否。同上，连理由文字都没有。 |
| 网址参数直接进录屏状态 | 否（见上）。 |
| 知道何时播完 | 没有官方信号。 |
| 画面 | 网页布局固定（棋盘 + 右侧走法表 + 引擎/开局面板），16:9/9:16 都不是「干净画面」，需要自己截取或裁剪；带 Stockfish、维基开局书等干扰元素。 |
| 上传了什么 | `/analysis/pgn/…` 是 GET，PGN 在网址里发给了 lichess 服务器（服务器把它原样塞进页面数据里再返回，[实测] 页面源里能看到我的 PGN 全文）。 |

### 2.2 导入棋局：POST /api/import（匿名可用）

- 请求：`application/x-www-form-urlencoded`，字段只有 `pgn`（一盘）。匿名可用，不要 token [实测：我没带任何凭据，返回 303 跳到新棋局；文档：`Accept: application/json` 时返回 `{id,url}`]。
- 限速：**匿名每小时 100 盘，带 OAuth 每小时 200 盘**（文档原文）[源码 api-import.yaml]；lila 里匿名一盘扣 2 点、带号扣 1 点。
- 导入后是公开棋局，任何人拿网址都能看；匿名上传者没法删 [推测，未找到匿名删除入口]。
- **评注被丢，自定义命令没用**：[实测] 玩具棋导入后，`/game/export/hibmRoIg?comments=1&clocks=1` 只回 `1. e4 e5 2. Nf3 *`，评注全无；棋局页面源里搜不到「理由」二字。玩家名 `claude:opus`、`codex:sol` 会保留在标签里。
- 导入棋局能否出 GIF：能，见 2.4。

### 2.3 Study（学习）与章节

| 项 | 结论 |
|---|---|
| 导入 PGN | 能：网页里创建章节时贴 PGN，或 `POST /api/study/{id}/import-pgn`（需 OAuth `study:write`，即要账号和 token）[源码 api 文档]。 |
| 多盘连播 | **一个 Study 最多 64 章**（`Study.maxChapters = 64`）[源码]，一份含多盘的 PGN（盘间隔两个以上空行）会自动拆成多章。但「一章播完自动接下一章」**没有**：autoplay 只作用于当前章，播到尾就停 [源码，推测章节间无自动衔接；未在真实 Study 里验证]。 |
| 自动播放与间隔 | 同 2.1，1 秒/5 秒两档，菜单点选，无网址参数。 |
| 评注 | 显示。Study 是带评注的模式。**但导入时所有形如 `[%…]` 的命令都会被正则整段删掉，只把文字留下**：源码里 `metaReg = \[%[^\]]++\]` 被 `removeMeta` 用来清评注，`[%clk]`、`[%emt]` 会被解析成节点的时钟/走子耗时，`[%csl]`、`[%cal]` 变成圈和箭头，其它未知命令（think/out/in/cacheread/cachewrite/illegal）**一律被吞**，不显示也不保存 [源码 StudyPgnImport.scala、tree.scala CommentParser]。所以理由文字能看，think/out/illegal 看不到；要看它们必须把数字写进评注文字里（不再放在 `[%…]` 里）。 |
| 录屏时隐藏评注 | 没有开关。评注栏是页面的一部分，得脚本隐藏（自己注入 CSS）[推测]。 |
| 网址参数进录屏状态 | 没有。Study 有嵌入页 `/study/embed/{id}/{chapterId}`，支持 `theme`、`pieceSet`、`bg`，无自动播放参数 [文档 lichess.org/developers]。 |
| 需要账号 | 创建 Study、导入章节都要登录。我没有账号，所以 Study 的界面表现是 **源码判断，没有实测**。 |
| 上传了什么 | 整份 PGN（含评注）存到 lichess 服务器，可设私有 / 不公开链接（Study 有可见性设置）[推测]。 |

### 2.4 GIF 导出

- 官方路径：`GET https://lichess.org/game/export/gif/{white|black}/{8位棋局id}.gif`，参数只有 `theme`、`piece`，另有 `players`、`ratings`、`clocks`、`glyphs` 四个布尔开关 [源码 routes、Export.scala、GifExport.scala]。Study 章节也有 `/study/{id}/{chapterId}.gif`（多一个 `showGlyphs`）。
- **只能对已存在于 lichess 的棋局出 GIF，不能直接提交任意 PGN**。要先把 PGN 导入成棋局（2.2），再用 id 取 GIF。
- [实测] 用玩具棋局取回：画面 **720×840（不能选比例）**，每帧延时 800ms（3 步 + 开头帧，末帧 5000ms）。延时不是我们可调的：服务器按走子耗时缩放（中位数目标 80 厘秒、最长 200 厘秒）；没有走子耗时的导入棋局一律 0.8 秒/帧 [源码 GifExport.scala]。**GIF 里没有评注**，带玩家名（`players=true`，会附评分）、上一步高亮、将军高亮。
- 用默认 curl UA 被 404，换浏览器样子的 UA 才 200：源码里是 `NoCrawlersUnlessPreview`，即对爬虫 UA 屏蔽 [源码]。所以不要期待用脚本稳定拉这个接口；也不该伪装 UA 去绕它。
- lichess 自己的渲染服务 lila-gif 的 `POST /game.gif` 才支持逐帧 `delay`、`fen`、`lastMove`、`check`、`white`/`black`，但那是**内部服务，没有对外开放**，需自托管（AGPL-3.0，归开源库调研）[源码 lila-gif README]。公开面上还有 `GET /export/fen.gif`（单个局面静态图，可带 `lastMove`、`theme`、`piece`）[源码 routes]。
- 播放是 GIF：无暂停、无评注、无「播完信号」；GIF 循环播放（推测）。

### 2.5 lichess 嵌入

- `/embed/game/{id}`、`/embed/{id}/{color}`、`/study/embed/{id}/{chapterId}`、`/embed/analysis`（可带 `fen`、`color`）。共同参数：`theme`（blue/brown/green/ic/purple…）、`pieceSet`、`bg`（light/dark/system）[文档 lichess.org/developers]。没有自动播放、没有播完事件、没有评注显示参数。

### 2.6 lichess 条款（[ToS 2026-08-01 版](https://lichess.org/terms-of-service)，[实测] 页面原文）

- 允许自动化调用 API：「You can use our services for your own personal or commercial use, such as in your own applications, projects, research, or products.」
- 但限速由对方说了算：「All use of our services are subject to reasonable caps, limits, restrictions, or other bottle-necking which are purely determined at Lichess' discretion.」
- 禁攻击：「You must not attack our website via any kind of volumetric attack, or attempt to exploit any bugs, weaknesses and vulnerabilities present in our website.」
- 可随时收回：「we reserve the right to exclude people from using our services at our sole discretion, and to determine what constitutes abuse of our services」。
- 内容授权：上传或展示内容即授予 lichess 全球、非独占、免版税、可再授权的许可（可宣传使用，不必联系你）。**所以上传真实棋谱等于授权给 lichess 使用**。
- 网站可商用、可复制：「You are welcome to use and reproduce our website for your personal and commercial use, so long as you comply with the relevant licenses」（页面字体、棋子图案各有各的许可，见 [lila COPYING](https://github.com/lichess-org/lila/blob/master/COPYING.md)）。
- API 使用规则（[API 文档](https://lichess.org/api)）：「Only make one request at a time.」超限返回 429，「waiting one minute before retrying will be sufficient」。导入接口限速见 2.2。
- 对录屏：ToS 没有专门禁录屏或截图的条款 [实测：通读了「Using our website / services」部分]。用无头浏览器打开网页录屏、量小，与「个人使用网站」没有冲突 [推测，非法律意见]；但爬虫 UA 会被部分接口挡。

## 3. chess.com（只读文档，未做任何自动化访问）

| 项 | 结论 |
|---|---|
| 导入 PGN | 能。分析页 [chess.com/analysis](https://www.chess.com/analysis)「Load PGN」贴文本或上传文件；分享按钮可生成链接 [文档：搜索结果与帮助页]。 |
| 多盘连播 | 不能（一次一盘，多盘 PGN 需存入「资料库」收藏夹，且我没查到自动连播）[文档，推测]。 |
| 自动播放与间隔 | 分析页有「自动播放」三角按钮，但社区反馈「间隔设置不起作用，总是回到默认 1 秒」，一盘 30 步不到 25 秒就播完 [文档：[论坛帖](https://www.chess.com/forum/view/game-analysis/is-there-a-way-to-replay-games-in-realtime-on-the-analysis-board-49731014)]；没有真实耗时重放，社区做了第三方 [chess-replay.joren.co](https://chess-replay.joren.co/) 补这个缺口。 |
| 评注 | 分析板支持评注（花括号、分号、括号），但我没查到它对 `[%emt]` 等自定义命令的处理，**未知**；未验证。 |
| 自定义元信息显示 | 未知，多半和 lichess 一样只认识标准命令 [推测]。 |
| 网址参数进录屏状态 | 无 [文档]。分享链接是「打开一个可点击走子的棋盘」。 |
| 嵌入 | 有：分享面板「Embed」，iframe `https://www.chess.com/emboard?id=…`，可选棋盘/棋子/坐标，没提自动播放 [文档：[embed 文章](https://www.chess.com/article/view/how-to-embed-share-chess-media)]。 |
| GIF | [chess.com/gifs](https://www.chess.com/gifs) 接受 PGN 或 chess.com 对局链接，可选棋盘和棋子风格、翻转；页面没说速度、尺寸、玩家名 [实测：只读页面文字]。 |
| API | Published-Data API 只读，**不能上传 PGN**；串行访问不限速，并行可能 429，建议 UA 带联系方式 [文档：[PubAPI](https://www.chess.com/news/view/published-data-api)]。 |
| 上传了什么 | 贴进分析页的 PGN 会交给 chess.com 服务器（分享链接需要），且需要登录才能保存 [推测]。 |
| 条款 | 见下，**对自动化最严**。 |

chess.com [用户协议](https://www.chess.com/legal/user-agreement)（页面标 Last Updated: March 25, 2026）[实测：页面原文]：

- 禁止：「use automation software (bots), hacks, modifications (mods) or any other unauthorized third-party software designed to modify the Services」
- 禁止：「use any robot, spider, site search/retrieval application, or other manual or automatic device or process to retrieve, index, “data mine,” or in any way reproduce or circumvent the navigational structure or presentation of the Services or its contents」
- 「D. Artificial Intelligence Restrictions」：「You may not use automated or artificial intelligence (AI) tools to access, scan, scrape, data mine, copy, or use the materials or content in the Services; for the purpose of developing training, or improving an AI model, machine-learning system, dataset, or competitive product or service.」
- 「Any other automated access, AI use, model training, or dataset creation involving our content requires prior written authorization from Chess.com. We may grant or withhold authorization at our sole discretion.」
- 「Chess.com reserves all rights to monitor, detect, restrict, or take action against any unauthorized automated access, scraping, copying, or AI-related use of the Services.」
- 用户对局记录（UGA）的授权：允许显示和使用，但「does not include any right to: (a) sell, resell or use it commercially; … (c) use any data mining, robots or similar data gathering or extraction methods; (d) download (other than page caching) any portion of the UGA」。
- 我的判断 [推测，非法律意见]：无头浏览器自动打开分析页、加载 PGN、录屏，落在「bots / automatic device」的字面范围内；即使是人工点击，录成视频发社交平台也碰到「商业使用 / 衍生使用」的边界。**建议不走 chess.com**，需要的话先发邮件问 legal@chess.com（PubAPI 页面也建议不确定就先问）。

## 4. 其它「PGN → 动图/视频」站点（挑 4 个）

> 只读了站点页面、术语页和前端脚本里的接口名，**没有提交任何 PGN 去实测**（提交前要先想好上传什么）。除 chess.video 外，页面是 JS 渲染，功能清单来自站点自述 [文档]。

| 项 | [chess.video](https://chess.video/) | [chessframe.com](https://chessframe.com/) | [chess.rodeo/video](https://chess.rodeo/video) | [plychess GIF 工具](https://plychess.com/tools/gif-generator) |
|---|---|---|---|---|
| 导入 PGN | 粘贴，或按 lichess/chess.com 用户名拉 | 粘贴、拖入 .pgn、手输 SAN | 粘贴，或拉 chess.com/lichess | 粘贴 |
| 多盘连播 | 未见（单盘） | 未见（单盘） | 未见 | 未见 |
| 输出 | MP4，16:9 / 9:16 / 1:1；免费 1080p60 带小水印，登录才有 4K | MP4；可调：格宽、帧率、走子滑动时长、停顿、字号、棋盘颜色；未见比例选项 | MP4，9:16 / 16:9 / 1:1；免费带水印，要登录才能导出 | GIF 或 WebM；帧率 2–8 fps；黑白方朝向、坐标、棋子风格 |
| 走子间隔 | 「0.5s between moves · 0.60s per move」默认，可调 | 三种预设节奏（Blitz/Classical/Cinematic）加细调 | 未见 | 2–8 fps |
| 玩家名 / 标题画面 | 未见说明 | **有**：首尾标题卡、玩家名、走法字幕；可选 Stockfish 评估条 | 走法标签、评估条 | 玩家名有；上一步高亮有 |
| 评注 | 不显示 | 只有走法字幕，没说能取 PGN 评注 | 只有走法分类（好/坏棋） | **明说会去掉评注**（「Strips … PGN comments」） |
| 自定义元信息 | 否 | 否 | 否 | 否 |
| 网址参数进入 | 无（前端脚本里只有 `/api/videos`、`/api/comments` 之类，无渲染参数） | 未见 | 未见 | 未见 |
| 播完信号 / 可无头录屏 | 不适用：站点直接出成片；首页加载了 Cloudflare Turnstile 反机器人脚本，且条款禁「automated bulk requests, scripted loops」 | 不适用 | 不适用 | 不适用 |
| 渲染位置 / 上传 | 服务器 GPU 渲染 [文档]；上传 PGN 和渲染设置，视频存 CDN 90 天；IP 只用于限流 | 未披露 | **浏览器本地渲染** [文档]，需注册 | **浏览器本地**（站点自述），但 terms 又写「process, display, and store」，两者互相矛盾，[推测] 以站点自述为准 |
| 条款要点 | 「Abusing the video rendering API through automated bulk requests, scripted loops, or any activity that places an unreasonable load on our infrastructure」禁止；禁止「reverse-engineer, scrape, or extract data from our rendering pipeline」；成品可自由使用，无版权声明。[terms](https://chess.video/terms)、[privacy](https://chess.video/privacy) | 没有可访问的 terms 页（`/terms` 404），个人项目 | 没细读条款（页面 65 万字节，多为脚本）；免费带水印、去水印要付费 | 「Do not scrape or harvest data in a way that burdens the Service.」；「Do not disrupt, interfere with, or overload our infrastructure.」[terms](https://plychess.com/terms) |

小结：这类站点的价值在于「把一盘棋直接变成社交平台可发的竖屏成片」，做样片看效果可以。它们做不到：多盘连播、显示我们的自定义元信息、每盘开头带思考深度和终局原因的标题画面、自动化批量出片（有的条款直接禁，有的有反机器人校验）。

补充两个被点到的名字：
- **chessvision**（chessvision.ai）：是「棋盘图片转 FEN」的识别工具，不是 PGN 回放/转视频站，**与需求无关**，没有深入。
- **ChessTempo**：它的 PGN 查看器是一段可嵌入的 JS（[old.chesstempo.com/pgn-usage.html](https://old.chesstempo.com/pgn-usage.html)），有 `pauseBetweenMoves`（毫秒）和多盘 PGN 字符串等参数，文档说明支持评注 [文档：搜索结果摘要]。它其实是开源库路线（也有 [mliebelt/ChessTempoViewer](https://github.com/mliebelt/ChessTempoViewer) 包装），交给开源库那份调研；我没有实测它对自定义命令的处理。
- **365chess.com**：只查到它是棋谱数据库，找不到公开的嵌入或自动播放说明 [文档：搜索无结果]，不建议花时间。

## 5. 勾选表（平台 × 需求）

图例：Y = 能（含证据级别）；N = 不能；? = 未查清；~ = 部分/受限。

| 需求 | lichess 分析板/导入 | lichess Study | lichess GIF | chess.com | chess.video | chessframe | chess.rodeo | plychess |
|---|---|---|---|---|---|---|---|---|
| 导入 PGN | Y 实测 | Y 源码（需账号） | ~ 先导入成棋局 | Y 文档 | Y 文档 | Y 文档 | Y 文档 | Y 文档 |
| 多盘连播 | N | ~ 最多 64 章，章间无自动接续 | N | N | N | N | N | N |
| 自动播放 | ~ 1s/5s 固定档，菜单点 | ~ 同左 | Y（GIF 自带循环） | ~ 有，间隔设置据说无效 | 出成片 | 出成片 | 出成片 | 出成片 |
| 间隔 2–3 秒可调 | N | N | N（服务器定，0.8s） | N | Y 可调 | Y 可调 | ? | Y 帧率 |
| 评注：可隐藏/显示 | N（匿名时评注被丢） | ~ 显示，无隐藏开关 | N（无评注） | ? | N | N | N | N（去掉） |
| 自定义元信息显示 | N | N（`[%…]` 被删） | N | ? | N | N | N | N |
| 网址参数进录屏状态 | N | N | 不适用 | N | N | ? | ? | ? |
| 知道何时播完 | N（无信号） | N | 不适用 | N | 不适用 | 不适用 | 不适用 | 不适用 |
| 9:16 / 16:9 干净画面 | N（720×840 或整页） | N | N（720×840） | ? | Y | ? | Y | ~ |
| 标题画面 | N | N | N | N | ? | Y | ? | N |
| 玩家名 | Y 实测 | Y | Y 实测 | Y | ? | Y | ? | Y |
| 上一步高亮 | Y | Y | Y | Y | ? | ? | ? | Y |
| 将军提示 | ~ | ~ | Y（GIF 服务支持） | ? | ? | ? | ? | ? |
| 终局原因 | Y（标签） | Y | N | ? | ? | ? | ? | ? |
| 上传的数据 | 网址里的 PGN 到 lichess；导入则存为公开棋局 | 整份 PGN 存在 lichess | 已导入的棋局 | PGN 到 chess.com | PGN 到服务器，视频存 90 天 | 未披露 | 浏览器本地 | 浏览器本地（自述） |
| 条款允许自动化 | ~ 允许用 API，限速由对方定 | ~ 同左 | ~ 爬虫 UA 会被拦 | **N 明文禁** | N 禁批量脚本 | ? 无条款页 | ? | ~ 不许「burden」服务 |

## 6. 条款要点与链接汇总

- lichess ToS：<https://lichess.org/terms-of-service>（2026-08-01 版）；API 文档与限速：<https://lichess.org/api>；许可汇总：<https://github.com/lichess-org/lila/blob/master/COPYING.md>；lila-gif 许可 AGPL-3.0：<https://github.com/lichess-org/lila-gif>。
- chess.com 用户协议：<https://www.chess.com/legal/user-agreement>（2026-03-25 更新）；PubAPI：<https://www.chess.com/news/view/published-data-api>。
- chess.video：<https://chess.video/terms>、<https://chess.video/privacy>；plychess：<https://plychess.com/terms>；chessframe、chess.rodeo 见各自主页。

## 7. 对选型的含义

1. 「平台」这一档可以在需求 1、2、6 上直接判死：没有网址参数进录屏状态，没有播完信号，没有 2–3 秒可调的自动走子，也不显示自定义元信息。
2. 如果只要「快速出一条成片发出去看效果」，chess.video 或 chessframe 已经够用；playwright 无头录制它们没意义，因为它们本来就出成片，且有反机器人和条款限制。
3. 值得在开源那份调研里重点看的东西（本次顺带发现）：lila-gif（逐帧延时，AGPL，需拿维护者拍板）；ChessTempo / 其它 PGN 查看器库里 `pauseBetweenMoves` 这类参数；lichess 前端本身开源，可以只借棋盘（chessground，GPL-3.0，边界要问维护者）。
4. 我没有验证的地方：lichess Study 的真实界面表现（要账号）、chess.com 分析板对自定义命令的处理、chessframe / chess.rodeo 的实际输出与限制、lichess 匿名导入的棋局能否被搜索引擎收录。
