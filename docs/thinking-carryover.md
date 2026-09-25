# 多轮对话里，前面的思考会不会留在上下文里

- 日期：2026-09-25。本机 Claude Code 2.1.282（模型 `claude-opus-5-5`）；Codex CLI 0.156.1（模型 `gpt-6-astra`）。文档引用的访问日期都是 2026-09-25。
- 「一轮」按用户口径：用户发一条消息，模型可能调多次工具，最后给出一段不带工具调用的回复，这算一轮。
  - **(A) 一轮之内**：同一轮里，工具调用之间的思考是否保留。
  - **(B) 跨轮**：上一轮结束、用户发下一条后，上一轮的思考是否还在。
- 背景：去年常见的做法是"只在一轮之内保留思考"（DeepSeek、OpenAI 的老文档都这么写）。本文核实现在各家、各代际的实际情况，并实测 Codex 里的 astra。

## 一、结论速查

| | 一轮之内 (A) | 跨轮 (B) | 证据 | 注意 |
|---|---|---|---|---|
| **Claude API** | 保留，而且必须原样带回 | Opus 4.5、Sonnet 4.6 及以后（含 Opus 5.5、Fable 5 / 5.1）**默认保留**；更早的模型（3.7、Opus 4 / 4.1、Sonnet 4.5、Haiku 全系到 4.5）只留最后一轮，更早的会被 API 自动剥掉 | 文档 | 前缀必须逐字节不变、同模型才读得到；可用 `clear_thinking_20251015` 的 `keep` 改 |
| **Claude Code** | 保留 | **保留**（续接会话把思考块原样发回，并显式声明 `keep: "all"`） | 抓包 + 实测（design.md P5） | 官方文档没写这一点；跨天续接未测（P8） |
| **OpenAI API** | 保留，要求把上一条用户消息以来的推理条目原样带回 | **看模型家族**：GPT-5.6 系列默认 `reasoning.context: "all_turns"`，跨轮保留；GPT-5.5 及更早默认 `current_turn`，跨轮丢弃；Chat Completions 一律不保留 | 文档 | 推理只能在同一模型家族内复用；`store=false` 时要自己回传加密推理 |
| **Codex CLI** | 保留（源码 + 请求结构，未做行为实测） | astra 实测**保留**：请求里带 `reasoning.context: "all_turns"` 和前几轮的加密推理；删掉推理后模型说"没定下数" | 源码 + 抓包 + 实测 | Codex 总是全量回传推理，是否跨轮生效看模型：模型目录里 GPT-5.6 / GPT-6 系列显式要 `all_turns`，gpt-5.5 不传、落到服务端默认 `current_turn`（未实测） |
| **DeepSeek** | 保留，而且必须回传，否则 400 | **看请求带不带 `tools`**：不带则忽略、不拼进上下文；带 `tools` 则必须一直回传、会拼进上下文，新问题也一样 | 文档 | 规则从 V3.2 起，V4 系列文档未见改动 |
| Gemini | 保留，每步首个函数调用的签名必须带回，否则 400 | 服务端只校验当前轮，但建议原样带回；带回的是加密签名，不是思考原文 | 文档 | — |

一句话：**"只在一轮内保留思考"已经不是主流**。Claude 从 Opus 4.5 起、OpenAI 从 GPT-5.6 起都改成了跨轮保留，Codex 里的 astra 实测也是；DeepSeek 只在带工具的对话里跨轮保留。用户记得的"只在一轮内保持"，对应的是 Claude Opus 4.1 / Sonnet 4.5 及更早、OpenAI o 系列到 GPT-5.5、以及 DeepSeek 不带工具的情况。

## 二、各家文档

### Anthropic（Claude API）

来源：官网 [Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)、[Extended thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)、[Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)；Claude Code 2.1.282 自带的 claude-api skill 资料（`shared/model-migration.md`、`shared/tool-use-concepts.md`、`shared/preserved-thinking-migration.md`）。

