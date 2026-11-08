[English](dependencies.en.md) | [简体中文](dependencies.md)

# 依赖与第三方材料

核对日期：2026-11-05，2026-11-08 许可方案落定；发布影响与组合边界见 [许可复核](license-review.md)。

## Python 与引擎

运行对弈与测试所需的规则库已在根目录 `requirements.txt` 中固定。Python 包的元数据均未声明额外运行时依赖。

| 组件 / 实测版本 | 用途与接入 | 第三方本体入库 | 许可与证据 |
|---|---|---|---|
| chess 1.11.2（python-chess 项目的模块包） | 国际象棋规则、PGN；`chess_.py`、`quiz.py` 同进程 import | 否 | GPL-3.0-or-later；[版本元数据](https://pypi.org/pypi/chess/1.11.2/json)、[官方许可](https://github.com/niklasf/python-chess/blob/v1.11.2/LICENSE.txt) |
| pyffish 0.0.90 | 中国象棋规则；`xiangqi.py`、`quiz.py` import C++ 扩展，不是 UCI 子进程 | 否 | GPL-3.0-or-later；[元数据](https://pypi.org/pypi/pyffish/0.0.90/json) 写 GPL3，classifier 与[该版源码包](https://files.pythonhosted.org/packages/16/f8/60fd663b19ed4c72cbd78148645be831bd712823144c34372adb639a3adf/pyffish-0.0.90.tar.gz) `src/main.cpp` 明确 v3 或以后 |
| Stockfish 19 / Fairy-Stockfish 14.0.1 / lc0 0.32.1 | 对手、裁判；`engine.py` 用 subprocess、stdin/stdout UCI；可换可执行文件 | 否 | 本机 Homebrew Cellar 版本；上游 GPLv3 系列：[Stockfish](https://github.com/official-stockfish/Stockfish/blob/master/src/main.cpp)、[Fairy-Stockfish](https://github.com/fairy-stockfish/Fairy-Stockfish#license)、[lc0](https://github.com/LeelaChessZero/lc0/blob/master/src/main.cc)。Stockfish/lc0 文件头明示 or-later，lc0 有 CUDA 附加许可；发行时还须核对实际构建及附带网络文件 |
| Maia 1100–1900 权重 | 本地 `.pb.gz` 交给 lc0；不是 Python import | 否 | [官方仓库](https://github.com/CSSLab/maia-chess#license) 声明软件 GPL，[LICENSE](https://github.com/CSSLab/maia-chess/blob/master/LICENSE) 为 GPLv3；权重在仓库 `maia_weights/`。本地未固定来源 commit/hash；未确认权重是否有独立授权及其“首选修改形式”，再分发前核实 |

> 注：原 `cchess 1.25.5`（元数据写 LGPL-3.0-or-later 但源码包 LICENSE 为 GPLv3 存在声明冲突）已彻底移除运行时依赖，中国象棋中文记谱已完全改用仓内自研实现（`agi_chess/xiangqi.py` 中的 `pgn_move`），不再依赖该包。

## 阅读器、录制与外部工具

| 组件 | 入库 / 版本来源 | 许可与范围 |
|---|---|---|
| chess.js 1.4.0 | vendored；[SOURCE](../viewer/vendor/chess.js/SOURCE.md) 有 npm 哈希 | BSD-2-Clause，已附 LICENSE |
| cm-chessboard 8.15.1 | vendored；[SOURCE](../viewer/vendor/cm-chessboard/SOURCE.md) 有 commit 与一处本地改动 | MIT，已附 LICENSE；未采用其自带非宽松许可棋子 |
| Cburnett 12 个 SVG 与生成精灵图 | vendored；[SOURCE](../viewer/vendor/cburnett-pieces/SOURCE.md) 有逐图来源、版本、哈希 | 多重授权中选择 BSD-3-Clause，已附 LICENSE；不是被迫选择 GPL |
| el_boss 三个 MP3 | vendored；[SOURCE](../viewer/vendor/sounds/SOURCE.md) 有逐音来源、哈希 | CC0 1.0；本轮沿用仓库既有逐项来源核验 |
| playwright-core 1.58.2 | 本体不入库；`viewer/package-lock.json` 固定版本 | Apache-2.0，录制/测试开发依赖；旧实验目录另声明 `^1.61.1`，不是正式阅读器版本 |
| Chromium、FFmpeg | 外部录制工具，不入库；FFmpeg 本机 9.0.2 | Chromium 含多方许可；FFmpeg 依构建选项可能 LGPL/GPL。当前调用工具不等于分发工具；将来随包附带须另核构建与声明 |
| `.agents/skills/llm-chat/` | 仓内自研脚本（`llm_chat.py`、`agy_core.py`），已随仓入库 | MIT（属本仓自有代码） |
| agy、模型 CLI（`claude`、`codex`） | 外部进程，不入库 | 安装与服务使用条件独立核对；本清单不授予其再分发权 |

## 研究数据

- [第一批国际象棋题库](../data/batch1/chess.jsonl)选自 [Lichess 公开谜题库](https://database.lichess.org/#puzzles)，上游按 CC0 提供。选取日期为 2026-09-25，筛选与抽样规则见[第一批选题脚本](../data/batch1/select_positions.py)；数据库会更新，已入库 JSONL 才是本批固定题目。第二批继承的 Lichess 谜题也保留该来源，筛选依据见[第二批选题脚本](../data/batch2/select_positions.py)。
- 两批中国象棋题及第二批新增的国际象棋整盘局面来自本研究及其前序研究的历史对局，来源与选取条件记在对应 JSONL 和选题脚本中。`runs/` 已随仓入库全部 65 个正式模型对局目录（171 盘 `game.pgn` 与引擎分析）及 9 批局面题判卷结果（`judged.jsonl`）；仅底层过程事件流 `game.jsonl`、纯引擎互弈标定原始对局及录屏 `.mp4` 未入库。这里说明来源，不把 Lichess 之外的材料一并宣称为 CC0；本仓自有研究数据采用根目录 MIT 许可，证据边界见[研究索引](research.md)。
- [人类评级刻度数据](../analysis/rating/human-scale.json)含带出处的第三方统计数据；引用来源不等于获得任意再许可权，研究引用与重新打包数据分别判断。

本清单不是完整二进制 SBOM，不覆盖未来容器基础镜像及传递依赖。
