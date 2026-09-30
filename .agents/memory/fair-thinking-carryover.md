---
name: fair-thinking-carryover
description: 模型对模型对弈时双方思考延续方式必须一致；Claude 对 GPT 双方都带思考；单模型测棋力时才用对它最好的方式
metadata:
  node_type: memory
  type: project
  originSessionId: 6735de81-360e-4311-b6f7-5c60ddf9b99e
  modified: 2026-09-30T13:52:51.101Z
---

2026-09-30 用户定：模型对模型对弈，双方的思考延续方式保持一致，才公平。

- Claude 对 GPT：codex 路做不到去掉前几轮思考，所以双方都带思考，opus 也带。
- Claude 对 DeepSeek：可以让 opus 不带（DeepSeek 本来就不回传思考），目前不做。
- 只有评估单个模型的棋力（对引擎等固定对手）时，才用对该棋手最好的组织方式。
- 用户的总体看法：带着思考才是对的，棋手要知道自己以前怎么想，人下棋要规划（比如挖坑）。

**Why:** opus 不带思考的 8 局（g6-*）漏吃明显少、比分更好，但用户认为对弈公平优先，且规划需要思考延续。
**How to apply:** 安排对弈时双方条件对齐；不要因为某一方用某种组织方式更强就单独给它开。见 [[converge-infra-real-player]]。
