# 进度与待办

更新：2026-09-25。

## 已完成

- 设计与前提核实：`design.md`（641c91f）。
- 跨轮思考保留的调研与实测：`thinking-carryover.md`（8f9ec96）。结论是 Claude（`claude -p` 续接会话）和 Codex 的 astra 跨轮都保留上一轮的思考，而且模型用得上。
- 项目骨架：`init-repo-harness` 建好了规范、软链和项目记忆。

## 等用户拍板

1. **按 `design.md` 开写程序**：写完先跑冒烟测试，报给用户后再开第一批实验。
2. **装国际象棋引擎**：`brew install stockfish lc0`，再下载 maia-1100 等权重，用作分级对手。这会改动本机装的软件，要用户点头。不装的话，国际象棋只能用本机的 Fairy-Stockfish 限 Elo 当对手，它的刻度没核实。

## 下一步（获准后）

- 实施 `design.md` 第二、三、五节：两种棋共用一套对局流程。变量包括思考延续（从零开始 / 带便条 / 同会话）、思考深度（medium–max）、局面呈现、给不给合法着法、自查、先复述。对手可以是模型、引擎或随机走子。
- 第一批实验按 `design.md` 第六节：固定局面上比四档思考深度；三档思考延续各下几盘；挑最好的做法对随机走子和 Maia-1100 定位棋力。

## 遗留

- 用户的全局脚本 `sync-repo-rules.sh` 在这台机器的 bash 3.2 上报 `mapfile: command not found`，所以 `AGENTS.md` 里还没插入共享开发规范块。修好脚本或装新版 bash 后补跑：`~/.harness/scripts/sync-repo-rules.sh --add coding ~/repos/llm-chess`。
- 跨轮调研的实验在 `~/.codex/sessions` 留了约 26 份复制出来的对照会话记录，文件名时间戳为 22-00-00 和 22-10-00，是否清理等用户定。
