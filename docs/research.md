[English](research.en.md) | [简体中文](research.md)

# 研究索引

这里导航 `docs/results/` 的全部 33 篇报告，覆盖 2026-09-25 至 11-14 的实验、复盘和历史数据复算。它们研究的是特定模型、提示和会话条件下的表现，不能合成一个跨棋种、跨档位的总排行榜。

想看哪类证据：

- 思考深度与延续：[第一批深度](results/batch1-depth.md)、[延续对照](results/batch1-carryover.md)、[会话内思考量](results/thinking-in-session.md)、[Argon/Opus 思考量对照](results/thinking-tokens-argon-opus-20261025.md)。
- 送子和漏吃为什么发生：[局面题诊断](results/batch2-capture.md)、[实战失败点重问](results/missed-captures.md)。两者选题和提示不同，错因比例不能直接拼接。
- 局面如何呈现：[第四批](results/batch4-presentation.md) → [跨模型复测](results/batch5-cross-model-presentation.md) → [真实棋手协议复测](results/batch6-real-presentation.md)。
- 棋力刻度：[Opus Max 对引擎定位](results/opus-max-rating.md)；Argon 的[历史比较](results/argon-high-chess-rating-20261019.md)、[四盘交手](results/argon-vs-agy-opus-high-20261020.md)及 Carbon 的[国象四盘交手](results/carbon-vs-agy-opus-high-20261114.md)、[中象四盘交手](results/carbon-vs-agy-opus-high-xq-20261114.md)只支持方向与暂定判断。
- 历史阶段总结：[第一轮总结](results/summary-round1.md)以第一至三批为主体，补入第四批局面呈现结论，不是最新总论；其中旧 Maia 人类评级链已被后续报告更正。

## 怎么读条件与样本

以下均按报告当时的条件记录，不用当前默认值改写旧实验。`stateless` 是每步新会话；`session` 是连续会话；`notes` 只把便条带到下一步。`real` 是「模型就是真实棋手」协议，不报将军、威胁或合法着法；早期实验不等同于这个协议。整盘中的标准开局与程序代走的随机开局也应分开看。

型号只写仓内材料能确认的值。部分报告只记 `claude:opus`，本索引保留别名；其中旧 CLI 国际象棋 14 盘 Opus–Astra 和 30 盘评级的 `claude-opus-5-5`，由[后续历史核对](results/argon-high-chess-rating-20261019.md)确认，不据此补全其他批次的型号。`agy:claude-opus-5-5-high` 与旧 CLI 的同名模型、不同 effort，不视为相同计算预算。

“局面数”“作答数”“盘数”分别列出；同题重复、同盘的两方、重复开局都不是独立样本。不同棋种的大失误阈值和看杀口径也不统一，跨表先看原报告定义。旧报告中的拒答重问是历史处理；2026-10-15 起现行规则是拒答立即终止，见 [项目状态](../STATUS.md)。

## 第一至三批：深度、延续与提示（2026-09-25—09-27）

- [第一批 A：思考深度](results/batch1-depth.md)（09-26，两种棋）。`claude-opus-5-5`，Claude CLI，stateless；medium / high / xhigh / max。各 30 局面，每档每题 2 遍，即每棋种每档 60 作答，共 480 作答。较深档位在选定题上总体更好；不是整盘胜率或 Elo 测量，题库有按旧失败点选题的偏差。

- [第一批 B：思考延续](results/batch1-carryover.md)（09-25—26，两种棋）。`claude-opus-5-5`、high；stateless / notes / session；国际象棋对 Maia-1100 各 3 盘，中国象棋对 Fairy-Stockfish nodes=100 各 2 盘，共 15 盘、模型恒执先。另有 37 个计算会话、6 个选择会话的延续对照，共 213 次调用。确认短间隔续接能利用此前思考；整盘中延续不是消除昏招的充分条件，小样本与确定性开局限制比较。

- [第二批块 0：中文提示](results/batch2-0.md)（09-26，两种棋）。`claude-opus-5-5`、xhigh、stateless；每棋种 30 局面 × 3 遍，共 180 作答，与第一批各 60 作答对照。英文比例降至 3.3%；国际象棋解中率上升不能单归因于中文提示，跨天与 CLI 小版本也变了。

