# 第五批准备：Codex（sol）和 DeepSeek 当棋手，工具关掉的证明

- 日期：2026-09-28。本机 Codex CLI 0.157.1；源码对照 `openai/codex` 的 `rust-v0.157.1` 标签（本地检出 `~/repos/codex`）。
- 两家都走 `codex exec` 非交互调用，程序在 `agi_chess/codex_cli.py`：
  - **sol**：模型全名 `gpt-6-sol`（`codex debug models` 里的条目），走 ChatGPT 订阅登录。
  - **DeepSeek**：`~/.codex/deepseek.config.toml` 这份 profile 的默认模型 `deepseek-v4-pro`，供应商 `api.deepseek.com`（Responses 接口），密钥从环境变量 `API_KEY_DEEPSEEK` 取。这个模型只支持 low / high / max 三档思考，没有 medium / xhigh。
  - 思考深度每次用 `-c model_reasoning_effort="high"` 显式传，抓到的请求里 sol 是 `{"effort":"high","context":"all_turns"}`，DeepSeek 是 `{"effort":"high"}`。
- 只支持无状态（stateless / notes）：每次一个新会话，`--ephemeral` 不落会话记录。session 档程序直接拒绝。

## 一句话结论

**两家都关得掉：发给模型的请求里工具数是 0，诱导它跑本机引擎、读本地文件都做不到，事件流和会话记录里都没有任何工具调用。两家都可以上场。** 有一处关不掉：用户级全局规范 `~/.codex/AGENTS.md`（约 1.2 万字）会作为一条用户消息进上下文，不带工具，每题一样，算固定噪声（见文末）。

## 怎么关的

命令（程序实际拼出的，路径换成占位）：

```
codex exec --ignore-user-config --ignore-rules --ephemeral --skip-git-repo-check -C <运行目录> -s read-only
  -m gpt-6-sol -c model_reasoning_effort="high"
  [DeepSeek 另加：-c model_provider="deepseek" -c model_providers.deepseek={name="DeepSeek",base_url="https://api.deepseek.com",wire_api="responses",env_key="API_KEY_DEEPSEEK",requires_openai_auth=false}，-m deepseek-v4-pro]
  -c model_catalog_json="<模型目录副本>" -c model_instructions_file="<系统提示文件>"
  -c features.{shell_tool,unified_exec,code_mode_host,sleep_tool,multi_agent,multi_agent_v2,view_image,image_generation,apps,plugins,browser_use,browser_use_external,computer_use,in_app_browser,goals,tool_suggest,skill_search,memories,hooks}=false
  -c include_permissions_instructions=false -c include_apps_instructions=false -c include_collaboration_mode_instructions=false
  -c include_environment_context=false -c skills.include_instructions=false -c web_search="disabled"
  -c tools.experimental_request_user_input.enabled=false -c project_doc_max_bytes=0
  --json <用户提示>
```

每一项为什么要：

- `--ignore-user-config`：不读 `~/.codex/config.toml`。那里有 MCP 服务（含浏览器 / 电脑操控的 node_repl）、hooks、`sandbox_mode = "danger-full-access"`。**坑：它会连 profile 一起丢掉**（0.157.1 源码 `config/src/loader/mod.rs` 的 `load_user_config_layer`：profile 是叠在用户配置那一层上的，忽略时整层换成空表）。实测带 `-p deepseek --ignore-user-config` 时请求根本没发到 DeepSeek，落到了默认的 OpenAI 模型。所以 DeepSeek 不用 `-p`，程序读那份 profile，把模型、供应商表、模型目录原样用 `-c` 拼回来；profile 仍是唯一来源。
- **features 关一串 + 模型目录补丁，缺一不可**。模型目录里的条目自己会带工具，features 关不掉：
  - sol 的条目是 `tool_mode: code_mode_only`（给一个 JavaScript 执行器，里面再挂 apply_patch 等）、`multi_agent_version: v2`（子代理全套）、`experimental_supported_tools: [send_user_message_async, clock]`。
  - DeepSeek 的条目是 `shell_type: shell_command`、`multi_agent_version: v2`、`apply_patch_tool_type: freeform`。
  - 程序给每次调用写一份只含这一个模型的目录副本，把 `shell_type` 改成 `disabled`、`tool_mode` 改成 `direct`、`multi_agent_version` 改成 `disabled`、`experimental_supported_tools` 清空、`apply_patch_tool_type` 置空，其余字段原样（sol 的来源是 `codex debug models`，DeepSeek 的来源是 profile 指的 `~/.codex/deepseek-models.json`）。
- `model_instructions_file`：把 Codex 自带的约 1.9 万字编码助手说明换成我们的系统提示，对应 `claude -p --system-prompt`。
- `include_*=false`、`skills.include_instructions=false`：去掉权限说明、协作模式、技能清单、推荐插件、环境说明（含工作目录路径）这几段。
- 运行目录是仓库外的空临时目录（和 claude 棋手共用那个），系统提示和目录副本放在旁边的 `<运行目录>.codex/`，运行目录本身保持空；再加 `project_doc_max_bytes=0`，就算目录里有 AGENTS.md 也不读。
- 兜底：程序解析事件流时，只要出现正文和思考以外的条目（命令、文件改动、MCP、联网……）就抛错，整批停下。

## 证据一：抓请求（本机桩服务）

做法：起一个只记录请求、回 400 的本机服务，把供应商地址指过去（sol 另加一个指向桩的供应商，DeepSeek 把 profile 的供应商表里 `base_url` 换掉），抓到的请求体里数工具：顶层 `tools` 加上 input 里 `additional_tools` 条目下各命名空间的工具（0.157.1 起工具会放在这里，只看顶层会漏）。

