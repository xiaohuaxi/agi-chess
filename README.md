[English](README.md) | [简体中文](README.zh-CN.md)

# agi-chess

**If an AI cannot even play a decent game of chess on its own, it cannot be called AGI.** Chess and Xiangqi (Chinese Chess) are games of simple rules and complete information that ordinary people play well without specialized training; reasoning step by step from the position on the board to the moves that follow runs on the same principle as reasoning from the known to the unknown. A model that excels at coding or hard exam problems yet blunders pieces away the moment it sits at a board without an engine is still "jagged intelligence"—far from truly general.

This project puts untuned general-purpose models at the board like human players—with no engines, legal-move lists, or tactical hints—to measure their real strength in International Chess and Xiangqi, diagnose why they blunder, and test how reasoning effort, board representation, and thought carryover affect their play. The repository includes the match and quiz runner, 171 official model games, 9 judged quiz batches, rating calibration scripts, research reports, and an interactive game viewer.

> **Interactive Game Viewer ([`viewer/`](viewer/)) — Browse All 171 Games Zero-Config**
>
> Without installing any chess engine or configuring API keys, run `node viewer/serve.mjs --port 8765 --bind 127.0.0.1` (or `python3 -m http.server 8765 --bind 127.0.0.1`) in the repository root and open [`http://127.0.0.1:8765/viewer/?files=/runs/g7-c-opus-astra-1/game.pgn,/runs/g7-c-opus-astra-1/analysis.jsonl&lang=en`](http://127.0.0.1:8765/viewer/?files=/runs/g7-c-opus-astra-1/game.pgn,/runs/g7-c-opus-astra-1/analysis.jsonl&lang=en) to immediately see the board, per-move model rationales, engine blunder/mistake annotations, elapsed time, and token stats. You can also open [`http://127.0.0.1:8765/viewer/?lang=en`](http://127.0.0.1:8765/viewer/?lang=en) without query parameters and drag any single-game `runs/<tag>/game.pgn` or multi-game batch `runs/<batch>/<game>/game.pgn` (optionally alongside its `analysis.jsonl`) onto the page; exporting MP4 replay videos requires running `npm ci` in `viewer/` with Chromium and `ffmpeg` available (see [Viewer & Video Guide](docs/viewer-guide.en.md)).

## Start Here

| What you want to do | Entry point |
| --- | --- |
| **Replay real model games or samples, read per-move rationales, or record MP4 videos** | **[Viewer & Video Guide](docs/viewer-guide.en.md) ([`viewer/`](viewer/))** |
| Browse all experiments, findings, and available public evidence | [Research Index](docs/research.en.md) |
| Recompute ratings, set up the environment, run tests, or launch matches | [Setup & Running](docs/setup.en.md) |
| Check dependency roles, upstream provenance, and licenses | [Dependencies & Provenance](docs/dependencies.en.md) |
| Understand prompts, match protocols, record formats, and failure handling | [System Design (zh-CN)](docs/design.md) |
| Track maintenance logs and open decisions | [Project Status (zh-CN)](docs/status.md) |

## Two Model-Free Quick Starts

All commands below run from the repository root and require neither model credentials nor chess engines. Recomputing ratings (`analysis/rating`) and browsing games (`viewer/`) do not require installing additional Python rule libraries.

### Install Python Rule Libraries (Optional)

If you want to run command-line matches, re-export game records, verify checked-in quiz banks offline, or run the Python offline test suite, install the rule libraries from `requirements.txt`:

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python3 data/batch1/select_positions.py check
python3 data/batch2/select_positions.py check
```

`select_positions.py check` verifies the checked-in Batch 1 and Batch 2 position banks (`data/batch1/` and `data/batch2/`) offline without engines or model accounts. For full environment setup and engine opponent installation, see [Setup & Running](docs/setup.en.md).

### Recompute Published Ratings

Requires only the Python 3 standard library:

```sh
python3 analysis/rating/rate.py report
```

The script reads checked-in match scores and human-scale anchor data and runs 1,000 bootstrap resamples (taking a few minutes). Its output reproduces the scales and intervals in the [Opus Max Rating Report](docs/results/opus-max-rating.md). It recomputes the statistical fit rather than re-playing raw games or re-running per-move engine evaluations.

### Replay Official Model Games and Sample PGNs

Start a local static HTTP server with Python 3:

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

Open in your browser (with `&lang=en` for the English UI):

- [Chess Peak Match (Opus Max vs Astra Max, Game 1)](http://127.0.0.1:8000/viewer/?files=/runs/g7-c-opus-astra-1/game.pgn&lang=en)
- [Xiangqi Peak Match (Opus Max vs Astra Max, Game 1)](http://127.0.0.1:8000/viewer/?files=/runs/g7-x-opus-astra-1/game.pgn&lang=en)
- [Chess Test Sample](http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/chess-sample.pgn&lang=en)
- [Xiangqi Test Sample](http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/xq-sample.pgn&lang=en)

Use the Left/Right arrow keys to step through moves and Space to play or pause; you can also open the [Blank Viewer](http://127.0.0.1:8000/viewer/?lang=en) and drag in any `.pgn` file (plus its `analysis.jsonl`), or point `files=` to any checked-in `/runs/<tag>/game.pgn` (for the 58 single-game directories) or `/runs/<batch>/<game>/game.pgn` (for the 7 multi-game batch directories `b1`, `b1-session`, `b2`, `b3max-ch`, `b3max-xq`, `zc`, `zx`, e.g. `/runs/zc/maia-1900-s1-w/game.pgn`). Press Ctrl-C in the terminal when finished. If port 8000 is busy, choose another port and update the URLs accordingly.

Viewing in a browser requires no `npm` installation. `runs/` includes `game.pgn` (with full per-move rationale annotations, elapsed time, and token counts) for all 171 official model games. Recording MP4 videos requires headless Chromium automation and FFmpeg; see the [Viewer & Video Guide](docs/viewer-guide.en.md).

The viewer defaults to Chinese (`lang=zh`); append `&lang=en` to switch the interface to English, and use `names=` to override displayed player names. See the [Viewer & Video Guide](docs/viewer-guide.en.md) for full URL parameters.

## Research Themes

- **Reasoning Depth & Session Continuity:** Position quizzes and full-game experiments separately test the impact of reasoning effort, multi-turn session continuation, and retaining vs. dropping prior thinking blocks. Identically named effort levels across providers do not imply equal compute budgets.
- **Board Representation & Blunder Taxonomy:** We compare ASCII boards, FEN strings, and piece lists, combining post-game engine analysis with visible model rationales to diagnose errors. Visible rationales are inspectable response text, not the model's hidden chain-of-thought.
- **Model-vs-Model Play & Rating Calibration:** Covers head-to-head model matches, fixed-strength engine opponents, and engine ladder calibration. Cross-model matches are mostly small-sample directional tests, and analogies to human rating pools carry anchor and conversion uncertainties.

The [Round 1 Summary](docs/results/summary-round1.md) summarizes only the initial phase of experiments; subsequent head-to-head matches, rating calibrations, and Gemini evaluations are cataloged in the [Research Index](docs/research.en.md). Each report preserves the conditions and conclusions of its time.

## Match Principles

Full games default to the **"Model as Real Player" (`real`) protocol**: each side plays inside one continuous session, chooses moves from the board state, and writes a visible rationale before its move. The harness validates legality and logs the game without offering engine hints, check warnings, threat lists, or legal-move enumerations; engines act strictly as opponents or post-game arbiters. Three consecutive illegal attempts on the same turn forfeit the game—a custom tournament rule defined by this project.

If a model invokes or attempts a tool call, the match pauses immediately; if a safety/anti-CoT-extraction refusal occurs, the match halts and preserves raw evidence without rephrasing or auto-resuming. Because upstream CLIs do not expose every internal tool event, "no observed tool event" is not a formal proof of zero tool attempts. See [System Design](docs/design.md) for protocol history and boundaries.

## Runtime & Data Boundaries

- **Official Games & Judged Quizzes Included:** `runs/` now ships with all 65 official model match directories—43 model-vs-model single-game directories + 22 model-vs-engine directories (15 single-game directories + 7 multi-game batch directories, 171 games in total)—including `game.pgn` (with per-move rationales, timing, and token metadata), `analysis.jsonl` / `analysis-summary.json` (per-move engine evaluations and blunder flags for 170 games), `summary.json` / `summary.md`, and 9 official position-quiz batches (`quiz-*`, 50 `judged.jsonl` files) with `judged.jsonl` and `report.txt`. Only bulky low-level event logs (`game.jsonl`), duplicate `record.txt` files, raw engine-vs-engine calibration games (whose outcomes are in `analysis/rating/games-engines.csv`), and `.mp4` video recordings are excluded.
- **Built-in `llm-chat` Dual-Channel Driver:** The repository bundles `llm-chat` (`llm_chat.py` and `agy_core.py`) under `.agents/skills/llm-chat/`, and `agi_chess/chat.py` invokes this in-repo script by default—no external `llm-chat` skill installation is required. Full-game matches drive two categories of model channels (see [Setup & Running](docs/setup.en.md)):
  - **Local Agent CLI Subscription Channel** (primary experimental channel): Claude (via `claude` CLI), GPT (via `codex` CLI), and Gemini (via `agy` CLI), using the subscription quota of the locally installed and authenticated CLI; if the required CLI is not installed, `llm-chat` immediately returns a clear "not installed" error.
  - **HTTP API Channel** (DeepSeek & OpenRouter): Configured via environment variables `API_KEY_OPENROUTER` (or `OPENROUTER_API_KEY`) and `API_KEY_DEEPSEEK` (or `DEEPSEEK_API_KEY`). When running `deepseek:flash` (`deepseek-flash`) or `deepseek:v4-pro` (`deepseek-v4-pro`), if `API_KEY_OPENROUTER` is set without `API_KEY_DEEPSEEK`, `llm-chat` automatically routes DeepSeek requests through OpenRouter (`deepseek-flash` → `deepseek/deepseek-v4.1-flash`, `deepseek-v4-pro` → `deepseek/deepseek-v4-pro`), so a separate official DeepSeek API key is not required.
- Model availability, CLI behavior, and session handling change over time. Model names and versions in reports document historical experiments rather than guaranteeing current service availability.
- Running `play` without `--dry-run` makes live model calls and consumes quota; start with the offline quick starts above.

## Repository Layout

| Path | Contents |
| --- | --- |
| `agi_chess/` | Match loop, position quizzes, PGN/record export, and post-game engine analyzer |
| `.agents/skills/` | Built-in `llm-chat` (multi-model session driver) and `replay-video` (viewer & video recording skill) |
| `tests/` | Python offline unit tests |
| `data/` | Checked-in position banks and selection scripts; some raw selection sources reside only on the maintainer's machine |
| `analysis/rating/` | Rating fitting scripts, match stats scripts, and input datasets |
| `viewer/` | Web PGN viewer, MP4 recorder, test fixtures, and vendored third-party assets |
| `docs/results/` | Batch-by-batch research reports |
| `runs/` | Checked-in outputs for 65 official model match directories (171 `game.pgn` files + engine analyses) and 9 judged quiz batches; raw `game.jsonl` streams and `.mp4` videos are git-ignored |

## Licensing

- Original source code, research reports, position banks, and the `viewer/` web application in this repository are licensed under the MIT License (see root [LICENSE](LICENSE));
- Third-party frontend components and media under `viewer/vendor/` retain their respective permissive licenses (BSD-2-Clause, MIT, BSD-3-Clause, CC0 1.0); see [Dependencies & Provenance](docs/dependencies.en.md);
- Rule validation in `agi_chess/` imports `chess` (`python-chess`) and `pyffish` in-process at runtime (both GPL-3.0-or-later, not distributed in this repo, installed locally via `python3 -m pip install -r requirements.txt`); running the combined Python program or redistributing a bundle containing them is subject to GPL-3.0-or-later. See [License Review](docs/license-review.en.md) for full details.
