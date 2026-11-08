[English](viewer-guide.en.md) | [简体中文](viewer-guide.md)

# Viewer & Video Recording Guide

The web viewer reads PGN files directly: standard PGN for International Chess and xqbase PGN for Xiangqi (Chinese Chess). You can browse all 180 official model games checked into `runs/<tag>/game.pgn`, the built-in test fixtures, or your own PGN files without model accounts or chess engines.

The viewer defaults to Chinese; append `lang=en` to the URL to switch the UI to English. For environment setup see [Setup & Running](setup.en.md), for viewer architecture and full URL parameter details see [Viewer Design (zh-CN)](viewer.md), and for asset and tool licenses see [Dependencies & Provenance](dependencies.en.md).

## Open Official Games & Built-in Samples

Start a local static HTTP server from the repository root:

```sh
python3 -m http.server --bind 127.0.0.1 8000
```

Open any of the links below in your browser:

- [Chess Peak Match (Opus Max vs Astra Max, Game 1)](http://127.0.0.1:8000/viewer/?files=/runs/g7-c-opus-astra-1/game.pgn&lang=en)
- [Xiangqi Peak Match (Opus Max vs Astra Max, Game 1)](http://127.0.0.1:8000/viewer/?files=/runs/g7-x-opus-astra-1/game.pgn&lang=en)
- [Chess Test Sample](http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/chess-sample.pgn&lang=en)
- [Xiangqi Test Sample](http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/xq-sample.pgn&lang=en)
- [Back-to-Back Playback of Both Samples](http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/chess-sample.pgn,/viewer/test/fixtures/xq-sample.pgn&autoplay=1&lang=en)

The repository's `runs/` directory contains `game.pgn` for all 65 official model match directories (180 games in total). Simply replace `files=` in the URL with any `/runs/<tag>/game.pgn` to inspect that match and read the model's move-by-move rationales. The HTTP server must be started from the repository root because paths in `files=` are resolved relative to the site root. Bind only to `127.0.0.1`, and press Ctrl-C in the terminal when finished. If port 8000 is in use, choose another port and update the URL. Because the viewer uses native browser ES modules, it cannot be opened directly via `file://`, and requires neither a build step nor `npm ci` for browsing.

## Browse Your Own PGNs

Open <http://127.0.0.1:8000/viewer/?lang=en> and drag `.pgn` files onto the page. Multiple dropped files play sequentially sorted by filename; prefix filenames with `01-`, `02-` to control playback order.

| Action | Shortcut |
| --- | --- |
| Previous / Next move | `←` / `→` |
| Play / Pause | `Space` |
| Start / End of current game | `Home` / `End` |
| Previous / Next game | `PgUp` / `PgDn` |

In wide windows (at least 900 px wide), the right panel displays the move list, move rationales/comments, elapsed time, and token counts recorded in the PGN; you can also click any move to jump directly to that ply. Narrow windows display a compact layout with the board and player banners. The viewer renders only the annotations and metadata embedded in the PGN—it does not run a live engine or fabricate missing metrics.

Common URL parameters (append after `files=...` with `&`):

| Parameter Example | Effect |
| --- | --- |
| `autoplay=1&gap=1.5` | Auto-play at 1.5 seconds per half-move (ply) |
| `anim=0` | Disable piece-sliding animation (default 0.3 s, counted inside `gap`) |
| `openhold=0.5` | Hold the initial board position for 0.5 s at the start of each game |
| `game=1&ply=20` | Open game 1 statically at the position after ply 20 |
| `ply=end` | Jump directly to the final position of the game |
| `summary=1` | Display the multi-game match summary scoreboard |
| `layout=wide` / `layout=compact` | Force wide two-column layout or compact single-column layout |
| `sound=1&vol=0.5` | Enable move/end sound effects at 50% volume (click or press a key first to unlock browser audio) |
| `lang=en` | English UI (original comment language and Chinese Xiangqi piece glyphs are preserved; Xiangqi moves render in WXF notation) |
| `names=opus=Claude Opus,astra=GPT astra` | Override displayed player names while keeping score attribution tied to raw PGN names |
| `title=1` | Show a title card before each game (disabled by default) |

Do not combine static positioning parameters (`game`, `ply`, `summary`) with `autoplay=1`. Web browsing starts muted by default; PGN side variations (RAV) are skipped in favor of the mainline. Xiangqi PGNs must use the xqbase move format supported by the viewer.

## Set Up Video Recording Tools

Video recording uses a Node.js script to drive headless Chromium frame-by-frame and pipes frames into FFmpeg to produce an MP4. It does not require Python rule libraries and makes no model calls. Prerequisites:

1. **Node.js and npm** (verified on the maintainer's machine on 2026-11-05 with Node.js 24.20.0 and npm 11.19.0; recorded as tested environment, not a strict minimum requirement).
2. Install locked dev dependencies in `viewer/`:

   ```sh
   cd viewer
   npm ci
   cd ..
   ```

3. **A Chromium browser compatible with Playwright.** `playwright-core` does not download browsers automatically; point to an existing Chromium binary via `--chromium /abs/path/to/Chromium` or the `VIEWER_CHROMIUM` environment variable. When unspecified, the script searches Playwright's local browser cache.
4. **FFmpeg executable**, specified via `--ffmpeg /abs/path/to/ffmpeg` or `VIEWER_FFMPEG` (falls back to `/opt/homebrew/bin/ffmpeg` if unspecified). Inspecting output streams also uses `ffprobe`.

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

When given a directory, `record.mjs` automatically loads `game.pgn` inside it—so you can record any checked-in official match directly (for example: `node viewer/record.mjs runs/g7-c-opus-astra-1 -o /tmp/g7-c-1.mp4 --gap 1.5 --openhold 0.5`). Common flags: `--no-sound` (mute), `--vol 0.5` (adjust volume), `--anim 0` (disable move animation), `--title` (enable title card), `--resulthold` (final position hold duration), and `--summaryhold` (series scoreboard hold duration). `--aspect 9:16` or `16:9` changes the viewport dimensions without specialized layout tuning, so inspect the output before publishing. View all flags with:

```sh
node viewer/record.mjs --help
```

Pressing Ctrl-C cleanly shuts down the recorder's Chromium instance, local HTTP server, and FFmpeg process, removing temporary files; output is written to a sibling temporary file and atomically renamed only upon completion.

Verify codec, resolution, and duration with `ffprobe`:

```sh
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,profile,pix_fmt,width,height,r_frame_rate:format=duration -of default=nw=1 /tmp/chess-sample.mp4
```

Expected defaults are `h264` (High profile), `yuv420p`, `1080x1440`, and `30/1`. Open the video to visually verify the opening frame, piece movement, text rendering, and end-of-game banner.

Checked-in `runs/<tag>/game.pgn` files are already exported and ready to view or record directly (do not run `export` on checked-in directories because bulky raw `game.jsonl` logs are excluded from git). If you record a new game that you ran locally yourself, first confirm the match has finished (the last entry in your local `game.jsonl` has `type=end`), then run `python -m llmchess export runs/<tag>` to export `game.pgn`.

To record with the English UI, append `--set lang=en --set "names=opus=Claude Opus,astra=GPT astra"` (optionally combined with `--openhold 0.5`). In English mode, Xiangqi moves are displayed in WXF notation while the input PGN remains in xqbase format.