- [第二批 A：吃子关系与看杀](results/batch2-capture.md)（09-26，两种棋）。`claude-opus-5-5`、xhigh、stateless、中文；base / selfcheck / threats / legal。中国象棋 30 局面 × 3 遍，国际象棋 21 局面 × 2 遍，每档 90 / 42 作答，共 528。列威胁可减少狭义送子漏吃，未稳定降低总体大失误；合法着法档属于历史辅助条件，不能混同当前 real 协议。此批含后来剔除的 x2-25。

- [第二批 B1 / C：国际象棋棋力与延续](results/batch2-chess-strength.md)（09-26）。`claude-opus-5-5`、xhigh；B1 stateless 16 盘，对随机走子及 Maia-1500 / 1900；C session 对 Maia-1900 8 盘，同种子同执色配对；随机代走 8 半回合。Maia-1900 的 10 盘得分 70%，存在放和与小样本影响；延续的质量收益未达预设门槛。Maia 档名不是人类等级分。

- [第二批 B2：中国象棋棋力](results/batch2-xiangqi-strength.md)（原报告未单列日期，属第二批）。Opus（原文未写完整型号）、xhigh、stateless、中文；随机代走 6 半回合。对 Fairy-Stockfish nodes=30 / 100 各 8 盘，共 16 盘；另列 5 组引擎标定，每组 20 盘。只定位于极低节点阶梯，不换人类段位；深度、语言和开局同时改变，不能将开局送车减少归因于单一变量。

- [第三批 A：写理由](results/batch3-reason.md)（09-26—27，两种棋）。Opus（原文未写完整型号）、xhigh、stateless、中文；base / reason。中国象棋 29 局面 × 3 遍，国际象棋 21 局面 × 2 遍，每档 87 / 42 作答，共 258。写理由便于核对部分错因，未稳定改善着法；看杀只判走后是否被杀，可能低估其他评分损失。

- [第三批 B：Max 整盘，提前停止](results/batch3-maxdepth.md)（09-27，两种棋）。`claude-opus-5-5`、max、stateless；沿用第二批随机开局和对手。计划 16 盘，仅完成国际象棋 4 盘、中国象棋 2 盘，其余 10 盘作废。完成的 6 盘全胜，质量改善只能看方向，不能把未完盘当结果；额度代价很高。

- [第一轮总结](results/summary-round1.md)（09-27，汇总09-25—27，两种棋）。以第一至三批 Opus 的上述样本为主体，并补入第四批局面呈现结论（中国象棋主要对照各 174 作答、国际象棋各 126 作答），没有新增作答或对局。原报告开头的范围说明未同步这一补充。它记录当时“深度最有用、延续次要”的阶段判断；不是最新总论，不覆盖后来真实棋手协议、Astra、Argon 或 Max 评级，旧人类评级链看后续更正。

- [棋力与人群对照](results/rating-reference.md)（09-27，10-03更正；国际象棋，另列围棋与中国象棋资料）。公开资料调研，无新增模型对局；后续引用 Opus Max 30 盘评级。明确作废“Maia-1900 ≈ lichess 1900”链；历史人群分布、平台和盘速各自有边界，中国象棋没有可用的人类刻度。资料快照不代表当前在线分数。

## 第四至六批：呈现方式与接入核验（2026-09-27—09-28）

- [第四批：局面怎么给](results/batch4-presentation.md)（09-27，两种棋）。`claude-opus-5-5`、high、stateless、中文；all / board / pieces / fen，后补 boardpieces。题库为中国象棋 29、国际象棋 21 局面；首轮每档每题 2 遍，共 400 作答；补测部分档 4 遍，合并后中国象棋 all / board / pieces 各 174、boardpieces 116，国际象棋 all / board 各 126 作答，其余保留首轮。中国象棋 pieces 较稳；国际象棋 board 的首轮优势未稳定复现，单给棋盘还缺易位权等信息。

- [第五批：跨模型呈现复测](results/batch5-cross-model-presentation.md)（09-28，两种棋）。`claude-opus-5-5` / `gpt-6-sol` / `deepseek-v4-pro`，均 high、stateless、中文；29 / 21 局面。Opus 复用第四批，次数见该报告；Sol 中国象棋 3 档各 174、国际象棋 3 档各 42 作答；DeepSeek 中国象棋三档 54 / 56 / 57，国际象棋 all / board / fen 为 37 / 17 / 11。支持维持共用默认给法，但不足以作模型绝对排名；DeepSeek 缺题、Codex 多带全局规范、判分有小幅抖动。

