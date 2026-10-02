# 棋谱阅读器：各平台现有选项与「做不做 app」评估

> 调研日期 2026-10-02。只调研，没改仓库。商店数据（价格、评分、下载量、更新日期）都是当天查的：苹果走 iTunes Search/Lookup 接口和 apps.apple.com 页面，Google Play 走商店页里的结构化数据，GitHub 走 `gh api`。临时文件和原始数据是会话临时文件，没入库。
> 与 2026-09-29 那轮调研（`docs/viewer-survey/`）的区别：那轮按「录视频 + 自定义元信息」的需求筛，几乎所有现成工具都不合格。本轮换了标准，问的是普通人能不能「打开一个棋谱文件，一步步看，看得到评注」。按这个标准，结论很不一样。
> 证据标注：**实测**＝本次亲手跑过；**商店**＝商店页或接口原文；**文档**＝官方说明或源码；**转述**＝下载站或搜索摘要，没逐条核对；**判断**＝我的推断。

## 0. 结论速览

**事实**
1. **国际象棋所有平台都不缺，而且多是免费的。** 每个平台都至少有一个免费、商店直装、能直接打开 .pgn、能显示评注的选项。最典型的是 lichess 官方 App（iOS/Android，免费、开源、无广告）：2026 年起能从文件管理器、邮件或「用…打开」直接打开 .pgn，多盘文件也能看。桌面上有 En Croissant（三平台，GPL-3.0，2026-09 仍在发版）、SCID vs PC、ChessX，Windows 另有 ChessBase Reader。
2. **中国象棋在 Windows、iOS、Android、网页上也有免费选项**，最强的是「皮卡鱼象棋在线」xiangqiai.com：网页版免费、免登录就能打开 PGN/XQF/CBR/CBL 和东萍格式，认中文记谱，有评注面板；还能「添加到主屏幕」，另有手机和电脑 App。我实测把 xqbase 风格、中文记谱、带评注的 PGN 粘进去，**只要评注里不带 `[%…]` 命令，着法和评注都对**；**一旦评注里带 `[%emt …]`、`[%think …]` 这类命令，就只读进前两步，评注还错位**。
3. **真正薄弱的地方很窄**：Linux 上没有像样的本机象棋打谱软件，不过网页版能补上；面向英文用户、能打开中文记谱文件的象棋阅读器很少；还有「每步带长理由 + 自定义命令」的模型对局，现有工具要么吞掉命令（lichess Study），要么读坏（xiangqiai 的实测），要么把长评注挤在着法列表里。
4. **上架的门槛与费用**：Apple 开发者每年 99 美元；Google Play 一次性 25 美元，但 2023-11-13 之后新开的个人账号要先找 12 个人连续封闭测试 14 天；Microsoft Store 个人开发者 2025-09 起免费注册。国内安卓商店基本要企业主体、软著和 APP 备案；App Store 中国区也要 ICP 备案号。
5. **现有依赖的许可都允许免费或收费分发**：MIT、BSD-2、BSD-3、CC0，随包带上版权声明就行。唯一的硬伤是象棋棋子用的楷体是本机系统字体，不能随 App 分发，要换成开源字体，比如霞鹜文楷（OFL-1.1）。

**判断**
- 「各平台普遍缺免费易得的棋谱阅读器」这个前提不成立。国际象棋完全不缺；中国象棋缺口很小，而且已经被 xiangqiai.com 这类免费网页加 App 占住。
- **收费 1–3 美元的 App 不值得做**：免费竞品强，国内商店的门槛实际上把个人挡在外面，按 85% 分成算，一年要卖出 39–117 份才抵得上 Apple 年费。
- **值得做的只有一件小事**：把现有阅读器做成免费的静态网页或 PWA，定位为「看大模型对局，每步带理由」的配套页面，和发出去的视频互相引流。卖点是长理由的阅读体验和自定义元信息，不是「又一个通用打谱器」。原生 App 先不做。仓库目前只在本地、没有远端，公开托管要另外拍板。

---

## 1. 总表：平台 × 棋种

