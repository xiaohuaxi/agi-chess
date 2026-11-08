[English](setup.en.md) | [简体中文](setup.md)

# Setup & Running

Start by recomputing published rating numbers or browsing the 171 checked-in official games and test samples in the viewer, then set up rule libraries, chess engines, and model CLIs only as needed. The first two activities make no model calls and consume no subscription or API quota.

All commands in this guide run from the repository root. For experimental conclusions see the [Research Index](research.en.md), for third-party provenance and licensing see [Dependencies & Provenance](dependencies.en.md), and for the project overview see [README](../README.md).

## Environment Requirements by Task

| Task | What You Need | Calls Models? |
| --- | --- | --- |
| Recompute published rating numbers | Python 3 standard library; CSV & JSON files in `analysis/rating/` | No |
| Browse official games, samples, or your own PGNs | Web browser + local static HTTP server; no build step or `npm` install needed | No |
| Run Python offline unit tests | Python 3, `chess`, `pyffish`; engine-integration tests also require local chess engines | No |
| Run Viewer JS tests | Node.js; browser tests also require `playwright-core` + Chromium, and round-trip tests require Python rule libraries | No |
| Run full-game model matches | Python rule libraries, built-in `llm-chat` (`.agents/skills/llm-chat/`), and either a local model CLI (`claude` / `codex` / `agy`) or an HTTP API key (`API_KEY_OPENROUTER` / `API_KEY_DEEPSEEK`); engine opponents also require engines | Yes |
| Record PGNs to MP4 video | Node.js, `playwright-core`, Chromium, FFmpeg; video verification also uses FFprobe | No |

## Free Quick Start: Recompute Ratings

```sh
python3 analysis/rating/rate.py report
```

This script reads checked-in data and prints results to the terminal without network access or chess engines. By default it performs 1,000 bootstrap resamples, which takes a few minutes. To quickly verify that the script runs, use fewer resamples:

```sh
python3 analysis/rating/rate.py report --boot 10
```

A small bootstrap count is only for smoke-checking execution, not for citing confidence intervals; keep the default 1,000 resamples for formal verification. For the experimental conditions and limitations behind these numbers, see the [Opus Max Rating Report](results/opus-max-rating.md). These numbers refit existing game outcomes rather than re-evaluating the models live. `rate.py export` requires raw engine-vs-engine calibration directories and low-level `game.jsonl` files that are not checked in; a fresh clone does not need to run `export` because the exported match tables are already committed in `analysis/rating/games-*.csv`.

## Free Quick Start: Browse Official Games & Samples

```sh
python3 -m http.server --bind 127.0.0.1 8000
```

Keep this terminal running and open in your browser:

- Chess Peak Match (Opus Max vs Astra Max, Game 1): <http://127.0.0.1:8000/viewer/?files=/runs/g7-c-opus-astra-1/game.pgn&lang=en>
- Xiangqi Peak Match (Opus Max vs Astra Max, Game 1): <http://127.0.0.1:8000/viewer/?files=/runs/g7-x-opus-astra-1/game.pgn&lang=en>
- Chess Test Sample: <http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/chess-sample.pgn&lang=en>
- Xiangqi Test Sample: <http://127.0.0.1:8000/viewer/?files=/viewer/test/fixtures/xq-sample.pgn&lang=en>

The repository's `runs/` directory includes `game.pgn` (with full per-move rationales, elapsed time, and token counts) for all 65 official model match directories (171 games in total). You can replace `files=` with any `/runs/<tag>/game.pgn` to inspect any official game. Press Space to play/pause and Left/Right arrow keys to step through moves; press Ctrl-C in the server terminal when done. The server binds only to `127.0.0.1`; if port 8000 is busy, pick another port and update the URL. The viewer uses ES modules and cannot be opened directly via `file://`. For full controls and video recording, see the [Viewer & Video Guide](viewer-guide.en.md).

The viewer defaults to Chinese; append `&lang=en` to switch the UI to English, and use `names=` to override displayed player names. See the [Viewer & Video Guide](viewer-guide.en.md) for syntax details.

## Python Package & Offline Tests

