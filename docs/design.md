# llm-chess 设计：模型对模型下棋

- 日期：2026-09-25。本机 Claude Code 2.1.282，服务端模型串 `claude-opus-5-5`；Codex CLI 0.156.1。
- 目的：研究通用大模型下棋为什么臭、基础设施怎么搭才对。对局流程外壳两种棋共用一份，棋种相关的部分各写一个平铺的模块（不写基类、不做继承层），无界面，命令行跑、全程落盘。
- 背景：既有工作调研 `~/repos/ai-research/topics/llm-board-games-survey.md`、上一轮中国象棋实测 `~/repos/ai-research/topics/llm-xiangqi-play.md`（读盘 67/67 全对，但每 6 步丢一个马炮级子力，错全在"谁能吃到谁"）。上一轮脚本是 jev-study 本地分支 `archive/duel-web` 上的 `games/xiangqi/llm_duel.py`（`11d0bf0`）和同分支的 `play_xiangqi.py`（`ending`、`banned`、`notation`、`rule_end`），规则底座是 jev-study 主干的 `games/xiangqi/boards.py`；本仓库从它们搬代码、不从 jev-study 导入。
- 结构选型（全抽象 / 完全分开 / 折中）的评估见 2026-09-25 的方案评估，采纳折中：一份流程外壳加两个棋种模块。

## 一、前提清单

核实用的小实验一共调了约 50 次 `claude -p`，按标价折算 $0.39。命令和原始输出在当次会话的草稿目录，没入库；关键输出摘在下面。