只收「免费或基础功能免费、正规渠道可得、能打开本地棋谱文件逐步看、能看到评注」的代表。✅ 已被很好满足；◐ 有，但有明显短板；✗ 基本没有。

| 平台 | 国际象棋（PGN） | 中国象棋（PGN / XQF 等，中文记谱） |
|---|---|---|
| 网页 | ✅ lichess Study（要登录，保留评注文字，吞掉未知的 `[%…]` 命令）；pgn.chessbase.com（免费网页 PGN 阅读器）；chess.com 分析页可「Load PGN」 | ✅ xiangqiai.com（免登录打开文件，认中文记谱，有评注面板；带 `[%…]` 命令的评注会读坏，见 §3.1 实测）；东萍 DhtmlXQ（能导入，老式小部件）；◐ xiangqi.com 只能粘贴、不认中文记谱 |
| Windows | ✅ ChessBase Reader（免费）、SCID vs PC、En Croissant、ChessX | ✅ 象棋桥（免费，v3.0，2008）、象棋巫师（免费）、XQStudio 象棋演播室（免费，很老）；象棋旋风收费（另有引擎价） |
| macOS | ✅ En Croissant、Scid vs Mac（4.27，2026-06）、ChessX；Mac App Store 上的 Chess Lab 免费（Chess Studio 收费 3.99 美元） | ◐ 象棋助手离线版（Mac App Store 免费，有内购，2026-09 更新，支持 PGN/XQF/CBR/CBL/东萍、可双击打开）；也可用网页版 |
| Linux | ✅ En Croissant（AppImage/rpm/deb）、ChessX、SCID vs PC | ✗ 本机只有 gmchess（老旧）、XBoard（不认中文记谱）；**实际靠网页版补** |
| iOS / iPadOS | ✅ lichess App（免费，可直接打开 .pgn）；ChessView（免费，无广告，能从「文件」或其它 App 分享打开 PGN）；Chess Studio Lite（免费，有功能限制；完整版 3.99 美元） | ✅ 中国象棋（Dorit，免费，支持 CBL/CBR/PGN/XQF/MXQ/CHE，带注释）；中国象棋对弈打谱（同一开发者的新版，免费）；象棋助手（有会员内购）；象棋公社（有内购）；xiangqiai 网页可加到主屏 |
| Android | ✅ lichess App（100 万+ 下载，可「用…打开」.pgn）；Chess PGN Master（免费，10 万+ 下载，Pro Key 7.99 美元）；Chessis（100 万+ 下载） | ✅ Google Play 上有 Xiangqi master（能导入 PGN，1000+ 下载）；国内商店有中国象棋对弈打谱（小米商店）、象棋公社；xiangqiai 网页可加到主屏、也有 App |

---

## 2. 国际象棋，分平台

