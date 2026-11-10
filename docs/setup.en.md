[English](setup.en.md) | [简体中文](setup.md)

# Setup & Running

Start by recomputing published rating numbers or browsing the 171 checked-in official games and test samples in the viewer, then set up rule libraries, chess engines, and model CLIs only as needed. The first two activities make no model calls and consume no subscription or API quota.

All commands in this guide run from the repository root. For experimental conclusions see the [Research Index](research.en.md), for third-party provenance and licensing see [Dependencies & Provenance](dependencies.en.md), and for the project overview see [README](../README.md).

## Environment Requirements & Quick Command Reference

| Task | Quick Command | What You Need | Calls Models? |
| --- | --- | --- | --- |
| Browse official games, samples, or your own PGNs | `node viewer/serve.mjs` (open `http://127.0.0.1:8765/viewer/?lang=en`) | Web browser + local static HTTP server; no build step or `npm` install needed | No |
| Recompute published rating numbers | `python3 analysis/rating/rate.py report --boot 10` (~1.5s quick check; omit `--boot 10` for full 1,000 resamples in ~1.5m) | Python 3 standard library; CSV & JSON files in `analysis/rating/` | No |
| Recompute 9 position-quiz summary tables | `python3 -m agi_chess.quiz report --batch batch2` (supports `batch1`, `batch2`, `batch3`, `4p`, `4p2`, `5-ds`, `5-sol`, `6r`, `6r-sol`) | Python 3 standard library; `runs/quiz-*/judged.jsonl` | No |
| Verify position banks & run Python tests | `python3 data/batch1/select_positions.py check && python3 data/batch2/select_positions.py check && python3 -m unittest discover -s tests -t . -v` | Python 3, `chess`, `pyffish`; 21 live-engine tests also require local `stockfish` and `fairy-stockfish` (auto-skipped if absent) | No |
| Run a zero-cost first match locally | `python3 -m agi_chess play --game chess --tag demo-random --white random --black random --max-plies 20 --seed 42` | Python 3, `chess`, `pyffish` (writes `runs/demo-random/game.pgn` in 0.1s) | No |
| Run post-game engine blunder analysis | `python3 -m agi_chess.analyze runs/demo-random` (add `--table` for multi-game summary; writes `analysis.jsonl` & `analysis-summary.json`) | Python rule libraries, local engine (`stockfish` for Chess, `fairy-stockfish` for Xiangqi), and a run directory containing `game.jsonl` | No |
| Run Viewer JS tests | `node --test 'viewer/test/*.test.js'` | Node.js; 29 browser tests also require `playwright-core` + Chromium, and 3 round-trip tests require Python rule libraries (32 in total, auto-skipped if absent) | No |
| Record PGNs to MP4 video | `npm --prefix viewer ci && node viewer/record.mjs runs/g7-c-opus-astra-1 -o /tmp/g7-c-1.mp4 --gap 1.5 --openhold 0.5` | Node.js, `playwright-core`, Chromium, FFmpeg; video verification also uses FFprobe | No |
| Run full-game model matches | `python3 -m agi_chess play --game chess --tag c1 --white claude:opus --black random --effort medium --max-plies 6 --on-limit pause` | macOS / Linux (including WSL2; `llm_chat.py` relies on `fcntl` and POSIX process groups), Python rule libraries, built-in `llm-chat` (`.agents/skills/llm-chat/`), and either a local model CLI (`claude` / `codex` / `agy`) or an HTTP API key (`API_KEY_OPENROUTER` / `API_KEY_DEEPSEEK`); engine opponents also require engines | Yes |

> **Platform Boundary:** The static web viewer (`viewer/`), rating recomputation (`analysis/rating/rate.py`), and quiz report generator (`quiz report`) work cross-platform; the model match invocation layer (`.agents/skills/llm-chat/scripts/llm_chat.py`, which uses `fcntl` file locks and POSIX process groups) targets macOS and Linux (including WSL2) and does not run on native Windows.

## Free Quick Start: Recompute Ratings & Quiz Reports