| # | 前提 | 状态 | 证据 |
|---|---|---|---|
| P1 | `claude -p --effort` 支持 medium / high / xhigh / max，并且真的发出去了 | **已核实** | `claude --help`：`--effort <level> ... (low, medium, high, xhigh, max)`。本机起一个桩服务（`ANTHROPIC_BASE_URL` 指过去，只记录请求体、回 400），四档各发一次，请求体里分别是 `output_config: {"effort": "medium"/"high"/"xhigh"/"max"}`，`thinking: {"type": "adaptive", "display": "omitted"}`，`max_tokens: 128000`，`tools: []`。 |
| P2 | 服务端按档位真的多想 | **已核实（小样本）** | 同一个国际象棋中局（无清单，只给 FEN、字符棋盘、着法记录），每档 2 次，思考 token：medium 151/121，high 191/231，xhigh 602/308，max 2225/1111；单次用时 6–26 秒。档位是有效的，而且 max 比 medium 多一个数量级；但在平静局面里绝对量都不大。上一轮 medium→high 只多 14% 的结论是在中国象棋、带自查提示的条件下，两者不矛盾。 |
| P3 | 能拿到每步的输入、输出、思考 token | **已核实** | `--output-format json` 的 `usage` 里有 `input_tokens`、`cache_read_input_tokens`、`cache_creation_input_tokens`、`output_tokens`、`output_tokens_details.thinking_tokens`；`modelUsage.<模型串>` 里另有 `thinkingTokens`、`costUSD`、`canonicalModel`。另有 `duration_ms`、`ttft_ms`、`total_cost_usd`、`session_id`、`stop_reason`、`api_error_status`。**output_tokens 已包含思考**：回复 "ok" 那次 output 37、thinking 33。输入总量 = 三个输入字段相加。 |
| P4 | 思考原文拿不到 | **已核实** | 请求里 `display: "omitted"`，会话记录里 thinking 块是空字符串加一段 868 字符的签名。Opus 5.5 文档：原始思考链在任何设置下都不返回，最多给摘要（`display: "summarized"`），`claude -p` 没有开关能改这一项（help 里没找到）。所以"它想了什么"只能看它写出来的正文。 |
| P5 | 同一会话续接（`--resume <id>`）时，上一轮的思考会带回模型上下文 | **已核实** | 三层证据：①**客户端确实发回去了**：续接时抓到的请求里，上一轮的 assistant 消息是 `[thinking(空文本, 签名 892 字符), text "ready"]`，且 `context_management: {"edits": [{"type": "clear_thinking_20251015", "keep": "all"}]}`，即全部保留、不清理。②**文档**（claude-api skill 随 2.1.282 带的迁移指南，Opus 5.5 节）：思考块绑定模型和会话，同一模型、同一会话、前缀逐字节不变时模型读得到；Claude Code 会保持前缀不变。③**实测**：第一轮让它"心里想一个 1–100 的数，只回 ready"，然后从这个状态分叉（`--resume --fork-session`）3 次，问同一组 6 个是/否问题。5 个会话 15 次分叉，同一会话内 3 次答案完全一致，不同会话之间出现 4 种不同答案（C `YYNNYN`、D/F `YNYNYN`、E `YYNYYN`、G `NYNYYN`）。这 5 个会话能看到的正文逐字相同（都是同一问题加 "ready"），唯一不同的就是那块看不见的思考；若思考没带回去，5 个会话应该答出同一种分布。**2026-09-25 在棋手同款开关下（P7 那套加空临时目录）复核**：①照样成立——续接请求里上一轮的 thinking 块（带 804–1852 字符签名）原样发回，`keep: "all"`，`tools` 仍为 `[]`，对局会话记录里也存着带签名的思考块；③行为复测**没得出定论**：两轮共 6 个会话，一轮里模型常先声明"我没有跨轮的隐藏记忆"、分叉答案不一致，另一轮 3 个会话全挑 37（`NNNYYY`，分不出是记得还是现编），还有 1 次被分类器拦下。要定论得做"删掉思考块再续接"的对照，没做。2026-09-26 删思考对照已做，结论：用得上，见 `results/batch1-carryover.md`。 |
| P6 | 不能直接问它"你上一轮想了什么" | **已核实** | 直接问"上一轮你在思考里挑的数是多少"，3/3 被安全分类器拦下（`Opus 5.5's safeguards flagged this message`）。文档说这是 `reasoning_extraction` 类拒答：要求在正文里吐出思考会被拒。换成"我放弃了，公布答案"，6 次里 2 次被拦、2 次它自称看不到之前的思考、2 次给了答案；而且 **Claude Code 会自动往会话里塞一条"上面的回复被安全分类器拦了，别再输出"的用户消息然后重试一次**，这条消息会永久留在会话里。 |
| P7 | 关掉工具、MCP、用户设置、CLAUDE.md 后，模型拿不到引擎 | **已核实** | 沿用上一轮命令（`--tools "" --strict-mcp-config --setting-sources "" --system-prompt ... CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`），抓到的请求 `tools: []`。system 里只剩 Claude Code 固定的一句身份说明和我们的系统提示，用户消息前多一小段 userEmail 提示，另有一条环境说明（工作目录、日期、模型名）。**2026-09-25 用对弈程序实际拼出的命令复核**（运行目录是仓库外的空临时目录，桩服务抓请求）：`tools: []`，没有 MCP，system 只有身份说明和我们的提示，全文搜不到 stockfish / fairy / lc0 / maia / `/opt/homebrew` / llm-chess / CLAUDE.md / AGENTS / memory / skill / hook。`--bare` 只认 API key、不能走订阅，不用；加 `--safe-mode` 请求体没有变化，不加。 |
| P8 | 续接跨天、跨长暂停后思考仍保留 | 待验证 | 文档说前缀必须逐字节一致。环境说明里带日期，续接时 Claude Code 是重放当初那条还是重新生成，没测。上一段 P5 的实测都在几分钟内完成。 |
| P9 | 走 API 直连更可控，但本研究不需要 | **已核实（文档）/ 决定不用** | 直连能多拿到：`display: "summarized"` 的思考摘要、`thinking-binding-controls` 的丢块报告、完全干净的 system（没有 Claude Code 那两段）、per-message effort。代价是走 API 计费、不走订阅额度，而且要自己维护 messages 数组、保证只追加不改写，否则思考块会被丢掉或 400。本研究要的"思考深度、思考延续、token 统计"`claude -p` 全都能做到，所以**默认 `claude -p`**，API 只作为以后要看思考摘要时的可选后端；要加时再在对局循环里加一个棋手分支。 |
| P10 | Codex 能当另一方 | **已核实（2026-09-28）** | sol 和 DeepSeek 都走 `codex exec`（`llmchess/codex_cli.py`），关 features + 补丁模型目录后请求里工具数为 0，诱导跑引擎、读文件都做不到，事件流和会话记录里没有工具调用；全局 `~/.codex/AGENTS.md` 关不掉，作为固定噪声进上下文。只支持无状态。详见 `results/batch5-isolation.md`。 |
| P11 | 国际象棋固定强度对手：Fairy-Stockfish 限 Elo | **已核实能用 / 分数标定待验证** | 本机 `/opt/homebrew/bin/fairy-stockfish`，`id name Fairy-Stockfish 14.0.1 XQ`，有 `UCI_LimitStrength`、`UCI_Elo`（500–2850）、`Skill Level`（-20..20）。实测同一局面每手 0.1 秒：不限强时 6 次只走 d5/Bb3/Qc2 三种好棋，限 500 时出现 Nxe5（送子）这类着法，限强生效。但它是经典估值、不是正版 Stockfish，Elo 标定和正版不一定一致；python-chess 驱动它时不能手动设 `UCI_Variant`（库自动管）。 |
| P12 | 正版 Stockfish、Maia | **已安装（用户同意）** | Stockfish 19 在 `/opt/homebrew/bin/stockfish`，lc0 v0.32.1 在 `/opt/homebrew/bin/lc0`；Maia 权重 1100–1900 共 9 档在 `~/.local/share/maia/maia-XXXX.pb.gz`（不入库）。官方 README：用 lc0 加载，`go nodes 1`、不搜索。另有 `pip` 包 `maia2`（要 torch，较重，不用）。 |
| P13 | 中国象棋固定强度对手 | 部分核实 | 同一个 Fairy-Stockfish 下中国象棋可限强，但 `UCI_Elo` 的标定是国际象棋的，**分数在中国象棋上没有意义**，只能当一把强度旋钮做相对比较。本机没有中国象棋的 Maia 类"像人"引擎。已定：这次不引入 Pikafish，就用本机 Fairy-Stockfish 限节点数或深度造几档弱对手，不和人类段位对应。 |
| P14 | 规则库 | **已核实** | 本机 python-chess 1.11.2、pyffish 0.0.90；系统 Python 3.9.6（代码要兼容 3.9，别用 `match`、`X | Y` 类型写法）。 |
| P15 | 长捉只能靠规则库判 | **已核实（文档）/ 边界待验证** | 规则库 pyffish 0.0.90 内嵌的 Fairy-Stockfish 和外部对手引擎 14.0.1 不是一个版本；外部引擎只禁长将、不禁长捉，所以不能指望引擎自己避开长捉。程序先用规则库算出会被判负的着法，引擎对手出棋时用 `searchmoves` 把它们排除；模型走到这类着法当非法着退回。长捉是 pyffish 的近似实现，边界没全测。 |
| P16 | 国际象棋三次重复、五十回合 | **已核实 / 已定口径** | python-chess 的 `outcome()` 默认不因三次重复、五十回合结束，要 `claim_draw=True`（本机实测）；但 `claim_draw=True` 在"走一步就能凑成三次重复"时也算可申诉，会早一个半回合结束（本机实测），所以程序改为直接查"局面已经出现三次""计数已经到 100 个半回合"。口径：**程序替棋手自动申诉，按终局判和**，终局原因写明是哪一条。五次重复、七十五回合是强制和，同样判和。 |
| P17 | `claude -p` 的运行目录会进提示 | **已核实** | 桩服务抓到的请求里，环境说明写着工作目录全路径、"Is a git repository"、当天日期，**没有** git 状态和提交记录。运行目录放在仓库外的空临时目录 `$TMPDIR/llmchess-cwd/<tag>-<随机>`（路径记进 config，续跑沿用，会话记录按它存），往上找不到任何 CLAUDE.md / AGENTS.md、也不是 git 仓库。 |
| P18 | 便条的措辞会触发安全分类器 | **已核实（小样本）** | 冒烟时原版便条要求（"留给下一步的自己：当前意图、预料对手会怎么应、下一两步打算走什么、要提防的坑"，加系统提示"你看不到自己之前的思考"）2/2 被以 `reasoning_extraction` 拒答，只改其中一处的三种写法又拒 3 次；改成"写一段便条，写什么由你定，程序下一步原样给你看"、系统提示不提思考后 4/4 通过，模型自己会写意图和计划。拒答时 `claude -p` 退出码 1、`is_error`、`stop_reason: "refusal"`，程序按拦截记，不当调用失败。 |

## 二、程序结构

对局流程外壳只写一份，两种棋各一个平铺的模块；两边只靠一组同名函数约定对接，**不写基类、不做注册、不写未实现的桩**。以后发现某块差异塞不进这组函数，再把那一块下放到棋种模块。

```
llmchess/
  cli.py         命令行：play / resume / dry-run；公共变量加两方分设；按 --game 选棋种模块
  claude_cli.py  拼 claude -p 命令（关工具、显式 effort）；调不通重试；撞额度抛暂停；用量展开；安全分类器拦截识别
  memory.py      stateless / notes / session：系统提示里那句说明、便条的要求与提取、重试话术
  runner.py      对局循环：轮到谁 → 棋种拼提示 → 调棋手（模型 / 引擎 / 随机，循环里直接分支）→ 棋种解析判合法（含禁着）
                 → 重试 / 判负 → 落子 → 棋种判终局 → 记录；暂停与续跑
  records.py     JSONL 事件读写、每方统计汇总
  engine.py      很薄的 UCI 文本收发：带完整历史（position fen 起始局面 moves …）、等待有上限、退出时收掉进程
  opening.py     随机开局：引擎浅搜 MultiPV 3，按种子抽前 N 个半回合（见第三节 opening）
  batch.py       批量驱动：一批盘并发跑完、续跑、自动 analyze、按对手汇总（见第五节末尾）
  xiangqi.py     中国象棋：规则包装（从 boards.py 搬）、终局与禁着（从 play_xiangqi.py 搬）、呈现 / 提示 / 自查 /
                 复述打分 / 着法解析（从 llm_duel.py 搬）、中文棋谱、引擎参数与坐标换算
  chess_.py      国际象棋：python-chess 包装、UCI / SAN 解析与非法原因（原因分类照搬 boards.violation 的国际象棋分支）、
                 呈现、提示、终局与自动申诉、PGN、引擎参数
tests/           纯规则部分的离线单元测试（解析、禁着、终局判定、续跑重放）
```

