[English](setup.en.md) | [简体中文](setup.md)

# 安装与运行

先复算已有结果或浏览仓内已入库的 171 盘正式对局与样例，再按需要准备规则库、引擎和模型调用环境。前两项不调用模型、不消耗订阅或 API 额度。

本文命令都从仓库根目录运行。研究结论见[研究索引](research.md)，依赖来源与许可见[依赖说明](dependencies.md)，项目入口见 [README](../README.zh-CN.md)。

## 按用途准备环境

| 用途 | 需要什么 | 是否调用模型 |
| --- | --- | --- |
| 复算已入库的评级数字 | Python 标准库；`analysis/rating/` 的 CSV、JSON | 否 |
| 浏览正式对局、样例或自己的棋谱 | 浏览器、本机静态服务；页面无需构建或 npm 安装 | 否 |
| 跑 Python 离线测试 | Python、`chess`、`pyffish`；部分测试需要本机引擎 | 否 |
| 跑阅读器 JS 测试 | Node.js；浏览器测试另需 `playwright-core` 与 Chromium，部分往返测试需要 Python 规则库 | 否 |
| 开模型对弈 | Python 规则库、仓内内置 `llm-chat`（`.agents/skills/llm-chat/`）、本地模型 CLI（`claude`/`codex`/`agy`）或 HTTP API Key（`API_KEY_OPENROUTER` / `API_KEY_DEEPSEEK`）；引擎对手另需引擎 | 是 |
| 把棋谱录成 MP4 | Node.js、`playwright-core`、Chromium、FFmpeg；核对视频另用 FFprobe | 否 |

## 免费入门：复算评级

```sh
python3 analysis/rating/rate.py report
```

脚本只读入库数据、向终端打印结果，不访问网络、不启动引擎。默认做 1,000 次自助法抽样，可能需要几分钟。只想快速确认脚本能跑，可用：

```sh
python3 analysis/rating/rate.py report --boot 10
```

少量抽样只适合检查运行，不用于引用区间；正式复算请保留默认次数。结果的条件和局限见[评级报告](results/opus-max-rating.md)。这些数字基于已有对局，并不代表重新测了一遍模型。`rate.py export` 依赖未入库的纯引擎互弈标定原始目录與底层 `game.jsonl`，新克隆的仓库无需执行它（汇总战绩已入库在 `analysis/rating/games-*.csv`）。

## 免费入门：浏览正式对局与样例

```sh
python3 -m http.server --bind 127.0.0.1 8000
```

保持这个终端运行，在浏览器打开：

- 国际象棋巅峰对局（Opus Max vs Astra Max 第 1 局）：<http://127.0.0.1:8000/viewer/?files=/runs/g7-c-opus-astra-1/game.pgn>
- 中国象棋巅峰对局（Opus Max vs Astra Max 第 1 局）：<http://127.0.0.1:8000/viewer/?files=/runs/g7-x-opus-astra-1/game.pgn>
- 国际象棋测试样例：<http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/chess-sample.pgn>
- 中国象棋测试样例：<http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/xq-sample.pgn>

仓库 `runs/` 已随仓包含全部 65 个正式模型对局目录（共 171 盘）的 `game.pgn`（内含每步完整思考理由批注、耗时与 token 统计），可直接将网址中的 `files=` 替换为任意 `/runs/<tag>/game.pgn` 浏览。按空格播放，左右键逐步看；用完在服务终端按 Ctrl-C。服务只绑定本机；若 8000 端口已占用，换个端口并同步修改网址。页面不能直接用 `file://` 打开。更多操作见[棋谱浏览与视频录制](viewer-guide.md)。

阅读器默认中文；在网址后加 `&lang=en` 切换英文，`names=` 可覆盖棋手显示名。具体写法见[阅读器指南](viewer-guide.md)。

## Python 程序与离线测试