- [第五批准备：工具隔离](results/batch5-isolation.md)（09-28，接入核验，无整盘棋）。`gpt-6-sol` 与 `deepseek-v4-pro`，Codex CLI 0.157.1、显式 high、stateless / notes；本机桩抓请求，并各真调 1 次诱导。该配置请求工具数为 0，用户级规范仍进入上下文；DeepSeek 正文曾写工具调用标记但未执行。只证明所测版本、路径与配置，不是以后接入的永久保证。

- [第六批：真实棋手协议给法复测](results/batch6-real-presentation.md)（09-28，两种棋）。Opus（原报告未写完整型号，Claude CLI）与 `gpt-6-sol`，high、stateless、real、不要理由；29 / 21 局面。Opus 中国象棋三档每题 3 遍、国际象棋两档每题 3 遍，共 387 作答；Sol 只做中国象棋三档，每题 2 遍，共 174。默认维持中国象棋 pieces、国际象棋 FEN＋棋盘；不是不报将军绝无影响的普遍证明。

- [llm-chat 三路隔离与思考延续](results/llm-chat-isolation.md)（09-28，接入核验）。Claude `opus`（报告仅记别名）/ `gpt-6-sol` / `deepseek-v4-pro`；Claude、GPT 为 medium，DeepSeek 为 high；共 17 次真调及本机桩核验，无完整对局。Claude / DeepSeek 零工具；GPT 请求残留 4 个工具、执行层禁用，程序另查工具事件。Claude / GPT 能带思考，DeepSeek 此路径只带历史正文。这里的历史诱导不是继续做真实模型探测的操作指南。

## 真实棋手整盘与失败点诊断（2026年9月下旬—10月初）

下列整盘使用标准初始局面、独立连续会话和 real 协议；Opus–Astra 给法为中国象棋子力清单、国际象棋 FEN＋字母棋盘，均走 llm-chat。除了首个 Opus–Sol 批次不写理由，其余写可见理由。样本间开局重复、双方质量一起波动，比分不能直接换算等级分。

- [Opus 对 Sol 首局](results/game-opus-vs-sol-1.md)（原报告未标日历日期，g1批；两种棋）。`claude-opus-5-5` 对 `gpt-6-sol`，双方 xhigh，Opus 恒执先；每棋种 1 盘，共 2 盘，未要求理由、每手最多 4 次非法。两盘均 Opus 将死；主要证明协议跑通，不能据此比较长期棋力。

- [会话里思考量为何少](results/thinking-in-session.md)（原报告未标日历日期，诊断上述g1国际象棋）。Opus / Sol（型号沿上述报告），xhigh；取 12 局面，每家 6 个；session / 新会话 / 旧路径 / 旧协议四条件，分别 2 / 2 / 1 / 2 遍，每家 43 次实际调用。思考量下降主要与连续会话及开局有关，没发现稳定质量下降；不是 token 数与棋力的换算公式。

- [Opus 对 Astra：国际象棋](results/game-opus-vs-astra-1.md)（09-29，三轮）。`claude:opus` 对 `gpt-6-astra`，双方 xhigh、带思考、简短理由；6 盘，Opus 2:4。初轮每手最多 4 次非法、后四盘 3 次。质量差小于比分印象，只能看方向；旧 CLI 的完整 Opus 型号见前述后续核对。

- [Opus 对 Astra：中国象棋](results/game-opus-vs-astra-xq-1.md)（原报告未标完整日期，g3 / g4批）。`claude:opus`（原报告未写服务端型号）对 `gpt-6-astra`，双方 xhigh、带思考、每手最多 3 次非法；4 盘，Opus 4:0。双方都反复漏看“炮隔炮打车”，不能只看比分就认定胜者没有同类缺陷。

- [Opus xhigh 对 Astra Max：国际象棋](results/game-opus-vs-astra-max-1.md)（原报告未标完整日期，g3 / g5批）。`claude:opus` xhigh 对 `gpt-6-astra` max，带思考、简短理由；4 盘，2:2。双方 ACPL 都比另一批低，不能将共同改善全部归于 Astra 调档；完整 Opus 型号由后续历史核对确认。