局面题模式在 `quiz.py`（第六节组 1；第二批的分档见第八节），整盘事后分析在 `analyze.py`。

**棋种模块的函数约定**（两个模块提供同名函数，循环按名字调用）：

```
start() -> 状态              turn(状态) -> 'w'/'b'           legal(状态) -> [着法]
banned(状态, 合法着法) -> 集合      parse(状态, 文字) -> (着法或 None, 不合法原因或 None)
push(状态, 着法)                ending(状态) -> None 或 {winner, reason}      in_check(状态)
render(状态, 这方配置) -> 本步局面正文       system_prompt(这方, 这方配置, 记忆说明) -> 文本
recite_score(状态, 回复)（只有中国象棋）     exports(状态, 配置, 终局, 统计, 每步元信息) -> {文件名: 文本}
engine_spec(描述) -> 引擎命令与参数       to_engine(着法) / from_engine(文字)
```

状态里固定存起始局面、每步之后的 FEN、全部落定着法和记谱，判重复、续跑都靠完整历史，与给模型看多少历史无关。

- **棋手**在循环里直接分支，不做多态：
  - `claude:<模型>`：沿用上一轮命令（见 P7），`stdin` 接 `/dev/null`（否则会等 3 秒并打警告），运行目录 `runs/<tag>/cwd`（P17）。
  - `engine:<名字>[:参数]`：国际象棋 `maia-1100`…`maia-1900`（lc0 加权重，`go nodes 1`）、`stockfish[:elo=N|nodes=N|movetime=毫秒]`；中国象棋 `fsf[:nodes=N|depth=N]`（Fairy-Stockfish，`UCI_Variant xiangqi`）。每步把起始局面和全部着法发给引擎，不只发末尾 FEN；等待有上限；中国象棋出棋时用 `searchmoves` 排除会被判长将 / 长捉的着法（P15）。`boards.Engine` 是单局面分析用的（不带历史、等待没有上限），不拿来当对手；另外 boards.py 实测过 Skill Level 不可复现，弱档一律用节点数或深度。
  - `random`：随机走子，按对局种子可复现，当最低参照（LLM CHESS 用它 [5]）。
  - `codex:<模型>` / `deepseek:<模型>`：局面题里走 `codex exec`，只支持无状态（quiz `--model sol|deepseek`，P10）；整盘（`--protocol real`）三路都走 llm-chat，支持连续会话（第九节）。
- **引擎只当对手和事后裁判**。给模型的提示里永远不出现引擎的任何输出；分析在对局结束后另跑。

## 三、变量与默认值

模型相关的变量两边可以分别设（`--w 变量=值`、`--b 变量=值`，w 是先走的红方 / 白方），不设就用公共值。

| 变量 | 取值 | 默认 | 说明 |
|---|---|---|---|
| `game` | `xiangqi` / `chess` | — | |
| 棋手 | `claude:<模型>` / `engine:<名字>[:参数]` / `random`（见第二节） | `claude:opus` | `--red`/`--white`、`--black` |
| `effort` | medium / high / xhigh / max | medium | 与上一轮一致，方便对照；实验里扫全档 |
| `protocol` | `real` / `legacy` | 整盘 real，局面题 legacy | 第九节。legacy 是改协议之前的提示和调用，逐字复现旧数据 |
| `memory` | `stateless` / `notes` / `session` | 整盘 real 下 session，legacy 和局面题 stateless | 见下 |
| `show` | `all` / `board` / `pieces` / `fen`；中国象棋另有 `boardpieces` | 中国象棋 `pieces`（只给子力清单）；国际象棋 `all`（FEN + 字母棋盘） | 局面怎么给，整盘（`--show`）和局面题（`--set show=`）共用一套。`show=all` 逐字复现改默认之前的提示（中国象棋棋盘 + 子力清单 + FEN 三样，第四批及以前的数据都是它）。依据：第四批局面题 high 下，中国象棋只给清单的昏招比三样全给少、也不会认错「車」，分不开时按简洁选；国际象棋只给字母棋盘和全给分不开，但棋盘缺易位权和吃过路兵信息，所以不换（`results/batch4-presentation.md` 末节） |
| `view` | 国际象棋：`fen`、`ascii`、`pieces`、`pgn`；中国象棋：`grid`、`pieces`、`fen`、`cells`、`board` | 由 `show` 决定 | 自定义组合，逗号分隔、按序拼；和 `show` 二选一 |
| `history` | -1 全部 / 0 不附 / N 最近 N 个半回合 | -1 | 上一轮 C/D/E 只附 20 步、A/B 附全部，两者混在一起了；这次统一全部 |
| `legal` | `none` / `list` | none | 测棋力时可以开，报告里分开写 [5][6] |
| `selfcheck` | on / off | off | 上一轮开了没见效；作单独变量。两种棋的自查文字各写各的 |
| `recite` | on / off | off | 先复述局面再走，程序逐格比对。复述格式和打分目前只有中国象棋有 |
| `retries` | 整数 | 3 | 非法重试上限，用完判负（和 Game Arena 一致 [1]） |
| `timeout` | 秒 | 3600 | 单次 `claude -p` 的超时（`--timeout`，整盘记进 config、resume 沿用，`resume --timeout` 只改那一次续跑并记进 resume 记录；局面题同名参数）。第一批写死 1800，max 档撞了 7/120 次 |
| `on_limit` | `wait` / `pause` | wait | 撞额度时：`wait` 在程序里等到解除接着调（报错里读得出解除时间就等到那时再加 2 分钟，读不出按 10 分钟起翻倍、最多 30 分钟退避；这种等待不占调不通的重试、也不占着法重试）；`pause` 是旧行为，写 pause、退出码 3。整盘 `play` / `resume` 和 `quiz run` 都有 `--on-limit`。等待中 Ctrl-C / SIGTERM：在等的线程马上醒来写 pause、退出码 3，再跑同一条命令（或 resume）接着来；已在跑的调用答完为止，再按一次强退 |
| `max_plies` | 整数 | 200 | 研究设的上限，到了判和；和棋规里的限着（中国象棋一百个半回合无吃子、国际象棋五十回合）分开记终局原因 |
| `opening` | 不设 / `random:N`，加 `--opening-seed` | 不设 | 随机开局（第二批 0.4）：前 N 个半回合由程序替双方走。每个半回合引擎浅搜（国际象棋 Stockfish、中国象棋 Fairy-Stockfish，固定深度 10、单线程、每局面 ucinewgame，同种子可复现），MultiPV 3，从和最好着分差 ≤50 厘兵的着法里按 (种子, 半回合号) 抽。建盘时生成一次写进 config，续跑照记录重放。引擎输出不进提示，模型只在着法历史里看到这几步 |

