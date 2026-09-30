---
name: thinking-carryover-is-key
description: 用户最初假设每步丢思考是下得臭的根源；实测不成立，但用户仍认为带思考才对（规划需要），对弈默认带思考
metadata:
  node_type: memory
  type: project
  originSessionId: 6735de81-360e-4311-b6f7-5c60ddf9b99e
  modified: 2026-09-30T13:53:22.215Z
---

用户的最初假设：每步从零调用会丢掉上一步的思考和计划（预判、挖坑、弃子），可能是下得臭的根源。

实测结论（第一、二批与 2026-09-30 的漏吃研究）：
- 思考延续是次要因素，不是根源；`claude -p` 与 Codex 跨轮都保留思考且用得上（`docs/thinking-carryover.md`）。
- 同一会话里模型想得更少；opus 不带前几轮思考时漏吃明显更少（`docs/results/missed-captures.md`、`game-opus-drop-vs-astra-1.md`）。

用户 2026-09-30 的看法仍是：带着思考才是对的方式，因为棋手要知道自己以前怎么想，人下棋要规划。所以对弈默认带思考，并要求双方一致，见 [[fair-thinking-carryover]]。

**How to apply:** 别再把「不带思考更强」当成改默认的理由；只在评估单个模型棋力时才考虑。相关：[[best-effort-not-big-project]]