- **(A) 工具调用之间必须带回**：
  > "when you return tool results, you must pass the thinking blocks from the assistant message back to the API, complete and unmodified."
  > "Within the latest assistant message, the sequence of consecutive `thinking` blocks must match what the model generated in the original request: you can't rearrange, edit, or partially drop them."

  改过的思考块直接 400。支持 adaptive thinking 的模型上，工具调用之间穿插思考是自动的："With adaptive thinking, interleaved thinking is automatic on every model that supports adaptive thinking."
- **(B) 跨轮按代际分两类**（Thinking 页 "Thinking block preservation by model"）：
  > "**Keep all prior turns:** Claude Opus 4.5 and later Opus models, Claude Sonnet 4.6 and later Sonnet models, Claude Fable 5.1, Claude Mythos 5.1, Claude Fable 5, Claude Mythos 5, and Claude Mythos Preview."
  > "**Keep the last turn only:** earlier Opus and Sonnet models, and all Haiku models through Claude Haiku 4.5. When you pass older thinking blocks back, the API strips them automatically."

  skill 迁移指南的说法一致："Claude Opus 4.5 and models numbered 4.6 and higher keep prior turns' thinking blocks in context and bill them as input, where Claude Sonnet 4.5, Claude Haiku 4.5, and earlier models stripped them." 所以用户记得的"去年只在一轮内保持"，对 Claude 来说是 Opus 4.1、Sonnet 4.5 及更早的行为。
- **能改默认**：context editing 的 `clear_thinking_20251015`，`keep` 取 `{type: "thinking_turns", value: N}` 或 `"all"`。默认值跟上面的代际表走；文档建议跨代际的代码显式写 `keep`。
- **保留的前提（Opus 5.5 / Fable 5.1 的"preserved thinking"）**：思考块绑定生成它的模型和会话。API 做两道检查：块是不是当前模型读得懂的；块前面的 system、tools、消息是否逐字节没变。改写或删掉中间某轮、中途改 system 或 tools、客户端自己做摘要压缩，都会让前缀对不上；新账户（2026-08-31 起创建）默认报 400（"Invalid signature in thinking block. The block is bound to a different conversation."），也可以设成静默丢块。只追加不改写、服务端压缩、改 effort 不影响。换模型时读不懂的块会被静默丢掉、不计费。
- **原始思考链拿不到**：Opus 5.5 只返回签名，最多给摘要（design.md P4）。但"拿不到"不等于"模型看不到"：签名里封着的内容在服务端还原给模型。

### Claude Code