两种棋的系统提示在「回答格式」那段要求「请用中文回答。」（第二批块 0.1，整盘和局面题共用；第一批国际象棋里英文作答和答错常一起出现）。

**思考与计划的延续（`memory`）**：

- `stateless`：每步新开一次，看不到自己之前的任何东西。主流做法 [1][5]。
- `notes`：每步回复最后要求多写一段便条（不超过约 150 字，写什么由它定；不列要写的内容，原因见 P18），程序把上一步的便条原样放进下一步提示；默认只带最近 1 条，`--notes-keep N` 可以多带。实测模型自己会写意图、预料的应着和下一两步打算。个人博客 [27] 的"跨步保留部分推理记录"就是这类做法，但没有对照。
- `session`：每方一条连续会话，第一步 `--session-id`，之后 `--resume`，平台把之前每一轮的思考块原样带着（P5）。每轮仍给完整局面（默认），这样测到的是"计划延续"而不是"记盘能力"；`--session-view move` 只告诉对手走了什么，就成了盲棋压力测试 [6]。
- 两条硬约束：提示里**不要**让它"回忆 / 复述上一轮的思考"（会被拦，P6）；便条的措辞用"给下一步的自己留话"，别用"总结你的推理"。

## 四、记录格式

每盘一个目录 `runs/<tag>/`（入 `.gitignore`），一行一条 JSON，和上一轮兼容并补字段：

- `config`：全部变量、两边系统提示、完整命令行、本机 Claude Code 版本、引擎名与参数、代码 commit；随机开局另有 `opening`（种子、半回合数、开局引擎与参数、`moves` / `record`、每步的候选与评分 `detail`）。
- `attempt`（每次调用一条）：半回合号、哪方、第几次尝试、提示原文、回复原文、解析出的着法、是否合法及原因、便条文本、复述得分；`usage` 展开成 `in`（无缓存输入）、`cache_read`、`cache_write`、`out`、`think`、`text_out = out − think`；`cost`、`duration_ms`、`ttft_ms`、`session_id`、服务端模型串、`stop_reason`、`api_error_status`；`claude` 字段存返回 JSON 原样。
- `move`：落定的一步、记谱、是否将军、本步各次尝试的合计用量。随机开局那几步带 `opening: true`（没有 attempt），不计入任何一方的统计。
- `flag`：安全分类器拦截（`stop_reason` 为 `refusal` 或结果正文含 `safeguards flagged`，或 `session` 模式下会话记录里出现 Claude Code 自动插入的那条"被安全分类器拦下"消息）单独记一条，并在报告里单列；这类不算非法着法、不扣重试次数。正文为空的回复（冒烟见过一次：`end_turn`、有思考、正文空）同样不扣重试次数，另计"空回复"。一步里被拦或空回复超过 2 次就暂停，交给人看。
- `call_fail`：一次 `claude -p` 超时或调不通（非零退出、回的不是 JSON），重试前记一条：半回合号、哪方、第几次着法尝试、第几次调用、是否超时、退出码、用时、stderr / stdout 末尾、下次重试前等几秒；局面题另带题号 / effort / 遍 / 档名。撞额度不记这条（记 `pause`）。
- `limit_wait`：撞额度在程序里等解除，等之前、等完各记一条（`phase` 为 start / end）：开始时间、读出的解除时间（读不出为空）、打算等几秒、第几次等、报错末尾；结束另记结束时间、实际等了多久、是否被停止信号打断。带的半回合号 / 题号同 `call_fail`。claude 报错里解除时间的写法没有公开格式，解析尽量宽松（epoch 秒、ISO 时间、「resets in 2h」「resets 5am (时区)」「resets Sep 27, 5am」），读错或离谱（早于 5 分钟前、晚于 8 天后）都退回退避。
- `drop_warn`：开了去掉此前思考的一方，续接轮 `thinking_dropped` 为 0 或没给（第九节）；不中断对局。开了的一方每条 `attempt` 另记 `thinking_dropped`。
- `pause` / `resume` / `forfeit` / `end`（结果、每方合计与中位数：调用数、非法数、每步输入/输出/思考 token、用时、花费）。
- 不管给模型的 `history` 设多少，记录里都有起始局面和全部落定着法；续跑时按它重放，重复局面照样判得出。
- 结束时另写 `record.txt`（棋谱加统计）和 `game.pgn`（国际象棋标准 PGN；中国象棋是 xqbase PGN，2026-09-29 起），中国象棋的 `record.txt` 用中文记谱。PGN 标签里有自定义的思考深度 `WhiteEffort` / `BlackEffort`（中国象棋 `RedEffort` / `BlackEffort`），取 `config` 里双方的 effort，只给模型棋手。终局原因用棋种自己的说法。已结束的盘可以按 `game.jsonl` 重新导出这两个文件（不调模型、不写记录）：`python3 -m llmchess export runs/<tag>`。
- **每步元信息**（2026-09-28 起，`records.move_meta` / `meta_comment`）：模型下的每个半回合，在棋谱里这步着法后面跟一段评注。写法是 PGN 评注里的内嵌命令 `[%名 参数]`（出自 PGN Specification Supplement：`[%` + 字母数字命令名 + 空格 + 参数 + `]`；读不懂的命令阅读器应原样保留、不做处理）。例：`1. e4 { [%emt 0:00:12] [%think 280] [%out 300] [%in 2] [%cacheread 100] [%cachewrite 50] }`。
  - `%emt h:mm:ss`：**标准命令**（规范补充：该步用掉的时间，只到整秒，四舍五入）。取本步各次调用用时之和（`attempt.elapsed`，只算成功回来的那次子进程，不含调不通的重试和等额度；llm-chat 路径含脚本起进程的开销）。
  - 以下都是**自定义命令**，没有通行写法：`%think` 思考 token、`%out` 输出 token（含思考）、`%in` 没走缓存的输入、`%cacheread` / `%cachewrite` 缓存读 / 写，都是本步所有调用的合计，口径同 `attempt.usage`；`%illegal` / `%flagged` / `%empty` 本步非法重选、被安全分类器拦、空回复的次数，为 0 时不写；`%dropped` 只有开了去掉此前思考的一方有（第九节），本步各次调用 llm-chat 报的 `thinking_dropped` 之和，0 也写（续接轮为 0 是要看的异常）。命令名按规范只用字母数字，所以不带下划线。
  - **缺省**：本步任何一次调用的后端没给某一项，这一项整条不写（不补 0、不部分相加）；有没有给看原始返回（`attempt.claude`），因为换算后的 `usage` 把缺的都记成 0。各后端：claude:opus（llm-chat 或 `claude -p`）全都给，思考 token 可以真是 0（自适应思考没想）；codex:sol（llm-chat 或 `codex exec`）思考 token 单独给（`reasoning_output_tokens`），缓存写 llm-chat 缺省记 0（`codex exec` 的 `turn.completed` 里有这个字段）；deepseek 走 llm-chat 时缓存写不给（省掉），思考 token 取 `completion_tokens_details.reasoning_tokens`，接口不给时省掉——至今没有 llm-chat 路径的 DeepSeek 整盘记录，实际给不给待看；走 `codex exec` 的旧记录里有。被拦 / 出错没回用量的调用让本步 token 全部省掉，只留 `%emt` 和次数。随机开局、引擎、随机走子的半回合不带评注。
  - **说明文字**：命令后面接落定那次回复里着法前面的文字（`memory.extract_reason`：从最后一处「着法:」/「Move:」切开，都没有就去掉最后一行）。现行整盘协议默认请棋手在着法前写理由（`reason=plain` / `brief` / `detailed`，第九节），每步都有；`reason=off` 或 2026-09-29 之前的 real 对局一般没有；旧协议（「可以先写简短的思路」）的对局多半有。PGN 花括号评注没有转义写法，所以 `{` `}` `%` 换成全角 `｛` `｝` `％`（`}` 会提前结束评注，行首 `%` 会让整行被当成转义行忽略，`[%` 会被当成命令），换行压成空格。
  - **折行**：PGN 标准（Edwards 1994）导入格式每行最多 255 个字符（4.3），导出格式每行不到 80 个印刷字符、词之间一个空格（8.2.1）；评注本身没有长度上限，但标准说评注的导出写法「needs definition work」，没定。python-chess 自带的导出把整段评注当一个词、不折行，所以 `game.pgn` 的着法部分由程序自己排：评注里的词也拆开，按显示宽度（全角算 2 列）每行不超过 79 列，中文优先在全角标点后断行，其次在普通空格处，最后在两个全角字符之间硬切，「中文 空格 中文」的空格不作断点（`records.words` / `chunks`），这样的断行读回来不补空格，才还原得了原文（2026-09-29 前是按宽度硬切、读回来多一个空格）；国际象棋评注后面的黑方着法补 `N...`。
  - 两种棋都写进 `game.pgn`。中国象棋的 `game.pgn` 按 xqbase 规范（`Game` 标签第一个，着法用 `xiangqi.pgn_move` 生成的无歧义中文记谱，评注后的黑方着法照规范例子不补 `N...`，细节见 `docs/viewer.md`）。中国象棋的 `record.txt` 不是哪种通行格式，**照 PGN 评注的写法自定义**：有评注时一个半回合一行，`1. 炮二平五 {[%emt 0:00:05] [%think 15] … 说明文字}`、`1... 马２进３`，折行同上；没有评注（引擎对随机之类）照旧一回合一行。通行的中国象棋 PGN（xqbase「中国象棋电脑应用规范（四）」）也用 `{}` 注释（「允许任意字符」，没写长度上限，也没有定义内嵌命令），`game.pgn` 的评注就是原样搬过去的。

