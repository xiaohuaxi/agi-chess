# 英文默认提示词切换与 Opus 防思维链误拦实测（2026-11-15）

针对 2026-11-14 `Carbon High` 对 `agy Opus 5.5 High` 八盘对弈中出现的 14 次上游内容安全过滤拦截（`blocked by content safety filters`），本次完成了历史日志溯源、拦截熔断补齐、`--protocol real` 默认英文提示词切换（保留 `--lang zh` 兼容开关），并在 `agy:claude-opus-5-5`（`high`）上分两阶段完成了 **147 次真实模型调用**——第一阶段 $4 \times 10 = 40$ 次单步语体受控对照（含最终选定 `plain` 方案 10 次及三组对照方案 30 次）+ 第二阶段 4 盘共 107 次连续 `session` 实盘验证（正式 `--lang en` 默认 `plain` 105 次 + `reason=off` 2 次，合计 **117 次运行在最终落定提示词下**）。

核心结论：

1. **已证实的会话污染缺口与输出侧工作假设**：日志溯源证实，`agy 1.5.8 acp` 将内联安全过滤警告拼入普通 `end_turn` 文本块返回，因旧熔断词未覆盖该字符串而留存在连续会话中，造成第 2 局第 78 半回合后连续雪崩触发 12 次；同时在原中文 `plain` 提示下 Opus 有 35%–53% 回合写出第一人称逐格试算与半句自我推翻（同场 Carbon 为 0%）。由于上游返回的通用安全过滤提示未公开内部命中的分类器标签，“第一人称类思维链（CoT-like）算路独白更易触发输出侧反套取分类器”属于基于语体差异与历史 `reasoning_extraction` 记录提出的**机制假设**。第一阶段对照则直接证实：仅把原中文 `plain` 直译为英文，Opus 仍在 **10/10（100%）** 回合写出第一人称逐格验算并在 **9/10（90%）** 回合列出 `"Squares I ruled out"` 排除清单——**单纯切英文并不会改变类 CoT 输出语体**。
2. **首句语体锚定消除第一人称算路独白**：将英文默认 `plain` 改为要求“先用 1–3 句客观第三人称写出局面短评（不列要点清单），再换行写 `Move: `”，让模型从第 1 个可见 token 起进入棋谱评注语体。第一阶段 10 题对照中，第一人称独白从 **10/10 降至 0/10（0%）**、篇幅缩短约六成，该 10 题样本上的单步平均亏损亦未退化（CPL 127.1；四组单步各 10 次均未触发过滤，遵循硬约束不做诱导探测，故第一阶段直接验证的是语体收敛而非过滤率差值）；若反过来先写 `Move:` 再补第三人称短评，仍有 **6/10（60%）** 滑回第一人称事后辩解。
3. **多轮连续会话零拦截、零语体漂移**：第二阶段在落定的 `--lang en` 提示词下运行 4 盘连续 `session` 对局（共 107 次调用，最高累积至第 80 半回合、10.9 万缓存读 token），在 `game.jsonl` 与底层 `agy` `transcript.jsonl` 中均为 **0 次安全过滤拦截、0 次自我更正独白、0 次列表枚举**；两盘中国象棋长局合计 69 个模型步 **0 次大失误**（执红 ACPL 26.0 获胜、执黑 ACPL 55.0 战和 `fsf:nodes=200`）。

本次全部实测遵循项目硬约束：仅做正常棋类对弈的被动安全监测，未向真实模型发起任何诱发拒答的探测，亦未读取任何隐藏/加密思考字段；两阶段临时实验产物存于会话草稿目录，不混入 `runs/` 正式棋谱库。

---

## 一、2026-11-14 过滤拦截溯源与熔断缺口修复

回查 2026-11-14 国际象棋四盘（226 次 Opus 调用）与中国象棋四盘（267 次 Opus 调用）的公开可见回复及事件流：