```sh
python3 analysis/rating/rate.py report --boot 10   # ~1.5s quick smoke check
python3 analysis/rating/rate.py report             # Full 1,000 bootstrap resamples (~1.5 min)
```

This script reads checked-in data and prints results to the terminal without network access or chess engines. A small bootstrap count (`--boot 10`) is great for a quick run check; keep the default 1,000 resamples for citing formal confidence intervals. For the experimental conditions and limitations behind these numbers, see the [Opus Max Rating Report](results/opus-max-rating.md). `rate.py export` requires raw engine-vs-engine calibration directories and low-level `game.jsonl` files that are not checked in; a fresh clone does not need to run `export` because the exported match tables are already committed in `analysis/rating/games-*.csv`.

To recompute the summary tables (legality rate, best-move rate, and blunder rate) across any of the 9 checked-in position-quiz batches (`runs/quiz-*/judged.jsonl`, 50 files total) in 0.1s using only the Python standard library:

```sh
python3 -m agi_chess.quiz report --batch batch2    # Supports batch1, batch2, batch3, 4p, 4p2, 5-ds, 5-sol, 6r, 6r-sol
```

## Free Quick Start: Browse Official Games & Samples

```sh
node viewer/serve.mjs
# Listens on 127.0.0.1:8765 by default; without Node.js, use: python3 -m http.server 8765 --bind 127.0.0.1
```

Keep this terminal running and open in your browser (passing a run directory or `game.pgn` automatically loads the companion `analysis.jsonl` blunder annotations):

- Blank Viewer (with 4 clickable featured games): <http://127.0.0.1:8765/viewer/?lang=en>
- Chess Peak Match (Opus Max vs Astra Max, Game 1): <http://127.0.0.1:8765/viewer/?files=/runs/g7-c-opus-astra-1&lang=en>
- Xiangqi Peak Match (Opus Max vs Astra Max, Game 1): <http://127.0.0.1:8765/viewer/?files=/runs/g7-x-opus-astra-1&lang=en>
- Chess: Argon High vs Opus High (Game 1): <http://127.0.0.1:8765/viewer/?files=/runs/argon-vs-agy-opus-high-20261019&lang=en>
- Chess Rating Calibration Match (Opus Max vs Maia-1900): <http://127.0.0.1:8765/viewer/?files=/runs/zc/maia-1900-s1-w&lang=en>
- Chess Test Sample: <http://127.0.0.1:8765/viewer/?files=/viewer/test/fixtures/chess-sample.pgn&lang=en>
- Xiangqi Test Sample: <http://127.0.0.1:8765/viewer/?files=/viewer/test/fixtures/xq-sample.pgn&lang=en>

The repository's `runs/` directory includes `game.pgn` (includes the visible reasoning, elapsed time, and token metadata recorded for model moves) for all 65 official model match directories (171 games in total): **58 single-game directories** (43 model-vs-model + 15 single-game model-vs-engine `b1-ch-*`/`b1-xq-*`) can be opened directly via `/runs/<tag>` (or `/runs/<tag>/game.pgn`), and **7 multi-game batch directories** (`b1`, `b1-session`, `b2`, `b3max-ch`, `b3max-xq`, `zc`, `zx`, 113 games in total) place each game in a second-level subdirectory `/runs/<batch>/<game>` (e.g. `?files=/runs/zc/maia-1900-s1-w`). The viewer automatically requests `analysis.jsonl` in the same directory to overlay blunder badges (silently ignoring 404s). Press Space to play/pause and Left/Right arrow keys to step through moves; press Ctrl-C in the server terminal when done. The server binds only to `127.0.0.1`; if port 8765 is busy, pass `--port 8000` to `node viewer/serve.mjs` and update the URL. The viewer uses ES modules and cannot be opened directly via `file://`. For full controls and video recording, see the [Viewer & Video Guide](viewer-guide.en.md).

The viewer defaults to Chinese; append `&lang=en` to switch the UI to English, and use `names=` to override displayed player names. See the [Viewer & Video Guide](viewer-guide.en.md) for syntax details.

## Python Package, Offline Tests & Zero-Cost First Match