`analyze` 读这个目录，逐步给出"走前最好能得多少、走后剩多少、亏了多少"、大失误 / 失误、规则判定（白送子、漏吃、漏杀），输出 `analysis.jsonl`。口径沿用上一轮（中国象棋截断 ±1000、只看未分胜负的步），国际象棋另加按胜率换算的亏损（lichess 式），并算平均每步亏损。随机开局的半回合照样评分，但不算进任何一方的大失误、ACPL 和件数。

## 五、对手模式

- **模型对模型**（自对弈或不同设置对打）：看不同做法，但两边都会犯错，结果噪声大，主要看逐步亏损而不是胜负。
- **模型对固定引擎配置**（固定引擎、固定节点数 / 深度 / 限 Elo，不暗示精确分数）：模型每步照常调用，引擎只负责回应；这是本研究的主力模式，因为对手恒定，胜负和逐步亏损都能比。
  - 国际象棋按从弱到强排一架梯子：`random` → Maia-1100 → Maia-1300/1500 → Stockfish 限 Elo。先用 Maia：它像人、强度有公开对照（ChessArena 里没有通用模型赢过 Maia-1100 [6]），Stockfish 限强在低分段走法不像人。要换算大致分数，就在梯子上找模型胜率约 50% 的那一档，每档至少 10 盘；只有一两盘的结果只能说"明显高于 / 低于"某一档。
  - 中国象棋只有 Fairy-Stockfish，限节点数或深度造几档，当相对旋钮用，不报分数（P13）。
- 引擎每步给固定时间或节点数（Maia `nodes 1`；Stockfish 限强每步 0.1–0.5 秒），写进 config。
- **批量驱动**（第二批 0.5，`python3 -m llmchess.batch run|summary`，用法见模块说明）：一批 = `runs/<批>/`，一盘一个子目录 `<对手>-s<种子>-<w|b>`（种子同时是开局种子和随机走子种子，w / b 是「我方」执先走方还是黑方，同一开局两色各一盘）。我方默认 `claude:opus` xhigh stateless，`--player` 换成引擎就是引擎对引擎（B2 标定）；随机开局默认国际象棋 8、中国象棋 6 个半回合。我方设置记在 `batch.json`，再跑须一致，对手和种子可以追加。再跑同一条命令即续跑：下完的跳过、没下完的 resume。`--on-limit`（默认 wait）和 `--timeout` 透传给每盘的 play / resume：wait 时撞额度的盘在自己进程里等，驱动照常开新盘。停下只有一条路：任一盘暂停（含 pause 模式撞额度），或驱动收到 Ctrl-C / SIGTERM（驱动装的是和 play 同一套 `claude_cli` 停止处理），驱动置 STOP 不再开新盘、在批次目录放 `.stop`（在跑的盘在下一步之前停，play / resume 的 `--stop-file`），并给每个在跑的盘发一次 SIGTERM，叫醒它里面在等额度 / 等重试的调用写 pause；第二次信号向在跑的盘的进程组发 SIGINT 直接打断；都退出码 3，再跑同一条命令续跑。每盘各在自己的进程组里跑。`summary.md` / `.json` 按（批次，对手）分组：只算下完的盘；战绩、得分率与 Wilson 95% 区间；我方未分胜负、非开局步的大失误率（国际象棋 lichess Blunder，中国象棋亏损 ≥250）与 ACPL，全组合计；第 20 个半回合局面的两两重合与独立盘数。

## 六、实验建议（第一批）

先说预期：强度都很低，胜负多半一边倒，**主要指标是逐步亏损和大失误率**，胜负是辅助。

| 组 | 做法 | 盘数 | 回答的问题 |
|---|---|---|---|
| 0 冒烟 | 两种棋各对随机走子一盘、各对一次引擎（Maia-1100 / 限节点的 Fairy-Stockfish），只走几个半回合，notes 和 session 各跑几步 | 4 | 流程、记录、拦截检测、续跑都通；离线单元测试另外覆盖：续跑后重复局面还能判、中国象棋坐标换算、国际象棋易位 / 吃过路兵 / 升变的解析 |
| 1 局面题测思考深度 | 不下整盘：取 30 个固定局面（国际象棋取公开谜题；中国象棋取上一轮 74 步昏招的走前局面），stateless，四档 effort 各答一遍 | 120 次调用 | 思考深度到底改不改变单步质量，比整盘便宜得多、噪声小 |
| 2 思考延续（国际象棋） | 对 Maia-1100，effort=high，memory 三种各 3 盘 | 9 | 带计划、带思考能不能少丢子、下得更连贯 |
| 3 思考延续（中国象棋） | 对 Fairy-Stockfish 最弱一档（限节点数），effort=high，memory 三种各 2 盘 | 6 | 同上，并和上一轮 5 盘对照 |
| 4 棋力定位（国际象棋） | 组 2 里表现最好的做法，对 random 5 盘、Maia-1100 5 盘 | 10 | 能不能赢随机；离 Maia-1100 多远，对照 o3(low) ≈758 [5] |