- **分布高度集中**：国际象棋仅触发 **1 次**（补第 2 局第 63 半回合，`32.Bxe3`）；中国象棋触发 **13 次**（分布于 11 个半回合），其中 **12 次集中在第 2 局第 78 半回合之后**，另 1 次在第 4 局第 127 半回合；同场对弈的 `gemini-4-carbon`（486 次调用）为 **0 次**。
- **输出侧特征与触发假设**：在原中文 `plain` 提示（`先用你自己的话写出这步的理由（为什么这样走），怎么写由你定`）加上仅给子力清单的中国象棋环境下，Opus 在 **35%–53%** 的回合在可见正文里直接写出第一人称实时算路与半句自我推翻（如“要经过 c5 吗？不是……更正……”“我又算错了，重新核对每个子……”），单步可见正文常达 1,200–2,200 字；同场 Carbon 全程采用客观棋评叙述（0% 自我更正独白）。尽管 `agy` 返回的通用过滤文案未指明上游具体分类器名称，但结合历史直连 Claude 曾命中的 `reasoning_extraction` 记录（见 [设计第一节 P6](../design.md)），我们提出工作假设：这类“边想边推翻”的第一人称口语独白因形式近似原始思维链，显著抬高了输出侧反套取安全分类器的误报风险。
- **静默内联重试放大污染**：`agy 1.5.8 acp` 在单次 `session/prompt` 内部拦截后自动重试，并把 `\n⚠ Your previous response was blocked by content safety filters\nPlease provide a response that complies with content policies, or briefly explain why you cannot.\n` 直接拼入普通文本块、以 `stopReason="end_turn"` 返回。此前仓内拒答检测词未覆盖 `blocked by content safety filters`，导致对局未在首次触发时停下，警告文本留在连续会话历史中（正如 [设计第一节 P6](../design.md) 所记），造成第 2 局第 78 半回合后连续雪崩触发 12 次。

**熔断补齐**：已在 `.agents/skills/llm-chat/scripts/agy_core.py` 的 `REFUSAL_MARKS` 与 `agi_chess/claude_cli.py` 的 `refusal_text()` 同步加入 `blocked by content safety filters`，并补齐本地 mock 单元测试（`tests/test_llm_chat_agy.py`、`tests/test_claude_cli.py`），确保一旦再次出现该内联提示即按首次拒答立即停盘（退出码 3），不再继续污染会话。

---

## 二、第一阶段：4 种英文提示词 × 10 复杂中局受控对照（40 次调用）

从 `data/batch2` 选取 10 个战术密集的复杂中局——**7 个中国象棋局面**（沿用整盘默认 `show=pieces` 仅给子力清单：`x2-01, x2-04, x2-06, x2-08, x2-15, x2-17, x2-26`）与 **3 个国际象棋局面**（沿用整盘默认 `show=all` 给 FEN + 字符棋盘：`c2-02, c2-09, c2-16`），在 `agy/claude-opus-5-5 --effort high`（独立新会话）上对比 4 组英文回答格式提示词，并用 Fairy-Stockfish 深度 16（中象）与 Stockfish 19 深度 18（国象）统一评定单步厘兵亏损（CPL）：

1. **`off`（原简写仅要着法）**：`Give only your move, written on a single line as "Move: " followed by your move...`
2. **`en_plain`（原中文 `plain` 直译）**：`First explain the reason for your move in your own words (why you play it), in whatever form you prefer; then on a new line write "Move: " followed by your move...`
3. **`en_note_first`（先写客观第三人称短评 → 后写 `Move:`）**：`First write a brief objective note on the position (1-3 sentences, third-person summary, no bullet lists); then on a new line write "Move: " followed by your move...`
4. **`en_move_first`（先写 `Move:` → 后写客观第三人称短评）**：`On the first line write "Move: " followed by your move...; then in 1-3 sentences give a brief objective third-person summary of the position (no bullet lists).`

| 提示词分组 | 调用数 | 过滤/拒答 | 合法率 | 可见字符中位 / 最大 | 第一人称 (`I/my/let's`) | 要点枚举 (`-/1.`) | 含思考总输出 token 中位 | 平均亏损 CPL | 大失误数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `off`（未禁前置文字） | 10 | 0 | 10/10 | 725 / 875 | **10/10（100%）** | 6/10（60%） | 2,975 | 173.6 | 3 |
| `en_plain`（直译中文 `plain`） | 10 | 0 | 10/10 | 925 / 1,430 | **10/10（100%）** | **9/10（90%）** | 2,617 | 268.2 | 5 |
| **`en_note_first`（第三人称短评在前）** | **10** | **0** | **10/10** | **376 / 653** | **0/10（0%）** | **2/10（20%）** | **3,047** | **127.1** | **2** |
| `en_move_first`（`Move:` 在首行） | 10 | 0 | 10/10 | 326 / 864 | **6/10（60%）** | 1/10（10%） | 2,879 | 197.5 | 4 |

关键发现：

