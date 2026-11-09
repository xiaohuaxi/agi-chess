# 待办与暂缓事项（TODO）

本文件记录深度审查中识别出、但按研究仓库「简单优先、反过度设计」原则决定暂不处理的非阻塞事项。

1. **`agi_chess/batch.py:take_lock` 创建锁文件的微秒级空文件窗口**
   - **相关位置**：`agi_chess/batch.py` `take_lock()`（约第 127–150 行）。
   - **现象与根因初判**：进程 A 调用 `os.open(path, O_CREAT | O_EXCL | O_WRONLY)` 创建 `.lock` 到写入 PID 之间存在微秒级空文件状态；若进程 B 恰好在此窗口触发 `FileExistsError` 并读取 `.lock`，会将空内容解析为 `pid = 0`（`alive = False`）并删除重建，导致双持锁。
   - **暂缓理由**：本工具为单人本地命令行研究脚本，不会在同一微秒并发启动指向同一 `--batch` 的两个驱动进程，暂不为此引入跨平台文件锁或临时文件硬链接重构。

2. **`agi_chess/records.py` 断电未换行尾行续写与坏行处理**
   - **相关位置**：`agi_chess/records.py` `write()` 与 `read()`（第 18–32 行）。
   - **现象与根因初判**：`read()` 对 JSON 解析失败的断电半行执行 `except ValueError: continue` 跳过；若上次进程在写盘中途断电/被 `SIGKILL` 导致文件末尾停在不含 `\n` 的半行残片，下次直接调用 `write()` 追加时会将新记录拼在同一行末尾，使该条新记录随残片一起被 `read()` 跳过。
   - **暂缓理由**：每条 JSONL 记录均为单次短字符串写入，仅在写盘瞬间断电且未检查文件直接续跑时才会出现无换行尾残片；保持当前 20 行极简追加读写实现，不引入日志截断修复与复杂审计状态机。

3. **`agi_chess/batch.py` 的 `batch_meta` / `check_meta` 反向回退默认值与非 Claude 棋手 `show` 比对**
   - **相关位置**：`agi_chess/batch.py` `batch_meta()` 与 `check_meta()`（第 96–125 行）。
   - **现象与根因初判**：为兼容早期未记录 `protocol` 与 `show` 字段的 `batch.json`，`batch_meta` 在默认值（`protocol='legacy'`、`show='all'`）时省略对应键，且仅在 `a.player.startswith('claude:')` 时记录 `show`；`check_meta` 只遍历新 `meta` 的键。若对已有 `protocol='real'` 或 `show='pieces'` 的未完批次中途改传 `--protocol legacy` 或 `--set show=all` 续跑，因新 `meta` 省略了该键而不会触发不一致报错。
   - **暂缓理由**：所有正式实验批次均按固定参数跑完归档，日常使用极少对同一未完批次中途混改协议或棋盘呈现参数，暂不修改 `batch.json` 元数据归一化逻辑。

4. **跨层嵌套目录误传与未配环境时的底层异常包装**
   - **相关位置**：`agi_chess/cli.py`、`agi_chess/claude_cli.py`、`agi_chess/codex_cli.py`、`data/batch{1,2}/select_positions.py`。
   - **现象与根因初判**：顶层已入库目录已加防覆盖拦截，但若用户刻意将 `--out` 指向某个单盘归档目录内部创建子目录，或在未按文档安装 `requirements.txt`（`chess` / `pyffish`）及本机 `claude` / `codex` CLI 时直接运行内部对弈/选题检查命令，Python 会抛出原生 `ModuleNotFoundError` 或 `FileNotFoundError` 堆栈。
   - **暂缓理由**：安装与运行前置条件已在 `README.md` 与 `docs/setup.md` 说明，常用只读入口（`--help`、`rate.py report`、`quiz report`、`viewer/`）均已脱离规则库与 CLI 依赖工作；不在内部运行路径上堆砌跨层目录树扫描或全局异常包装。