Python 3.13 is recommended; use `python3.13 -m venv .venv` to select it explicitly on systems with several versions. If building `pyffish` fails, check the local C++ toolchain and SDK.

The repository provides `requirements.txt` for installing the rule libraries. To run the match harness, export PGN records, or execute the Python test suite, install the dependencies in a Python virtual environment (recomputing ratings in `analysis/rating`, printing quiz reports via `quiz report`, and browsing PGNs in `viewer/` do not require these packages):

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -c 'import chess, pyffish; print("Rule libraries imported successfully")'
python -m agi_chess --help
python data/batch1/select_positions.py check
python data/batch2/select_positions.py check
python -m unittest discover -s tests -t . -v
```

`chess` is the PyPI distribution for `import chess` (`python-chess`); Xiangqi rules are provided by `pyffish`, while Chinese move notation uses our in-repo implementation (no `cchess` needed). Because `pyffish` includes a native C++ extension, installing it on a new platform may require a C++ build toolchain; on Debian/Ubuntu, if `venv` (`ensurepip is not available`), build tools, or Stockfish are missing, install them via `sudo apt install python3-venv build-essential python3-dev stockfish`.

`python3 data/batch1/select_positions.py check` and `python3 data/batch2/select_positions.py check` rely only on the two rule libraries above to validate the checked-in Batch 1 and Batch 2 position banks (`data/batch1/{xiangqi,chess}.jsonl` and `data/batch2/{xiangqi,chess}.jsonl` FENs, side to move, and move legality) offline, without launching engines or reading `runs/`.

The full Python test suite (320 tests) includes 21 live-engine handshake and move-generation tests that require `stockfish` and `fairy-stockfish`. **When local engines are not installed, `unittest -v` automatically skips those 21 engine tests while passing all 299 offline tests**; with both engines installed, all 320 tests pass (0 fail / 0 skip). Engines are standalone executables not installed by `pip`; their licenses are documented separately in [Dependencies & Provenance](dependencies.en.md).

Without any API key or local engine, you can play a complete 20-ply match between two `random` movers in 0.1s, or inspect the exact real-player prompts with `--dry-run`:

```sh
# Play 20 plies between two random movers (writes runs/demo-random/{game.jsonl,record.txt,game.pgn}, viewable at ?files=/runs/demo-random)
python -m agi_chess play --game chess --tag demo-random --white random --black random --max-plies 20 --seed 42

# Print the system prompt and first-move user prompt without calling any model or writing files
python -m agi_chess play --game xiangqi --tag demo-prompt --dry-run

