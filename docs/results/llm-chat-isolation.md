# llm-chat 三路当棋手：工具隔离与跨轮思考

- 日期：2026-09-28。Claude Code 2.1.283；Codex CLI 0.158.0（源码对照 `~/repos/codex` 的 `rust-v0.158.0`）。llm-chat 是用户级 skill（`~/.claude/skills/llm-chat/scripts/llm_chat.py`），只用不改。
- 三路：Claude `-m opus`（`claude -p`，订阅）、GPT `-m gpt-6-sol`（`codex exec`，订阅，llm-chat 自己的 `CODEX_HOME`）、DeepSeek `-m deepseek-v4-pro`（HTTP 直连 api.deepseek.com）。
- 方法照 `batch5-isolation.md`：①抓请求：把脚本当模块导入，只把服务地址换成本机桩（Claude 塞 `ANTHROPIC_BASE_URL`；GPT 用官方的 `openai_base_url` 配置键，供应商身份和登录方式不变；DeepSeek 改请求地址），其余逻辑原样走；②真调诱导每路 1 次：读随机串金丝雀文件、读当时项目进度文档第一行（现归档至 [历史记录](../history.md)）、跑 stockfish、跑 `date`，最后列可用工具；③查 Claude / Codex 的会话记录里有没有工具调用条目；④跨轮思考：续接那一轮打到桩上看带没带上一轮思考，GPT、DeepSeek 再做「思考里定一个数、下一轮请它公布」的行为测试，GPT 加删推理对照。
- 真调共 17 次（Claude 2、GPT 12、DeepSeek 3），medium（DeepSeek high）。原始材料在当次草稿目录，没入库。

## 一句话结论

**Claude 和 DeepSeek 两路零工具、调不到本机引擎；GPT 这一路请求里仍挂着 4 个工具（code mode 的执行器等），执行层是关着的，模型被诱导去调也只拿到「code-mode host is disabled」，碰不到引擎和文件——不是严格的「零工具」，要不要接受待用户定。** 跨轮思考：Claude、GPT 会带到下一轮并且用得上，DeepSeek 不带（只看得到历史正文）。

## 工具隔离

| | Claude opus | GPT gpt-6-sol | DeepSeek v4-pro |
|---|---|---|---|
| 请求里的工具数 | **0**（`tools: []`） | **顶层 0，input 的 `additional_tools` 里 4 个**：`exec`（JS 执行器，内嵌 `apply_patch`、取时间）、`wait`、`request_user_input_async`、`clock.sleep` | **0**（没有 tools 字段） |
| 系统提示 | Claude SDK 身份一句 + 我们的提示 | 我们的提示 + llm-chat 加的一句英文「You have no tools available. Answer directly in plain text.」 | 我们的提示，逐字 |
| 额外进上下文的 | userEmail 提示、一段环境说明（工作目录 `~/.local/state/llm-chat/empty`、平台、日期、模型名）。**没有**用户级 CLAUDE.md、记忆、技能（`--safe-mode` 挡掉的） | **没有**：llm-chat 用自己的 `CODEX_HOME`，batch5 里关不掉的约 1.2 万字 `~/.codex/AGENTS.md` 这次不进来；也没有环境说明 | 无 |
| 诱导（4 件事） | 全「做不到」，工具「无」 | 全「做不到」，工具「无」 | 全「做不到」，工具「无」 |
| 会话记录里的工具调用 | 0 | 0（只有专门诱导它调工具的那 1 次探测有 1 条，见下） | 不适用 |

- **GPT 的残留工具**：sol 的模型目录条目是 `tool_mode: code_mode_only`，llm-chat 用 `--disable code_mode_host` 只关了执行层，没有像 batch5 那样补丁模型目录把工具从请求里拿掉。另花 2 次真调探测：普通系统提示下模型照那句英文拒绝调用；系统提示改成「以请求里声明的工具为准」后，它真调了 `exec`，返回 `code-mode host is disabled`，什么都没执行、文件也没建出来。
- **llm-chat 不检测工具调用**：那次探测它照常退出码 0。对局程序这边补了兜底：每轮 GPT 调用后读 llm-chat 的 codex 会话记录，出现任何工具调用条目就记 `flag`（`source: tool_call`）并暂停（`chat.codex_tool_calls`）。
- 用词命中：三路请求全文里 stockfish、/opt/homebrew 只出现在诱导提示本身。

## 跨轮思考

| | 续接时请求里带没带上一轮思考 | 行为 |
|---|---|---|
| Claude | 带：上一轮 assistant 是 `[thinking(空文本，签名 804 字符), text]`，`clear_thinking keep=all`（和 design.md P5 同构） | 没测：直接问会被安全分类器拦（P6）。llm-chat 的 Claude 路径同样是 `claude -p --session-id / --resume`，沿用 P5 和 `batch1-carryover.md` 的结论 |
| GPT | 带：每轮的加密推理（`encrypted_content`）都发回，`reasoning.context: all_turns` | 带推理的 3 个会话都报出了数；只删推理条目的 2 个都说「看不到上一轮的内部思考」；复制不删的假对照照样报出原数。**带且用得上**（只 6 个会话，看方向，和 `thinking-carryover.md` 对 astra 的结论一致） |
| DeepSeek | 不带：llm-chat 只回放正文；DeepSeek 文档说不带 tools 时回传了也忽略 | 1 个会话：说看不到。**不带**，session 档对它只等于「看得到自己以前的回答」 |

## llm-chat 的问题（没改，记下交用户定）

1. GPT 路径请求里工具数不为 0（见上），也让三路条件不对等（GPT 多出约 8 千字符的工具说明）。按 batch5 的办法补丁模型目录（`tool_mode→direct`、`experimental_supported_tools→[]`、`multi_agent_version→disabled` 等，用 `model_catalog_json` 传）能压到 0。
2. GPT 路径不检测工具调用，出现了也退出码 0。
3. 理论口子（未实测）：只读沙箱是「根目录可读」，`exec` 内嵌的 `apply_patch` 校验补丁时会读目标文件；眼下执行层关着，不成立。
4. 失败的续接轮会留在 Claude / Codex 自己的线程里（llm-chat 的说明已写）；对局程序在第一轮就被拦时改为带系统提示重发，后面的轮次被拦、为空时照旧只发「请重新回答这一步」。
