[English](viewer-guide.en.md) | [简体中文](viewer-guide.md)

# Viewer & Video Recording Guide

The web viewer reads PGN files directly: standard PGN for International Chess and xqbase PGN for Xiangqi (Chinese Chess). You can browse all 192 official model games checked into `runs/` (79 single-game directories `runs/<tag>/game.pgn` and 7 multi-game batch directories `runs/<batch>/<game>/game.pgn`), the built-in test fixtures, or your own PGN files without model accounts or chess engines.

The viewer defaults to Chinese; switch languages directly from the top bar or home page, or append `lang=en` to the URL. For environment setup see [Setup & Running](setup.en.md), for viewer architecture and full URL parameter details see [Viewer Design (zh-CN)](viewer.md), and for asset and tool licenses see [Dependencies & Provenance](dependencies.en.md).

## Browse Online Zero-Install (GitHub Pages)

If you want to inspect the 192 official model games checked into `runs/` (or drag in your own local `.pgn` files), open the hosted GitHub Pages site directly on desktop or mobile without cloning the repository or starting a local server (all three pages share top-bar navigation, and passing a run directory automatically overlays per-move engine evaluations, best moves, and blunder annotations from its companion `analysis.jsonl`):

- **[Featured Viewer Home](https://xiaohuaxi.github.io/agi-chess/?lang=en)** ([中文界面](https://xiaohuaxi.github.io/agi-chess/)): built-in featured games, local `.pgn` drag-and-drop, and instant Chinese/English switching.
- **[No-Engine Series Board (`series.html`)](https://xiaohuaxi.github.io/agi-chess/series.html?lang=en)** ([Xiangqi tab `?variant=xiangqi&lang=en`](https://xiaohuaxi.github.io/agi-chess/series.html?variant=xiangqi&lang=en)): variant-separated head-to-head model series summaries, three-model round-robin tables, engine calibration anchors, and direct links to signature tactical moments.
- **[All 192 Games Catalog (`catalog.html`)](https://xiaohuaxi.github.io/agi-chess/catalog.html?lang=en)** ([Batch filter example `?batch=zc&lang=en`](https://xiaohuaxi.github.io/agi-chess/catalog.html?batch=zc&lang=en)): filterable index of all 192 official games by variant, matchup category (model-vs-model / vs engine or random), model pills, and keywords; opening a game from the Series Board or Catalog preserves your browse state for one-click return in the top bar.
- Featured games and signature blunder positions:
  - [Chess: Gemini 4 Neon `xhigh` vs. Carbon `high` (Game 1, ply 40 `20...Re8??` blunder)](https://xiaohuaxi.github.io/agi-chess/?files=runs/neon-xhigh-vs-carbon-high-20261119&ply=40&lang=en)
  - [Chess: GPT-6.2 Astra `max` vs. Gemini 4 Neon `xhigh` (Game 4, `59.Qhd5#`, Astra 11.7 ACPL / 0 blunders)](https://xiaohuaxi.github.io/agi-chess/?files=runs/neon-xhigh-vs-astra-max-20261119-4&lang=en)
  - [Xiangqi: Opus 5.5 `high` vs. Gemini 4 Carbon `high` (Game 3, ply 9 `5.R9.8??` screened-Cannon blunder)](https://xiaohuaxi.github.io/agi-chess/?files=runs/carbon-vs-agy-opus-high-xq-20261114-3&ply=9&lang=en)
  - [Chess Peak Match (Opus Max vs. Astra Max, Game 1)](https://xiaohuaxi.github.io/agi-chess/?files=runs/g7-c-opus-astra-1&lang=en)
  - [Xiangqi Peak Match (Opus Max vs. Astra Max, Game 1)](https://xiaohuaxi.github.io/agi-chess/?files=runs/g7-x-opus-astra-1&lang=en)
  - [Chess Rating Calibration Match (Opus Max vs. Maia-1900)](https://xiaohuaxi.github.io/agi-chess/?files=runs/zc/maia-1900-s1-w&lang=en)

The repository's `runs/` directory contains `game.pgn` for all 86 official model match directories (192 games in total): **79 single-game directories** (64 model-vs-model + 15 single-game model-vs-engine `b1-ch-*`/`b1-xq-*`) can be passed directly as `runs/<tag>`, and **7 multi-game batch directories** (`b1`, `b1-session`, `b2`, `b3max-ch`, `b3max-xq`, `zc`, `zx`, 113 games in total) place each game in a second-level subdirectory `runs/<batch>/<game>` (e.g. `runs/zc/maia-1900-s1-w`). Replace `files=` in the online URL with any of those paths to inspect that game, its move-by-move rationales, and its engine blunder badges.

## Local Offline Server, Newly Played Local Runs & Test Fixtures

For offline environments, inspecting newly played local runs (`runs/<tag>`), opening built-in test fixtures (`viewer/test/fixtures/*.pgn`), or recording MP4 videos, start a local static HTTP server from the repository root:

```sh
node viewer/serve.mjs
# Listens on 127.0.0.1:8765 by default; without Node.js, use: python3 -m http.server 8765 --bind 127.0.0.1
```

Open any of the local links below in your browser:

- [Local Viewer Home (with featured games)](http://127.0.0.1:8765/viewer/?lang=en)
- [Local Official Game Example (Opus Max vs. Astra Max, Game 1)](http://127.0.0.1:8765/viewer/?files=/runs/g7-c-opus-astra-1&lang=en)
- [Chess Test Sample](http://127.0.0.1:8765/viewer/?files=/viewer/test/fixtures/chess-sample.pgn&lang=en) · [Xiangqi Test Sample](http://127.0.0.1:8765/viewer/?files=/viewer/test/fixtures/xq-sample.pgn&lang=en)
- [Back-to-Back Playback of Both Samples](http://127.0.0.1:8765/viewer/?files=/viewer/test/fixtures/chess-sample.pgn,/viewer/test/fixtures/xq-sample.pgn&autoplay=1&lang=en)

When a path points to `game.pgn` (or a directory shorthand), the viewer automatically requests `analysis.jsonl` in the same directory to validate and overlay engine blunder/mistake/inaccuracy badges (silently ignoring 404s, while also supporting comma-separated multiple files). Start the local server from the repository root; it binds only to `127.0.0.1` (press Ctrl-C in the terminal when finished). If port 8765 is in use, pass `--port 8000` to `node viewer/serve.mjs` and update the URL. Because the viewer uses native browser ES modules, it cannot be opened directly via `file://`, and requires neither a build step nor `npm ci` for browsing.

## Interactive Controls, Your Own PGNs & Deep-Link Sharing

Open the [Live Viewer](https://xiaohuaxi.github.io/agi-chess/?lang=en) or <http://127.0.0.1:8765/viewer/?lang=en> to click one of the built-in featured games or drag `.pgn` files (optionally alongside matching `analysis.jsonl` files) onto the page (dropped files are parsed locally in your browser and never uploaded). Multiple dropped files play sequentially sorted by filename; prefix filenames with `01-`, `02-` to control playback order.

| Action | Shortcut |
| --- | --- |
| Previous / Next move | `←` / `→` |
| Play / Pause | `Space` |
| Start / End of current game | `Home` / `End` |
| Previous / Next game | `PgUp` / `PgDn` |

- **Desktop Two-Column & Mobile Stacked Layouts:** All pages use a fixed dark eye-comfort theme. In wide windows (at least 900 px wide), the right panel displays the move list, move rationales/comments, engine evaluations, elapsed time, and token counts recorded in the PGN (click any move to jump directly to that ply). On phones or narrow browser windows (`< 900 px` in normal browsing), the viewer switches to a stacked layout with **the step-control bar tucked directly beneath the board**, followed by the current move's rationale and an **8-row line-aligned scrollable move box**; only recording mode (`rec=1`) or explicit `layout=compact` hides the info panel to show just the board and player banners.
- **Per-Move Engine Score, Best Move & Channel-Retry Warning Rendering:** When a companion `analysis.jsonl` is loaded, the annotation panel displays **fixed first-player-perspective (White in Chess / Red in Xiangqi)** per-move engine eval/win-rate swings and the engine's best move alongside blunder/mistake/inaccuracy badges. Historical PGN comments containing inline channel-retry `⚠` notices split and dim the raw warning text into a separate block so it does not clutter the player's move rationale.
- **Shareable Position Deep Links (`ply=`):** Manually stepping through moves or clicking a move automatically updates `ply=` (and `game=` in multi-game playlists) in the browser address bar, so copying the URL shares that exact position.
- **Language Toggle:** Switch between Chinese and English directly from the top bar or home page, or pass `lang=en` / `lang=zh` in the URL. The viewer renders only the annotations and metadata embedded in the PGN (and companion `analysis.jsonl`), without running a live engine or fabricating missing metrics.

Common URL parameters (append after `files=...` with `&`):

| Parameter Example | Effect |
| --- | --- |
| `autoplay=1&gap=1.5` | Auto-play at 1.5 seconds per half-move (ply) |
| `anim=0` | Disable piece-sliding animation (default 0.3 s, counted inside `gap`) |
| `openhold=0.5` | Hold the initial board position for 0.5 s at the start of each game |
| `game=1&ply=20` | Open game 1 statically at the position after ply 20 (manual stepping also updates `ply` in the URL bar) |
| `ply=end` | Jump directly to the final position of the game |
| `summary=1` | Display the multi-game match summary scoreboard |
| `layout=wide` / `layout=compact` | Force wide two-column layout or recording-style compact board-only layout (defaults to two-column at `>= 900 px` and scrollable stacked mobile layout below `900 px`) |
| `sound=1&vol=0.5` | Enable move/end sound effects at 50% volume (click or press a key first to unlock browser audio) |
| `lang=en` | English UI (original comment language and Chinese Xiangqi piece glyphs are preserved; Xiangqi moves render in WXF notation) |
| `names=opus=Claude Opus,astra=GPT astra` | Override displayed player names while keeping score attribution tied to raw PGN names |
| `title=1` | Show a title card before each game (disabled by default) |

Do not combine static positioning parameters (`game`, `ply`, `summary`) with `autoplay=1`. Web browsing starts muted by default; PGN side variations (RAV) are skipped in favor of the mainline. Xiangqi PGNs must use the xqbase move format supported by the viewer.

## Set Up Video Recording Tools

Video recording uses a Node.js script to drive headless Chromium frame-by-frame and pipes frames into FFmpeg to produce an MP4. It does not require Python rule libraries and makes no model calls. Prerequisites:

1. **Node.js >= 22 and npm** (quoted globbing in `node --test 'viewer/test/*.test.js'` requires Node.js 22+; on Node 18/20, omit the single quotes so the shell expands the glob: `node --test viewer/test/*.test.js`. Verified on 2026-11-05 with Node.js 24.20.0 and npm 11.19.0).
2. Install locked dev dependencies in `viewer/` from the repository root:

   ```sh
   npm --prefix viewer ci
   ```

3. **A Chromium browser compatible with Playwright.** `playwright-core` does not download browsers during `npm ci`; point to an existing binary via `--chromium /abs/path/to/Chromium` or `VIEWER_CHROMIUM`. When unspecified, the script checks Playwright's local browser cache (installable for the locked `1.58.2` version from the repository root via `node viewer/node_modules/playwright-core/cli.js install --with-deps chromium`) and then searches `PATH` and standard system paths for `chromium`, `chromium-browser`, `google-chrome-stable`, `google-chrome`, `/snap/bin/chromium`, and macOS `/Applications/Google Chrome.app/...`.
4. **FFmpeg executable**, specified via `--ffmpeg /abs/path/to/ffmpeg` or `VIEWER_FFMPEG` (otherwise searched automatically in `PATH` and standard paths such as `/usr/bin/ffmpeg`, `/usr/local/bin/ffmpeg`, and `/opt/homebrew/bin/ffmpeg`). Inspecting output streams also uses `ffprobe`.
5. **CJK fonts on headless Linux servers:** Xiangqi piece glyphs and Chinese UI text render using system fonts. On headless Linux systems, install Chinese fonts before recording or taking screenshots (e.g., on Ubuntu/Debian: `sudo apt install fonts-noto-cjk fonts-arphic-ukai`); otherwise the Chinese characters on Xiangqi pieces will render as missing-glyph tofu boxes.

The web viewer itself does not depend on these recording tools—you never need Chromium or FFmpeg just to browse games.

## Record to MP4

Run from the repository root (the output directory must exist, and the target filename must not already exist):

```sh
node viewer/record.mjs viewer/test/fixtures/chess-sample.pgn -o /tmp/chess-sample.mp4 --gap 1.5 --openhold 0.5
```

Default output is 3:4 aspect ratio, 1080×1440 resolution, H.264 at 30 fps, with move and game-end audio. Passing multiple inputs plays them in order and appends a final series scoreboard:

```sh
node viewer/record.mjs viewer/test/fixtures/chess-sample.pgn viewer/test/fixtures/xq-sample.pgn -o /tmp/two-samples.mp4 --gap 1.5 --openhold 0.5
```

When given a directory, `record.mjs` automatically loads `game.pgn` directly inside it—so you can record any checked-in single-game directory (`node viewer/record.mjs runs/g7-c-opus-astra-1 -o /tmp/g7-c-1.mp4 --gap 1.5 --openhold 0.5`) or any single-game subdirectory inside a multi-game batch (`node viewer/record.mjs runs/zc/maia-1900-s1-w -o /tmp/zc-s1w.mp4`; note that top-level batch directories like `runs/zc` only contain `summary.*`, so pass the second-level game subdirectory). Common flags: `--no-sound` (mute), `--vol 0.5` (adjust volume), `--anim 0` (disable move animation), `--title` (enable title card), `--resulthold` (final position hold duration), and `--summaryhold` (series scoreboard hold duration). `--aspect 9:16` or `16:9` changes the viewport dimensions without specialized layout tuning, so inspect the output before publishing. View all flags with:

```sh
node viewer/record.mjs --help
```

Pressing Ctrl-C cleanly shuts down the recorder's Chromium instance, local HTTP server, and FFmpeg process, removing temporary files; output is written to a sibling temporary file and atomically renamed only upon completion.

Verify codec, resolution, and duration with `ffprobe`:

```sh
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,profile,pix_fmt,width,height,r_frame_rate:format=duration -of default=nw=1 /tmp/chess-sample.mp4
```

Expected defaults are `h264` (High profile), `yuv420p`, `1080x1440`, and `30/1`. Open the video to visually verify the opening frame, piece movement, text rendering, and end-of-game banner.

Checked-in `runs/<tag>/game.pgn` (for 79 single-game directories) and `runs/<batch>/<game>/game.pgn` (for 7 multi-game batch directories) files are already exported and ready to view or record directly (do not run `export` on checked-in directories because bulky raw `game.jsonl` logs are excluded from git). If you record a new game that you ran locally yourself, first confirm the match has finished (the last entry in your local `game.jsonl` has `type=end`), then run `python -m agi_chess export runs/<tag>` to export `game.pgn`.

To record with the English UI, append `--set lang=en --set "names=opus=Claude Opus,astra=GPT astra"` (optionally combined with `--openhold 0.5`). In English mode, Xiangqi moves are displayed in WXF notation while the input PGN remains in xqbase format.