The repository provides `requirements.txt` for installing the rule libraries. To run the match harness, export PGN records, or execute the Python test suite, install the dependencies in a Python virtual environment (recomputing ratings in `analysis/rating` and browsing PGNs in `viewer/` do not require these packages):

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -c 'import chess, pyffish; print("Rule libraries imported successfully")'
python -m agi_chess --help
python data/batch2/select_positions.py check
python -m unittest discover -s tests -t .
```

`chess` is the PyPI distribution for `import chess` (`python-chess`); Xiangqi rules are provided by `pyffish`, while Chinese move notation uses our in-repo implementation (no `cchess` needed). Because `pyffish` includes a native C++ extension, installing it on a new platform may require a C++ build toolchain; on Debian/Ubuntu, if `venv`, build tools, or Stockfish are missing, install them via `sudo apt install python3-venv build-essential python3-dev stockfish`. If installation fails, check your Python version and native compiler setup.

`python3 data/batch2/select_positions.py check` relies only on the two rule libraries above to validate the checked-in Batch 2 position bank (`data/batch2/{xiangqi,chess}.jsonl` FENs, side to move, and move legality) offline, without launching engines or reading `runs/`.

Running the full test suite without skips also tests engine handshakes and move generation, which requires `stockfish` and `fairy-stockfish` on the machine. When engines are absent, engine-dependent tests are automatically skipped; for complete verification, install both engines and check that both failures and skipped counts are zero. Engines are standalone executables not installed by `pip`; their licenses are documented separately in [Dependencies & Provenance](dependencies.en.md).

Verified on the maintainer's machine (2026-11-05): `/usr/bin/python3` is Python 3.9.6 with `chess 1.11.2` and `pyffish 0.0.90` installed (the legacy `cchess` dependency has been removed in favor of in-repo notation), passing all 314 offline unit tests. Always run commands with the same Python interpreter where you installed the packages.

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
- **Historical stateless position-quiz mode** (`python3 -m agi_chess.quiz`): Invokes `claude` or `codex exec` directly; running `python3 -m agi_chess.quiz run --game chess --batch batch2 --ids c2-01 --efforts medium --reps 1 --model deepseek` uses a Codex CLI profile and reads `$CODEX_HOME/deepseek.config.toml` (or `~/.codex/deepseek.config.toml` when `CODEX_HOME` is unset) by default, overridable via `AGI_CHESS_DEEPSEEK_CONFIG` (with backward compatibility for `AGICHESS_DEEPSEEK_CONFIG` and `LLMCHESS_DEEPSEEK_CONFIG`). Minimal credential-free templates:

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

  Minimal accompanying model catalog `~/.codex/deepseek-models.json`:

  ```json
  {
    "models": [
      {
        "slug": "deepseek/deepseek-v4-pro",
        "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}, {"effort": "high"}]
      }
    ]
  }
  ```

Review the CLI `--help` output and Section 9 of [System Design (zh-CN)](design.md) before launching live games. The `--max-plies 6` command against `random` above is only a short smoke check, not a strength evaluation. Use a fresh `--tag` for each run; outputs are written to `runs/<tag>/` (local `game.jsonl` event streams are git-ignored). Never grant model players access to chess engines or rule-library tools. Any tool call attempt or anti-CoT-extraction safety refusal immediately halts the match for inspection without auto-retrying.

For engine opponents, International Chess supports `stockfish` or `lc0` with Maia weights (looked up by default at `~/.local/share/maia/maia-1100.pb.gz`, etc., not bundled in this repo). Xiangqi uses `fairy-stockfish`. Engine binaries are resolved in order via environment variables (`STOCKFISH`, `LC0`, `FAIRY_STOCKFISH`), `PATH`, and standard system directories (`/usr/games`, `/usr/local/games`, `/usr/local/bin`, `/usr/bin`, `/opt/homebrew/bin`). Engines serve strictly as opponents or post-game arbiters—never as move advisors for model players.

## Viewer Tests & Video Recording

Browsing PGNs in a web browser requires neither Node.js, Chromium automation, nor FFmpeg. Those tools are only needed for running the viewer test suite or recording MP4 videos (run `cd viewer && npm ci && cd ..`, install the locked Chromium revision from the repository root via `node viewer/node_modules/playwright-core/cli.js install --with-deps chromium` or use a system `chromium` / `google-chrome-stable` package along with `ffmpeg`, and on headless Linux servers install CJK fonts such as `sudo apt install fonts-noto-cjk fonts-arphic-ukai` on Ubuntu/Debian so Chinese Xiangqi piece glyphs do not render as tofu boxes); see the [Viewer & Video Guide](viewer-guide.en.md).

```sh
node --test 'viewer/test/*.test.js'   # Quoted globbing requires Node 22+; on Node 18/20, omit single quotes: node --test viewer/test/*.test.js
```

The JS test suite validates the PGN parser, UI logic, and all checked-in `game.pgn` files under `runs/`. It explicitly reports skipped tests: browser playback tests are skipped when `playwright-core` or a working Chromium binary is absent, and Python round-trip tests require a `python3` interpreter with `chess` and `pyffish` installed.