预计时长（粗估，按 P2 和上一轮：medium 平均 15–20 秒一步，max 可能 1–2 分钟一步；对引擎时模型只走一半步数，一盘 60–100 个半回合）：
- 组 1：120 次调用，max 档占大头，串行 1–2 小时，开 4 路并行约 30 分钟。
- 组 2：每盘约 40 步模型着法 × 20–40 秒 ≈ 15–25 分钟，`session` 越往后输入越长会更慢一些；9 盘串行约 3–4 小时，3 路并行约 1.5 小时。
- 组 3：自对弈时两边都是模型，改成对引擎后每盘约 20–40 分钟，6 盘并行约 1.5 小时。
- 组 4：约 3 小时串行。
- 花费按标价折算：上一轮 medium 一盘 $3–10（自对弈、两边都付），这次对引擎只付一边，high 档估计每盘 $2–6；`session` 模式因为历史越积越长，会贵一些（主要是缓存读取）。走订阅额度时这些钱不真付，但会吃额度，额度撞上时程序会停在两步之间等续跑。

## 七、风险

- **盘数太少**：每组 2–3 盘分不清"做法的效果"和"这盘碰巧"，上一轮就吃过这个亏。所以把思考深度拆去局面题（组 1），整盘只测非做不可的思考延续；结论写成"方向"，不写成"显著"。
- **`session` 模式的混杂**：连续会话里模型除了能看到之前的思考，还能看到之前的全部提示和回复；它要是比 `stateless` 好，分不清是思考起作用还是看到了历史局面。`notes` 正好当中间档：只带它自己写的计划、不带思考。要彻底拆开，可以加一档"stateless + 全部历史正文"，第一批先不跑。
- **安全分类器**：提示里一旦有"回忆 / 复述你的思考"就会被拦（P6），`session` 模式下 Claude Code 还会往会话里塞一条提示并重试，从此污染这一方的历史。要检测并记录，出现就把这盘标出来。
- **跨天续跑可能丢思考**（P8 待验证）：`session` 模式的一盘尽量一次下完；撞额度暂停后续跑的盘在报告里标出。
- **Codex 能用引擎**（P10）：已证明关得掉（`results/batch5-isolation.md`）；Codex 升级后工具的挂法会变（0.157 起工具挪进了 input 里的 `additional_tools`），升级后要重抓一次请求核实工具数仍是 0。
- **Elo 换算很粗**：Fairy-Stockfish 限强的标定未核实，Maia 是"像某分段的人"而不是精确标尺，几盘结果只能给区间。和公开数字对照时要写清对手和条件不同。
- **会话越长越贵越慢**：`session` 模式 100 个回合后每步输入可能到几十万 token（大部分走缓存）。1M 上下文装得下，但要盯住额度。
- **看不到思考原文**（P4）：昏招归因只能靠它写出来的正文和便条；如果以后要读思考摘要，只能走 API 直连。

## 八、局面题分档（第二批块 0.3、块 A）

- **分档**：`quiz run --arm <档名> --set 变量=值`（可重复）。可改的变量：`view`、`legal`、`selfcheck`、`recite`（只有中国象棋），加上只有局面题有的 `threats`、`attackmap`；其余同第一批（stateless、history=0、该棋种默认 view），effort 仍由 `--efforts` 给。记录放 `runs/quiz-<批>/<档名>/<棋种>/`；不给 `--arm` 时不许 `--set`，布局同第一批（`runs/quiz-<批>/<棋种>/`）。
- **不混写**：`batch.json` 记档名、`--set` 值和用过的局面文件。同一档名下 `--set` 不同，或者换了局面文件、同一 id 的局面内容却不同，都直接报错。
- **judge / report**：`judge` 不给 `--arm` 就判全部档（含第一批旧布局），按 `batch.json` 找局面；`report` 按「档 × effort」分组出表，有档时表头多一列「档」。
- **复用**：`quiz copy --from-arm A --arm B` 把 A 档里和 B 档局面内容相同（按局面、着法历史、对手刚走那步比，不看 id）的已答记录复制过来，复制前逐条核对系统提示和用户提示一字不差，不一样就跳过；复制出的记录换成 B 的题号、标 `copied_from`。块 A 的 base 档就这样复用块 0 的 `zh` 复测。
- **threats 档**（`threats=on`）：系统提示要求在「着法:」之前先写「走后威胁:」清单，列出走完打算走的这步之后，对方所有能吃我子的着法和能将我的着法，每行一着、用和着法相同的坐标写，没有写「无」。程序取落定那次回答里的清单（非法重试前的不算），按走后真实局面算出对方全部合法的吃子、将军着法（走子规则全由 pyffish / python-chess 判），记列中、漏列、错列，写进 result 的 `threats` 字段，**不回灌**给模型。judge 另记引擎在走后局面给对方的首选应着（`refute`），把 threats 档的每条大失误归成「列出了还走」「没列出」「反击不是吃子或将军」「没写清单」四类；report 另出一张表，给真实威胁被列出的比例和这四类的条数。
- **attackmap 档**（`attackmap=on`）：局面后附程序算出的攻击关系（对方每个子现在能吃到我哪些子、我哪些子没有保护；中国象棋用 pyffish 的合法着法算，国际象棋用 python-chess 的攻击关系算）。它碰到硬约束「棋手不准用规则库帮忙」，**待用户拍板，未批不准跑**：`quiz run` 遇到它，除非同时给 `--allow-attackmap`，否则直接退出；只允许 `--dry-run` 看提示。
- **超时**：`quiz run --timeout` 同整盘，超时或调不通时 `call_fail` 写进该题自己的记录（带题号 / effort / 遍 / 档名），result 里另有 `call_fails`、`timeouts` 计数。

## 九、「模型就是真实棋手」协议（2026-09-28 起整盘默认，`--protocol real`）