# If stockfish or fairy-stockfish is installed, run post-game engine analysis on your local game (writes analysis.jsonl & analysis-summary.json)
python -m agi_chess.analyze runs/demo-random
```

> **Note:** `python3 -m agi_chess.analyze` reads the raw `game.jsonl` log in a run directory to replay moves (`--table` also requires local `game.jsonl`). All 65 official match directories checked into `runs/` already include precomputed `analysis.jsonl` and `analysis-summary.json` files (for blunder classifications, check `lichess: "Blunder"` in International Chess and `cls: "blunder"` in Xiangqi), so you can inspect them directly or verify their cached summaries via `python3 -m agi_chess.analyze runs/g7-c-opus-astra-*` without re-running the engine.

## Model Matches: Built-in `llm-chat`, Local CLI Subscriptions & HTTP API Keys

Full-game matches run through `agi_chess/chat.py`, which invokes `llm-chat`. **The repository now bundles `llm-chat` (including `scripts/llm_chat.py` and `scripts/agy_core.py`) directly under `.agents/skills/llm-chat/`, and `agi_chess/chat.py` calls this in-repo script by default.** External users do not need to wait for or install any external `llm-chat` skill (though you can still override the script path via the `AGI_CHESS_LLM_CHAT` environment variable, with backward compatibility for `AGICHESS_LLM_CHAT` and `LLMCHESS_LLM_CHAT`).

`llm-chat` drives two categories of model channels for full-game matches:

1. **Local Agent CLI Subscription Channel (primary experimental channel):**
   - **Claude:** Invoked via the local `claude` CLI (e.g., `--white claude:opus`);
   - **GPT:** Invoked via the local `codex` CLI (e.g., `--black codex:astra`);
   - **Gemini (or models routed via agy):** Invoked via the local `agy` CLI (e.g., `--white gemini:gemini-4-argon-high` or `agy:claude-opus-5-5-high`).
   - This channel directly uses the subscription quota of the locally installed and authenticated CLI (tested during development with `claude 2.1.282` and `codex 0.156.1+`; you can sanity-check your local CLI setup with `claude --version`, `codex --version`, or `agy --version`, and verify prompt generation offline with `python3 -m agi_chess play --game chess --white claude:opus --black random --dry-run`). If the required CLI executable is not installed on your machine, `llm-chat` immediately returns a clear "not installed" error message.

2. **HTTP API Channel (DeepSeek & OpenRouter):**
   - Configured via environment variables `API_KEY_OPENROUTER` (or alias `OPENROUTER_API_KEY`) and `API_KEY_DEEPSEEK` (or alias `DEEPSEEK_API_KEY`).
   - **Automatic OpenRouter Fallback for DeepSeek:** When running `deepseek:flash` (`deepseek-flash`) or `deepseek:v4-pro` (`deepseek-v4-pro`), if `API_KEY_DEEPSEEK` (or `DEEPSEEK_API_KEY`) is set, `llm-chat` connects to the official DeepSeek API directly; if only `API_KEY_OPENROUTER` (or `OPENROUTER_API_KEY`) is set without `API_KEY_DEEPSEEK`, `llm-chat` automatically routes the request through OpenRouter (`deepseek-flash` → `deepseek/deepseek-v4.1-flash`, `deepseek-v4-pro` → `deepseek/deepseek-v4-pro`), so you do not need to apply for a separate official DeepSeek API key.

Configuration and command examples:

```sh
# Option 1: Use an authenticated local CLI (claude / codex / agy) against a random mover (short smoke test)
python -m agi_chess play --game chess --tag my-first-game --white claude:opus --black random --effort medium --max-plies 6 --on-limit pause

