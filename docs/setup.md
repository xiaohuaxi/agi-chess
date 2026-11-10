[English](setup.en.md) | [简体中文](setup.md)

# 安装与运行

先复算已有结果或浏览仓内已入库的 171 盘正式对局与样例，再按需要准备规则库、引擎和模型调用环境。前两项不调用模型、不消耗订阅或 API 额度。

本文命令都从仓库根目录运行。研究结论见[研究索引](research.md)，依赖来源与许可见[依赖说明](dependencies.md)，项目入口见 [README](../README.zh-CN.md)。

## 按用途准备环境与命令速查

| 用途 | 直达命令 | 需要什么 | 是否调用模型 |
| --- | --- | --- | --- |
| 浏览正式对局、样例或自己的棋谱 | `node viewer/serve.mjs`（打开 `http://127.0.0.1:8765/viewer/`） | 浏览器、本机静态服务；页面无需构建或 npm 安装 | 否 |
| 复算已入库的评级数字 | `python3 analysis/rating/rate.py report --boot 10`（快检 1.5s；去掉 `--boot 10` 跑完整 1,000 次约 1.5m） | Python 标准库；`analysis/rating/` 的 CSV、JSON | 否 |
| 复算 9 批局面题判卷汇总表 | `python3 -m agi_chess.quiz report --batch batch2`（可换 `batch1`、`batch2`、`batch3`、`4p`、`4p2`、`5-ds`、`5-sol`、`6r`、`6r-sol`） | Python 标准库；`runs/quiz-*/judged.jsonl` | 否 |
| 校验题库与跑 Python 测试 | `python3 data/batch1/select_positions.py check && python3 data/batch2/select_positions.py check && python3 -m unittest discover -s tests -t . -v` | Python、`chess`、`pyffish`；21 项真引擎测试另需本机 `stockfish` 与 `fairy-stockfish`（未装自动 skip） | 否 |
| 零成本试跑首盘对局 | `python3 -m agi_chess play --game chess --tag demo-random --white random --black random --max-plies 20 --seed 42` | Python、`chess`、`pyffish`（0.1 秒生成 `runs/demo-random/game.pgn`） | 否 |
| 事后引擎逐手复盘与恶手分析 | `python3 -m agi_chess.analyze runs/demo-random`（多盘汇总加 `--table`；输出 `analysis.jsonl` 与 `analysis-summary.json`） | Python 规则库、本机引擎（国象 `stockfish`，中象 `fairy-stockfish`）及含 `game.jsonl` 的对局目录 | 否 |
| 跑阅读器 JS 测试 | `node --test 'viewer/test/*.test.js'` | Node.js；29 项浏览器测试另需 `playwright-core` 与 Chromium，3 项往返测试需 Python 规则库（共 32 项，未装自动 skip） | 否 |
| 把棋谱录成 MP4 | `npm --prefix viewer ci && node viewer/record.mjs runs/g7-c-opus-astra-1 -o /tmp/g7-c-1.mp4 --gap 1.5 --openhold 0.5` | Node.js、`playwright-core`、Chromium、FFmpeg；核对视频另用 FFprobe | 否 |
| 开模型对弈 | `python3 -m agi_chess play --game chess --tag c1 --white claude:opus --black random --effort medium --max-plies 6 --on-limit pause` | macOS / Linux（含 WSL2；`llm_chat.py` 依赖 `fcntl` 与 POSIX 进程组）、Python 规则库、仓内内置 `llm-chat`（`.agents/skills/llm-chat/`）、本地模型 CLI（`claude`/`codex`/`agy`）或 HTTP API Key（`API_KEY_OPENROUTER` / `API_KEY_DEEPSEEK`）；引擎对手另需引擎 | 是 |

> **运行环境边界**：静态阅读器（`viewer/`）、评级复算（`analysis/rating/rate.py`）与局面题报表（`quiz report`）跨平台可用；模型对弈调用层（`.agents/skills/llm-chat/scripts/llm_chat.py` 使用 `fcntl` 文件锁与 POSIX 进程组管理）面向 macOS 与 Linux（含 WSL2），不支持原生 Windows。

## 免费入门：复算评级与局面题判卷表

```sh
python3 analysis/rating/rate.py report --boot 10   # 约 1.5 秒快速检查运行
python3 analysis/rating/rate.py report             # 完整 1,000 次自助法抽样（约 1.5 分钟）
```

