# 棋谱阅读器：调研过的项目

> 2026-09-29 调研。详细证据在同目录各报告里。这里只记「看过什么、为什么不用」，免得以后再翻一遍。
> 调研时浅克隆到 `~/repos/` 的仓库，没用上的已删；留下的标「保留」。

## 国际象棋

| 项目 | 许可 | 结论 | 不用的原因 |
|---|---|---|---|
| lichess 分析板 / Study / GIF 接口 | 网站 | 不用 | 自动播放只有 1s、5s 两档，没网址参数；导入丢评注，Study 删 `[%…]`；要公开上传 |
| chess.com | 网站 | 不用 | 用户协议禁止自动化访问 |
| chess.video、chessframe、chess.rodeo、plychess | 网站 | 不用 | 只做单盘出片，不显示自定义元信息，反机器人或禁批量 |
| pgn4web | GPL-2.0+ | 不用 | 最接近（连播、间隔、网址参数、每步回调都有），但缺将军高亮、标题画面、播完信号，代码老旧，强 copyleft |
| lichess-org/pgn-viewer | GPL-3.0+ | 不用 | 回放界面最好，但没有自动播放、只读第一盘，强 copyleft |
| mliebelt/pgn-viewer | GPL-3.0+ | 不用 | 功能开发已停，没有开播 API 和播完信号 |
| chessground / chessops | GPL-3.0+ | 不用 | 强 copyleft；chessops 只认标准评注命令 |
| cm-chessboard | MIT | **保留**，候选棋盘 | — |
| @mliebelt/pgn-parser | Apache-2.0 | **保留**，候选 PGN 解析 | 实测能把 `[%think 34]` 解析成键值 |
| chess.js | BSD-2-Clause | **保留**，候选规则库 | 只读单盘，多盘要先切 |
| cm-pgn | MIT | 不用 | 依赖的 chess.mjs 许可两处写法对不上；评注只给原始字符串 |
| chessboard.js、chessboard2、chessboardjsx、react-chessboard | MIT / ISC | 不用 | 前三个已停维护；react-chessboard 要 React |
| lila-gif | AGPL-3.0+ | 不用 | 出 gif，宽度固定 720，无标题画面、多盘、终局原因 |
| gifpgn、c2g | GPL-3.0+ | 不用 | 出 gif，同上；c2g 会把 `%emt` 当时钟画 |
| pgn-to-gif、chess_gif、pgn2gif、chess-animator、pgn-to-video-converter | MIT 等 | 不用 | 功能太薄，多已停更 |
| python-chess | GPL-3.0+ | 本项目已在用（pip 包），克隆删了 | — |

## 中国象棋

| 项目 | 许可 | 结论 | 不用的原因 |
|---|---|---|---|
| 东萍 DhtmlXQ | 无许可声明 | 不用 | 最接近的网站（中文记谱、评注、间隔可调），但不能连播、无网址参数、位图棋盘、许可不明 |
| pychess.org / pychess-variants | AGPL-3.0 | 不用 | 无自动播放、无中文记谱、要登录上传；前后端绑死 |
| xqbase.com | 网站 | 不用 | 不能导入自己的棋谱；它的「中国象棋 PGN 规范」可作为格式参照 |
| ChessDB、elephantchess、xiangqi.com、mistboard | 网站 | 不用 | 分析 / 查询工具，没有棋谱自动回放 |
| vschess | LGPL-3.0（另附 GPL-3.0 原文，待确认） | **保留**，只作参考 | 不能连播，将军只有音效，位图棋盘录竖屏发虚；读 PGN 会删评注内容。中文记谱解析可参考 |
| xiangqi-setup | 代码 AGPL-3.0+，素材多为 CC0 | **保留**，取 CC0 棋盘棋子素材 | 代码不用 |
| chessgroundx | GPL-3.0 | 不用 | 只是棋盘组件，省不了多少，强 copyleft |
| ffish.js | GPL-3.0 | 不用 | 无中文记谱，读 PGN 丢评注 |
| xiangqi.js | BSD-2-Clause | 不用 | 无中文记谱，读 PGN 删评注 |
| xiangqiboard.js | MIT，素材许可不明 | 不用 | 2020 停更，jQuery |
| python-chinese-chess | GPL-3.0 | 不用 | 只出棋盘 gif |
| XQWLight | GPL-2.0+ | 不用 | 人机对弈小程序，不是播放器 |
| jshou/xiangqi_viewer | MIT | 不用 | 玩具级 |

## 录屏方式

见[录制技术调研](recording.md)及[历史本机录屏经验](post-studio-recording.md)：Playwright 自带录像（recordVideo）只到 CSS 像素、VP8 25fps 低码率、按实时录；timesnap / timecut 2022 年后没发布；puppeteer-screen-recorder 底层同样是实时截屏。

## 要不要做成对外的 app（2026-10-02，不立项）

研究问题是各平台是否缺免费易得的看谱软件，以及免费或1–3美元的app是否值得开发。三轮调研：`app-market-1.md`（各平台 × 棋种现有选项）、`app-market-2.md`（iOS 为主的数量、价格、销量代理、评论）、`app-market-3.md`（免费 app 的用量与回报）。结论：两种棋各平台基本都有免费、能直接打开棋谱文件的选项；纯看谱需求本身小且多年不涨，收费的卖不动，免费的也拿不到量。最终**不立项**。阅读器用于本项目的对局展示与视频制作。