用户定的原则，不再当变量测：棋手只看到局面、知道轮到自己，自己选着；系统不替它看棋（不报吃子、丢子、威胁，不给合法着法）；每盘每方固定一段连续会话（`memory=session` 是唯一默认）；非法着法计数、告诉它不合法、让它重选；不要求中文。**2026-09-29 起默认请棋手在着法之前用自己的话写出这步的理由**（用户定，见下表「说明理由」一行）；**理由措辞默认「不修饰」**（`reason=plain`：「先用你自己的话写出这步的理由（为什么这样走）」，不说简短也不说详细，写多少由模型自己判断；2026-09-30 用户定）。之前的默认「简短」（`reason=brief`）保留可选；两者差别很小（`results/missed-captures.md` 3.5：同样 14 个漏吃局面 opus 去掉此前思考，不修饰 84 次零拦截，吃到 48/84 对简短 44/84，只能说持平），**不当作变量，此前「简短」下的对局照样有效、数据合并统计**。2026-09-30 当天几经改动：上午曾把所有棋手一律改成「详细」（5baf861），随后改成按棋手分（带思考的「简短」、去掉思考的「详细」，0e707cf）；当天用户定**放弃「详细」措辞**——opus 去掉此前思考 + 详细时频繁被 Anthropic 安全防护拦下，不改措辞去绕——默认先回到所有棋手「简短」，`detailed` 档弃用、只为复现保留（见下「去掉此前思考」）；同日补测后默认再改成「不修饰」。5baf861 之前的 18 局是「简短」版，这几次改动之间开的只有冒烟。旧局续跑沿用开局时存下的系统提示，不受影响。整盘从标准初始局面开始，不用预设或随机开局，背谱也接受（2026-09-29 用户定；`--opening random:N` 留给以后专门的实验）；会话里比新会话想得少、但缓存命中更省，也接受（`results/thinking-in-session.md`）。改协议之前的提示和调用逐字保留为 `--protocol legacy`（旧记录的 config 里没有 `protocol`，续跑自动走旧的；局面题默认也是旧的，`--set protocol=real` 换新）。

**提示逐句去留**（盘点稿和 astra 的裁决原文在当次草稿，拿不准的几条是和 astra〔Codex，最强档，high〕一起定的）：

| 原来的句子 | 去留 | 理由 |
|---|---|---|
| 系统：执哪方、对手是另一位棋手、目标是赢棋 | 留 | |
| 系统：规则（将死、困毙、重复、限着、满 N 个半回合判和） | 留，改写禁着 | 比赛规则人下之前就知道。中国象棋原写「长将判负（这类着法会被当作不合规退回）」，改成「不许长将、长捉，走出这类着法按不合法退回」，和程序实际做法一致 |
| 新增：非法重选的赛制 | 加 | 「着法不合法或认不出会告诉你，由你重新选；一步里连续 3 次都没给出合法着法判负。」赛制预先讲清，astra 定（次数 9/29 从 4 改 3，见下「重选上限」） |
| 系统：坐标约定 | 留 | 记谱是裁判和棋手共同的语言，不是替它看棋 |
| 系统：「每一步我都会给你当前局面。」+ 延续说明 | 改 | session：「本盘在同一段连续对话中进行。每一步都会给你当前局面和对方上一步着法。」不再说「你前面的思考都还在」：不做保证，也避开安全分类器（P6） |
| 系统：「请用中文回答。可以先写简短的思路……」 | 删 | 用户定：不要求中文（第二批块 0 证实不影响棋力）。改成「回答格式：只需给出着法，写成一行「着法: 」加着法」，着法写法说明保留；理由那半句见下一行 |
| 系统：「说明理由」 | 加（`reason=plain`，默认；`brief` 可选；`--reason off` / `--w reason=off` 关；`detailed` 已弃用，见下「去掉此前思考」） | 2026-09-28 曾定不加（第三批证实写理由不改变下法）；2026-09-29 用户改定要写：「回答格式：先用你自己的话简短写出这步的理由（为什么这样走），怎么写由你定；然后另起一行写「着法: 」加着法……」（`memory.ANSWER_LEAD`，这是 `brief`）。`plain` 删掉「简短」两字、`detailed` 把「简短」换成「详细」，其余一字不差。取值沿革：9/29 起 config 里记 `reason=on`（「简短」）；9/30 上午 5baf861 把 on 的措辞改成「详细」；当天改成现在的 brief / detailed / off 三档，命令行不再收 `on`（报错提示改写法）；同日 detailed 弃用，默认先回到 brief，补测后改成 plain（brief 保留可选，两者不当变量、数据合并）。旧记录 config 里的 `on` 不用管：续跑用 config 里存下的系统提示，不按 `reason` 重拼。局面题的理由提示（`quiz.REASON_ASK`）不变。只要回答里的可见文字，不提思考、不设栏目、不限语言长度；着法照旧按下面的解析读（理由里提到别的着法不影响，取最后一处「着法:」）。导出棋谱时理由进该步评注（第四节）。只在 real 下有；改之前的 real 记录 config 里没有 `reason`，续跑按 off |
| 系统：自查三问（selfcheck） | 默认关，保留开关 | 教它怎么想，不是替它看；新协议不开 |
| 每步：第几回合、轮到你走 | 留 | |
| **每步：「你现在正被将军！」/「你现在没有被将军。」** | **两句都删** | 替它识别 / 排除攻击。**这是删掉的唯一一处实质信息**，旧的局面题和整盘都带着它 |
| 每步：对方刚走 | 留；国际象棋只写 UCI | SAN 带「+」「#」等于替它报将军。中国象棋中文记谱不带将军标记，照旧「炮８平５（h7e7）」 |
| 每步：子力清单里的「（16 子）」 | 删 | 数子也是替它数；棋盘图例（大写白方……）留，那是字符含义的约定 |
| 每步：全部着法记录 | 只在新会话第一条给一次 | 连续会话里前文已有每一步，重复会让上下文按平方涨。标题改「此前已走着法」，国际象棋只写 UCI。随机开局的几步就靠这一次补给它 |
| 每步：合法着法清单（`legal=list`） | 整盘禁用 | 原则 3 |
| 每步：「请走一步。最后一行只写「着法: 」加你的着法。」 | 改成「请走一步。」 | 格式已在系统提示里 |
| 非法后：「你刚才的着法「X」不能走：<细原因>。请重新走一步（还剩 N 次机会，用完判负）。」 | 改 | 只解释纯写法问题，和局面有关的一律「这步不合法」：「回答里没有找到着法」「这步的写法认不出来」「这步的写法对应不止一步棋，请写明起点和终点坐标」「这步不合法」；接「请重新走一步（本步还可重选 N 次，用完判负）。」起点没子、蹩马腿、被将、牵制、照面、长将长捉都只说不合法（被将、牵制、照面会泄露对方的攻击关系；其余也是替它查盘）。完整原因照旧进记录（`attempt.reason`），给棋手看的类别另记 `attempt.feedback` |
| 重选上限 | **一手棋最多 3 次**，同一手连续 3 次非法直接判负；不设整盘总数上限（2026-09-29 用户定，原为 4 次） | **本项目自定的赛制，不是任何正式棋规**：控制试探和花费的选择，不是实验得出的最佳值；调用故障、空回复、被拦照旧不计非法。程序里是 `--retries` 默认按协议取：real 2（一步最多 3 次）、legacy 3（旧实验照旧）；次数记进 config，改之前开的 real 盘续跑照记录仍是 4 次（系统提示也是开局时那份） |
| 回复被拦或为空：「请重新回答这一步。」 | 留；同一手连拦两次后附「简短」（2026-10-02 用户定） | 不是棋的问题。第一轮就被拦时 llm-chat 不存会话，程序改为连系统提示带完整局面重发。**被拦兜底**：被拦后第一次重问照旧（不修饰）；重问又被拦，这一手之后的重问在提示末尾附上系统提示里「回答格式：」那段、把写理由半句换成 `brief` 的「简短」措辞（`memory.brief_format`，现成措辞，不新写；系统提示不动——会话里它只在首轮给，换了会带到整盘）。理由：避免误拦反复；「简短」与「不修饰」用户已定为不当变量（见上「说明理由」一行），换着用不影响数据合并。只限这一手，下一手回到默认；只由被拦触发，空回复不算（但已触发后这一手里空回复的重问也带着）；非法着的重选、一步里超过 2 次暂停都不变。本来就是 `brief`、`off` 或旧协议时什么都不变。用了兜底的那条 attempt 记 `reason_fallback: brief`；续跑从记录里数这一手被拦几次，照样接上 |

