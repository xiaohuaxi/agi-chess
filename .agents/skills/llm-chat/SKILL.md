---
name: llm-chat
description: Plain-text, multi-turn chat with another model (DeepSeek, Grok, Gemini, Claude, GPT, any OpenRouter id) through one script, with no tools; Gemini via agy also takes attached audio, video, image and PDF files. Use when you need another model to generate or discuss text or to describe media; not for handing off an agent task (use codex-run or agy-run) or for built-in subagents.
---

# LLM Chat

`scripts/llm_chat.py` sends one user message to a model and prints the answer. It is plain text generation: the model gets no tools, no files, and no project rules, and nothing runs as an agent. The one exception is `--attach` on agy models: the model may open exactly the attached files. Sessions let you continue the same conversation over several calls.

Use this when a task needs another model's words: a second opinion, a draft, a translation, a persona reply. When the other model must look around files on its own, run commands, or edit code, use `codex-run` or `agy-run` instead.

## Invoke

The user message is read from stdin, so it never shows in process arguments. The first turn needs a system message.

```bash
printf '%s' "$question" | python3 <this-skill>/scripts/llm_chat.py -m x-ai/grok-4.7 --system "You are a careful reviewer."
printf '%s' "$follow_up" | python3 <this-skill>/scripts/llm_chat.py -m x-ai/grok-4.7 --session <session-id>
```

Options:

- `-m, --model <id>`: required on every call; see routing below.
- `--system <text>` or `--system-file <path>`: required on the first turn, pick one. Nothing else is added: no AGENTS.md or other rules are read.
- `--session <id>`: continue an existing session (the id printed by the first turn).
- `--effort <level>`: reasoning effort, passed through as-is (e.g. `low`, `medium`, `high`; DeepSeek accepts `low`/`high`/`max`).
- `--max-tokens <n>`: output cap. Reasoning tokens count toward it on the HTTP routes, so a small cap can leave the answer empty, which is an error. Claude gets it via `CLAUDE_CODE_MAX_OUTPUT_TOKENS`; GPT does not support it and the call fails if it is set.
- `--timeout <seconds>`: default 600 (xAI is sometimes slow).
- `--attach <path>`: agy models only, repeatable, on any turn. A file for the model to read: audio (wav, mp3, m4a, flac, ogg, ...), video (mp4, mov, ...), images, PDF, text. See "No tools, no web" for what the model may do with it.
- `--drop-thinking`: later turns resend the earlier user messages and visible answers but not the model's thinking from those turns. Each turn still thinks as usual. Set it on the first turn; see "Dropping earlier thinking" below.

## Output

On success (exit 0):

- stdout: the answer text only, ending with a newline.
- stderr: the last line is `LLM_CHAT_META ` followed by one JSON object:

| key | meaning |
| --- | --- |
| `session` | session id to pass as `--session` next time |
| `model` | concrete model that answered (locked for later turns) |
| `provider` | who served it: OpenRouter's provider display name, `DeepSeek`, `anthropic (claude subscription)`, `openai (codex subscription)`, `google (agy subscription)` |
| `cache_read`, `cache_write` | prompt tokens read from / written to cache; `null` when the backend does not report it (DeepSeek writes) |
| `cost_usd`, `cost_basis` | this turn's cost. OpenRouter: real charge (`billed`). Claude: list-price estimate, not charged on a subscription (claude reports a running session total; the script subtracts the previous turn's total). DeepSeek and GPT: `null` |
| `input_tokens`, `output_tokens`, `reasoning_tokens` | this turn's usage (for GPT, codex reports running totals for the thread; the script subtracts the previous turn's totals) |
| `attachments` | agy only: files attached on this turn |
| `thinking_dropped` | Claude with `--drop-thinking` only: thinking blocks removed from earlier turns just before this turn (0 on the first turn; usually 1 after a turn that thought) |

Other stderr lines may appear before it; parse only the `LLM_CHAT_META ` line.

## Waiting for long requests

One request can run for a long time: deep reasoning can take around ten minutes. The script enforces its own `--timeout` (default 600s), and when cancelled it stops its child processes and saves nothing. The caller's shell tool has its own wait limit, though (Claude Code's foreground Bash: 2 minutes by default, 10 at most), and can kill the script before the script's timeout fires.

So run any request that may not be quick through the host's managed background execution: in Claude Code, Bash with `run_in_background` (you are notified when it finishes); in Codex, let the managed shell yield and wait on it with a long window. Do not append `&` or otherwise detach the script, which loses the wait and cancel handle. Use the foreground only for requests that are clearly short.

## Routing

Decided from the model id, in this order (a leading `~` is ignored when reading the vendor):