脚本只读入库数据、向终端打印结果，不访问网络、不启动引擎。少量抽样（`--boot 10`）只适合快速验证运行，正式引用置信区间请保留默认的 1,000 次抽样。结果的条件和局限见[评级报告](results/opus-max-rating.md)。`rate.py export` 依赖未入库的纯引擎互弈标定原始目录与底层 `game.jsonl`，新克隆的仓库无需执行它（汇总战绩已入库在 `analysis/rating/games-*.csv`）。

若要从已入库的 9 批局面题判卷文件（`runs/quiz-*/judged.jsonl`，共 50 份）秒级复算各条件下的合法着法率、最佳着法率与大失误率汇总表（同样仅需 Python 标准库）：

```sh
python3 -m agi_chess.quiz report --batch batch2    # 可换 batch1、batch2、batch3、4p、4p2、5-ds、5-sol、6r、6r-sol
```

## 免费入门：浏览正式对局与样例

```sh
node viewer/serve.mjs
# 默认监听 127.0.0.1:8765；无 Node.js 时可用：python3 -m http.server 8765 --bind 127.0.0.1
```

保持这个终端运行，在浏览器打开（传入对局目录名或 `game.pgn` 会自动伴随加载同目录 `analysis.jsonl` 的恶手标注）：

- 空白阅读器（含 4 盘代表局一键直达入口）：<http://127.0.0.1:8765/viewer/>
- 国际象棋巅峰对局（Opus Max vs Astra Max 第 1 局）：<http://127.0.0.1:8765/viewer/?files=/runs/g7-c-opus-astra-1>
- 中国象棋巅峰对局（Opus Max vs Astra Max 第 1 局）：<http://127.0.0.1:8765/viewer/?files=/runs/g7-x-opus-astra-1>
- 国际象棋 Argon High vs Opus High 第 1 局：<http://127.0.0.1:8765/viewer/?files=/runs/argon-vs-agy-opus-high-20261019>
- 国际象棋等级分锚定局（Opus Max vs Maia-1900）：<http://127.0.0.1:8765/viewer/?files=/runs/zc/maia-1900-s1-w>
- 国际象棋测试样例：<http://127.0.0.1:8765/viewer/?files=/viewer/test/fixtures/chess-sample.pgn>
- 中国象棋测试样例：<http://127.0.0.1:8765/viewer/?files=/viewer/test/fixtures/xq-sample.pgn>

仓库 `runs/` 已随仓包含全部 65 个正式模型对局目录（共 171 盘）的 `game.pgn`（包含原记录中各模型步的可见思考理由、耗时与 token 元数据）：其中 **58 个单盘目录**（43 个模型互弈 + 15 个单盘模型对引擎 `b1-ch-*`/`b1-xq-*`）可直接传 `/runs/<tag>`（或 `/runs/<tag>/game.pgn`），**7 个多盘批次目录**（`b1`、`b1-session`、`b2`、`b3max-ch`、`b3max-xq`、`zc`、`zx`，共 113 盘）位于二级子目录 `/runs/<batch>/<game>`（如 `?files=/runs/zc/maia-1900-s1-w`）；阅读器会自动请求同目录的 `analysis.jsonl` 叠加恶手徽章（若无则静默忽略）。按空格播放，左右键逐步看；用完在服务终端按 Ctrl-C。服务只绑定本机；若 8765 端口已占用，可用 `node viewer/serve.mjs --port 8000` 换端口并同步修改网址。页面不能直接用 `file://` 打开。更多操作见[棋谱浏览与视频录制](viewer-guide.md)。

阅读器默认中文；在网址后加 `&lang=en` 切换英文，`names=` 可覆盖棋手显示名。具体写法见[阅读器指南](viewer-guide.md)。

## Python 程序、离线测试与零成本试跑

建议使用 Python 3.13；多版本环境可用 `python3.13 -m venv .venv` 明确选择解释器。若安装 `pyffish` 报编译或链接错误，先核对本机 C++ 工具链与 SDK。