| 名称 | 平台 | 价格 | 获取 | 打开本地文件 / 用…打开 | 评注 | 多盘 | 维护 | 许可 | 出处 |
|---|---|---|---|---|---|---|---|---|---|
| lichess App | iOS、Android | 免费，无广告 | 商店直装；看文件不用登录（判断：打开本地文件不需要账号） | 能。Android 声明了 .pgn 和 PGN 类型的「打开 / 分享」（文档：清单文件）；iOS 声明了 PGN 文档类型（文档：Info.plist）；PR #2671「从文件管理器、消息里打开 PGN」2026-02 合入，#3255「iOS 支持分享 PGN」2026-06 合入 | 分析界面显示评注（判断，未实测） | 能，PR #2656「打开含多盘的 PGN」2026-02 合入 | 活跃：v0.28.4，2026-09-17 | GPL-3.0 | [App Store](https://apps.apple.com/us/app/lichess/id1662361230)（4.1 分，639 条评分）；[Google Play](https://play.google.com/store/apps/details?id=org.lichess.mobileV2)（3.8 分，1.46 万条评分，100 万+ 下载，2026-09-17 更新）；[mobile 仓库](https://github.com/lichess-org/mobile)；[#2671](https://github.com/lichess-org/mobile/pull/2671)、[#2656](https://github.com/lichess-org/mobile/pull/2656)、[#3255](https://github.com/lichess-org/mobile/pull/3255) |
| lichess 网页 | 网页 | 免费 | 分析板免登录；Study 要登录 | 粘贴或网址带 PGN；Study 可导入多盘 | 前次实测：匿名分析板把评注整个丢掉；Study 保留文字，删掉所有 `[%…]` 命令 | Study 多章节 | 活跃 | AGPL（站点） | `docs/viewer-survey/chess-platforms.md` §2；[论坛：PGN 导入 Study](https://lichess.org/forum/general-chess-discussion/importing-pgn-files-into-lichesss-studies) |
| chess.com 分析页 | 网页、App | 基础免费，会员收费 | 网页可用；保存要登录（转述） | 「Load PGN」可粘贴或上传 | 支持花括号评注；自定义命令怎么处理未核实 | 未核实 | 活跃 | 商业 | `chess-platforms.md` §3 |
| ChessBase 网页阅读器 | 网页 | 免费 | 打开即用 | 菜单里打开 PGN（转述） | 显示评注（转述） | 未核实 | 未核实 | 商业 | [pgn.chessbase.com](https://pgn.chessbase.com/)；功能出自 chess.com 论坛帖的转述 [链接](https://www.chess.com/forum/view/game-analysis/free-pgn-reader)，本次页面没抓到正文 |
| ChessBase Reader | Windows | 免费 | 官网下载 .msi | 能开 PGN、CBH | 评注、变着、符号 | 是（库） | Reader 2017 版；之后的版本号未核实 | 商业免费软件 | [ChessBase 2017-10-27 公告](https://en.chessbase.com/post/chessbase-reader-2017) |
| En Croissant | Win / Mac / Linux | 免费 | 官网或 GitHub 下载 | 能 | 能 | 能 | 活跃：v0.15.1，2026-09-05；1916 星 | GPL-3.0 | [官网](https://encroissant.org/)、[GitHub](https://github.com/franciscoBSalgueiro/en-croissant) |
| SCID vs PC | Win / Mac / Linux | 免费 | SourceForge | 能 | 能 | 能（数据库） | Windows 4.26、Mac 4.27（2026-06-26）；Linux 包停在 2023-08（转述） | GPL 族（Scid 系） | [SourceForge](https://sourceforge.net/projects/scidvspc/files/) |
| ChessX | Win / Mac / Linux | 免费 | SourceForge | 能 | 能 | 能 | 仓库 2026-05 有推送 | GPL-2.0 | [SourceForge](https://sourceforge.net/projects/chessx/)、[GitHub](https://github.com/Isarhamster/chessx) |
| macOS 自带「国际象棋」 | macOS | 免费 | 系统自带 | **不能导入 PGN**（只能导出） | — | — | — | — | [chess.com 论坛](https://www.chess.com/forum/view/general/can-mac-users-open-pgn-files)（转述） |
| Chess Lab / Chess Studio（Mac） | macOS | Chess Lab 免费；Chess Studio 3.99 美元；Chess Studio Lite 免费 | Mac App Store | 能 | 能 | 能 | 2026-10-01 更新 | 商业 | [Chess Lab](https://apps.apple.com/us/app/chess-lab/id1557677888?mt=12) |
| SUPERB CHESS BOARD | macOS | 2.99 美元 | Mac App Store | 能 | 能 | 能 | v20.0，2025-01 | 商业 | [商店](https://apps.apple.com/us/app/id1251365291)（评分不足） |
| ChessView | iOS | 免费，无广告、无账号 | App Store | 能，从「文件」、邮件、消息或其它 App 分享打开 | 未核实（描述里没写评注） | 未核实 | v1.19，2026-09-20 | 商业 | [商店](https://apps.apple.com/us/app/id6748862638)（5.0 分，1 条评分） |
| Chess Studio Lite / Chess-Studio | iOS | Lite 免费（「部分功能受限」）；完整版 3.99 美元 | App Store | 能导入；也能从 Dropbox、Google Drive、OneDrive 拿 | 「带注解和文字评注地查看」 | 能（数据库） | v4.8.9，2026-10-01 | 商业 | [Lite](https://apps.apple.com/us/app/id694586937)（4.4 分，11 条评分）、[完整版](https://apps.apple.com/us/app/id684224545)（4.7 分，117 条评分） |
| SUPER CHESS BOARD（iPGNViewer） | iOS | 免费，内购 2.99 美元解锁全部功能 | App Store | 能，但要经 Finder 文件共享导入 | 能 | 能 | v21.0，2026-01 | 商业 | [商店](https://apps.apple.com/us/app/id1252538573)（2.0 分，3 条评分） |
| Chess PGN Master | Android | 免费；Pro Key 7.99 美元 | Google Play | 能 | 能看；加评注要 Pro（转述） | 能 | 2026-09-26 更新 | 商业 | [Play](https://play.google.com/store/apps/details?id=com.kalab.pgnviewer)（4.2 分，2248 条评分，10 万+ 下载）；[Pro Key](https://play.google.com/store/apps/details?id=com.kalab.pgnviewerpro)（4.6 分，399 条评分，1 万+ 下载） |
| Chessis | Android | 免费（有没有付费功能未核实） | Google Play | 自带 PGN 阅读器 | 未核实 | 未核实 | 2026-09-12 更新 | 商业 | [Play](https://play.google.com/store/apps/details?id=com.chessimprovement.chessis)（4.65 分，3.15 万条评分，100 万+ 下载）；[官网](https://www.chessis.app/) |

小结（判断）：国际象棋每个平台都有免费、直装、能「用…打开」的选择，手机端连 lichess 官方 App 都补齐了打开文件这一项。没有市场空档。我们能做出差异的只剩「长理由的阅读体验」和「认得自定义元信息」。

---

## 3. 中国象棋，分平台

### 3.1 xiangqiai.com（皮卡鱼象棋在线）实测

- **它说自己能做什么**（文档：[使用指南](https://xiangqiai.com/guide/)，本次抓取）：导入「棋谱文件：PGN、XQF、CBR、CBL 等常见格式都能打开」；粘贴文字时认「东萍（DhtmlXQ）、PGN，以及『炮二平五 马8进7』这样的中文着法」；电脑上点着法列表里的哪一步，右边就显示那一步的注释和变着，手机上点当前步弹出着法面板；棋谱集里能用 ‹ › 一盘接一盘地看。网页版保存要登录，App 不登录也能存在本机。网页可以「添加到主屏幕」，另有手机 App 和电脑版 App。页面没出现收费字样。导入窗口底部写着「棋谱解析：微思象棋库」，也就是 vschess（LGPL-3.0）。
- **实测**（无头 Chromium，粘贴两份 3–4 步的玩具 PGN，xqbase 规范、中文记谱、黑方用全角数字；截图在 `tmp/xqtest/after.png`、`after2.png`）：
  - 评注是纯文字时：4 步全部正确导入，记谱显示成「炮二平五 / 马8进7 / 马二进三 / 车9平8」，每步都标着「注」，点开后右侧完整显示长理由并自动换行。**能用，体验不错。**
  - 评注里带 `[%emt 0:00:12] [%think 340]` 时：**只导入了前两步**，黑方第一步还被显示成「马２进３」（不对）；第一步的评注栏显示的是黑方的理由（错位），红方那段长理由不见了。我们导出的 PGN 每步都带这类命令，所以**我们的棋谱直接丢进去会读坏**。
- 判断：中文用户「打开一个象棋棋谱看看」这件事，它已经免费地覆盖了网页、手机、电脑三端。它的短板正好是我们的特长：认得模型对局的元信息命令、为长理由做的版式。

### 3.2 其它选项

| 名称 | 平台 | 价格 | 打开本地文件 | 中文记谱 / 评注 | 维护 | 出处 |
|---|---|---|---|---|---|---|
| 象棋桥 | Windows | 免费 | 能：XQF、PGN、MXQ、CBR、CBL；可拖入、可关联后双击 | 中文记谱；评注能看能编辑 | v3.0，2008-05（腾讯软件中心标注）；下载站另有 v3.0.4 | [腾讯软件中心](https://pc.qq.com/detail/18/detail_92738.html)、[下载站介绍](https://www.32r.com/soft/44734.html)（转述） |
| 象棋巫师 | Windows | 免费 | 能：PGN、CHE、XQF 等 | 能；还支持朗读，照顾视障用户 | 下载站上是 v5.5.x（转述） | [xqbase 手册](https://www.xqbase.com/xqwizard/help_edit.htm)、[下载站](https://www.onlinedown.net/soft/38287.htm) |
| XQStudio 象棋演播室 | Windows | 免费（绿色版） | 能（XQF 是它的原生格式） | 能 | 下载站最新 v1.63；原始发布年份未核实（判断：已停更多年） | [下载站](https://www.jb51.net/game/595833.html)（转述） |
| 象棋旋风 | Windows | 收费：引擎 90–720 元，分档（转述） | 能，PGN 等 | 能，可自动播放 | 在售 | [腾讯软件中心](https://pc.qq.com/detail/11/detail_18691.html)、[知乎](https://www.zhihu.com/question/49330491)（转述） |
| 中国象棋（Dorit） | iOS | 免费 | 能：CBL、CBR、PGN、XQF、MXQ、CHE，「支持注释、变着」 | 能 | v1.6.8，2023-08（中国区已查不到，台湾、澳门、香港、美国区还在） | [App Store](https://apps.apple.com/us/app/id504275369)（美区 3.8 分，90 条评分） |
| 中国象棋对弈打谱 | iOS；Android（小米商店） | 免费；iOS 页面上没有内购 | 同上（描述照搬，同一开发者） | 能 | v1.7.5，2026-06-01 | [App Store](https://apps.apple.com/cn/app/id6755039199)（4.6 分，50 条评分）；[小米商店](https://app.mi.com/details?id=com.cnvcs.xiangqi) |
| 象棋助手 / 象棋助手离线版 | iOS、Mac | 免费，有内购（会员） | 支持 PGN、XQF、CBR；Mac 版还支持 CAM、CBF、CBL、东萍 UBB，可批量导入、可双击打开 | 能 | 2026-09 更新 | [iOS](https://apps.apple.com/cn/app/id6443748058)（4.4 分，79 条评分）、[Mac](https://apps.apple.com/cn/app/id6747945474)（评分不足） |
| 象棋公社 / 棋路（成都棋路科技） | iOS、Android | 免费，有内购；旧版「棋路」的终身会员 3.99 美元、月会员 0.99 美元（转述） | 旧版棋路支持 CBL、XQF、PGN、CHE、7LU（转述）；新版象棋公社的描述只写了「棋谱残局」，能不能导入本地文件未核实 | 能 | 2026-09-20 | [象棋公社 App Store](https://apps.apple.com/cn/app/id6504705887)（4.7 分，2159 条评分）、[官网](https://chessroad.cn/)、[小众软件对棋路的介绍](https://www.appinn.com/mdevs/)（转述） |
| 天天象棋（腾讯） | iOS、Android | 免费；会员订阅每月 30 元 | **看不了本地棋谱**，只能看它自己的棋谱库和对局；导出都要靠第三方工具（转述） | — | 活跃 | [App Store](https://apps.apple.com/cn/app/id403941510)；[CSDN 导出办法](https://blog.csdn.net/weixin_50198812/article/details/149942778)（转述） |
| Xiangqi master | Android（Google Play） | 免费 | 「能导入 PGN 文件」 | 记谱方式未核实 | 2026-07-22，1000+ 下载 | [Play](https://play.google.com/store/apps/details?id=com.github.gekomad.rangyxx_app) |
| 东萍 DhtmlXQ | 网页 | 免费 | 能导入多种格式；选文件会上传到东萍 | 中文记谱、逐步评注 | 老式小部件，没有许可声明 | `docs/viewer-survey/xiangqi-platforms.md` §1 |
| vschess（微思象棋） | 网页（站长用的组件，也能在线打谱） | 「永久免费」 | 支持东萍、鹏飞、世家、PGN、QQ、中游、联众、打虎将、文本 | 有注释（前次调研：读 PGN 时会删评注内容） | GitHub 最后推送 2025-10 | [官网](https://www.xiaxiangqi.com/vschess/)、[GitHub](https://github.com/FastLight126/vschess)（LGPL-3.0） |
| xiangqi.com | 网页 | 免费，部分功能要登录 | **只能粘贴**，PGN 要求以 `[Game "Chinese Chess"]` 开头；示例是 `C2=5` 这种字母记法，不是中文 | 没提评注 | — | [导入说明](https://www.xiangqi.com/articles/game-notation-import-guidelines) |
| pychess.org | 网页 | 免费 | Study 能导入多盘并保留评注，但要登录、要上传 | 不显示中文记谱 | 活跃 | `xiangqi-platforms.md` §3 |
| Linux 本机 | Linux | — | gmchess（老旧，Ubuntu 16.04 时代就有包）、XBoard、Liground 主要用来对弈，不认中文记谱 | — | — | [Launchpad gmchess](https://launchpad.net/ubuntu/xenial/+package/gmchess)、[Linux 下玩象棋的博客](https://blog.williamgates.net/2024/05/play-xiangqi-in-linux-with-open-source-tools/) |
| Mac App Store 其它 | macOS | 宽立象棋免费；Chinese Chess ™ 4.99 美元 | 主要是对弈，能不能打开棋谱未核实 | — | — | 苹果 iTunes 接口检索结果 |

---

## 4. 空档判断

**事实**
- 国际象棋：六个平台各有至少一个免费、正规渠道、能直接打开文件的选项（§1、§2）。
- 中国象棋：Windows 有三款免费老软件；iOS 有两款免费打谱 App（都支持 PGN、XQF 和注释）；网页、Android、iOS、桌面都能用 xiangqiai.com。Linux 本机的象棋打谱几乎是空的。
- 英文环境：xiangqi.com 的导入只认字母记法、只能粘贴；pychess 要登录，也不显示中文记谱；Google Play 上的英文象棋 PGN 阅读器很少（Xiangqi master 只有 1000+ 下载）。
- 模型对局的特殊需求：lichess Study 删掉未知的 `[%…]` 命令（前次读源码确认）；xiangqiai 遇到这类命令就读坏（本次实测）。我们自己的阅读器是认这些命令的。

**判断**
- 普通人「打开一个棋谱、逐步看、看评注」这个需求，**两种棋都已被很好满足**，收费的空档基本不存在：免费、开源、大平台背书的选项（lichess、xiangqiai）已经在那里。
- 剩下的缺口：①Linux 象棋（用户极少，网页已经补上）；②英文用户看中文记谱的象棋棋谱（小众）；③「每步一段长理由 + 用时、token 这类元信息」的模型对局。只有 ③ 和我们的研究直接相关，但它本身不是一个市场，是我们内容的展示需求。
- 中文记谱的 xqbase PGN 在 iOS、macOS、网页上：普通带评注的文件已经有免费工具能看（实测 xiangqiai 没问题）；只有带 `[%…]` 命令的文件会出问题。导出时把这类命令转成纯文字，也能绕开。

---

## 5. 做成 App 的可行性与代价（粗估）

### 5.1 形态与工作量（判断，按现有约 1700 行纯 JS、无构建的阅读器估）

| 形态 | 要补的东西 | 粗估 | 门槛 / 风险 |
|---|---|---|---|
| **静态网页 + PWA** | 打开文件的按钮（拖拽已经有）；可安装的应用清单和离线缓存；手机上能读评注的版式（现在窄版只剩棋盘，评注被藏起来）；打包一款开源楷体；对外的说明和隐私声明 | 2–5 天 | 要一个公开托管的地方（仓库现在只在本地，要拍板）。「用…打开」.pgn 只有 Chrome/Edge 桌面版支持，安卓和 iOS 都不支持（[MDN 兼容数据](https://github.com/mdn/browser-compat-data/blob/main/manifests/webapp/file_handlers.json)）；接收别的 App 分享过来的文件，只有安卓 Chrome 等 Chromium 系支持，Safari 不支持（[MDN 兼容数据](https://github.com/mdn/browser-compat-data/blob/main/manifests/webapp/share_target.json)）。iOS 上只能在页面里点按钮从「文件」挑 |
| 桌面（Tauri，MIT 或 Apache-2.0 双许可；或 Electron） | 套壳；关联 .pgn 文件让它能双击打开；三平台打包 | 2–4 天，另加签名的麻烦 | Mac 公证要 Apple 开发者账号（99 美元/年）；Windows 不签名会被 SmartScreen 拦，签名证书要另外花钱（价格本次未核实）；Microsoft Store 个人上架免费，由商店签名 |
| 手机（Capacitor，MIT） | 套壳；注册文档类型或分享入口；触屏版式 | 3–7 天，另加审核往返 | iOS 有审核规则 4.2：「要超出重新包装的网站」（[Apple 审核指南](https://developer.apple.com/app-store/review/guidelines/)），纯套壳有被拒的风险；Android 新开的个人账号要 12 人封闭测试 14 天 |

### 5.2 上架费用与条件（事实）

| 渠道 | 费用 | 条件 | 出处 |
|---|---|---|---|
| Apple（App Store 和 Mac App Store 是同一个账号） | 99 美元/年 | 小企业计划下分成 15%（年收入 100 万美元以内）；中国区要 ICP 备案号，2023-09-30 起对新 App 生效，2024-04-01 起没有备案的不能更新、会被下架 | [Apple 注册页](https://developer.apple.com/programs/enroll/)、[分成说明](https://appbot.co/blog/app-developers-apple-google-small-business-programs/)、[ICP 要求](https://www.appfilingchina.com/blog/app-filing-number-is-needed-for-apps-to-be-listed-on-the-apple-app-store-in-china) |
| Google Play | 一次性 25 美元 | 每年前 100 万美元收入分成 15%；2023-11-13 之后新开的个人账号要 12 名测试者连续测 14 天；另外，Google 的开发者实名验证 2026-09 起先在巴西、印尼、新加坡、泰国强制，2027 年推向全球，商店外安装的 APK 也要验证 | [费用](https://splitmetrics.com/blog/google-play-apple-app-store-fees/)、[Keep Android Open 条目](https://en.wikipedia.org/wiki/Keep_Android_Open) |
| Microsoft Store | 个人注册免费（2025-09 起） | 要证件加自拍验证身份 | [Windows 开发者博客](https://blogs.windows.com/windowsdeveloper/2025/09/10/free-developer-registration-for-individual-developers-on-microsoft-store/)、[Microsoft Learn](https://learn.microsoft.com/en-us/windows/apps/publish/whats-new-individual-developer) |
| 国内安卓商店（华为、小米、OPPO、vivo、应用宝） | 不收注册费（转述） | 基本要企业主体（小米已不支持个人或个体户用身份证认证）；软著，且名称必须完全一致；APP 备案；联网的还要域名 ICP 备案 | [小米：APP 备案和软著名称原则](https://dev.mi.com/xiaomihyperos/documentation/detail?pId=1796)、[CSDN 汇总](https://blog.csdn.net/luck332/article/details/146996371)、[知乎](https://www.zhihu.com/question/7719310451)（部分转述） |

### 5.3 收费 1–3 美元的现实

- **事实**：按 15% 分成，每份到手 0.85–2.55 美元。光是 Apple 年费 99 美元，就要每年卖出 39 份（定价 3 美元）到 117 份（定价 1 美元）才持平。同类收费品的价格和销量：Chess PGN Master Pro Key 7.99 美元，Play 上 1 万+ 下载；Chess Studio 3.99 美元，117 条评分；SUPERB CHESS BOARD 2.99 美元，评分不足。中国象棋用户主要在国内，Google Play 在国内用不了，国内商店又要企业主体和软著。
- **判断**：①直接竞品免费，而且背后有 lichess、皮卡鱼生态这样的大号，付费意愿很低；②中国象棋的主要用户进不了收费渠道（国内安卓要公司，iOS 中国区要备案）；③收费就有义务做客服和退款（App Store 的退款由苹果处理，但差评和兼容性投诉要自己接）。各种棋谱格式（XQF、CBL、GBK 编码等）的兼容性投诉会是主要的支持成本。收入大概率抵不上年费和时间。

### 5.4 依赖许可对上架和收费的影响

| 依赖 | 许可（仓库 `viewer/vendor/` 里的原文） | 对免费或收费分发的影响 |
|---|---|---|
| cm-chessboard | MIT | 可以，随包附上版权声明 |
| chess.js | BSD-2-Clause | 可以，附上声明 |
| cburnett 棋子 | Wikimedia 上作者给了 GFDL / CC BY-SA 3.0 / BSD / GPL 任选，本仓库选的是 **BSD-3**（`vendor/cburnett-pieces/LICENSE`、`SOURCE.md` 已逐页核过） | 可以；第 3 条不许用作者名义背书推广 |
| 走子音效 | CC0 1.0（`vendor/sounds/SOURCE.md`） | 可以，不用署名 |
| 楷体（`app.css` 里写的是 Kaiti SC、STKaiti、KaiTi 等**系统字体**） | 系统字体，许可不允许随 App 分发 | 网页版不打包时，安卓、Linux 没有楷体会退回别的字体；做 App 或 PWA 要打包开源楷体，比如[霞鹜文楷](https://github.com/lxgw/LxgwWenKai)（OFL-1.1，允许随软件分发、随软件一起卖，不许单独卖字体；只截取用得到的几十个字就很小） |
| 中国象棋规则和棋盘 | 本仓库自己写的（`viewer/lib/xiangqi.js`、`xqboard.js`） | 没有第三方许可问题 |
| playwright-core | 只在开发和录屏时用 | 不进出货包，不受影响 |

结论（判断）：许可不挡路，免费、收费都行；要做的只是换掉楷体、整理一份第三方声明。

---

## 6. 建议

**事实依据**：§1 总表显示两种棋在各平台都已有免费、直装的选项；§3.1 实测显示主流工具对「带命令的长评注」处理不好；§5 显示收费上架的固定成本和国内门槛都不低。

**判断与建议**
1. **不做收费 App，也不急着做原生 App。** 通用打谱器市场已经被免费工具占满，1–3 美元的定价撑不起 Apple 年费，中国象棋的主要用户又进不了收费渠道。
2. **如果要往外发，先做免费的静态网页（PWA）**，用 2–5 天把阅读器整理成「看大模型对局」的公开页面：手机版式里显示每步理由；加打开文件的按钮；打包开源楷体；附第三方声明。它的价值在于和视频配套（视频简介里放链接，观众点进去逐步看模型的理由），不在于跟 lichess、xiangqiai 抢通用用户。前提是要有一个公开托管的地方，仓库现在只在本地，这件事要用户拍板。
3. **兼容别人的工具比自己做 App 更省事**：导出时可以额外出一份「纯文字评注」版的 PGN（把 `[%…]` 转成文字），这样用户用 lichess App 或 xiangqiai 也能正常看。这一步只要几十行转换，覆盖面比自己上架大得多。
4. 桌面或手机套壳等网页版有人用了再说。真要做，先上免费的 Microsoft Store（零注册费），iOS 和国内安卓放最后。

---

## 7. 没核实或有局限的地方

- lichess App、ChessView、Chessis 显示评注的实际体验，没有在真机上测。
- 象棋公社能不能导入本地棋谱文件，没核实；棋路的会员价是第三方转述。
- pgn.chessbase.com 的页面正文没抓到，功能出自转述。
- chess.com 分析页怎么处理自定义命令，本次和上次都没测（它的条款禁止自动化访问）。
- 下载站上的版本号和日期（象棋桥、象棋巫师、XQStudio）不一定是原始发布日期。
- iTunes 接口不返回内购信息，内购情况来自抓取的 App Store 页面，只查了表里列出的几款。
- 工作量都是粗估，没有拆任务。