- [Opus xhigh 对 Astra Max：中国象棋](results/game-opus-vs-astra-max-xq-1.md)（原报告未标完整日期，g5批）。`claude:opus`（原报告未写服务端型号）xhigh 对 `gpt-6-astra` max，带思考；4 盘，2:2。相较双方 xhigh 有 Astra 改善方向，但同盘 Opus 也改善，4 盘不足以隔离调档效果。

- [能吃未吃 / 白送未被吃](results/missed-captures.md)（09-29—30，两种棋）。Opus（原报告未写完整型号）与 `gpt-6-astra`，从 g2—g5 的 17 盘中专挑 14 例失败点；截断会话分叉，每格 4—6 遍，重问主要为 xhigh，一格按实战 max。13/14 例可见理由未体现关键吃子，单独问吃子 26 次全列对；Opus 去掉旧思考在部分例子有改善。是失败点诊断，不能推到所有局面；可见理由也不等于隐藏思考。

- [Opus 去掉此前思考对 Astra](results/game-opus-drop-vs-astra-1.md)（09-30开跑，两种棋）。`claude:opus` 对 `gpt-6-astra`，双方 xhigh，只有 Opus drop_thinking 开、简短理由；各 4 盘，共 8 盘，Opus 比分为国际象棋 3:1、中国象棋 4:0。质量改善有方向、成本增加，但对手也一起改善，不能全归因于删思考；两家思考延续方式不同，研究批次不改变公平对局默认。

- [双方 Max 巅峰对决](results/game-opus-max-vs-astra-max-1.md)（09-30—10-01，两种棋）。`claude:opus` 对 `gpt-6-astra`，双方 max、带思考、plain 理由；各 4 盘，共 8 盘，Opus 为 3:1、4:0，无加赛。小样本只看方向；国际象棋两盘开局前 43 半回合相同，中国象棋一盘 Astra 会话曾自动压缩。国际象棋 Opus 完整型号由后续历史核对确认。

## 对引擎的评级（2026-10-01—10-04）

- [Opus Max 棋力定位](results/opus-max-rating.md)（10-01—03对局，10-04补新规回看；两种棋）。`claude-opus-5-5`、max、llm-chat、连续会话带思考、plain 理由、real；随机代走国际象棋 8 / 中国象棋 6 半回合。国际象棋对 Maia-1900 和 Stockfish 19 限强三档，共 30 盘；中国象棋对 Fairy-Stockfish 14.0.1 节点阶梯，共 37 盘，另有引擎互下标定。国际象棋旧到上限计和版约 lichess Blitz 1910 / Rapid 2020，新规事后回看约 1800 / 1920；这是两种口径的点估计，不是一个置信区间，且原盘没有按新提示重下。中国象棋只给引擎相对位置，不给人类段位。评级刻度可用入库CSV离线复算；全部对局的 `game.pgn`（含每步思考理由、耗时与 token 统计）及引擎复盘 `analysis.jsonl` 已随 `runs/` 入库。

## Argon、Carbon 与后续比较（2026-10-19—11-14）

- [Argon High 中国象棋自弈](results/argon-high-xiangqi-20261019.md)（10-19）。双方 `gemini:gemini-4-argon-high`、high、agy、独立连续会话、real、plain、子力清单；1 盘，158 半回合、黑胜。复现送车与漏吃，所有着法合法不代表攻防可靠；自弈一盘不能评级或排模型强弱。

- [Argon High 国际象棋自弈](results/argon-high-chess-20261019.md)（10-19）。双方 `gemini:gemini-4-argon-high`、high、agy、独立连续会话、real、plain、FEN＋棋盘；1 盘，85 半回合、白胜。开局和部分攻王有质量，仍有基础占格错误与自信的错误理由；一盘无法区分背谱与计算，也不能从 ACPL 换 Elo。

- [Argon High 与历史模型的暂定定位](results/argon-high-chess-rating-20261019.md)（10-19离线比较，国际象棋）。`gemini-4-argon-high` high，自弈 1 盘，对比旧 `claude-opus-5-5` 与 `gpt-6-astra` 的 14 盘及 Opus Max 评级 30 盘；原表合计 45 盘、60 个棋手侧记录。另补对 agy Opus High 1 盘，不混入原表；10-25及10-31补充保留四盘后的主观中心（Blitz约1700／Rapid约1800）与1600类比的边界，没有新增实验。Blitz 1600—2000 / Rapid 1750—2100 只是选对手的主观范围，不是实测评级、上下界或置信区间。