仓库提供 `requirements.txt` 用于安装规则库依赖。若要运行对弈程序、导出棋谱或跑 Python 测试，应先在自己选择的 Python 虚拟环境安装规则库（仅复算评级 `analysis/rating` 与本地静态浏览 `viewer/` 无需安装这两个库）：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -c 'import chess, pyffish; print("规则库可导入")'
python -m agi_chess --help
python data/batch2/select_positions.py check
python -m unittest discover -s tests -t .
```

`chess` 是代码中 `import chess` 对应的包；中国象棋规则由 `pyffish` 提供，中文记谱已改用仓内自研实现（无需 `cchess`）。`pyffish` 含本机扩展，新平台可能需要编译环境；在 Debian/Ubuntu 上若系统缺少 `venv`、编译工具或 Stockfish，可先运行 `sudo apt install python3-venv build-essential python3-dev stockfish`。本文没有核实全新的 Python/操作系统组合能否安装；安装失败时先检查解释器和该包的构建要求。

`python3 data/batch2/select_positions.py check` 仅依赖上述规则库，离线校验已入库的第二批局面题（`data/batch2/{xiangqi,chess}.jsonl` 的 FEN、行棋方与着法合法性），不启动引擎、不读取 `runs/`。

完整测试包含引擎握手与走子，需要能找到 `stockfish` 和 `fairy-stockfish`。缺少引擎时相关引擎测试会跳过；完整验证须安装两种引擎，并同时检查失败和 skipped。引擎是单独安装的程序，不会由上述 pip 命令提供；它们的许可与规则库分开列在[依赖说明](dependencies.md)。

2026-11-05 本机核实：`/usr/bin/python3` 为 Python 3.9.6，可导入 `chess 1.11.2`、`pyffish 0.0.90`（原 `cchess` 运行时依赖已移除，改用仓内自研记谱）；此前该解释器下离线测试 314 项通过。同机默认 `python3` 为 Homebrew Python 3.15.0，未安装这些规则库，直接导入会报 `ModuleNotFoundError`。安装在哪个解释器下，运行和测试就用哪个解释器；评级复算与静态服务不需要这些包。

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
- **历史无状态局面题模式**（`python3 -m agi_chess.quiz`）：仍按原路径直调 `claude` 或 `codex exec`；其中 `python3 -m agi_chess.quiz run --game chess --batch batch2 --ids c2-01 --efforts medium --reps 1 --model deepseek` 走 Codex CLI profile，默认读取 `$CODEX_HOME/deepseek.config.toml`（未设 `CODEX_HOME` 时为 `~/.codex/deepseek.config.toml`）还原供应商与模型目录配置，也可通过环境变量 `AGI_CHESS_DEEPSEEK_CONFIG`（兼容 `AGICHESS_DEEPSEEK_CONFIG` 与 `LLMCHESS_DEEPSEEK_CONFIG`）覆盖配置文件路径。无凭据最小配置模板示例：

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

  配套的模型目录最小模板 `~/.codex/deepseek-models.json`：

  ```json
  {
    "models": [
      {
        "slug": "deepseek/deepseek-v4-pro",
        "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}, {"effort": "high"}]
      }
    ]
  }
  ```

先看 CLI 帮助与[对弈协议](design.md)第九节。上面的 `--max-plies 6` 配 `random` 对手只是短冒烟，不用于评测棋力。每盘用新的 `--tag`，输出写入 `runs/<tag>/`（新建本地运行目录默认仅入库指定的已提交正式批次，底层 `game.jsonl` 被 git 忽略）。真实评测条件与停止规则见设计文档；不要给模型棋手开放引擎或规则库工具。工具调用或明确的防思维链泄露类拒答应立即停盘分析，不自动重问续跑。

若改用引擎对手，国际象棋支持 Stockfish，或 lc0 配 Maia 权重；Maia 权重默认在 `~/.local/share/maia/maia-1100.pb.gz` 等文件中，仓库不提供。中国象棋使用 Fairy-Stockfish。引擎按环境变量（`STOCKFISH`、`LC0`、`FAIRY_STOCKFISH`）、`PATH` 以及 `/usr/games`、`/usr/local/games`、`/usr/local/bin`、`/usr/bin`、`/opt/homebrew/bin` 顺序查找。引擎只当对手或事后裁判，不替模型选着。

## 阅读器测试与录制

纯网页浏览不需要 Node.js、Chromium 自动化或 FFmpeg。只有开发测试和录制才需要额外工具（在 `viewer/` 下执行 `npm ci`，并准备 Chromium 与 `ffmpeg`，如在仓库根目录执行 `node viewer/node_modules/playwright-core/cli.js install --with-deps chromium` 以安装与锁定版本 `playwright-core==1.58.2` 配套的浏览器，或使用系统安装的 `chromium` / `google-chrome-stable` 与 `ffmpeg`；在 Linux 服务器/无桌面环境录屏或截图时还需安装中文字体，如 Ubuntu/Debian：`sudo apt install fonts-noto-cjk fonts-arphic-ukai`，否则中国象棋棋盘上的汉字棋子会显示为方块）；安装及操作见[棋谱浏览与视频录制](viewer-guide.md)。

```sh
node --test 'viewer/test/*.test.js'   # 引号通配需 Node 22+；Node 18/20 请去掉单引号运行 node --test viewer/test/*.test.js
```

JS 测试会校验阅读器解析及已入库 `runs/` 下全部正式对局 `game.pgn`，并说明跳过的项目：没有 `playwright-core` 或可运行的 Chromium 时，浏览器部分会跳过；部分往返测试会启动 `python3`，它须能导入上述规则库。跳过不表示该部分已验证。
