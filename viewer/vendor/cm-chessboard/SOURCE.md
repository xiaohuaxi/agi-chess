# cm-chessboard

- 来源：https://github.com/shaack/cm-chessboard ，提交 `3188c99f183b9060ab312c69b2d80823294df924`（package.json 版本 8.15.1，与 npm 上 cm-chessboard@8.15.1 同版本号），2026-09-29 取自本机克隆 `~/repos/cm-chessboard`。
- 拷了什么：`src/` 整个目录（ES 模块，相对路径互相引用、无依赖）；`assets/chessboard.css`、`assets/extensions/markers/markers.{css,svg}`。许可 MIT，见 `LICENSE`。
- **没拷它自带的棋子**：`standard.svg` 是 CC BY-SA 3.0、`staunty.svg` 是 CC BY-NC-SA 4.0。改用 Cburnett 原件按 BSD 拼的 `assets/pieces/cburnett.svg`，来源、许可和生成脚本见 `../cburnett-pieces/`。

## 本地改动（只此一处）

- `src/Chessboard.js` 默认棋子文件由 `pieces/standard.svg` 改成 `pieces/cburnett.svg`（行内注释标了 `llm-chess:`）。原因：原文件已移除，默认值不改的话，谁忘了传参数就会去取一个不存在的文件。升级 cm-chessboard 时记得重做这一处。
