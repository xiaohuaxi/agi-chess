[English](README.md) | [简体中文](README.zh-CN.md)

# agi-chess

**If an AI cannot even play a decent game of chess on its own, it cannot be called AGI.** Chess and Xiangqi (Chinese Chess) are games of simple rules and complete information that ordinary people play well without specialized training; reasoning step by step from the position on the board to the moves that follow runs on the same principle as reasoning from the known to the unknown. A model that excels at coding or hard exam problems yet blunders pieces away the moment it sits at a board without an engine is still "jagged intelligence"—far from truly general.

This project puts untuned general-purpose models at the board like human players—with no engines, legal-move lists, or tactical hints—to measure their real strength in International Chess and Xiangqi, diagnose why they blunder, and test how reasoning effort, board representation, and thought carryover affect their play. The repository includes the match and quiz runner, 171 official model games, 9 judged quiz batches, rating calibration scripts, research reports, and an interactive game viewer.

> **Interactive Game Viewer ([`viewer/`](viewer/)) — Browse All 171 Games Zero-Config**
>
> Without installing any chess engine or configuring API keys, run `node viewer/serve.mjs` in the repository root (listening on `127.0.0.1:8765` by default; or `python3 -m http.server 8765 --bind 127.0.0.1` if Node.js is unavailable), then open [`http://127.0.0.1:8765/viewer/?lang=en`](http://127.0.0.1:8765/viewer/?lang=en) to click a built-in featured game or go straight to [`http://127.0.0.1:8765/viewer/?files=/runs/g7-c-opus-astra-1&lang=en`](http://127.0.0.1:8765/viewer/?files=/runs/g7-c-opus-astra-1&lang=en) (passing a run directory or `game.pgn` automatically loads the companion `analysis.jsonl` blunder annotations) to see the board, per-move model rationales, engine blunder/mistake badges, elapsed time, and token stats. You can also drag any `runs/<tag>/game.pgn` or `runs/<batch>/<game>/game.pgn` (optionally alongside its `analysis.jsonl`) onto the page; exporting MP4 replay videos requires running `npm --prefix viewer ci` with Chromium and `ffmpeg` available (see [Viewer & Video Guide](docs/viewer-guide.en.md)).

## Start Here

| What you want to do | Entry point |
| --- | --- |
| **Replay real model games or samples, read per-move rationales, or record MP4 videos** | **[Viewer & Video Guide](docs/viewer-guide.en.md) ([`viewer/`](viewer/))** |
| Browse all experiments, findings, and available public evidence | [Research Index](docs/research.en.md) |
| Recompute ratings, set up the environment, run tests, or launch matches | [Setup & Running](docs/setup.en.md) |
| Check dependency roles, upstream provenance, and licenses | [Dependencies & Provenance](docs/dependencies.en.md) |
| Understand prompts, match protocols, record formats, and failure handling | [System Design (zh-CN)](docs/design.md) |
| Track maintenance logs and open decisions | [Project Status (zh-CN)](docs/status.md) |

## Quick Starts (No Model Accounts or Engines Needed)

All commands below run from the repository root and require neither model credentials nor chess engines.

### Part 1: Zero-Dependency 30-Second Experience (Only Python 3 Stdlib or Node.js)

1. **Browse 171 Official Games & Engine Blunder Reviews**:

   ```sh
   node viewer/serve.mjs
   # Or without Node.js: python3 -m http.server 8765 --bind 127.0.0.1
   ```

   Open in your browser (passing a directory path or `game.pgn` automatically overlays blunder badges from the same directory's `analysis.jsonl`):
   - [Blank Viewer (with 4 clickable featured games)](http://127.0.0.1:8765/viewer/?lang=en)
   - [Chess Peak Match (Opus Max vs Astra Max, Game 1)](http://127.0.0.1:8765/viewer/?files=/runs/g7-c-opus-astra-1&lang=en)
   - [Xiangqi Peak Match (Opus Max vs Astra Max, Game 1)](http://127.0.0.1:8765/viewer/?files=/runs/g7-x-opus-astra-1&lang=en)
   - [Chess: Argon High vs Opus High (Game 1)](http://127.0.0.1:8765/viewer/?files=/runs/argon-vs-agy-opus-high-20261019&lang=en)
   - [Chess Rating Calibration Match (Opus Max vs Maia-1900)](http://127.0.0.1:8765/viewer/?files=/runs/zc/maia-1900-s1-w&lang=en)
   - [Chess Test Sample](http://127.0.0.1:8765/viewer/?files=/viewer/test/fixtures/chess-sample.pgn&lang=en) · [Xiangqi Test Sample](http://127.0.0.1:8765/viewer/?files=/viewer/test/fixtures/xq-sample.pgn&lang=en)

   Use Left/Right arrow keys to step through moves and Space to play or pause; replace `files=` with any single-game directory `/runs/<tag>` (58 single-game directories) or multi-game batch subdirectory `/runs/<batch>/<game>` (7 multi-game batch directories `b1`, `b1-session`, `b2`, `b3max-ch`, `b3max-xq`, `zc`, `zx`). The viewer defaults to Chinese (`lang=zh`); append `&lang=en` for English, and use `names=` to override displayed player names (see [Viewer & Video Guide](docs/viewer-guide.en.md)).

2. **Recompute Rating Scales in Seconds** (requires only the Python 3 standard library):

   ```sh
   python3 analysis/rating/rate.py report --boot 10   # ~1.5s quick table (10 bootstrap resamples)
   python3 analysis/rating/rate.py report             # Full 1,000 bootstrap resamples (~1.5 min, reproduces exact report CIs)
   ```

   Reads checked-in match scores and human-scale anchor data to reproduce the scales and intervals in the [Opus Max Rating Report](docs/results/opus-max-rating.md). It recomputes the statistical fit rather than re-playing raw games or re-running per-move engine evaluations.

3. **Recompute All 9 Position-Quiz Summary Tables in 0.1s** (requires only the Python 3 standard library):

   ```sh
   python3 -m agi_chess.quiz report --batch batch2    # Outputs table in 0.1s; supports batch1, batch2, batch3, 4p, 4p2, 5-ds, 5-sol, 6r, 6r-sol
   ```

### Part 2: Install Python Rule Libraries & Run Your First Local Match (Optional)

To run command-line matches, export game records, verify position banks offline, or run the Python unit test suite, install the rule libraries (`chess` and `pyffish`):

Python 3.13 is recommended. If you have several Python versions installed, use `python3.13` instead of `python3` when creating the virtual environment; `pyffish` includes a native extension and may require a working C++ toolchain (see [Setup](docs/setup.en.md)).

1. **Create a virtual environment and install `requirements.txt`** (on Ubuntu/Debian, if `ensurepip` is missing, run `sudo apt install python3-venv` first):

   ```sh
   python3 -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Verify position banks and run unit tests**:

   ```sh
   python3 data/batch1/select_positions.py check
   python3 data/batch2/select_positions.py check
   python3 -m unittest discover -s tests -t . -v
   ```

   `select_positions.py check` verifies the Batch 1 and Batch 2 position banks offline; when local Stockfish / Fairy-Stockfish engines are not installed, `unittest -v` automatically skips the 21 live-engine integration tests while passing all offline tests.

3. **Run a Zero-API-Cost First Match in 0.1s & Inspect Prompts**:

   ```sh
   # Play 20 plies between two random movers (no API key or engine needed; writes runs/demo-random/game.pgn in 0.1s, viewable at ?files=/runs/demo-random)
   python3 -m agi_chess play --game chess --tag demo-random --white random --black random --max-plies 20 --seed 42
   # Print the system prompt and first-move user prompt under the real-player protocol without calling any model
   python3 -m agi_chess play --game xiangqi --tag demo-prompt --dry-run
   ```

   For full environment setup, engine opponent installation, and post-game engine blunder analysis (`python3 -m agi_chess.analyze runs/<tag>`), see [Setup & Running](docs/setup.en.md).

## Research Themes & Key Findings

- **Reasoning Depth & Session Continuity:** Position quizzes and full-game experiments separately test the impact of reasoning effort, multi-turn session continuation, and retaining vs. dropping prior thinking blocks. Identically named effort levels across providers do not imply equal compute budgets.
- **Board Representation & Blunder Taxonomy:** We compare ASCII boards, FEN strings, and piece lists, combining post-game engine analysis with visible model rationales to diagnose errors. Visible rationales are inspectable response text, not the model's hidden chain-of-thought.
- **Model-vs-Model Play & Rating Calibration:** Covers head-to-head model matches, fixed-strength engine opponents, and engine ladder calibration. Cross-model matches are mostly small-sample directional tests, and analogies to human rating pools carry anchor and conversion uncertainties.

**Summary of Core Quantitative Findings** (see [Research Index](docs/research.en.md) and [Project Status (zh-CN)](docs/status.md) for full details):

- **Calibrated Playing Strength (Opus Max across 67 Engine Calibration Games):** In International Chess (30 games), under engine adjudication at the 200-ply cap (≥300 cp lead wins), Opus Max fits at **+189 scale points above Maia-1900** (95% CI: 66–313), corresponding to **~1800 Lichess Blitz / ~1920 Lichess Rapid** (or +281 / ~1910 Blitz / ~2020 Rapid under the original cap-is-draw rule); in Xiangqi (37 games), it fits at **+121 Elo above Fairy-Stockfish `nodes=100`** (95% CI: +1 to +236), comparable to or slightly above `nodes=300` (+82) and clearly below `nodes=1000` (+385).
- **Move Legality & Capture Rules Are Not the Primary Bottleneck:** Under the real-player protocol, models rarely output illegal moves. In targeted diagnostics across 14 full-game missed-capture/hanging-piece positions, models listed every legal capture **26/26 times** when asked in isolation, yet failed to mention the critical capture in 13/14 full-game rationales—pointing to **selective attention during search and shallow lookahead** rather than board-reading or rule ignorance.
- **Board Representation & 1-Ply Blind Spots (Especially in Xiangqi):** More input is not always better—in Xiangqi, giving **only the piece list (`pieces`)** yielded the lowest blunder rate (21% vs. 34% for `FEN + ASCII board + piece list`, where the ASCII grid caused models to confuse Black's `車` with Red's). Models in Xiangqi repeatedly exhibited 1-ply self-hangs (such as walking a Rook into a screened Cannon capture, `炮隔炮打车`) and left hanging major pieces uncaptured for multiple consecutive plies.
- **Reasoning Depth Dominates, While Thought Carryover Cuts Both Ways:** Scaling `effort` (`medium → high → xhigh → max`) is the single most effective lever for reducing blunders (e.g., in the `max` vs. `max` peak match against Astra, Opus won 3:1 in Chess and 4:0 in Xiangqi). Continuous sessions (`session`) genuinely reuse prior thinking and cut per-move thinking tokens, but retaining prior thinking can also lock in early blind spots (dropping prior thinking via `drop_thinking` reduced missed captures for Opus at 2–3× the per-move token and time cost).

The [Round 1 Summary](docs/results/summary-round1.md) summarizes only the initial phase of experiments; subsequent head-to-head matches, rating calibrations, and Gemini evaluations are cataloged in the [Research Index](docs/research.en.md). Each report preserves the conditions and conclusions of its time.

## Match Principles

Full games default to the **"Model as Real Player" (`real`) protocol**: each side plays inside one continuous session, chooses moves from the board state, and writes a visible rationale before its move. The harness validates legality and logs the game without offering engine hints, check warnings, threat lists, or legal-move enumerations; engines act strictly as opponents or post-game arbiters. Three consecutive illegal attempts on the same turn forfeit the game—a custom tournament rule defined by this project.

If a model invokes or attempts a tool call, the match pauses immediately; if a safety/anti-CoT-extraction refusal occurs, the match halts and preserves raw evidence without rephrasing or auto-resuming. Because upstream CLIs do not expose every internal tool event, "no observed tool event" is not a formal proof of zero tool attempts. See [System Design](docs/design.md) for protocol history and boundaries.

## Runtime & Data Boundaries

- **Official Games & Judged Quizzes Included:** `runs/` now ships with all 65 official model match directories—43 model-vs-model single-game directories + 22 model-vs-engine directories (15 single-game directories + 7 multi-game batch directories, 171 games in total)—including `game.pgn` (includes the visible reasoning, elapsed time, and token metadata recorded for model moves), `analysis.jsonl` / `analysis-summary.json` (per-move engine evaluations and blunder flags for 170 games), `summary.json` / `summary.md`, and 9 official position-quiz batches (`quiz-*`, 50 `judged.jsonl` files) with `judged.jsonl` and `report.txt`. Only bulky low-level event logs (`game.jsonl`), duplicate `record.txt` files, raw engine-vs-engine calibration games (whose outcomes are in `analysis/rating/games-engines.csv`), and `.mp4` video recordings are excluded.
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
