# 安装与运行

先复算已有结果或浏览仓内样例，再按需要准备规则库、引擎和模型调用环境。前两项不调用模型、不消耗订阅或 API 额度，也不需要作者本机的 `runs/`。

本文命令都从仓库根目录运行。研究结论见[研究索引](research.md)，依赖来源与许可见[依赖说明](dependencies.md)，项目入口见 [README](../README.md)。

## 按用途准备环境

| 用途 | 需要什么 | 是否调用模型 |
| --- | --- | --- |
| 复算已入库的评级数字 | Python 标准库；`analysis/rating/` 的 CSV、JSON | 否 |
| 浏览样例或自己的棋谱 | 浏览器、本机静态服务；页面无需构建或 npm 安装 | 否 |
| 跑 Python 离线测试 | Python、`chess`、`cchess`、`pyffish`；部分测试需要本机引擎 | 否 |
| 跑阅读器 JS 测试 | Node.js；浏览器测试另需 `playwright-core` 与 Chromium，部分往返测试需要 Python 规则库 | 否 |
| 开模型对弈 | Python 规则库、仓外 `llm-chat`、对应模型 CLI/账号；引擎对手另需引擎 | 是 |
| 把棋谱录成 MP4 | Node.js、`playwright-core`、Chromium、FFmpeg；核对视频另用 FFprobe | 否 |

## 免费入门：复算评级

```sh
python3 analysis/rating/rate.py report
```

脚本只读入库数据、向终端打印结果，不访问网络、不启动引擎。默认做 1,000 次自助法抽样，可能需要几分钟。只想快速确认脚本能跑，可用：

```sh
python3 analysis/rating/rate.py report --boot 10
```

少量抽样只适合检查运行，不用于引用区间；正式复算请保留默认次数。结果的条件和局限见[评级报告](results/opus-max-rating.md)。这些数字基于已有对局，并不代表重新测了一遍模型。`rate.py export` 则依赖未入库的原始 `runs/`，新克隆的仓库不需要执行它。

## 免费入门：浏览样例

```sh
python3 -m http.server --bind 127.0.0.1 8000
```

保持这个终端运行，在浏览器打开：

- 国际象棋：<http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/chess-sample.pgn>
- 中国象棋：<http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/xq-sample.pgn>

样例是测试棋谱，不是整套实验数据。按空格播放，左右键逐步看；用完在服务终端按 Ctrl-C。服务只绑定本机；若 8000 端口已占用，换个端口并同步修改网址。页面不能直接用 `file://` 打开。更多操作见[棋谱浏览与视频录制](viewer-guide.md)。

## Python 程序与离线测试

仓库目前没有统一的 Python 安装包或依赖锁文件。若要运行对弈程序、导出棋谱或跑 Python 测试，应先在自己选择的 Python 虚拟环境安装规则库。下面的版本只是一次已核实环境的复现参考，**不是支持版本范围或跨平台保证**：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install chess==1.11.2 cchess==1.25.5 pyffish==0.0.90
python -c 'import chess, cchess, pyffish; print("规则库可导入")'
python -m llmchess --help
python -m unittest discover -s tests -t .
```

`chess` 是代码中 `import chess` 对应的包；中国象棋还用 `cchess` 和 `pyffish`。`pyffish` 含本机扩展，新平台可能需要编译环境。本文没有核实全新的 Python/操作系统组合能否安装；安装失败时先检查解释器和该包的构建要求。

完整测试包含引擎握手与走子，需要能找到 `stockfish` 和 `fairy-stockfish`。缺少引擎时部分测试会跳过，另有直接调用引擎的测试会失败；完整验证须安装两种引擎，并同时检查失败和 skipped。引擎是单独安装的程序，不会由上述 pip 命令提供；它们的许可与规则库分开列在[依赖说明](dependencies.md)。

2026-11-05 本机核实：`/usr/bin/python3` 为 Python 3.9.6，可导入 `chess 1.11.2`、`cchess 1.25.5`、`pyffish 0.0.90`；此前该解释器下离线测试 314 项通过。同机默认 `python3` 为 Homebrew Python 3.15.0，未安装这些规则库，直接导入会报 `ModuleNotFoundError`。安装在哪个解释器下，运行和测试就用哪个解释器；评级复算与静态服务不需要这些包。

## 模型对弈：还需要仓外组件

整盘对弈默认走 `llmchess/chat.py` 调用的用户级 `llm-chat` 脚本。**该脚本没有随本仓库提供，计划随后随 skills 独立公开；目前不能只克隆本仓库就完整复现模型对弈。**

已有该组件的使用者需自行准备对应 CLI 与登录/凭据。代码的默认脚本位置是 `~/.claude/skills/llm-chat/scripts/llm_chat.py`，可用环境变量 `LLMCHESS_LLM_CHAT` 指向自己的副本。Claude、GPT 使用各自本机 CLI，Gemini/agy 使用 agy，DeepSeek 使用其 HTTP 服务；可用型号、额度与收费由账号和服务决定。本仓库不提供账号、凭据或额度。

先看 CLI 帮助与[对弈协议](design.md)第九节。所有组件准备好后，才运行真正的对弈命令；例如下面会调用模型，消耗其额度：

```sh
python -m llmchess play --game chess --tag my-first-game --white claude:opus --black random --effort medium --max-plies 6 --on-limit pause
```

这是短冒烟，随机对手和 6 个半回合的上限不用于评测棋力。每盘用新的 `--tag`，记录写进被 git 忽略的 `runs/<tag>/`。真实评测条件与停止规则见设计文档；不要给模型棋手开放引擎或规则库工具。工具调用或明确的防思维链泄露类拒答应立即停盘分析，不自动重问续跑。

若改用引擎对手，国际象棋支持 Stockfish，或 lc0 配 Maia 权重；Maia 权重默认在 `~/.local/share/maia/maia-1100.pb.gz` 等文件中，仓库不提供。中国象棋使用 Fairy-Stockfish。Stockfish/lc0 先从 `PATH` 查找，再尝试 `/opt/homebrew/bin/`；Fairy-Stockfish 还可通过 `FAIRY_STOCKFISH` 指定。引擎只当对手或事后裁判，不替模型选着。

## 阅读器测试与录制

纯网页浏览不需要 Node.js、Chromium 自动化或 FFmpeg。只有开发测试和录制才需要额外工具；安装及操作见[棋谱浏览与视频录制](viewer-guide.md)。

```sh
node --test 'viewer/test/*.test.js'
```

JS 测试会说明跳过的项目：没有 `playwright-core` 或可运行的 Chromium 时，浏览器部分会跳过；依赖作者本机 `runs/` 的回归在没有数据时也跳过。部分往返测试会启动 `python3`，它须能导入上述规则库。跳过不表示该部分已验证。
