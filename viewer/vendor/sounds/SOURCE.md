# 走子音效：el_boss「Chess Puzzle Blitz SFX」（CC0）

- 来源：freesound 上 el_boss 的音效包 https://freesound.org/people/el_boss/packs/30764/ （2020-11-25 上传，包内 4 个文件）。作者 el_boss。
- 许可：CC0 1.0（公有领域贡献，https://creativecommons.org/publicdomain/zero/1.0/）。2026-10-02 逐个打开下面三页核过，许可栏都写「Creative Commons 0」、链接指向 `publicdomain/zero/1.0/`。CC0 不要求署名，这里记来源只为可追溯。
- 下载日期：2026-10-02。原始文件要登录 freesound 才能下，这里用的是网站公开的试听版（`-hq.mp3`，与原件同一许可），48 kHz 单声道 MP3。
- 处理：**没有改文件**，原样存下、只改了文件名。音量不烤进文件：各声的增益在 `viewer/lib/sound.js` 里（页面播放和录制混音共用那一张表），定值的依据见 `docs/viewer.md`「走子音效」。

| 文件 | 原名 / 页面 | 试听版地址 | 时长 | 原始峰值 / 单声响度 | SHA-256 |
|---|---|---|---|---|---|
| move.mp3（落子） | Piece Placement，https://freesound.org/people/el_boss/sounds/546119/ | https://cdn.freesound.org/previews/546/546119_9129912-hq.mp3 | 0.11 s | −12.2 dBFS / −32.7 LUFS | f7f22fb32c610b525813ac5fc913f2da5d2548eb68c949cac1c4ed79c17880e3 |
| capture.mp3（吃子） | Piece Capture，https://freesound.org/people/el_boss/sounds/546120/ | https://cdn.freesound.org/previews/546/546120_9129912-hq.mp3 | 0.24 s | −2.3 dBFS / −20.6 LUFS | b0cc3ddd1760c17234d049a2c2d4564979ea784304c828a719ec6f66b90ca1a0 |
| end.mp3（终局） | Board Start，https://freesound.org/people/el_boss/sounds/546121/ | https://cdn.freesound.org/previews/546/546121_9129912-hq.mp3 | 0.61 s | −6.6 dBFS / −25.2 LUFS | 3136ab230407843cef8ff19d41b470ceec6cc491f6fafbfdbcba1b3d8ecdf241 |

- 「单声响度」的量法：单个音太短（不到 400 ms），EBU R128 的 integrated 直接量会报 −70；先补静音到 1.5 秒再量 integrated（静音块被门限滤掉，结果约等于有声那段的响度）：`ffmpeg -i x.mp3 -af "apad=whole_dur=1.5,ebur128=peak=sample" -f null -`。
- 终局声用的是包里的「Board Start」（开局摆盘声）：约 0.5 秒的一串木子碰撞，听感上和单声的落子 / 吃子明显不同，拿来当「这盘结束」的提示。包里第四个文件 Piece Slide（拖子声）没用。
