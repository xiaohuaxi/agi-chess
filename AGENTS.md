# llm-chess 项目规范

> 本文件是本仓库的项目级 agent 规范（真身 `AGENTS.md`，Claude Code 经软链读作 `CLAUDE.md`）。
> 只放硬约束与指针；背景、机制、推导下沉到 `docs/` 或项目级 skill，用引用指过去。

## 这个仓库做什么

研究通用大模型（Claude Opus、GPT astra 等未做棋类专训的模型）下中国象棋和国际象棋为什么下得臭，以及基础设施该怎么搭才算对。程序无界面，模型对模型，或模型对固定强度引擎。研究性质、尽力而为：做不下去就停，别滚成大工程。

## 先读

- `docs/status.md`：现在做到哪、下一步、还等用户拍板的事。**开工先读它，收工前更新它。**
- `docs/design.md`：程序设计、变量、记录格式、第一批实验，以及前提核实（含 `claude -p` 的思考深度、token 字段）。
- `docs/thinking-carryover.md`：各家模型跨轮是否保留思考（文档加实测）。「同一会话连续下」这档靠它成立。
- 上游研究，在另一个仓库：`~/repos/ai-research/topics/llm-board-games-survey.md`（别人怎么让模型下棋，有出处）、`~/repos/ai-research/topics/llm-xiangqi-play.md`（第一轮 Opus 对 Opus：读盘全对，昏招集中在「谁能吃到谁」）。

## 硬约束

- **棋手不准用引擎或规则库帮忙**：引擎只能当对手，或事后当裁判判昏招。Codex 当棋手前，先证明它的工具关掉了、调不到本机引擎。
- **模型走 `claude -p`**，用订阅额度，不用 API 直连。思考深度每次显式传。
- **仓库只在本地**，没有远端，不推送。
- **规则判定照搬旧实现，不自己改棋规**：中国象棋规则在 `~/repos/jev-study/games/xiangqi/boards.py`（pyffish），国际象棋用 python-chess。第一轮的对弈脚本在 jev-study 本地分支 `archive/duel-web` 的 `games/xiangqi/llm_duel.py`，只读参考，别切那个分支。
- 对局原始记录放被 git 忽略的目录，结论写进 `docs/`。结论必须写明盘数和条件，盘数少就说只能看方向。
