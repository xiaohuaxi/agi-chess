# 当前状态

更新：2026-11-23。这里维护当前快照与待办，不追加流水账；实验总览表、历次维护和决定沿革见 [历史记录](docs/history.md)，报告与 `runs/` 映射见 [研究索引](docs/research.md)。

## 已完成与可用

- 两种棋的单盘对弈、暂停续跑、批量对弈、局面题、事后引擎分析与离线评级复算均已实现；入口见 [安装与运行](docs/setup.md)。整盘调用层已收归仓内，支持 Claude / Codex / DeepSeek / agy 与显式 OpenRouter 路由；新 Gemini 对局统一 `agy:`，旧记录可续跑。开盘前检查双方 CLI / Key，缺 CLI 给出需替换型号占位的 API 命令模板；dry-run 离线，resume 固定原后端。 对弈入口指引已澄清：通常优先仓库 CLI，通道验证或故障排查可按需直接调用底层；暂不新增对弈 skill。 独立 clone 冷读上手验收已完成：自行建立依赖环境，零成本入口及订阅、OpenRouter 短对弈的暂停/续跑/导出均可用；测试数据仅留临时副本，不入库。`quiz report` 会回写 `report.txt`，入门文档未明确提醒此副作用（其中“只读”原句指评级脚本，并非 quiz report）；本机缺 `ensurepip` 可用已有 pip 向独立环境安装依赖。
- 中英双语棋谱阅读器支持理由、用量、逐着引擎评分与最佳着、失误标记、连播、走子动画及有声视频，[GitHub Pages 在线站点](https://xiaohuaxi.github.io/agi-chess/)已补齐三页同级架构——精选阅读器首页、[分棋种无引擎对阵总览榜（`series.html`）](https://xiaohuaxi.github.io/agi-chess/series.html)与[全部 192 盘可筛选目录（`catalog.html`）](https://xiaohuaxi.github.io/agi-chess/catalog.html)（含三页统一对外模型/引擎显示名与录屏短名隔离、手机端紧贴棋盘翻步栏与 8 行着法滚动框、`/catalog/` 与 `/series/` 尾斜杠静态重定向、404 三页入口、手动翻步 `ply` 深链接分享及 GitHub Actions Playwright CI/CD 自动部署）；见 [阅读器指南](docs/viewer-guide.md)。随仓有 95 个正式对局/局面题目录、192 份棋谱；原始 `game.jsonl`、`record.txt`、视频和新跑目录不入库，缺原始记录时不能重导或重新分析。
- 第一轮研究、Opus Max 棋力定位、Argon High 及 Carbon High 对 agy Opus High 的报告均已完成。统计脚本和人类刻度数据在 `analysis/rating/`；自有内容许可与规则依赖边界已定，见 [依赖](docs/dependencies.md)和[许可说明](docs/license-review.md)。
- 离线与通道验证快照（2026-11-23）：`--protocol real` 新对局默认切换为英文提示词 `--lang en`（`--lang zh` 逐字节保留历史中文提示，旧记录无 `lang` 自动按中文续跑），并将英文默认 `reason=plain` 定为 1–3 句客观第三人称局面短评、`reason=off` 收紧为无附加说明的单行 `Move:`；仓内 `llm-chat`（`agy_core.REFUSAL_MARKS`）与 `agi_chess/claude_cli.refusal_text` 同步补齐 `blocked by content safety filters` 首次即停熔断。全量 Python 单测 **373 项通过（0 skip）**、阅读器测试 **110 项通过（0 skip，含 S1–S8 真实用户场景专项端到端测试）**、两批题库校验全部通过，并在 `agy:claude-opus-5-5`（`high`）上完成 147 次真实调用验证（[报告](docs/results/english-prompts-filter-mitigation-20261115.md)）。此前 `agy 1.5.8 acp` 零工具收口、Python 3.13 干净归档副本与 Linux / WSL2 完整回归均已通过；安装建议沿用 Python 3.13（系统 `/usr/bin/python3` 3.9 亦可运行）。

## 核心研究结论

- 现有证据主要指向算得不够深和判断错误，思考延续与提示技巧不是主要解法；提高思考深度收益最大。局部漏吃也存在注意力问题，不能概括为所有错误都“看见了”。见 [第一轮总结](docs/results/summary-round1.md)与[漏吃诊断](docs/results/missed-captures.md)。小样本只看方向。
- Opus–Astra 的 real 协议、带理由对局共 34 盘，按棋种、effort 和思考延续条件分组；完整比分、先后手与指标保留在[历史总览](docs/history.md)。其中 Max 对 Max 各棋种 4 盘，Opus 国际象棋 3:1、中国象棋 4:0；详见[报告](docs/results/game-opus-max-vs-astra-max-1.md)，不混算不同条件。
- Opus Max 对引擎定位已定稿：国际象棋 30 盘，新上限裁决事后回看约 lichess Blitz 1800 / Rapid 1920；中国象棋 37 盘，在 Fairy-Stockfish 阶梯约 +121（nodes=100 为 0），不换算人类段位。锚点、区间及旧规则差异见[定位报告](docs/results/opus-max-rating.md)；旧“Maia-1900 就是 lichess 1900”的推算已作废。
- Argon High 对 agy Opus High 四盘 3:1，但开局重复、样本小，不能按比分上调评级。Blitz 1700 / Rapid 1800 只是主观中心，1600 类比不是下限；与 Opus Max 尚无直接对阵，约 100 分差也未验证。见[对阵报告](docs/results/argon-vs-agy-opus-high-20261020.md)、[暂定定位](docs/results/argon-high-chess-rating-20261019.md)和[token 对照](docs/results/thinking-tokens-argon-opus-20261025.md)。
- Carbon High 对 agy Opus High 两种棋各四盘对称先后手全部规则将死：国际象棋 **4:0**（加权 ACPL 18.1 / 35.4，Lichess 大失误 2 / 7；剔除含 1 次 `agy` 内部过滤重试的补第 2 局仍为 3:0、ACPL 17.7 / 35.0），中国象棋 **3:1**（执红 2:0、执黑 1:1，加权 ACPL 50.1 / 56.0，大失误 11 / 14、合并件数 8 / 9；剔除含 12 次过滤重试的第 2 局为 2:1、ACPL 51.7 / 55.1，零重试的第 1、3 局为 2:0、ACPL 51.2 / 67.7）。国象失误密度明显低于十月 Argon 四盘，中象在仅给子力清单下差距收窄且双方仍出现送车入象口与连续 8 半回合互盲炮架抽车；小样本只看方向，不拟合 Elo 分差或外推旧 Opus Max 锚点。每步思考 token 上，国象 Carbon High（均值 2,724.4 / 中位 1,489）与同日探索自弈的 Hydrogen High（正常步均值 1,327.1 / 中位 911）落在旧 CLI Opus `xhigh` 量级，中象 Carbon High（均值 7,326.5 / 中位 5,582）升至国象约 2.7–3.8 倍、落在旧 CLI Opus `xhigh` 与 `max` 之间，且经历 4 次上下文自动压缩均平稳续下无死循环。见[国际象棋四盘报告](docs/results/carbon-vs-agy-opus-high-20261114.md)与[中国象棋四盘报告](docs/results/carbon-vs-agy-opus-high-xq-20261114.md)。
- 英文默认提示词与 Opus 防思维链误拦实测已完成（共 147 次 `agy:claude-opus-5-5` `high` 调用，其中最终落定的 `--lang en` 提示词占 117 次）：日志溯源确认 11-14 的 14 次安全过滤中，`agy` 内联警告因旧熔断词未覆盖而留存会话引发雪崩（中象第 2 局第 78 半回合后连触 12 次），同时原中文 `plain` 下 Opus 有 35%–53% 回合输出第一人称逐格验算与半句自我更正独白（工作假设为类思维链语体更易触发输出侧反套取分类器）。第一阶段受控对照（4 组 × 10 题 = 40 次，均 0 过滤）证实直译原中文 `plain` 仍有 100% 第一人称独白与 90% 排除列表，而首句锚定 1–3 句客观第三人称短评将第一人称独白与自我更正降至 **0%**（10 题样本 CPL 127.1）；第二阶段在落定 `--lang en` 提示词下跑 4 盘连续 `session` 实盘（共 107 次调用，含 `plain` 105 次、`off` 2 次，最长 80 半回合），全程 **0 次过滤/拒答、0% 自我更正、0% 列表枚举**，两盘中象合计 69 步零大失误（ACPL 26.0 / 55.0）。后续直连 `claude -p` 跑 `xhigh` / `max` 仍须小步扩并发并保持首次即停熔断，见[防误拦实测报告](docs/results/english-prompts-filter-mitigation-20261115.md)。
- `gemini-4-neon`（`xhigh`）、`gemini-4-carbon`（`high`）与 `gpt-6.2-astra`（`xhigh` / `max`）国际象棋对称评测、计费折算与隐式缓存溯源已完成（共 13 盘全部规则将死完赛）：本机 `agy 1.5.12` 与 `codex-cli 0.167.2` 零工具桩抓包核验通过，全部 26 段棋手会话底层审计 **0 工具调用/尝试、0 安全过滤/拒答、0 上下文压缩**，`Neon` 481 次调用仅 2 次（0.4%）多步自续写、无循环异常。三组对称四盘呈自洽梯队：**`Neon xhigh` 对 `Carbon high` `4:0`**（执白 2/2、执黑 2/2，加权 ACPL 35.1 / 46.4，Lichess 大失误 8 / 13）、**`Neon xhigh` 对 `Astra 6.2 max` `2:2`**（各取执白 2 胜，加权 ACPL 40.8 / 41.0，大失误 9 / 9）、**`Carbon high` 对 `Astra 6.2 max` `1:3`**（加权 ACPL 45.1 / 35.8，大失误 14 / 8；另首轮对 `Astra 6.2 xhigh` 单盘白胜，ACPL 22.5 / 47.1）。每步思考 token 上，`Neon xhigh`（均值 4,054.8 / 中位 1,996.0）与 `Carbon high`（均值 3,764.2 / 中位 2,011.0）同级，`Astra 6.2` 维持精炼推理刻度（`xhigh` 均值 222.3、`max` 均值 800.4）。已沉淀官方 API 与 Antigravity 同池五模型折算单价表（`Neon` 订阅抵扣 `$1/$0.05/$5` 为 API `$3/$0.15/$15` 的 1/3、同池 `Carbon` `$2/$0.10/$10` 的 2 倍可用量；全批 13 盘 API 折算合计 `$177.56`，Gemini 订阅池合计抵扣 `$71.92`），并通过跨轮跳格命中数学实锤 `Neon` 缓存命中偏低（按 token 59.45% vs `Carbon` 92.64%）系上线初期服务端多副本无会话粘性路由且无跨实例持久缓存所致，见[对称评测与缓存溯源报告](docs/results/neon-carbon-astra-chess-20261119.md)。

## 当前工作与未决定方向

- [仓库](https://github.com/xiaohuaxi/agi-chess)已公开，上手检查和文档整理已完成；尚未选定下一轮研究，也可就此收工。以下仅是候选，不是已批准的实验计划。
- 优先候选：修正看杀判分口径后离线重判已有数据；其次是 xhigh 对更强对手补测上限，或 Max 对更强对手补盘。国际象棋重测上限须重新决定范围；Max 重开先定额度上限，一次只开 2–4 盘，长评测按 5 小时窗口均匀使用、给日常工作留余量。
- 中国象棋暂不补人类段位、不引入 Pikafish；不另做“列候选着法”或“程序告知吃子关系”实验。此前 Sol 不再测、GPT 棋手选择 Astra、DeepSeek 不再充值或做实验而只作辅助参考的决定保留，未完成的 DeepSeek 补测不列为续跑任务。
- 对阵统计与跨模型统一等级分后续候选：跨批次、跨提示语言与不同思考预算的统计合并边界已复审定界（在线 `series.html` 按棋种与可比实验条件分列展示，不跨断裂对阵图硬合单一 Elo）；后续若需拟合跨模型统一等级分，须在统一英文协议与多样化固定开局下补齐强连通番棋与多模型引擎锚点（或届时再与外部 `chess_series_board.py` 脚本交叉比对）。

## 有效约定与研究限制

- 现行硬约束见 [AGENTS.md](AGENTS.md)，协议、默认呈现与调用恢复见 [设计](docs/design.md)第三、九节：真实棋手协议、默认英文提示 `--lang en`（`--lang zh` 保留历史中文提示）、标准初始局面、连续会话、单盘默认 medium / 批次默认 xhigh 与理由 plain（英文下为客观第三人称局面短评）；模型互弈双方思考延续一致，`drop_thinking` 默认关。棋力定位的随机开局按专门方案，不外推为普通互弈默认。旧记录沿用存下的提示，安全停止规则始终用现行要求。
- 工具调用或尝试即暂停，防思维链泄露类拒答一次即终止，不重问、不改措辞绕过、不判棋手输；历史重问仅为事实。仓内 `llm-chat` 的 `agy acp` 路径通过新会话 `tools: []`、权限请求事前拒绝（无拒绝项则 `cancelled` 并杀进程组）与流事件事后审计收紧工具面；agy 调用失败时仅在结果携带完整非空答复且非 `cancelled`/`refusal` 时取回，传输类失败新盘默认每方每半回合最多自动重发 2 次（`--agy-retries`），其余不确定结果停下，`resume --retry-uncertain` 显式授权（见设计第一节 2026-11-11 与 2026-11-13 段）。新盘 llm-chat 会话记录在对局目录 `.llm-chat/`（不入库），单盘与批次续跑均从该目录预检和续接（旧盘在获批次锁与配置校验后再迁移）。`agy 1.5.8 acp` 对上游内容安全过滤内联重试注入的 `blocked by content safety filters` 现已纳入 `llm-chat` 与 `agi_chess` 首次即停熔断；而运行时无害内部工具（`manage_task` / `finish`）未逐条外报、空输出内联重试提示 `Model produced invalid output.` 仍属外部观测边界（事后须结合底层 transcript 核查），“未发现工具/拒答流事件”不自动等同底层零事件证明。
- Codex 升级后需重新核实棋手隔离；旧局面题零工具请求与旧整盘请求挂 4 个 code mode 工具但执行层关闭，是不同路径的历史证据，不可混用。局面题直调还会带全局规范作为固定噪声；整盘走 llm-chat 无这段，见[隔离报告](docs/results/llm-chat-isolation.md)。
- 中国象棋默认只给子力清单，国际象棋保留 FEN + 字母棋盘；只给棋盘会缺易位与吃过路兵信息。real 有引擎一方到上限按评分裁决，模型互弈仍判和；细节以设计为准。理由 brief / plain 不作变量、允许合并；大失误阈值在各棋种内部比较，跨棋种须先统一口径。
- 看杀题仅判走后是否被将杀，会漏计引擎评分大跌，真实损失被低估；“变好 ≥6 且变坏 ≤1”的门槛按每题 2 遍制定，扩为 6 遍后偏严，待重定。见[理由实验](docs/results/batch3-reason.md)及[跨模型呈现实验](docs/results/batch5-cross-model-presentation.md)。
- “复述局面”提示要求用棋盘同字，但中国象棋默认已无棋盘；该档默认关闭，若再跑须先改提示或用 `show=all`。
- 跨天续接是否丢思考（P8）未单独验证，等额度 3–17 小时后接上会话不等于思考完整；同名 high 和跨模型 token 数不代表相同预算，agy Opus 上报 thinking=0 不能解释为无思考，缺计不能补零。
- [历史走法解析审计](docs/move-parsing-audit.md)已覆盖此前 171 盘正式棋谱对应的原始记录（10,472 个接受模型步）及 2,684 份正式中国象棋局面题回答，未发现接受的明确着法被执行成另一手。确认旧 B1 国象 1 次合法着法被提取器误拒，重答后换手；该 bug 已于 `a363108` 修复，受影响旧基线不进入最终 `zc` Max 评级拟合，但不能断言反事实盘果不变。中象另发现 61 步理由/便条中的记谱配对不一致，最终坐标指令均忠实执行；这不是理由错误总数的穷尽统计。
- 文本协议存在取值边界未明确的问题：当前解析采用开头可识别的着法，不检查后附中文或坐标；如果把后附内容视为说明，这一行为本身不等于误落子，不能仅因没有核对括号就认定是 bug。另已复现多位数字截断、同一行或跨语言改口的解析缺口，未在本次历史正式接受步中触发。正式中象 2 次含 `x` 的格式拒绝重答后走同手，另 1 盘非正式局因繁体“著法”标签漏识别而重答换手；后续统一考虑结构化输出，本次不改规则或旧记录。
- pyffish 长捉为近似判定，边界未全测（P15）；中国象棋分析器最佳着未排除长将/长捉禁着。连续引擎判题受哈希历史影响，亏损可漂几到几十厘兵，曾有 2 条大失误标记翻转，门槛附近比较需考虑噪声。
- 旧 stateless 整盘约 7%–11% 非中文作答与错误的关系样本不足；首批 session 原始每步费用重复累计，分析器会做差重算，原始记录未修。DeepSeek 题目缺答与 Sol 清单档的混合表现只保留历史结果，不另开修复实验。
- Sol 局面题旧批次曾把 WebSockets 回退 HTTPS 的连接错误误判为工具调用而停批，`codex_cli` 只放过重连提示，原因待处理；因已停止 Sol 实验，保留限制，不追加运行。
- Opus 不带思考时两盘同处误走已移动的 a 兵，是否“忘了走过什么”证据不足；另有一次仅回复 `<reasoning_effort>40</reasoning_effort>`、未给着法的异常，原因未查。详见[不带思考实验](docs/results/game-opus-drop-vs-astra-1.md)与[中国象棋 Astra Max 对阵](docs/results/game-opus-vs-astra-max-xq-1.md)。

## 暂缓工程问题

以下五项暂缓处理，沿用研究仓库简单优先的决定；本次只更新记录，不改代码。

1. **批次锁的空文件窗口**（`agi_chess/batch.py:take_lock`）：独占创建 `.lock` 到写入 PID 之间为空，另一进程可能读成 pid=0、删锁重建而双持锁。暂缓：单人本地脚本极少同一瞬间启动同一批次的两个驱动，不为此引入跨平台文件锁或硬链接重构。
2. **JSONL 无换行残片续写丢记录**（`agi_chess/records.py:write/read`）：断电或 SIGKILL 留下无换行半行，下次追加会把新记录拼上残片，读取时整行跳过。暂缓：短记录单次写入，需恰逢中断且未经检查直接续跑才触发，保留极简实现，不引入截断修复或复杂审计状态机。
3. **批次元数据回退与非 Claude 呈现比对缺口**（`agi_chess/batch.py:batch_meta/check_meta`）：legacy / all 默认值省略键，show 仅为 Claude 记录，检查只遍历新键；未完批次从 real / pieces 改回默认可能绕过一致性校验。暂缓：正式实验固定参数跑完归档，少有中途混改，不改元数据归一化逻辑。
4. **嵌套归档目录误传及缺依赖的底层堆栈**（`agi_chess/cli.py`、`claude_cli.py`、`codex_cli.py`、`data/batch{1,2}/select_positions.py`）：顶层归档防覆盖已做，但误把输出指到单盘归档内部建子目录仍有缺口；未装规则库或旧局面题所需 CLI 时内部命令仍可能报原生 ModuleNotFoundError / FileNotFoundError；整盘模型 CLI 缺失已有开盘前检查。暂缓：安装前提已有文档，常用只读入口已脱离依赖，不增加跨层目录扫描或全局异常包装。

5. **棋手回复改为 JSON 结构化输出**：当前用文本标记提取着法，存在前缀、附注及改口的取值边界问题。后续将唯一着法字段与可见理由字段分开，以简化解析。暂缓：历史审计未发现正式对局中已接受的明确着法被执行成另一手，用户决定留待后续统一改进；具体 schema、通道支持与旧记录兼容在实施时确定。JSON 不保证消除服务商拒答或误判，详见[审计文档的后续改进](docs/move-parsing-audit.md#后续改进暂缓)。
