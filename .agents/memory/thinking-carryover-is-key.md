---
name: thinking-carryover-is-key
description: 用户认为每步丢掉上一步思考可能是下棋臭的根源，思考延续是本项目的核心变量
metadata:
  type: project
---

用户的核心假设：agent 每步从零调用会丢掉模型上一步的思考和计划（预判、挖坑、弃子、谋杀法），这可能是下得臭的根源。思考深度（medium→max）是第二个变量。用户说的「一轮」指一次 agent run：从用户发问到模型给出不含工具调用的回复为止。

2026-09-25 已核实：`claude -p` 续接会话和 Codex 的 astra，跨轮都保留上一轮的思考，而且模型用得上（见 `docs/thinking-carryover.md`）。

**How to apply:** 设计实验时把「从零开始 / 带便条 / 同会话连续」三档思考延续放在首位。解读结果时分清「看到之前的思考」和「看到历史局面」这两个因素。相关：[[best-effort-not-big-project]]