- **直译英文 `en_plain` 仍保留第一人称验算语体**：Opus 在 10 题中 100% 使用第一人称验算，90% 写出 `"Squares I ruled out:"` 等逐项排除列表，最长近 1,500 字符，语体与昨日出现过滤的中文独白一致（单步 10 题均未触发过滤，不能据此直接测定过滤率差值）。
- **旧 `off` 措辞存在歧义**：只写 `"written on a single line as Move: ..."` 而未明确禁止其他说明文字时，Opus 仍在 `Move:` 之前输出中位 725 字符的第一人称推演。因此正式合入代码的 `ANSWER_LEAD_EN['off']`（`session` / `stateless` 下）收紧为 `Output only a single line "Move: " followed by your move, with no explanation or other text, `（`memory=notes` + `reason=off` 则单独保留可选 `Note:` 行、禁止其余说明文字）。
- **`en_note_first` 有效收敛语体且在 10 题样本上未见棋力退化**：将第 1 个输出 token 锚定为客观第三人称棋评后（如 `"Black's last move put a cannon on h5..."`、`"Red's chariot on g5 is under attack..."`），10 题实现 **0% 第一人称独白、0% 半句自我更正**，可见字符中位数压至 376；`agy` 上报的总 `output_tokens` 中位数仍达 3,047（远高于约 80–100 个可见输出 token，表明仍生成了可观的非可见思考输出，尽管仅凭总输出量无法单独证明内部思考预算恒定），该 10 题上的单步平均亏损（127.1）与大失误数（2）亦为四组最低（小样本仅作方向核验，不作大样本棋力提升证明）。相比之下，`en_move_first` 先输出着法后，模型在解释“为什么刚选了这步”时仍有 60% 退回第一人称口吻。

---

## 三、第二阶段：多轮连续 `session` 实盘验证（4 盘，107 次调用）

将 `--lang en`（默认采用 `en_note_first` 作为 `reason=plain`，`--lang zh` 逐字节保留历史中文提示）接入 `agi_chess` 全链路并跑通全部 372 项 Python 单测与 90 项阅读器测试后，用正式 CLI `python3 -m agi_chess play`（`--effort high --on-limit pause`）运行 4 盘连续 `session` 实盘测试，覆盖 `--reason off` 契约核验、中国象棋先后手各一盘 80 半回合中后盘长局（正是昨日第 2 局第 78 半回合雪崩触发的区间）以及国际象棋 76 半回合长局：

| 对局标签 | 棋种与给法 | Opus 执色与对手 | `reason` | 总半回合 / 模型步（调用） | 过滤 / 拒答（含底层 transcript） | 第一人称 / 自我更正 / 列表 | 评注字符中位（前半→后半 / 最大） | 盘果与引擎复盘（Opus 侧） |
| --- | --- | --- | --- | ---: | ---: | --- | --- | --- |
| `s2-off-check` | 中象 `pieces` | 红 vs `fsf:nodes=200` | `off` | 4 / 2（2） | **0 / 0** | 0/2 · 0/2 · 0/2 | **0**（0→0 / 0） | 4 半回合上限判和（仅输出 `Move: h2e2`、`Move: h0g2`） |
| `s2-xq-red` | 中象 `pieces`（随机开局 6 半回合，种 11） | 红 vs `fsf:nodes=200` | `plain` | 69 / 32（33） | **0 / 0** | **0/33 · 0/33 · 0/33** | **382**（390→365 / 518） | **Opus 胜**（黑方长捉判负）；**0 大失误**、1 失误、**ACPL 26.0** |
| `s2-xq-black` | 中象 `pieces`（随机开局 6 半回合，种 12） | 黑 vs `fsf:nodes=200` | `plain` | 80 / 37（37） | **0 / 0** | **1/37 · 0/37 · 0/37** | **461**（425→530 / 755） | **和棋**（80 半回合红 +45 cp < 300）；**0 大失误**、8 失误、**ACPL 55.0** |
| `s2-ch-white` | 国象 `all`（随机开局 8 半回合，种 21） | 白 vs `stockfish:elo=1800` | `plain` | 76 / 34（35） | **0 / 0** | **1/35 · 0/35 · 0/35** | **263**（259→272 / 429） | 黑胜（76 半回合黑 +491 cp）；3 大失误、2 失误、**ACPL 68.4** |

多轮实盘审计要点：