- [Argon 对 agy Opus High 单盘](results/argon-vs-agy-opus-high-20261019.md)（10-19，国际象棋）。`gemini:gemini-4-argon-high` 对 `agy:claude-opus-5-5-high`，双方 llm-chat→agy、Google额度、high、独立 session、real、plain、标准开局；1 盘，Argon 执白胜。支持有竞争力，不能将未经标定的 agy High 当作旧 CLI Max 评级锚；Opus 上报思考0不能解释成无内部思考。

- [Argon 对 agy Opus High 三盘与四盘合看](results/argon-vs-agy-opus-high-20261020.md)（10-20，连同10-19；国际象棋）。型号及条件同上，三局并发、六个独立会话；新 3 盘 Argon 2胜1负，累计 4 盘 3胜1负。开局高度重复、第三局有异常恢复及用量缺计；累计 ACPL 44.7 / 53.3，不能据比分拟合 Elo 差或认定稳定优势。

- [国际象棋每步思考 token 对照](results/thinking-tokens-argon-opus-20261025.md)（10-25离线复算，覆盖既有9—10月记录）。`gemini-4-argon-high` high、旧 `claude-opus-5-5` high / xhigh / max、`gpt-6-astra` xhigh / max，另单列 agy Opus High。使用自弈 1 盘、Argon对Opus 4 盘、旧交手 14 盘、评级 30 盘及旧High对Maia 3 盘；局面题另列30题、High / xhigh / Max各60作答，不新增实验。Argon完整三盘154步的用量更接近旧xhigh；Max两家token差不是算力或棋力倍数。缺计不填0，agy Opus的220次回复全报0不构成可靠思考量分布。

- [Carbon 对 agy Opus High 四盘与思考量对照](results/carbon-vs-agy-opus-high-20261114.md)（11-14，国际象棋）。`agy:gemini-4-carbon` 对 `agy:claude-opus-5-5`，双方 llm-chat→agy（`1.5.8 acp`）、Google订阅额度、high、独立连续 session、real、plain、标准开局；对称先后手 4 盘（首局单跑、后三局并发），Carbon **4:0** 全部将死，加权 ACPL 18.1 / 35.4，Lichess 大失误 2 / 7（剔除含 1 次 `agy` 内部过滤重试的补第 2 局仍为 3:0、ACPL 17.7 / 35.0）。另附同日 `agy:gemini-4-hydrogen` high 探索自弈（52 半回合）的思考量与通道行为对照：Carbon（221 步均值 2,724.4 / 中位 1,489）与 Hydrogen（正常单次步均值 1,327.1 / 中位 911）均落在旧 CLI Opus `xhigh` 会话量级区间；小样本不拟合 Elo 分差或传递旧 Opus Max 评级。

- [Carbon 对 agy Opus High 中国象棋四盘与思考量对照](results/carbon-vs-agy-opus-high-xq-20261114.md)（11-14，中国象棋）。型号与通道同上，四局并发、独立连续 session、real、plain、子力清单、标准开局；对称先后手 4 盘，Carbon **3:1**（红 2/2、黑 1/2）全部将死，加权 ACPL 50.1 / 56.0，大失误 11 / 14（合并件数 8 / 9；剔除含 12 次 `agy` 过滤重试的第 2 局为 2:1、ACPL 51.7 / 55.1，零重试的第 1、3 局为 2:0、ACPL 51.2 / 67.7）。仅给子力清单下 Carbon 每步思考均值 7,326.5、中位 5,582，升至同日国象约 2.7–3.8 倍并落在旧 CLI Opus `xhigh` 与 `max` 之间，经历 4 次上下文自动压缩均平稳续下无死循环；另记录 `agy 1.5.8 acp` 将内部重试的 `⚠ … blocked by content safety filters` 提示拼入普通文本流并以 `end_turn` 返回的观测现象。

## 仓库里有什么证据