1. Claude: `anthropic/<name>` (the prefix is stripped), `claude-*`, or the aliases `opus`, `sonnet`, `haiku`, `fable` (optionally `[1m]`). Runs the local `claude -p` with the subscription login.
2. GPT: `openai/<name>` (prefix stripped) or `gpt-*`. Runs the local `codex exec` with the subscription login. Use full names such as `gpt-6-luna`.
3. agy: `gemini-*` or `agy/<slug>` (prefix stripped). Runs the local `agy` (Antigravity CLI) with the Google subscription login. Slugs come from `agy models` and change with the subscription, so look them up instead of guessing (e.g. `gemini-3.8-flash-high`; the suffix is the thinking level).
4. DeepSeek: `deepseek/<name>` (prefix stripped) or `deepseek*`. Calls `https://api.deepseek.com` directly when `API_KEY_DEEPSEEK` (or `DEEPSEEK_API_KEY`) is set. Current ids: `deepseek-flash`, `deepseek-v4-pro` (bare `deepseek` defaults to `deepseek-v4-pro`). When no DeepSeek key is set in the environment and `API_KEY_OPENROUTER` (or `OPENROUTER_API_KEY`) is set, automatically falls back to OpenRouter (`deepseek-flash` → `deepseek/deepseek-v4.1-flash`, `deepseek` / `deepseek-v4-pro` → `deepseek/deepseek-v4-pro`; legacy aliases `deepseek-chat` and `deepseek-reasoner` map to the same models).
5. Any other `vendor/name` id: OpenRouter with `API_KEY_OPENROUTER` (or `OPENROUTER_API_KEY`). A bare id without `/` that matches none of the above is an error.

For Gemini, use the agy slugs by default: the subscription already pays for them, and only agy takes attachments. `google/gemini-*` still goes to OpenRouter and is billed per token there; use it when the agy weekly quota is out (`agy -p /usage` shows it without spending any) or when a model is not on agy.

Claude and GPT never go to OpenRouter. The OpenRouter path refuses, before sending anything: any id whose vendor is `anthropic` or `openai` (with or without a leading `~`) or that contains `claude` or `gpt-`; every `openrouter/*` id such as `openrouter/auto`; and presets (`@...`). Routers and presets are refused because they may pick a Claude or GPT model on their own. Name a concrete `vendor/model` instead.