仓库提供 `requirements.txt` 用于安装规则库依赖。若要运行对弈程序、导出棋谱或跑 Python 测试，应先在自己选择的 Python 虚拟环境安装规则库（仅复算评级 `analysis/rating`、复算局面题报表 `quiz report` 与本地静态浏览 `viewer/` 无需安装这两个库）：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -c 'import chess, pyffish; print("规则库可导入")'
python -m agi_chess --help
```

`chess` 是代码中 `import chess` 对应的包；中国象棋规则由 `pyffish` 提供，中文记谱已改用仓内自研实现（无需 `cchess`）。`pyffish` 含本机扩展，新平台可能需要编译环境；在 Debian/Ubuntu 上若系统缺少 `venv`（报 `ensurepip is not available`）、编译工具或 Stockfish，可先运行 `sudo apt install python3-venv build-essential python3-dev stockfish`。

无需任何 API Key 或本地引擎，即可用 `random` 棋手在 0.1 秒内跑通首盘完整对局，或用 `--dry-run` 检查真实棋手协议提示词：

```sh
# 双方随机走子试跑 20 个半回合（生成 runs/demo-random/{game.jsonl,record.txt,game.pgn}，可在阅读器打开 ?files=/runs/demo-random）
python -m agi_chess play --game chess --tag demo-random --white random --black random --max-plies 20 --seed 42

# 仅打印系统提示词与第一步用户提示词，不调模型、不写盘
python -m agi_chess play --game xiangqi --tag demo-prompt --dry-run

# 若本机已安装 stockfish 或 fairy-stockfish，可对刚跑出的本地对局运行事后引擎逐手复盘（生成 analysis.jsonl 与 analysis-summary.json）
python -m agi_chess.analyze runs/demo-random
```

> **提示**：`python3 -m agi_chess.analyze` 需读取对局目录下的原始 `game.jsonl` 重放落定着法（`--table` 多盘汇总表同样需读取本地 `game.jsonl`）；仓内已入库的 65 个正式对局目录均已预先算好并随仓提交了 `analysis.jsonl` 与 `analysis-summary.json`（其中恶手字段国际象棋看 `lichess: "Blunder"`，中国象棋看 `cls: "blunder"`），无需重跑引擎即可直接分析或用 `python3 -m agi_chess.analyze runs/g7-c-opus-astra-*` 核对已入库分析摘要。

按需校验题库或运行完整测试（不是试跑首盘的前置步骤）：

```sh
python data/batch1/select_positions.py check
python data/batch2/select_positions.py check
python -m unittest discover -s tests -t . -v
```

`python3 data/batch1/select_positions.py check` 与 `python3 data/batch2/select_positions.py check` 仅依赖上述规则库，离线校验已入库的第一批与第二批局面题（`data/batch1/{xiangqi,chess}.jsonl` 与 `data/batch2/{xiangqi,chess}.jsonl` 的 FEN、行棋方与着法合法性），不启动引擎、不读取 `runs/`。

完整单元测试（共 320 项）包含 21 项真引擎握手与走子测试，需要能找到 `stockfish` 和 `fairy-stockfish`。**当本机未安装这两个引擎时，`unittest -v` 会自动跳过这 21 项真引擎测试（其余 299 项全部通过属正常预期）**；安装两个引擎后 320 项全部通过（0 fail / 0 skip）。引擎是单独安装的程序，不会由 `pip` 提供；它们的许可与规则库分开列在[依赖说明](dependencies.md)。

## 模型对弈：内置 `llm-chat`、本地 CLI 订阅与 HTTP API 配置

整盘对弈默认走 `agi_chess/chat.py` 调用的 `llm-chat` 脚本。**仓库现已在 `.agents/skills/llm-chat/` 内置了完整 `llm-chat`（含 `scripts/llm_chat.py` 与 `scripts/agy_core.py`），`agi_chess/chat.py` 默认直接调用该仓内脚本，外部用户无需再额外等待或安装外部 `llm-chat` skill**（如仍需覆盖脚本路径，可设置环境变量 `AGI_CHESS_LLM_CHAT`，同时兼容 `AGICHESS_LLM_CHAT` 与 `LLMCHESS_LLM_CHAT`）。

`llm-chat` 在整盘对弈中统一驱动两类模型通道：

1. **本地 Agent CLI 订阅通道（主力实验通道）：**
   - **Claude**：通过本机 `claude` CLI 调用（如 `--white claude:opus`）；
   - **GPT**：通过本机 `codex` CLI 调用（如 `--black codex:astra`）；
   - **Gemini（或经 agy 路由的模型）**：通过本机 `agy` CLI 调用（如 `--white gemini:gemini-4-argon-high` 或 `agy:claude-opus-5-5-high`）。
   - 该通道直接使用用户本机已安装并登录的对应 CLI 订阅额度（研发实测版本：`claude 2.1.282`、`codex 0.156.1+`；开工前可用 `claude --version`、`codex --version`、`agy --version` 检查版本，并用 `python3 -m agi_chess play --game chess --white claude:opus --black random --dry-run` 离线核对提示生成）。若本机未安装对应 CLI，`llm-chat` 会直接返回明确的未安装错误提示。

2. **HTTP API 通道（DeepSeek 及 OpenRouter）：**
   - 支持设置环境变量 `API_KEY_OPENROUTER`（或别名 `OPENROUTER_API_KEY`）以及 `API_KEY_DEEPSEEK`（或别名 `DEEPSEEK_API_KEY`）。
   - **自动回退机制**：运行 `deepseek:flash`（`deepseek-flash`）或 `deepseek:v4-pro`（`deepseek-v4-pro`）时，若设置了 `API_KEY_DEEPSEEK`（或 `DEEPSEEK_API_KEY`），则直连 DeepSeek 官方 API；若只有 `API_KEY_OPENROUTER`（或 `OPENROUTER_API_KEY`）而没有配置 DeepSeek 官方 Key，`llm-chat` 会自动通过 OpenRouter 访问 DeepSeek 模型（`deepseek-flash` → `deepseek/deepseek-v4.1-flash`，`deepseek-v4-pro` → `deepseek/deepseek-v4-pro`），无需单独申请 DeepSeek 官方 Key。

配置与运行示例：

```sh
# 方式一：使用已登录的本机 CLI（如 claude / codex / agy）对弈随机对手（短冒烟）
python -m agi_chess play --game chess --tag my-first-game --white claude:opus --black random --effort medium --max-plies 6 --on-limit pause