**去掉此前思考（`drop_thinking`，2026-09-30 接入，默认关）**：`--drop-thinking on`（两方）或 `--w` / `--b drop_thinking=on`（一方）。开了的一方续接时，llm-chat 发请求前把此前几轮的思考从会话里删掉，用户消息和可见回答（含理由）照带，每轮照常思考（`llm-chat --drop-thinking`，实现与实测见 llm-chat 的 SKILL.md；这一档来自 `results/missed-captures.md`：opus 续接时不带此前思考，能吃未吃明显变少）。
- **什么时候开**（2026-09-30 用户定）：模型对模型对弈，双方的思考延续方式保持一致以示公平。Claude 对 GPT：codex 这一路做不到去掉思考，所以双方都带（opus 也不开）；Claude 对 DeepSeek（DeepSeek 本来就不回传思考）可以让 opus 也开，目前不做。只有评估单个模型的棋力（对引擎等固定对手）时，才用对这个棋手最好的组织方式。用户总体看法：带着思考才是对的方式，棋手要知道自己以前怎么想（人下棋要规划，比如挖坑）。所以 opus 开了它对 astra 的 8 盘（`results/game-opus-drop-vs-astra-1.md`，方向上不差、偏好）只作研究结论，默认关不变。
- **限制**，开局前就查、报错退出，一次模型都不调：只有 Claude 棋手能开（GPT 路 llm-chat 不支持、一给就报错；DeepSeek 本来就不回传思考，开了是空操作，也按不支持处理）；只对 `memory=session` 有意义；只在 real 下。引擎、随机棋手不看这一项（两方公共开关给了也不报错）。
- **怎么传**：只在会话首轮（带 `--system` 的那次）传 `--drop-thinking`，llm-chat 把它存进会话、之后续接省略即沿用（中途加上会报错）。第一次调用被拦、会话没存下时，程序重发新会话会再带上。续跑接同一会话，不用再传。
- **理由措辞不跟着变**：两方 `reason` 不给时都是 `plain`（不修饰；此前是 `brief`，两者不当变量）。0e707cf 曾让开了的一方默认 `detailed`（前几步写下的理由是它唯一的记忆），2026-09-30 用户定放弃：**`detailed` 弃用**，原因是 opus 去掉此前思考 + 详细措辞频繁被 Anthropic 安全防护拦下（见下「风险」），不改措辞去绕。`detailed` 只为复现保留，要显式给（`--w reason=detailed`）。系统提示里「本盘在同一段连续对话中进行」那句不变（可见对话确实连续）。
- **记录**：config 的 `sides` 每方记 `drop_thinking` 和实际 `reason`，`commands` 里开了的一方多一个 `--drop-thinking`；旧记录没有 `drop_thinking`，续跑按关。开了的一方每条 `attempt` 记 llm-chat META 的 `thinking_dropped`（本次发出前删掉的思考块数；首轮 0，续接通常 1）。续接轮拿到 0 或没给，写一条 `drop_warn`（半回合、第几次、会话、`thinking_dropped`、本次运行里这方上一次调用的思考 token `prev_think`，续跑后第一步不知道记 None）并在终端提示，不中断对局。`prev_think` 为 0 时多半是上一轮本来没思考；不为 0 还拿到 0，要怀疑 claude 升级后思考换了存法、llm-chat 没删掉，抓一次发出的请求复核。棋谱每步元信息多一个 `[%dropped N]`（第四节）。
- **成本**：开了的一方第 2 步不命中缓存，之后每步多写一轮问答的缓存；输入本身因不带思考小很多。
- **被拦的风险**（`detailed` 弃用的原因）：同日另一组截断重问（opus 去掉思考 +「详细」措辞）114 次里 47 次（41%）被安全防护拦下，同样的局面用「简短」措辞 200 多次、「不修饰」84 次都一次没拦（`results/missed-captures.md`）。「去掉思考 + 不修饰」整盘里仍要留意 `flag` 数（被拦不算非法、不扣重选；一步里超过 2 次暂停）。

**着法解析**：先找「着法: 」；没有就认英文「Move: 」；再没有就取最后一个非空行（不超过 30 个字符），交给棋种的解析判合不合法。所以只回一行着法、或用英文作答都读得出来。旧协议不变（只认「着法: 」）。

**模型调用走 llm-chat**（`llmchess/chat.py`）：用户级 skill `~/.claude/skills/llm-chat` 的脚本，一个入口三路——`claude:<模型>`（claude -p）、`codex:<模型>`（GPT，短名如 sol 按 `codex debug models` 取最新一代全名，现为 gpt-6-sol）、`deepseek:<模型>`（HTTP 直连 api.deepseek.com，默认 deepseek-v4-pro，思考只有 low / high / max）。脚本只用不改；它的会话 id 记进每条 attempt，续跑照记录接上同一段对话。思考深度每次 `--effort` 显式传。config 记 `backend: llm-chat`、每方实际模型 `models`、脚本路径和内容摘要 `llm_chat`。调不通重试、撞额度等解除、停止信号、安全分类器拦截照旧沿用 `claude_cli.call`（`run` 钩子把脚本的输出折成原来的样子）。隔离与跨轮思考的实测见 `results/llm-chat-isolation.md`。
- 旧路（`claude -p` 直调、`codex exec` 无状态）原样保留，给旧记录续跑和局面题用，已有数据可以逐字复现。

## 附：核实用的桩服务

```python
# 记录 claude 发出的请求体，然后回 400。用法：python3 stub.py 18765 outdir
# 另开终端：ANTHROPIC_BASE_URL=http://127.0.0.1:18765 claude -p ... （正常参数）
import json, sys, http.server, itertools
OUT = sys.argv[2]; n = itertools.count()
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('content-length', 0)))
        with open('%s/req%02d.json' % (OUT, next(n)), 'wb') as f: f.write(body)
        msg = json.dumps({'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'stub'}}).encode()
        self.send_response(400); self.send_header('content-type', 'application/json')
        self.send_header('content-length', str(len(msg))); self.end_headers(); self.wfile.write(msg)
    def log_message(self, *a): pass
http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()
```

## 参考编号

方括号编号沿用上面那份调研的参考文献表：[1] Game Arena，[5] LLM CHESS，[6] ChessArena，[27] Benedict Brady 博客。
