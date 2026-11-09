[English](README.md) | [简体中文](README.zh-CN.md)

# agi-chess

**如果连象棋都下不明白，那就不能称为 AGI 了。** 中国象棋与国际象棋规则透明、信息完全公开，常人不经专门训练也能下得有来有回；从眼前局面一步步推出后着，与从已知一步步推出未知本是一脉相承的推理能力。哪怕模型在写代码、解难题上再拿手，只要离开外部引擎、自己坐到棋盘前就频频漏算送子，它就仍是偏科的“锯齿状智能”，离真正的“通用”还差一层。

本项目让未经棋类专训的通用大模型在不借引擎、不给合法着法提示的条件下，像真人一样下国际象棋与中国象棋，实测它们的真实棋力、拆解它们为何犯错，并检验思考深度、局面表示与思考延续方式对下法的影响。仓库收录了完整的对弈与局面题程序、171 盘正式对局棋谱、9 批局面题数据、等级分标定脚本、研究报告及配套棋谱阅读器。

> **棋谱阅读器（[`viewer/`](viewer/)）——零配置直接回放 171 盘对局**
>
> 无需安装引擎或配置 API Key，在仓库根目录运行 `node viewer/serve.mjs --port 8765 --bind 127.0.0.1`（或 `python3 -m http.server 8765 --bind 127.0.0.1`），直接点开示例对局 [`http://127.0.0.1:8765/viewer/?files=/runs/g7-c-opus-astra-1/game.pgn,/runs/g7-c-opus-astra-1/analysis.jsonl`](http://127.0.0.1:8765/viewer/?files=/runs/g7-c-opus-astra-1/game.pgn,/runs/g7-c-opus-astra-1/analysis.jsonl) 即可看到棋盘、每步模型思考理由、引擎复盘恶手标注、耗时与 token 统计。也可不带参数打开 [`http://127.0.0.1:8765/viewer/`](http://127.0.0.1:8765/viewer/) 并把任意单盘目录 `runs/<tag>/game.pgn` 或多盘批次子目录 `runs/<batch>/<game>/game.pgn`（可连带同目录 `analysis.jsonl`）拖入页面查看；导出 MP4 复盘视频需先在 `viewer/` 下执行 `npm ci` 并具备 Chromium 与 `ffmpeg`（详见[棋谱阅读器指南](docs/viewer-guide.md)）。

## 从这里开始

| 想做什么 | 入口 |
| --- | --- |
| **看两种棋的正式对局或样例、逐步读理由或录成视频** | **[棋谱阅读器指南](docs/viewer-guide.md)（[`viewer/`](viewer/)）** |
| 了解做过哪些实验、哪些结论有公开数据 | [研究索引](docs/research.md) |
| 复算评级、配置环境、跑测试或对弈 | [安装与运行](docs/setup.md) |
| 查看依赖用途、版本来源和许可 | [依赖与来源](docs/dependencies.md) |
| 理解提示、赛制、记录格式和异常处理 | [程序设计](docs/design.md) |
| 跟进维护工作与尚未决定的事项 | [项目进度](docs/status.md) |

## 两条不调用模型的快速开始

以下命令均在仓库根目录执行，不需要模型账号或棋类引擎。仅复算评级（`analysis/rating`）与浏览棋谱（`viewer/`）无需安装额外的 Python 规则库。

### 安装 Python 规则依赖（可选）

若需运行命令行对弈、导出棋谱、离线校验已入库题库或执行 Python 离线测试，可通过仓库提供的 `requirements.txt` 安装规则库：

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python3 data/batch1/select_positions.py check
python3 data/batch2/select_positions.py check
```

`select_positions.py check` 离线校验已入库的第一批与第二批局面题（`data/batch1/` 与 `data/batch2/`），无需引擎或模型账号。完整环境配置与引擎对手安装详见[安装与运行](docs/setup.md)。

### 复算已有评级

只需要 Python 3 标准库：

```sh
python3 analysis/rating/rate.py report
```

脚本读取已入库的战绩与人类刻度数据，执行 1,000 次自助抽样，通常需要几分钟。输出对应 [Opus max 棋力定位报告](docs/results/opus-max-rating.md) 中的刻度与区间。它复算统计结果，不重新生成原始对局，也不等于核验了每一步引擎分析。

### 播放正式对局与样例棋谱

用 Python 3 在本机启动静态服务：

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

浏览器打开：

- [国际象棋巅峰对局（Opus Max vs Astra Max 第 1 局）](http://127.0.0.1:8000/viewer/?files=/runs/g7-c-opus-astra-1/game.pgn)
- [中国象棋巅峰对局（Opus Max vs Astra Max 第 1 局）](http://127.0.0.1:8000/viewer/?files=/runs/g7-x-opus-astra-1/game.pgn)
- [国际象棋测试样例](http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/chess-sample.pgn)
- [中国象棋测试样例](http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/xq-sample.pgn)

用左右方向键逐步看棋，空格播放或暂停；也可以打开 [空白阅读器](http://127.0.0.1:8000/viewer/) 后拖入 PGN 文件（及对应 `analysis.jsonl`），或将网址中的 `files=` 替换为 `/runs/<tag>/game.pgn`（58 个单盘目录）或 `/runs/<batch>/<game>/game.pgn`（7 个多盘批次目录 `b1`、`b1-session`、`b2`、`b3max-ch`、`b3max-xq`、`zc`、`zx`，如 `/runs/zc/maia-1900-s1-w/game.pgn`）浏览任意已入库正式对局。结束后在服务终端按 Ctrl-C 停止。若端口被占用，换一个端口，并同步修改链接。

浏览页面不需要 npm 安装。`runs/` 已随仓包含全部 171 盘正式模型对局的 `game.pgn`（包含原记录中各模型步的可见思考理由、耗时与 token 元数据）。视频录制另需浏览器自动化与 ffmpeg，见[指南](docs/viewer-guide.md)。

阅读器默认中文；在网址后加 `&lang=en` 切换英文，`names=` 可覆盖棋手显示名。具体写法见[阅读器指南](docs/viewer-guide.md)。

## 研究内容

- **思考深度与会话组织：** 局面题与整盘实验分别观察 effort、会话延续及此前思考保留的影响，不能假设同名 effort 在不同服务商之间代表相同计算预算。
- **局面表示与错误类型：** 比较棋盘、FEN、子力清单等输入，并用事后分析和模型可见理由定位错误。理由是可检查的回答正文，不等于模型的内部思考。
- **模型对弈与棋力定位：** 包含模型互弈、固定配置引擎对手和引擎标定。跨模型对局多为小样本；人类等级分类比还有锚点与换算误差。

[第一轮总结](docs/results/summary-round1.md) 只概括当时的研究阶段；后续模型对弈、评级及 Gemini 实验见[研究索引](docs/research.md)。各篇报告保留当时的条件和结论。

## 当前对弈原则

整盘默认采用「模型就是真实棋手」协议：每方一个连续会话，依据局面选择着法并给出可见理由。程序验证走法、记录对局，不向模型提供引擎建议或合法着法列表；引擎用于对手和事后裁判。同一步连续三次非法判负，是本项目自定的赛制。

发现工具调用或尝试时暂停；出现防思维链泄露类拒答时终止并保留证据，不自动换措辞或续跑。上游工具事件存在观察盲区，因此“未观察到工具调用”不等于已经证明完全隔离。具体协议、历史差异与限制见[程序设计](docs/design.md)。

## 运行与数据边界

- **正式对局与判卷产物已入库：** `runs/` 目录已随仓入库全部 65 个正式模型对局目录——43 个模型互弈单盘目录 + 22 个模型对引擎目录（15 个单盘 + 7 个多盘批次，合计 171 盘）——的 `game.pgn`（包含原记录中各模型步的可见思考理由、耗时与 token 元数据）、`analysis.jsonl` / `analysis-summary.json`（170 盘的引擎逐着评分与恶手判定）、`summary.json` / `summary.md`，以及 9 个正式局面题批次（`quiz-*`，共 50 份 `judged.jsonl`）的汇总判卷结果 `judged.jsonl` 与 `report.txt`。仅排除了体积庞大的底层过程事件流 `game.jsonl`、重复的 `record.txt`、纯引擎互弈标定原始对局（结果已在 `analysis/rating/games-engines.csv`）及录屏 `.mp4` 视频。
- **内置 `llm-chat` 双通道调用层：** 仓库已在 `.agents/skills/llm-chat/` 内置 `llm-chat`（含 `llm_chat.py` 与 `agy_core.py`），`agi_chess/chat.py` 默认直接调用仓内脚本，无需额外安装外部 `llm-chat` skill。整盘对弈统一驱动两类通道（详见[安装与运行](docs/setup.md)）：
  - **本地 Agent CLI 订阅通道**（主力实验通道）：Claude（通过 `claude` CLI）、GPT（通过 `codex` CLI）、Gemini（通过 `agy` CLI），直接使用本机已安装并登录的 CLI 订阅额度；若未安装对应 CLI，`llm-chat` 会直接返回未安装错误提示。
  - **HTTP API 通道**（DeepSeek 及 OpenRouter）：支持设置环境变量 `API_KEY_OPENROUTER`（或 `OPENROUTER_API_KEY`）和 `API_KEY_DEEPSEEK`（或 `DEEPSEEK_API_KEY`）。运行 `deepseek:flash`（`deepseek-flash`）或 `deepseek:v4-pro`（`deepseek-v4-pro`）时，若仅配置了 `API_KEY_OPENROUTER` 而未设置 `API_KEY_DEEPSEEK`，`llm-chat` 会自动通过 OpenRouter 访问 DeepSeek 模型（`deepseek-flash` → `deepseek/deepseek-v4.1-flash`、`deepseek-v4-pro` → `deepseek/deepseek-v4-pro`），无需单独申请 DeepSeek 官方 Key。
- 模型可用性、CLI 行为和会话处理会变化。报告中的型号与版本是实验记录，不是对当前服务可用性的保证。
- 不加 `--dry-run` 的 `play` 可以实际调用模型并消耗额度；首次使用请先走上面的离线路径。

## 目录

| 路径 | 内容 |
| --- | --- |
| `agi_chess/` | 对弈、局面题、记录导出与事后分析 |
| `.agents/skills/` | 内置 `llm-chat`（多模型会话调用脚本）与 `replay-video`（棋谱观看与录屏指南） |
| `tests/` | Python 离线测试 |
| `data/` | 已入库局面题与选题脚本；部分选题来源只在维护者本机 |
| `analysis/rating/` | 评级脚本、对局统计脚本及其输入数据 |
| `viewer/` | 阅读器、录制工具、测试样例与第三方素材 |
| `docs/results/` | 分批研究报告 |
| `runs/` | 已入库的 65 个正式模型对局目录（171 盘 `game.pgn` 与引擎分析）及 9 批局面题判卷结果；底层 `game.jsonl` 与 `.mp4` 视频被 Git 忽略 |

## 许可说明

- 仓内自有源码、研究报告、题库与 `viewer/` 阅读器采用 MIT 许可证（见根目录 [LICENSE](LICENSE)）；
- `viewer/vendor/` 下的第三方前端组件与素材保留各自的原有宽松许可证（BSD-2-Clause、MIT、BSD-3-Clause、CC0 1.0），详见[依赖与来源](docs/dependencies.md)；
- `agi_chess/` 规则判定在运行时同进程依赖 `chess`（python-chess）与 `pyffish`（均为 GPL-3.0-or-later，不随仓分发，由用户通过 `python3 -m pip install -r requirements.txt` 自行安装）；同进程组合运行或将其打包再分发时须遵守 GPL-3.0-or-later。关于许可边界与接入分析，详见[许可复核](docs/license-review.md)。