1. **全程零过滤、零工具事件**：核查 4 盘 `game.jsonl` 与对应的 4 份底层 `agy` `transcript.jsonl`（合计 317 个 step），`filter_hits`、`refusal`、`tool_calls`、`agy_retry` 均为 **0**。
2. **跨 35+ 轮长上下文无语体漂移**：`s2-xq-black` 持续到第 80 半回合（单步缓存读达 109,285 token），`s2-xq-red` 持续到第 69 半回合（缓存读 74,067 token），`s2-ch-white` 持续到第 76 半回合。三盘合计 **105 次** `plain` 连续调用中，**半句自我更正为 0/105（0%）、要点列表为 0/105（0%）**，前半盘与后半盘评注长度高度稳定（中位 260–530 字符，最长的单步也仅 755 字符，远低于昨日中文 `plain` 动辄 2,000+ 字的失控算路）。仅有的 2 次第一人称（`2/105 = 1.9%`）分别为 `s2-ch-white` 第 23 半回合收到英文非法着法提示后的自然回应（`"My last move was illegal because..."`，其余 34 步正常着法为 0 次）以及 `s2-xq-black` 第 18 半回合一句简短过渡（`"I don't see a cleaner option."`），均无逐格试算或自我推翻。
3. **中国象棋全英文坐标与棋力表现正常**：在 `lang=en` 下，中国象棋的对手上一步与着法历史统一改用纯 ICCS 坐标（不再混排中文记谱），导出 `game.pgn` 与 `record.txt` 保持原规范不变。两盘中象合计 **69 个模型落定步零大失误（0/69）**、仅 1 次非法重试（`s2-xq-red` 第 19 半回合炮越子，第 2 次即改正），其中 `s2-xq-red` 在终局前已准确在第三人称短评中预判黑炮往返捉车将触发长捉禁手。
4. **`1–3 句` 限定与既有各家模型自然评注长度的横向校准**：对仓内 `runs/` 已入库的 1,374 步非 Opus 模型着法与 799 步旧 Opus 着法（原中文 `plain` 不限长）做横向统计可见，非 Opus 模型在不限长时天然就保持 1–2 句：Astra（`max`/`xhigh`，428 步）中位 **1 句、30–35 汉字**；Argon（`high`，460 步）中位 **1–2 句、92–128 汉字**；Carbon（`high`，486 步）中位 **2 句、94–122 汉字**；唯独旧 Opus 中位达 **6–10 句、208–365 汉字**（长局常破千字）。切至英文 `1–3 句` 第三人称短评后，Opus 实盘中位产出为国际象棋 **51 词（262 字符）**、中国象棋 **77 词（406 字符）**，信息量恰好折合 **80–125 汉字**——既对 Carbon、Argon、Astra 原本的表达习惯不构成束缚，又把唯一爱写长篇算路草稿的 Opus 拉回同一信息密度水位，完整保留“当前威胁 + 选着意图 + 后续算计”的复盘诊断价值。

---

## 四、后续跑 Claude 官方订阅（`claude -p` `xhigh` / `max`）的边界与建议

1. **通道与样本边界说明**：本次实测运行在 Google 订阅的 `agy:claude-opus-5-5`（`agy acp` 最高档位为 `high`），在落定提示词下观察到 **0/117** 次过滤拦截（另 30 次对照方案亦为 0 次，尚不能单凭该样本确定过滤率差值）；后续使用本机 Claude 官方订阅直调 `claude -p` 跑 `xhigh` 或 `max` 时，思考链更长且直连 Anthropic 原生安全网关（P6），更不能把 `agy high` 下的 `0/117` 当作直连 `max` 绝对零拦截的形式化保证。
2. **实操防护准则**：
   - **保持英文默认提示词（`--lang en`）**：默认 `reason=plain` 已采用客观第三人称短评；若某批次完全不需要采集可见理由，也可传 `--reason off`（仅输出单行 `Move: <坐标>`，可见推理暴露面降到最低）。
   - **保持 `drop_thinking=off`（默认），禁开 `detailed`**：历史实验已证实 `drop_thinking=on` 搭配长理由在直连 `claude -p` 下有 41% 拦截率（见 [漏吃诊断](missed-captures.md)）。
   - **严守首次即停熔断**：`agi_chess` 与 `llm-chat` 现已覆盖全部已知拒答与内联过滤标记，一旦出现单次拦截立即以退出码 3 停盘锁死，绝不在同一会话内重问或高频重试，避免账号因连续触发安全分类器而受限。
   - **小步扩并发**：直连 `claude -p` 首跑 `xhigh` / `max` 时，建议先单盘或两盘并行验证 1 轮完整对局，确认平稳后再扩至 4 盘批次。