# 方式二：使用 DeepSeek 官方 API Key 或 OpenRouter API Key 运行整盘对弈（DeepSeek 思考档位支持 low / high / max）
export API_KEY_DEEPSEEK="sk-..."        # 或使用同义变量 DEEPSEEK_API_KEY
# 若无 DeepSeek 官方 Key，仅配置 OpenRouter 即可自动路由 deepseek:flash / deepseek:v4-pro：
export API_KEY_OPENROUTER="sk-or-..."   # 或使用同义变量 OPENROUTER_API_KEY
python -m agi_chess play --game chess --tag ds-smoke --white deepseek:v4-pro --black random --effort low --max-plies 6 --on-limit pause
```

可用型号、额度与收费由账号和服务决定；本仓库不提供账号、凭据或额度。请注意 DeepSeek 在两种运行模式下的配置差异：
- **整盘对弈模式**（`python3 -m agi_chess`）：由仓内 `.agents/skills/llm-chat/` 通过 HTTP 直连 DeepSeek 官方 API 或 OpenRouter，**只需设置 `DEEPSEEK_API_KEY`（`API_KEY_DEEPSEEK`）或 `OPENROUTER_API_KEY`（`API_KEY_OPENROUTER`）环境变量，无需安装 Codex CLI**。
- **历史无状态局面题模式**（`python3 -m agi_chess.quiz`）：仍按原路径直调 `claude` 或 `codex exec`；其中 DeepSeek 走 Codex CLI profile，默认读取 `$CODEX_HOME/deepseek.config.toml`（未设 `CODEX_HOME` 时为 `~/.codex/deepseek.config.toml`）还原供应商与模型目录配置，也可通过环境变量 `AGI_CHESS_DEEPSEEK_CONFIG`（兼容 `AGICHESS_DEEPSEEK_CONFIG` 与 `LLMCHESS_DEEPSEEK_CONFIG`）覆盖配置文件路径。

  示例中的运行命令请使用独立输出目录，保留 `--batch batch2` 选择题库：

  ```sh
  python3 -m agi_chess.quiz run --game chess --batch batch2 --out runs/quiz-deepseek-demo --ids c2-01 --efforts medium --reps 1 --model deepseek
  ```

  每次新实验换一个 `--out`；后续 `judge` / `report` 使用相同的 `--out`。默认的 `runs/quiz-batch2` 已有公开判卷数据，新克隆缺少原始作答，程序会拒绝向其中追加实验。

  无凭据最小配置模板示例：

  ```toml
  # ~/.codex/deepseek.config.toml（仅在运行 quiz --model deepseek 时需要；整盘对弈无需此文件）
  model = "deepseek/deepseek-v4-pro"
  model_provider = "openrouter"
  model_catalog_json = "~/.codex/deepseek-models.json"

  [model_providers.openrouter]
  name = "OpenRouter"
  base_url = "https://openrouter.ai/api/v1"
  env_key = "OPENROUTER_API_KEY"
  wire_api = "chat"
  ```

  配套的模型目录最小模板 `~/.codex/deepseek-models.json`（须保留 `codex exec` 反序列化 `ModelInfo` 所需的基础字段）：

  ```json
  {
    "models": [
      {
        "slug": "deepseek/deepseek-v4-pro",
        "shell_type": "shell_command",
        "tool_mode": null,
        "multi_agent_version": "v2",
        "experimental_supported_tools": [],
        "apply_patch_tool_type": "freeform",
        "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}, {"effort": "high"}]
      }
    ]
  }
  ```

先看 CLI 帮助与[对弈协议](design.md)第九节。上面的 `--max-plies 6` 配 `random` 对手只是短冒烟，不用于评测棋力。每盘用新的 `--tag`，输出写入 `runs/<tag>/`（新建本地运行目录默认仅入库指定的已提交正式批次，底层 `game.jsonl` 被 git 忽略）。真实评测条件与停止规则见设计文档；不要给模型棋手开放引擎或规则库工具。工具调用或明确的防思维链泄露类拒答应立即停盘分析，不自动重问续跑。

若改用引擎对手，国际象棋支持 Stockfish（如 `--black engine:stockfish:elo=1900` 或 `engine:stockfish:nodes=1000`），或 lc0 配 Maia 权重（如 `--black engine:maia-1500`；权重默认在 `~/.local/share/maia/maia-1100.pb.gz` 等文件中，仓库不提供）。中国象棋使用 Fairy-Stockfish，棋手标识符写为 `engine:fsf`（默认 `nodes=1000`，可指定节点数或深度，如 `--black engine:fsf:nodes=100` 或 `engine:fsf:depth=10`）。引擎按环境变量（`STOCKFISH`、`LC0`、`FAIRY_STOCKFISH`）、`PATH` 以及 `~/.local/bin`、`/usr/games`、`/usr/local/games`、`/usr/local/bin`、`/usr/bin`、`/opt/homebrew/bin` 顺序查找。引擎只当对手或事后裁判，不替模型选着。

## 阅读器测试与录制

纯网页浏览不需要 Node.js、Chromium 自动化或 FFmpeg。只有开发测试和录制才需要额外工具（在仓库根目录执行 `npm --prefix viewer ci`，并准备 Chromium 与 `ffmpeg`，如执行 `node viewer/node_modules/playwright-core/cli.js install --with-deps chromium` 以安装与锁定版本 `playwright-core==1.58.2` 配套的浏览器，或使用系统安装的 `chromium` / `google-chrome-stable` 与 `ffmpeg`；在 Linux 服务器/无桌面环境录屏或截图时还需安装中文字体，如 Ubuntu/Debian：`sudo apt install fonts-noto-cjk fonts-arphic-ukai`，否则中国象棋棋盘上的汉字棋子会显示为方块）；安装及操作见[棋谱浏览与视频录制](viewer-guide.md)。

```sh
node --test 'viewer/test/*.test.js'   # 引号通配需 Node 22+；Node 18/20 请去掉单引号运行 node --test viewer/test/*.test.js
```

JS 测试（共 90 项）会校验阅读器解析及已入库 `runs/` 下全部正式对局 `game.pgn`，并说明跳过的项目：58 项纯 JS 与棋谱校验无需额外依赖；未安装 `playwright-core`/Chromium 或未安装 Python 规则库时，29 项浏览器测试与 3 项 Python 往返测试（共 32 项）会按缺失项自动跳过；安装依赖并具备 Chromium 与 Python 规则库后，90 项测试全部通过（0 fail / 0 skip）。跳过不表示该部分已验证。