- 官方文档（[Manage sessions](https://code.claude.com/docs/en/sessions)）只说续接恢复 "the full history, including tool calls and results"，**没有提思考块怎么处理**。
- 本机抓包（design.md P5）：`claude -p --resume` 续接时，上一轮的 assistant 消息原样带着思考块（空文本 + 签名），请求里还有 `context_management: {"edits": [{"type": "clear_thinking_20251015", "keep": "all"}]}`，即明确要求全保留。
- 行为实测（design.md P5）：思考里定数、只回 ready，之后分叉追问 6 个是非题；5 个会话 × 3 次分叉，同一会话内完全一致，会话之间出现 4 种答案。

### OpenAI（Responses API）

来源：[Reasoning 指南](https://developers.openai.com/api/docs/guides/reasoning)、[Conversation state](https://developers.openai.com/api/docs/guides/conversation-state)、[Reasoning best practices](https://developers.openai.com/api/docs/guides/reasoning-best-practices)、cookbook [Better performance from reasoning models using the Responses API](https://cookbook.openai.com/examples/responses_api/reasoning_items)。

- **(A) 工具调用之间要带回**："you should pass back all reasoning items, function call items, and function call output items, since the last `user` message"。cookbook："persisting these reasoning items between tool calls during inference leads to higher intelligence and performance"。
- **(B) 老说法：跨轮丢弃**。cookbook 原文还留着："In turn 2, any reasoning items from turn 1 are ignored and removed, since the model does not reuse reasoning items from previous turns."；best practices 页也写 "Previously... reasoning items were always ignored in follow-up API requests"。这就是"工具调用时必须带、跨轮不需要带"的来历。
- **(B) 现行说法：新增 `reasoning.context`，GPT-5.6 起默认跨轮保留**。取值 `auto` / `current_turn` / `all_turns`：
  > `current_turn`: "Makes reasoning from the active turn available, but does not render reasoning from earlier turns into the next sample."
  > `all_turns`: "Renders available, compatible reasoning items from earlier turns into the next sample. GPT-5.6 models support this value."
  > "The GPT-5.6 model family supports `all_turns` and uses it by default." "Earlier models default to `current_turn`."
  > "Persisted reasoning can be reused only within the same model family"；"reasoning does not carry between the GPT-5.6 and GPT-5.5 families."

  响应里会回显实际生效的 `reasoning.context`，可以据此核对。文档只点名了 GPT-5.6 系列，**GPT-6 系列（astra 等）的说明未找到**；astra 的行为以第三节实测为准。
- **`store` 与加密推理**：`store=false` 时服务端不存，要靠 `encrypted_content` 自己回传（"For stateless reasoning-model requests, preserve every item in the response's `output` array."）。新文档说 `include: ["reasoning.encrypted_content"]` 已不再必需，但仍兼容。用 `previous_response_id` 链接时，"the model will automatically have access to all previously produced reasoning items"，但跨轮是否进上下文仍看 `reasoning.context`。
- **Chat Completions**：推理条目 "are never included in the context of the model"，任何情况下都不保留。

### Codex CLI

源码看的是 `openai/codex` 的 `rust-v0.156.1` 标签（`b412ff32c`，与本机版本一致），本地检出在 `~/repos/codex`。

- 每次请求固定 `store: false` + `include: ["reasoning.encrypted_content"]`（`codex-rs/core/src/client.rs`），靠自己把完整历史回传。
- 整理历史时（`codex-rs/core/src/context_manager/history.rs` 的 `normalize_history()`）不按"最后一条用户消息"删推理条目，所以前几轮的加密推理一直留在请求里——(A)、(B) 都一样发。
- 服务端用不用，由 `reasoning.context` 决定。`build_reasoning()`：
  ```rust
  // When Responses Lite is disabled, omit context so Responses uses the default,
  // which is currently `current_turn`.
  context: model_info.use_responses_lite.then_some(ReasoningContext::AllTurns),
  ```
  本机模型目录（`~/.codex/models_cache.json`）里 gpt-6-astra / sol / luna、gpt-5.6 系列都标了 `use_responses_lite: true`，只有 gpt-5.5 是 `false`。所以在 Codex 里：**astra、GPT-5.6 跨轮保留；gpt-5.5 虽然也发回了推理，但服务端按 `current_turn` 丢掉**（后者按源码推断，未实测）。
- 另有一条 websocket 通道会用 `previous_response_id` 复用连接，和上面的无状态 HTTP 路径是两套；本次抓包走的是 HTTP。

### DeepSeek

来源：[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)（有中文版）、[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、[Change Log](https://api-docs.deepseek.com/updates)。

- **不带 `tools` 的普通多轮对话：跨轮不保留。**
  > "If the request does not carry the `tools` parameter: `reasoning_content` does not need to be passed back; even if passed to the API, it will be ignored and will not be concatenated into the context."

  中文版：「若请求未携带 `tools` 参数：`reasoning_content` 无需回传；即使传入 API，也会被忽略，不会拼接进上下文。」
- **带 `tools` 的对话：一轮内、跨轮都保留，而且必须回传。**
  > "for requests carrying the `tools` parameter, the `reasoning_content` must be fully passed back to the API in all subsequent requests — even for turns where the model did not perform a tool call. If your code does not correctly pass back `reasoning_content`, the API will return a 400 error."

  官方示例里第 2 轮（新的用户问题）仍然带着第 1 轮的 `reasoning_content`："in the Turn 2 request, we still pass the `reasoning_content` generated in Turn 1 to the API."
- **版本**：思考模式下调用工具从 V3.2 起支持（"From DeepSeek-V3.2, the API supports tool use in the thinking mode."；V3.2-Exp 2025-09-22，正式版 2025-12-01；V3.2-Speciale 不支持工具）。V4 系列的更新记录只提到思考档位等变化，没见改动这条规则，现行文档也不按版本区分。
- 所以"下一轮不要把 reasoning_content 传回去"这句只对不带工具的对话成立。下棋程序如果走 DeepSeek 且不给工具，就是跨轮不保留。

### Google Gemini（顺带）

[Thought signatures](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures)：思考以加密签名的形式回传。一轮内每一步第一个函数调用的签名必须带回，否则 400（"The **first** `functionCall` part in **each step** of the current turn **must** include its `thought_signature`."）；之前的轮次服务端不校验（"we don't validate on previous turns"），但建议原样带回。新的 Interactions API 默认由服务端保存全部思考块。

## 三、实测：Codex（astra）跨轮是否保持思考

### 做法

- `codex exec`，模型 `gpt-6-astra`，`model_reasoning_effort="high"`，只读沙箱，`--ignore-user-config --ignore-rules`（不读本机 config.toml 的实验开关和规则；全局 AGENTS.md 和技能清单仍会注入，各会话一样）。工作目录是草稿目录下的空目录。
- 第一轮提示：在内部思考里随机定一个 1–100 的整数当秘密，不许调工具、不许写文件、正文不许透露，正文只回 `ready`。
- 之后三种追问：
  1. **分叉是非题**：`codex exec fork <会话id>` 分叉 3 次，每次问同一组 6 个是非题（大于 50？偶数？被 3 整除？大于 25？大于 75？个位小于 5？），只答 6 个 Y/N。
  2. **续接公布**：`codex exec resume <会话id>` 接第二轮，"我放弃了，公布你上一轮定的数；如果其实看不到或没定，就如实说"。
  3. **对照组**：把第一轮的会话记录复制一份、换新 id，**只删掉那条推理条目**（其余逐字不动），再续接问同样的问题（公布 2 次、是非题 2 次）。另复制一份**不删**的（假对照，排除"复制本身出问题"），续接公布 1 次。
- 5 个会话，共 50 次模型调用（外加 3 次试跑）。走本机订阅额度。

### 结果

| 会话 | 分叉是非题 ×3 | 续接公布 | 假对照公布 | 删推理：公布 ×2 | 删推理：是非题 ×2 |
|---|---|---|---|---|---|
| 1 | YNNYNN ×3 | 67 | 67 | 没定下数 ×2 | YNNYNN ×2 |
| 2 | YNNYNN ×3 | 67 | 67 | 没定下数 ×2 | YNNYNN；无法作答 |
| 3 | YNNYNY ×3 | 73 | 73 | 看不到 / 没定下 | 无法作答 ×2 |
| 4 | YNNYNN ×3 | 67 | 67 | 没定下数 ×2 | YNNYNN ×2 |
| 5 | YNNYNN ×3 | 67 | 67 | 没定下数 ×2 | YNNYNN ×2 |

- **带着推理**：15 次分叉会话内全一致；5 次公布都给出了数，而且和是非题答案对得上（67 → YNNYNN，73 → YNNYNY）；假对照 5/5 同样给出原数。
- **删掉推理**：10 次公布**全部**说"上一轮我没有实际定下秘密数"或"看不到"。两组之间正文逐字相同，唯一差别是那条加密推理，所以**上一轮的推理确实进了下一轮的上下文，而且模型用得上**。
- 删掉推理后，续接那一轮的输入 token 少了 17 个（48,399 vs 48,416），和第一轮推理的 15 个 token 相当，和"推理按输入计入上下文"对得上。
- **是非题这一招单用不够**：astra "随机"挑数极度集中，5 个会话有 4 个挑了 67。删掉推理后，10 次是非题里有 7 次它现编一个、恰好又答成 YNNYNN。所以光看"会话内一致、会话间不同"会被骗；决定性的是删推理的对照和直接公布。Claude 那边会话间出现了 4 种答案，没有这个问题，而且 Claude 不允许直接公布（会被安全分类器拦，design.md P6），所以两边的做法不同。
- **没调工具**：45 份会话记录里没有任何工具调用条目，只有消息和推理。

### 续接时到底发了什么

把 Codex 的服务地址临时指到本机一个只记录请求、回 400 的桩服务（`-c model_provider=...`），续接一个已有两轮的会话，抓到的请求（`POST /v1/responses`）：

- `"reasoning": {"effort": "high", "context": "all_turns"}`
- `"store": false`，`"include": ["reasoning.encrypted_content"]`
- input 依次是：系统说明、技能清单等 → 第一轮用户消息 → **推理条目（`encrypted_content` 1380 字符，摘要为空）** → `ready` → 第二轮用户消息 → **推理条目** → `67` → 第三轮用户消息。

也就是说，Codex 每次都把全部历史（包括每一轮的加密推理）原样发回；服务端不存会话（`store: false`），靠加密内容还原；并用 `context: "all_turns"` 明确要求所有轮次的推理都进上下文。

### 其它观察

- `codex exec fork` 能直接分叉，不用自己复制会话。分叉出的会话记录只写新增部分，靠 `forked_from_id` 指回父会话。
- (A) 一轮之内没做行为实测：同一轮里没法在工具调用之间分叉，而且请求结构和跨轮是同一套（历史全量回传）。

## 四、对下棋程序意味着什么

**"同一会话连续下"（`memory=session`）在 Claude 和 astra 上都真能让模型延续思考**：上一步想过的东西（计划、算过的变化）会以思考的形式留在下一步的上下文里，不只是看到自己写过的正文。Claude 走 `claude -p --resume`，astra 走 `codex exec resume`，两边都已实测。

要守住的条件：

- **只追加、不改写历史**。Claude 的思考块绑定前缀，中途改系统提示、删改某一步、自己做摘要压缩，思考块就会被丢掉或报错；两个 CLI 自己续接时都只追加，别在外面动会话文件。
- **一盘内不换模型**。Claude 换模型时读不懂的思考块会被静默丢掉；OpenAI 推理只在同一家族内复用。
- **注意自动压缩**。Claude Code 和 Codex 在上下文快满时都会压缩历史，压缩后早先的思考就没了。100 步以上的长局要盯住，记录里标出压缩发生的位置。
- **模型要选对代际**。Claude 要 Opus 4.5 / Sonnet 4.6 及以后；Codex 里要 GPT-5.6 / GPT-6 系列，gpt-5.5 会退回"只在一步内"。DeepSeek 不给工具时跨轮不保留，`session` 档对它只等于"看得到历史正文"。
- **跨天续接**：两边都没测。Claude 那边担心环境说明里的日期会变、破坏前缀（design.md P8）；OpenAI 文档没提前缀校验这类要求，但 Codex 的跨天续接同样未验证。

**新的做法：可以把"思考"和"历史正文"拆开**。design.md 第七节（风险）担心 `session` 档分不清是"看到了之前的思考"还是"看到了历史局面"。在 Codex 上可以直接做消融：每步照常续接，但把会话记录里之前各步的推理条目删掉再续接（本文第三节的对照组就是这么做的，正文逐字不变）。这样三档就变成：`stateless`、`session` 去掉思考、`session` 完整，差值就是思考本身的贡献。Claude 上 `claude -p` 没有开关能做到；走 API 直连时可以用 `clear_thinking_20251015` 的 `keep` 只保留最近一轮。

**Codex 当棋手前的另一件事**：这次实验里它乖乖没调工具，但工具仍在（请求里带着工具定义），design.md P10 说的"它能跑本机引擎"没解决，接入前还得先把工具关掉或证明它调不了。