| 入库材料 | 能做什么 | 缺什么 |
|---|---|---|
| [33篇结果报告](results/) | 阅读条件、汇总数字、关键案例及限制 | 正式批次的棋谱、引擎分析与判卷汇总已入库 `runs/`；早期临时目录或截断分叉实验的底层事件流不在库 |
| [正式对局与局面题判卷产物](../runs/) | 直接浏览全部 73 个正式模型对局目录——51 个模型互弈单盘目录 + 22 个模型对引擎目录（15 个单盘目录 `runs/<tag>/game.pgn` + 7 个多盘批次子目录 `runs/<batch>/<game>/game.pgn`，合计 179 盘）——的 `game.pgn`（含每步思考理由、耗时与 token 统计）、`analysis.jsonl` / `analysis-summary.json`（178 盘）、`summary.json` / `summary.md`，以及 9 个正式局面题批次（`quiz-*`，共 50 份 `judged.jsonl`）的判卷结果 `judged.jsonl` 与 `report.txt` | 不含体积庞大的底层过程事件流 `game.jsonl`、重复的 `record.txt`、纯引擎互弈标定原始对局（结果已在 `games-engines.csv`）及 `.mp4` 录屏 |
| [第一批题库](../data/batch1/)与[第二批题库](../data/batch2/) | 查看选定局面与选题脚本；配合 `runs/quiz-*/judged.jsonl` 核对 9 个正式局面题批次的逐题判卷记录 | 早期未归入 `quiz-*` 正式目录的临时作答不在库；后续报告按各批剔除条件使用题库 |
| [评级战绩与脚本](../analysis/rating/) | 从 `games-engines.csv`、`games-opus.csv`、`human-scale.json` 离线复算评级刻度（`rate.py report`），或直接查看已入库的批次汇总 `runs/zc/summary.md`、`runs/zx/summary.md` | `rate.py export` 重导 CSV 所需的纯引擎标定原始目录不在库（导出后的 CSV 已入库）；`stats.py` 统计每盘花费与墙钟需读取未入库的本机 `game.jsonl` |
| [阅读器 fixtures](../viewer/test/fixtures/) | 测试、演示解析和显示 | 仅供测试演示；查看真实实验对局请直接打开单盘目录 `runs/<tag>/game.pgn` 或多盘批次子目录 `runs/<batch>/<game>/game.pgn` |

评级复算在仓库根运行 `python3 analysis/rating/rate.py report --boot 10`（1.5 秒快检；去掉 `--boot 10` 跑完整 1,000 次自助法抽样约 1.5 分钟），不调用模型或引擎；9 批局面题判卷汇总表可运行 `python3 -m agi_chess.quiz report --batch batch2`（可换 `batch1`、`batch2`、`batch3`、`4p`、`4p2`、`5-ds`、`5-sol`、`6r`、`6r-sol`，0.1 秒出表）。`runs/` 现已随仓入库全部 179 盘正式模型对局的 `game.pgn`、引擎逐着复盘 `analysis.jsonl` 以及 9 批正式局面题判卷结果 `judged.jsonl`；仅体积庞大的底层事件流 `game.jsonl`、纯引擎互弈标定原始目录及录屏 `.mp4` 视频保持被 Git 忽略。

### `runs/` 目录前缀与实验批次速查表

