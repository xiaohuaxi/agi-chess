# cm-chessboard（原样拷贝，未改）

- 来源：https://github.com/shaack/cm-chessboard ，提交 `3188c99f183b9060ab312c69b2d80823294df924`（package.json 版本 8.15.1，与 npm 上 cm-chessboard@8.15.1 同版本号），2026-09-29 取自本机克隆 `~/repos/cm-chessboard`。
- 拷了什么：`src/` 整个目录（ES 模块，相对路径互相引用、无依赖）；`assets/chessboard.css`、`assets/pieces/standard.svg`、`assets/extensions/markers/markers.{css,svg}`。
- 没拷：`assets/pieces/staunty.svg`（CC BY-NC-SA 4.0，禁商用）、其余扩展的样式。

## 许可

- 代码（`src/`、`assets/*.css`、`markers.svg`）：MIT，见 `LICENSE`。
- 棋子 `assets/pieces/standard.svg`：**CC BY-SA 3.0**。文件开头注释写明：取自 Wikimedia Commons「SVG chess pieces/Standard」，作者 Cburnett、Rfc1394，由 shaack 为 cm-chessboard 修改。许可全文 `assets/pieces/CC-BY-SA-3.0.txt`（取自 https://creativecommons.org/licenses/by-sa/3.0/legalcode.txt ）。
  - 用它要署名（作者 + 许可 + 链接）；改了它的话，改后的文件也按 CC BY-SA 发布。
  - 旁证：Commons 上 Cburnett 的原件（如 `File:Chess_klt45.svg`）标的是 `{{self|GFDL|migration=relicense|BSD|GPL}}`，即 GFDL / CC BY-SA 3.0 / BSD / GPL 任选；cm-chessboard 这份改过的精灵图只声明了 CC BY-SA 3.0。