# Option 2: Use a DeepSeek official API key or an OpenRouter API key (DeepSeek supports effort levels: low / high / max)
export API_KEY_DEEPSEEK="sk-..."        # or alias DEEPSEEK_API_KEY
# Or if you only have an OpenRouter key, deepseek:flash / deepseek:v4-pro routes via OpenRouter automatically:
export API_KEY_OPENROUTER="sk-or-..."   # or alias OPENROUTER_API_KEY
python -m agi_chess play --game chess --tag ds-smoke --white deepseek:v4-pro --black random --effort low --max-plies 6 --on-limit pause
```

Available model slugs, rate limits, and billing depend on your own accounts and subscriptions; this repository does not provide accounts, credentials, or quota. Note the configuration difference for DeepSeek between the two execution modes:
- **Full-game match mode** (`python3 -m agi_chess`): Driven by the built-in `.agents/skills/llm-chat/` over HTTP directly to DeepSeek or OpenRouter. **You only need to set `DEEPSEEK_API_KEY` (`API_KEY_DEEPSEEK`) or `OPENROUTER_API_KEY` (`API_KEY_OPENROUTER`); Codex CLI is not required.**
- **Historical stateless position-quiz mode** (`python3 -m agi_chess.quiz`): Invokes `claude` or `codex exec` directly; DeepSeek uses a Codex CLI profile and reads `$CODEX_HOME/deepseek.config.toml` (or `~/.codex/deepseek.config.toml` when `CODEX_HOME` is unset) by default, overridable via `AGI_CHESS_DEEPSEEK_CONFIG` (with backward compatibility for `AGICHESS_DEEPSEEK_CONFIG` and `LLMCHESS_DEEPSEEK_CONFIG`).

  Use a separate output directory for the example run, keeping `--batch batch2` to select the position bank:

  ```sh
  python3 -m agi_chess.quiz run --game chess --batch batch2 --out runs/quiz-deepseek-demo --ids c2-01 --efforts medium --reps 1 --model deepseek
  ```

  Choose a fresh `--out` for each new experiment and pass the same `--out` to subsequent `judge` / `report` commands. The default `runs/quiz-batch2` contains published judged results without raw answers in a fresh clone, so the program refuses to append experiments there.

  Minimal credential-free configuration template:

  ```toml
  # ~/.codex/deepseek.config.toml (needed only for quiz --model deepseek; not needed for full-game matches)
  model = "deepseek/deepseek-v4-pro"
  model_provider = "openrouter"
  model_catalog_json = "~/.codex/deepseek-models.json"

  [model_providers.openrouter]
  name = "OpenRouter"
  base_url = "https://openrouter.ai/api/v1"
  env_key = "OPENROUTER_API_KEY"
  wire_api = "chat"
  ```

  Minimal accompanying model catalog `~/.codex/deepseek-models.json` (must include the base `ModelInfo` fields required by `codex exec` deserialization):

  ```json
  {
    "models": [
      {
        "slug": "deepseek/deepseek-v4-pro",
        "shell_type": "shell_command",
        "tool_mode": null,
        "multi_agent_version": "v2",
        "experimental_supported_tools": [],
        "apply_patch_tool_type": "freeform",
        "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}, {"effort": "high"}]
      }
    ]
  }
  ```

Review the CLI `--help` output and Section 9 of [System Design (zh-CN)](design.md) before launching live games. The `--max-plies 6` command against `random` above is only a short smoke check, not a strength evaluation. Use a fresh `--tag` for each run; outputs are written to `runs/<tag>/` (local `game.jsonl` event streams are git-ignored). Never grant model players access to chess engines or rule-library tools. Any tool call attempt or anti-CoT-extraction safety refusal immediately halts the match for inspection without auto-retrying.

For engine opponents, International Chess supports `stockfish` (e.g. `--black engine:stockfish:elo=1900` or `engine:stockfish:nodes=1000`) or `lc0` with Maia weights (e.g. `--black engine:maia-1500`; weights are looked up by default at `~/.local/share/maia/maia-1100.pb.gz`, etc., not bundled in this repo). Xiangqi uses `fairy-stockfish`, specified via the player identifier `engine:fsf` (defaults to `nodes=1000`, or pass custom nodes/depth such as `--black engine:fsf:nodes=100` or `engine:fsf:depth=10`). Engine binaries are resolved in order via environment variables (`STOCKFISH`, `LC0`, `FAIRY_STOCKFISH`), `PATH`, and standard system directories (`~/.local/bin`, `/usr/games`, `/usr/local/games`, `/usr/local/bin`, `/usr/bin`, `/opt/homebrew/bin`). Engines serve strictly as opponents or post-game arbiters—never as move advisors for model players.

## Viewer Tests & Video Recording

Browsing PGNs in a web browser requires neither Node.js, Chromium automation, nor FFmpeg. Those tools are only needed for running the viewer test suite or recording MP4 videos (run `npm --prefix viewer ci` from the repository root, install the locked Chromium revision via `node viewer/node_modules/playwright-core/cli.js install --with-deps chromium` or use a system `chromium` / `google-chrome-stable` package along with `ffmpeg`, and on headless Linux servers install CJK fonts such as `sudo apt install fonts-noto-cjk fonts-arphic-ukai` on Ubuntu/Debian so Chinese Xiangqi piece glyphs do not render as tofu boxes); see the [Viewer & Video Guide](viewer-guide.en.md).

```sh
node --test 'viewer/test/*.test.js'   # Quoted globbing requires Node 22+; on Node 18/20, omit single quotes: node --test viewer/test/*.test.js
```

The JS test suite (90 tests) validates the PGN parser, UI logic, and all checked-in `game.pgn` files under `runs/`. It explicitly reports skipped tests: 58 pure-JS and PGN verification tests run with zero extra dependencies; when `playwright-core`/Chromium or the Python rule libraries are absent, the 29 browser playback tests and 3 Python round-trip tests (32 in total) are skipped accordingly; with `playwright-core`, Chromium, and the Python rule libraries installed, all 90 tests pass (0 fail / 0 skip).
