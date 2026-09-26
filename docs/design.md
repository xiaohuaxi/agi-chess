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
| P10 | Codex 能当另一方 | 待验证（没写，要加时再加一个棋手分支） | `codex exec` 有 `--json`、`-m`、`-c key=value`（推理档位走配置项）、`--ephemeral`、`exec resume`。**它自带 shell**，只读沙箱也能跑本机的 python-chess 和 Fairy-Stockfish，等于能用引擎。怎么把它的工具全关掉、怎么取思考 token，实施前要单独核实。 |
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
  xiangqi.py     中国象棋：规则包装（从 boards.py 搬）、终局与禁着（从 play_xiangqi.py 搬）、呈现 / 提示 / 自查 /
                 复述打分 / 着法解析（从 llm_duel.py 搬）、中文棋谱、引擎参数与坐标换算
  chess_.py      国际象棋：python-chess 包装、UCI / SAN 解析与非法原因（原因分类照搬 boards.violation 的国际象棋分支）、
                 呈现、提示、终局与自动申诉、PGN、引擎参数
tests/           纯规则部分的离线单元测试（解析、禁着、终局判定、续跑重放）
```

局面题模式（第六节组 1）和 `analyze` 还没写，做到那一批时再加。

**棋种模块的函数约定**（两个模块提供同名函数，循环按名字调用）：

```
start() -> 状态              turn(状态) -> 'w'/'b'           legal(状态) -> [着法]
banned(状态, 合法着法) -> 集合      parse(状态, 文字) -> (着法或 None, 不合法原因或 None)
push(状态, 着法)                ending(状态) -> None 或 {winner, reason}      in_check(状态)
render(状态, 这方配置) -> 本步局面正文       system_prompt(这方, 这方配置, 记忆说明) -> 文本
recite_score(状态, 回复)（只有中国象棋）     exports(状态, 配置, 终局, 统计) -> {文件名: 文本}
engine_spec(描述) -> 引擎命令与参数       to_engine(着法) / from_engine(文字)
```

状态里固定存起始局面、每步之后的 FEN、全部落定着法和记谱，判重复、续跑都靠完整历史，与给模型看多少历史无关。

- **棋手**在循环里直接分支，不做多态：
  - `claude:<模型>`：沿用上一轮命令（见 P7），`stdin` 接 `/dev/null`（否则会等 3 秒并打警告），运行目录 `runs/<tag>/cwd`（P17）。
  - `engine:<名字>[:参数]`：国际象棋 `maia-1100`…`maia-1900`（lc0 加权重，`go nodes 1`）、`stockfish[:elo=N|nodes=N|movetime=毫秒]`；中国象棋 `fsf[:nodes=N|depth=N]`（Fairy-Stockfish，`UCI_Variant xiangqi`）。每步把起始局面和全部着法发给引擎，不只发末尾 FEN；等待有上限；中国象棋出棋时用 `searchmoves` 排除会被判长将 / 长捉的着法（P15）。`boards.Engine` 是单局面分析用的（不带历史、等待没有上限），不拿来当对手；另外 boards.py 实测过 Skill Level 不可复现，弱档一律用节点数或深度。
  - `random`：随机走子，按对局种子可复现，当最低参照（LLM CHESS 用它 [5]）。
  - Codex、API 直连：没写，要加时再加一个棋手分支（P9、P10）。
- **引擎只当对手和事后裁判**。给模型的提示里永远不出现引擎的任何输出；分析在对局结束后另跑。

## 三、变量与默认值

模型相关的变量两边可以分别设（`--w 变量=值`、`--b 变量=值`，w 是先走的红方 / 白方），不设就用公共值。

| 变量 | 取值 | 默认 | 说明 |
|---|---|---|---|
| `game` | `xiangqi` / `chess` | — | |
| 棋手 | `claude:<模型>` / `engine:<名字>[:参数]` / `random`（见第二节） | `claude:opus` | `--red`/`--white`、`--black` |
| `effort` | medium / high / xhigh / max | medium | 与上一轮一致，方便对照；实验里扫全档 |
| `memory` | `stateless` / `notes` / `session` | stateless | 见下 |
| `view` | 国际象棋：`fen`、`ascii`、`pieces`、`pgn`；中国象棋：`grid`、`pieces`、`fen`、`cells`、`board` | 国际象棋 `fen,ascii`；中国象棋 `grid,pieces,fen` | 逗号分隔、按序拼 |
| `history` | -1 全部 / 0 不附 / N 最近 N 个半回合 | -1 | 上一轮 C/D/E 只附 20 步、A/B 附全部，两者混在一起了；这次统一全部 |
| `legal` | `none` / `list` | none | 测棋力时可以开，报告里分开写 [5][6] |
| `selfcheck` | on / off | off | 上一轮开了没见效；作单独变量。两种棋的自查文字各写各的 |
| `recite` | on / off | off | 先复述局面再走，程序逐格比对。复述格式和打分目前只有中国象棋有 |
| `retries` | 整数 | 3 | 非法重试上限，用完判负（和 Game Arena 一致 [1]） |
| `timeout` | 秒 | 3600 | 单次 `claude -p` 的超时（`--timeout`，整盘记进 config、resume 沿用；局面题同名参数）。第一批写死 1800，max 档撞了 7/120 次 |
| `max_plies` | 整数 | 200 | 研究设的上限，到了判和；和棋规里的限着（中国象棋一百个半回合无吃子、国际象棋五十回合）分开记终局原因 |

两种棋的系统提示在「回答格式」那段要求「请用中文回答。」（第二批块 0.1，整盘和局面题共用；第一批国际象棋里英文作答和答错常一起出现）。

**思考与计划的延续（`memory`）**：

- `stateless`：每步新开一次，看不到自己之前的任何东西。主流做法 [1][5]。
- `notes`：每步回复最后要求多写一段便条（不超过约 150 字，写什么由它定；不列要写的内容，原因见 P18），程序把上一步的便条原样放进下一步提示；默认只带最近 1 条，`--notes-keep N` 可以多带。实测模型自己会写意图、预料的应着和下一两步打算。个人博客 [27] 的"跨步保留部分推理记录"就是这类做法，但没有对照。
- `session`：每方一条连续会话，第一步 `--session-id`，之后 `--resume`，平台把之前每一轮的思考块原样带着（P5）。每轮仍给完整局面（默认），这样测到的是"计划延续"而不是"记盘能力"；`--session-view move` 只告诉对手走了什么，就成了盲棋压力测试 [6]。
- 两条硬约束：提示里**不要**让它"回忆 / 复述上一轮的思考"（会被拦，P6）；便条的措辞用"给下一步的自己留话"，别用"总结你的推理"。

## 四、记录格式

每盘一个目录 `runs/<tag>/`（入 `.gitignore`），一行一条 JSON，和上一轮兼容并补字段：

- `config`：全部变量、两边系统提示、完整命令行、本机 Claude Code 版本、引擎名与参数、代码 commit。
- `attempt`（每次调用一条）：半回合号、哪方、第几次尝试、提示原文、回复原文、解析出的着法、是否合法及原因、便条文本、复述得分；`usage` 展开成 `in`（无缓存输入）、`cache_read`、`cache_write`、`out`、`think`、`text_out = out − think`；`cost`、`duration_ms`、`ttft_ms`、`session_id`、服务端模型串、`stop_reason`、`api_error_status`；`claude` 字段存返回 JSON 原样。
- `move`：落定的一步、记谱、是否将军、本步各次尝试的合计用量。
- `flag`：安全分类器拦截（`stop_reason` 为 `refusal` 或结果正文含 `safeguards flagged`，或 `session` 模式下会话记录里出现 Claude Code 自动插入的那条"被安全分类器拦下"消息）单独记一条，并在报告里单列；这类不算非法着法、不扣重试次数。正文为空的回复（冒烟见过一次：`end_turn`、有思考、正文空）同样不扣重试次数，另计"空回复"。一步里被拦或空回复超过 2 次就暂停，交给人看。
- `call_fail`：一次 `claude -p` 超时或调不通（非零退出、回的不是 JSON），重试前记一条：半回合号、哪方、第几次着法尝试、第几次调用、是否超时、退出码、用时、stderr / stdout 末尾、下次重试前等几秒；局面题另带题号 / effort / 遍 / 档名。撞额度不记这条（记 `pause`）。
- `pause` / `resume` / `forfeit` / `end`（结果、每方合计与中位数：调用数、非法数、每步输入/输出/思考 token、用时、花费）。
- 不管给模型的 `history` 设多少，记录里都有起始局面和全部落定着法；续跑时按它重放，重复局面照样判得出。
- 结束时另写 `record.txt`（棋谱加统计）；国际象棋另出 `game.pgn`，中国象棋的 `record.txt` 用中文记谱。终局原因用棋种自己的说法。

`analyze` 读这个目录，逐步给出"走前最好能得多少、走后剩多少、亏了多少"、大失误 / 失误、规则判定（白送子、漏吃、漏杀），输出 `analysis.jsonl`。口径沿用上一轮（中国象棋截断 ±1000、只看未分胜负的步），国际象棋另加按胜率换算的亏损（lichess 式），并算平均每步亏损。

## 五、对手模式

- **模型对模型**（自对弈或不同设置对打）：看不同做法，但两边都会犯错，结果噪声大，主要看逐步亏损而不是胜负。
- **模型对固定引擎配置**（固定引擎、固定节点数 / 深度 / 限 Elo，不暗示精确分数）：模型每步照常调用，引擎只负责回应；这是本研究的主力模式，因为对手恒定，胜负和逐步亏损都能比。
  - 国际象棋按从弱到强排一架梯子：`random` → Maia-1100 → Maia-1300/1500 → Stockfish 限 Elo。先用 Maia：它像人、强度有公开对照（ChessArena 里没有通用模型赢过 Maia-1100 [6]），Stockfish 限强在低分段走法不像人。要换算大致分数，就在梯子上找模型胜率约 50% 的那一档，每档至少 10 盘；只有一两盘的结果只能说"明显高于 / 低于"某一档。
  - 中国象棋只有 Fairy-Stockfish，限节点数或深度造几档，当相对旋钮用，不报分数（P13）。
- 引擎每步给固定时间或节点数（Maia `nodes 1`；Stockfish 限强每步 0.1–0.5 秒），写进 config。

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
- **Codex 能用引擎**（P10）：接 Codex 前必须先证明它调不了本机的棋库和引擎，否则不能当棋手。
- **Elo 换算很粗**：Fairy-Stockfish 限强的标定未核实，Maia 是"像某分段的人"而不是精确标尺，几盘结果只能给区间。和公开数字对照时要写清对手和条件不同。
- **会话越长越贵越慢**：`session` 模式 100 个回合后每步输入可能到几十万 token（大部分走缓存）。1M 上下文装得下，但要盯住额度。
- **看不到思考原文**（P4）：昏招归因只能靠它写出来的正文和便条；如果以后要读思考摘要，只能走 API 直连。

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