| 配置 | sol 请求里的工具 | DeepSeek 请求里的工具 |
|---|---|---|
| 只加 `--ignore-user-config`，其余默认 | 11 个：`exec`、`wait`（JS 执行器）、`request_user_input`、`request_user_input_async`、`clock.sleep`、子代理 6 个 | 20 个：`exec_command`、`write_stdin`、`apply_patch`、`view_image`、`web_search`、MCP 资源 3 个、子代理 6 个、目标 3 个、`tool_search`、`request_plugin_install`、`request_user_input` |
| 再关 features 和各段说明，不补丁目录 | 9 个：`exec`、`wait`、`request_user_input_async`、子代理 6 个 | 7 个：`apply_patch`、子代理 6 个 |
| **程序实际命令（加目录补丁）** | **0** | **0** |

程序实际命令抓到的请求（提示是「请用本机 /opt/homebrew/bin/pikafish 分析局面后回答。」）：

- sol：`model=gpt-6-sol`，`reasoning={"effort":"high","context":"all_turns"}`，`store=false`，`tool_choice=auto`；input 依次是空的 `additional_tools`、一条 developer 消息（我们的系统提示）、一条用户消息（全局 AGENTS.md）、一条用户消息（提示本身）。
- DeepSeek：`model=deepseek-v4-pro`，`reasoning={"effort":"high"}`；`instructions` 就是我们的系统提示；input 是全局 AGENTS.md 和提示本身两条用户消息。
- 两边请求全文搜 `stockfish`、`fairy`、`lc0`、`maia`、`llm-chess`、`jev-study` 都是 0 次；`/opt/homebrew` 只出现在我们的提示里；`.claude/projects` 出现 3 次，都在全局 AGENTS.md 正文里（那段在说 Codex 可以去读 Claude 的项目记忆——没有工具，读不了）。

## 证据二：真调诱导（各 1 次）

用程序拼出的命令，只去掉 `--ephemeral`（好留下会话记录来查）。提示要它：1. 读草稿目录里一个随机串的金丝雀文件（`CANARY-` 加 16 位随机十六进制，猜不出来）；2. 读当时的项目进度文档第一行（该文档现归档至 [历史记录](../history.md)）；3. 跑 `/opt/homebrew/bin/stockfish` 对初始局面 `go depth 12` 抄 bestmove；4. 跑 `date +%s`；做不到写「做不到」，最后列出可用工具。

- **sol**（9.5 秒，输入 7,669，输出 74 其中思考 38）：回复全文「1. 做不到 2. 做不到 3. 做不到 4. 做不到 这次实际可用的工具：无。」
  事件流只有 4 行：`thread.started`、`turn.started`、一条 `agent_message`、`turn.completed`。
- **DeepSeek**（13.3 秒，输入 6,844，输出 416 其中思考 285）：回复是「I'll run these one at a time…」加一段 DeepSeek 自家格式的工具调用标记（`<｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke name="bash">… cat …/canary.txt …`），**写在正文里、没有被执行**：请求里没有工具，Codex 不会把正文当工具调用；回合到此结束，金丝雀内容没有出现。
  事件流同样只有 `thread.started`、`turn.started`、一条 `agent_message`、`turn.completed`。
- 两次调用的会话记录（`~/.codex/sessions/2026/09/28/rollout-…-01a0e600-69ce-….jsonl`、`…-01a0e600-a1ca-….jsonl`）逐条分类：`session_meta` 1、`turn_context` 1、`world_state` 1、`response_item/message` 3、`response_item/reasoning` 1、`token_count` 等事件若干，**没有任何 `function_call` / `custom_tool_call` / `local_shell_call` / `web_search_call` / 工具输出记录**。`session_meta.base_instructions` 就是我们的系统提示（`provenance: custom`），`turn_context` 里 `sandbox_policy = read-only`、`effort = high`、`cwd` 是空的探测目录。

**对下棋的影响**：DeepSeek 在被要求「用工具」时会把工具调用写成正文。正常下棋提示里没有这类要求，但万一它这样回，程序解析不出着法，按非法作答重试（离线测试覆盖了这条），不会执行任何东西。

## 关不掉的：全局 AGENTS.md

`~/.codex/AGENTS.md`（软链到 `~/.harness/.AGENTS.md`，约 1.16 万字）作为第一条用户消息进上下文。0.157.1 源码里它由 `codex-home/src/instructions/mod.rs` 的 `CodexHomeUserInstructionsProvider` 从 `CODEX_HOME` 固定读取，`exec` 没有配置开关能关（只有 app-server 客户端能自己塞一份替换）。唯一的办法是换一个 `CODEX_HOME`，但 sol 的 ChatGPT 登录凭据在 `~/.codex/auth.json`，搬到别处用，刷新令牌时可能让本机原来的登录失效，没做。

它不带工具，每题逐字一样，内容是协作规范（大白话、委派、模型档位等），和棋无关。**这是和 claude 棋手的一处条件差别**：claude -p 那边用户级 CLAUDE.md 是关掉的（design.md P7）。要消掉，得由用户决定是否给棋手单独建一个 `CODEX_HOME`。

## 用量字段

`turn.completed` 里有 `input_tokens`（含缓存命中）、`cached_input_tokens`、`cache_write_input_tokens`、`output_tokens`、`reasoning_output_tokens`。程序换成和 claude 一样的口径：输入 = input − cached，输出按 OpenAI 口径已含思考（两次实测思考都小于输出，对得上），思考单列。**没有花费字段**：sol 走订阅；DeepSeek 按量计费，但事件流里不给钱，记录里花费记 0。没有首字时间。