| `runs/` 目录（或前缀） | 类型与规模 | 棋种与对阵 / 实验条件 | 对应报告 |
| --- | --- | --- | --- |
| `g1-c-opus-sol`、`g1-x-opus-sol` | 单盘目录 × 2（2 盘） | 国象 / 中象：Opus `xhigh` vs Sol `xhigh`（`real` 协议首跑，未写理由） | [Opus 对 Sol 首局](results/game-opus-vs-sol-1.md) |
| `g2-c-*` | 单盘目录 × 6（6 盘） | 国象：Opus `xhigh` vs Astra `xhigh`（双方带思考、写理由，2:4） | [Opus 对 Astra：国际象棋](results/game-opus-vs-astra-1.md) |
| `g3-x-*`、`g4-x-*` | 单盘目录 × 4（4 盘） | 中象：Opus `xhigh` vs Astra `xhigh`（双方带思考、写理由，4:0） | [Opus 对 Astra：中国象棋](results/game-opus-vs-astra-xq-1.md) |
| `g3-c-max-*`、`g5-c-max-*` | 单盘目录 × 4（4 盘） | 国象：Opus `xhigh` vs Astra `max`（2:2） | [Opus xhigh 对 Astra Max：国际象棋](results/game-opus-vs-astra-max-1.md) |
| `g5-x-max-*` | 单盘目录 × 4（4 盘） | 中象：Opus `xhigh` vs Astra `max`（2:2） | [Opus xhigh 对 Astra Max：中国象棋](results/game-opus-vs-astra-max-xq-1.md) |
| `g6-c-*`、`g6-x-*` | 单盘目录 × 8（8 盘） | 国象 / 中象：Opus `xhigh`（`drop_thinking=on`）vs Astra `xhigh`（国象 3:1、中象 4:0） | [Opus 去掉此前思考对 Astra](results/game-opus-drop-vs-astra-1.md) |
| `g7-c-*`、`g7-x-*` | 单盘目录 × 8（8 盘） | **巅峰对决**：国象 / 中象 Opus `max` vs Astra `max`（国象 3:1、中象 4:0） | [双方 Max 巅峰对决](results/game-opus-max-vs-astra-max-1.md) |
| `argon-high-*`、`argon-vs-agy-opus-high-*`、`gemini38-*` | 单盘目录 × 7（7 盘） | Gemini Argon High 自弈（中象/国象各 1 盘）、Argon High vs agy Opus High 国象 4 盘（3:1）、Gemini 3.8 Flash High 中象自弈 | [Argon 中象自弈](results/argon-high-xiangqi-20261019.md)、[国象自弈](results/argon-high-chess-20261019.md)、[对 agy Opus 四盘](results/argon-vs-agy-opus-high-20261020.md) |
| `carbon-vs-agy-opus-high-*` | 单盘目录 × 8（8 盘） | Gemini Carbon High vs agy Opus High 国象 4 盘（4:0）、中象 4 盘（3:1） | [国象四盘](results/carbon-vs-agy-opus-high-20261114.md)、[中象四盘](results/carbon-vs-agy-opus-high-xq-20261114.md) |
| `b1-ch-*`、`b1-xq-*` | 单盘目录 × 15（15 盘） | 第一批 B：Opus `high`（`stateless`/`notes`/`session`）对 Maia-1100（9 盘）与 FSF `nodes=100`（6 盘） | [第一批 B：思考延续](results/batch1-carryover.md) |
| `b1`、`b1-session`、`b2` | 多盘批次目录 × 3（40 盘） | 第二批 B1/C 国象（24 盘，对 random / Maia-1500 / Maia-1900）与 B2 中象（16 盘，对 FSF `nodes=30,100`） | [第二批 B1/C 国象](results/batch2-chess-strength.md)、[第二批 B2 中象](results/batch2-xiangqi-strength.md) |
| `b3max-ch`、`b3max-xq` | 多盘批次目录 × 2（6 盘） | 第三批 B：Opus `max`（`stateless`）对引擎（国象 4 盘、中象 2 盘全胜） | [第三批 B：Max 整盘](results/batch3-maxdepth.md) |
| `zc`（30 盘）、`zx`（37 盘） | 多盘批次目录 × 2（67 盘） | **Opus Max 棋力定位**：国象对 Maia-1900 / Stockfish 限强三档；中象对 FSF `nodes=30..1000` 阶梯 | [Opus Max 棋力定位](results/opus-max-rating.md) |
| `quiz-{batch1,batch2,batch3,4p,4p2,5-ds,5-sol,6r,6r-sol}` | 局面题目录 × 9（50 份 `judged.jsonl`） | 第一至六批局面题判卷结果与汇总表（含 `report.txt`，可用 `python3 -m agi_chess.quiz report --batch <名>` 重算） | [第一批 A](results/batch1-depth.md)、[第二批 A](results/batch2-capture.md)、[第三批 A](results/batch3-reason.md)、[第四至六批](results/batch4-presentation.md) |

使用程序见[安装与运行](setup.md)，看棋谱和出视频见[阅读器指南](viewer-guide.md)；当前工作状态与后续待办见[项目状态](../STATUS.md)。实验与维护沿革见[历史记录](history.md)。本索引只导航已有材料，没有追加模型调用、引擎分析或棋力重估。

阅读器技术与历史需求调研见[调研索引](viewer-survey/README.md)；[历史本机录屏经验](viewer-survey/post-studio-recording.md)保留实现取舍，私人原片和外部工具不随仓库提供。内部发帖交接材料已移出工作树，不作为研究或现行操作规范。