The three CLIs run with a whitelisted environment (home, path, user, shell, locale, temp dir, proxy and CA-certificate variables). Variables such as `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `CLAUDE_CODE_USE_BEDROCK` or `OPENAI_BASE_URL`, `OPENAI_API_KEY` are never passed, so a call cannot leave the subscription login; for agy, `GEMINI_API_KEY` and the `AGY_LLM_GATEWAY_*` variables are dropped the same way.

OpenRouter pins one provider with no fallback: `x-ai` → `xai`, `google` → `google-ai-studio`. For other vendors the script checks the model's endpoints and pins the endpoint whose slug equals the vendor name; if there is none, nothing is pinned and each turn records the provider that served it. The pin is chosen on the first turn and kept.

## Sessions

- The first turn fixes the system message. On later turns omit it, or pass the identical text; different text is an error and nothing is sent.
- The first turn's concrete model id is locked, so an alias cannot change model mid-conversation. Passing a different model id on a later turn switches model, allowed only within the same kind of backend (OpenRouter and DeepSeek share history; Claude stays Claude; GPT stays GPT; agy stays agy).
- A failed turn is not saved. Claude, GPT and agy keep their own history, though, so a failed turn there may still have reached their thread.
- Two calls on the same session at once: the second fails immediately with "in use". Run turns of one session one after another.

## Dropping earlier thinking

By default each route resends whatever its backend keeps, and for recent Claude and GPT models that includes every earlier turn's thinking. `--drop-thinking` leaves it out, keeping the visible conversation intact. It is fixed on the first turn: later turns may omit the flag or repeat it, but passing it to a session started without it is an error. Turning it on or off mid-way would mix two conditions, and thinking that was already dropped cannot come back.

- Claude: before each resumed turn the script removes the thinking blocks from the claude transcript that `--resume` reads (under `~/.claude/projects/`, see State); nothing else changes except that the record after a removed one is re-linked to the one before it. So the transcript of such a session keeps thinking only for its latest turn (on current Opus the thinking there is only an opaque signature anyway). If the transcript cannot be found or parsed, the turn fails before anything is sent. Caching covers one exchange less than usual: the cache entry written at the end of each request stops matching once that turn's thinking is gone (most likely because it ends where the thinking began). So turn 2 reads nothing from cache, and from turn 3 on `cache_read` covers everything up to the answer before the latest question; the latest question and answer are written again. Measured on Opus: `cache_read` 0, 550, 651, 761 on turns 2 to 5 of a small session, against about the whole previous prompt with the switch off.
- OpenRouter: earlier answers are sent without their `reasoning` / `reasoning_details`; the session file still stores them.
- DeepSeek: no change, since earlier reasoning is never resent there anyway.
- agy: not supported (exit 1, nothing sent); agy keeps the conversation in its own state.
- GPT: not supported. codex keeps a thread's reasoning in its own state with no option to leave it out, so the flag is an error (exit 1, nothing sent).

## State

Everything lives under `${XDG_STATE_HOME:-~/.local/state}/llm-chat/`, created on first use:

- `sessions/`: one JSON file per session (system message, model, history for HTTP routes, per-turn usage), a lock file, and for GPT the instructions file. API keys are never written here.
- `codex-home/`: isolated Codex home. Its `auth.json` is a symlink to the main Codex login (`$CODEX_HOME` or `~/.codex`), created once under a lock. If it is a regular file or points somewhere else, the script stops and asks for a manual fix instead of changing it. Never replace it with a copy: a copy that refreshes its token would log the main one out.
- `agy/<session>/`: the agy workspace for that session: `.agents/agents/llm-chat-session.md` (the session agent; its prompt is the system message) and `files/turn-<n>/` with the attachments, hard-linked when possible, else copied. Kept with the session.
- `empty/`: empty working directory for the claude and codex CLIs. It must stay empty; the script refuses to run otherwise.

Claude runs also leave transcripts under `~/.claude/projects/` for that directory; `--drop-thinking` rewrites them as described above.

## No tools, no web

The model should answer from its own knowledge. Each route is locked down as below; anything detected afterwards fails the turn (exit 1, nothing saved). Detection is after the fact: whatever the tool did has already happened.

- OpenRouter: ids with a variant suffix (`:online` turns on web search; `:free`, `:nitro` and the rest change provider routing) and ids containing `multi-agent` are refused before sending. Every request sends `"plugins": [{"id": "web", "enabled": false}]` to override an account-wide web default. A response with `annotations` (web citations), `tool_calls`, or any server-tool or search counter above 0 in `usage` is an error.
- DeepSeek: no built-in search; the same response checks apply.
- Claude: the tool list is empty; any `usage.server_tool_use` counter above 0 is an error.
- agy: the session agent has one tool, `view_file`, inherits no rules, skills or MCP servers, and is not callable as a subagent. Headless agy cannot ask for permission, so a read outside the session workspace ends the turn; that, any other tool, or a `view_file` on anything other than the files attached on this turn or an earlier saved turn fails the turn (a failed turn's attachments are removed). agy fixes an agent's tools when the conversation starts, so `view_file` is present from the first turn even if nothing is ever attached. agy also writes Gemini safety-filter notices into the answer with a success status; such an answer fails the turn too (the filter is intermittent; retrying often works).
- GPT: web search is off. GPT-6 models still get a few built-in local tools (exec, wait, and similar) that cannot actually run here and have no network access. Any event other than the answer, a reasoning summary, or the exact code-mode-unavailable notice codex prints each turn is an error (a tool call, web search, command, file change, any other error).

Limits of this guarantee:

- OpenRouter router or orchestration models (e.g. `typesafe/jev-router`, `sakana/fugu-max`) pick or delegate to other models internally. The script keeps no allow or deny list for them; choose concrete models yourself.
- Zero web access assumes the OpenRouter account does not force the web plugin on. If it is on by default with "Prevent overrides", the per-request disable is ignored and the search runs before the script can refuse the answer.
- codex's `clock.sleep` may run without showing up in the event stream. It only waits; it touches no network or files.

## Errors

Any failure prints `llm-chat: error: <reason>` on stderr, prints nothing on stdout, and exits 1 (bad arguments exit 2). SIGINT or SIGTERM cancels the turn: the CLI child and everything it started are stopped and waited for before the session lock is released, nothing is saved, and the exit code is 130. This covers HTTP errors, an error body inside an HTTP 200, empty or truncated answers, CLI failures, missing keys, and session problems. There are no retries or fallbacks; decide yourself whether to try again. Context overflow is not handled: the backend's error is reported as-is.

## Notes

- Caching needs a long enough prompt (Gemini about 4K tokens). For Gemini the script marks the end of the prompt before the new message as a cache point, which is what makes the second turn hit the cache.
- A very long first message can drown the system message on some models (seen with Gemini Flash); put key instructions in the user message too if that matters.
