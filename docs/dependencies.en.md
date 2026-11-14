[English](dependencies.en.md) | [简体中文](dependencies.md)

# Dependencies & Third-Party Provenance

Verified: 2026-11-05; licensing finalized: 2026-11-08. For distribution implications and combined-work boundaries, see [License Review](license-review.en.md).

## Python Packages & Chess Engines

The rule libraries required to run matches and unit tests are pinned in the root `requirements.txt`. Neither Python package declares additional runtime dependencies in its PyPI metadata.

| Component / Tested Version | Role & Integration | Bundled in Repo? | License & Evidence |
|---|---|---|---|
| `chess 1.11.2` (`python-chess` module package) | International Chess rules & PGN; imported in-process by `chess_.py` and `quiz.py` | No | GPL-3.0-or-later; [PyPI metadata](https://pypi.org/pypi/chess/1.11.2/json), [upstream LICENSE](https://github.com/niklasf/python-chess/blob/v1.11.2/LICENSE.txt) |
| `pyffish 0.0.90` | Xiangqi rules; `xiangqi.py` and `quiz.py` import this C++ extension in-process (not a UCI subprocess) | No | GPL-3.0-or-later; [PyPI metadata](https://pypi.org/pypi/pyffish/0.0.90/json) says GPL3, while classifiers and `src/main.cpp` in the [0.0.90 source sdist](https://files.pythonhosted.org/packages/16/f8/60fd663b19ed4c72cbd78148645be831bd712823144c34372adb639a3adf/pyffish-0.0.90.tar.gz) explicitly state v3 or later |
| Stockfish 19 / Fairy-Stockfish 14.0.1 / lc0 0.32.1 | Engine opponents & post-game arbiters; `engine.py` communicates via `subprocess` stdin/stdout UCI; swappable executables | No | Local Homebrew Cellar builds; upstream GPLv3 family: [Stockfish](https://github.com/official-stockfish/Stockfish/blob/master/src/main.cpp), [Fairy-Stockfish](https://github.com/fairy-stockfish/Fairy-Stockfish#license), [lc0](https://github.com/LeelaChessZero/lc0/blob/master/src/main.cc). Stockfish/lc0 file headers specify "or later", and lc0 has a CUDA additional permission; any binary distribution must verify the exact build and bundled network weights |
| Maia 1100–1900 weights | Local `.pb.gz` neural network weights passed to `lc0`; not imported by Python | No | [Upstream repo](https://github.com/CSSLab/maia-chess#license) states GPL for the software and [LICENSE](https://github.com/CSSLab/maia-chess/blob/master/LICENSE) is GPLv3; weights live under `maia_weights/` upstream. Verify weight licensing and "preferred form for modification" before redistributing any weight files |

> Note: The legacy `cchess 1.25.5` dependency (whose PyPI metadata claimed LGPL-3.0-or-later while its source tarball shipped a GPLv3 `LICENSE`) has been completely removed. Xiangqi Chinese move notation is now handled entirely by our in-repo implementation (`pgn_move` in `agi_chess/xiangqi.py`).

## Web Viewer, Video Recorder & External CLIs

| Component | Bundling / Provenance | License & Scope |
|---|---|---|
| `chess.js 1.4.0` | Vendored; npm tarball hash recorded in [SOURCE](../viewer/vendor/chess.js/SOURCE.md) | BSD-2-Clause (`LICENSE` included) |
| `cm-chessboard 8.15.1` | Vendored; upstream commit and one local patch recorded in [SOURCE](../viewer/vendor/cm-chessboard/SOURCE.md) | MIT (`LICENSE` included); upstream non-permissive piece SVGs were excluded |
| Cburnett 12 piece SVGs & generated sprite | Vendored; per-file provenance, revisions, and hashes recorded in [SOURCE](../viewer/vendor/cburnett-pieces/SOURCE.md) | BSD-3-Clause selected from upstream multi-licensing (`LICENSE` included); not bound to GPL |
| `el_boss` 3 MP3 sound effects | Vendored; per-file provenance and hashes recorded in [SOURCE](../viewer/vendor/sounds/SOURCE.md) | CC0 1.0 |
| `Node.js >= 22` | External runtime, not bundled (tested with 24.20.0 on 2026-11-05) | Runs `viewer/` tests and recorder; quoted globbing in `node --test 'viewer/test/*.test.js'` requires Node 22+ (on Node 18/20, omit single quotes and run `node --test viewer/test/*.test.js`) |
| `playwright-core 1.58.2` | Not bundled; version pinned in `viewer/package-lock.json` | Apache-2.0, dev/recording dependency; the archived recording experiment directory separately declares `^1.61.1`, which is not the production viewer version |
| Chromium, FFmpeg | External recording executables, not bundled (tested with local FFmpeg 9.0.2) | Chromium includes multiple licenses; FFmpeg may be LGPL or GPL depending on build flags. Invoking local tools does not constitute distributing them; verify build flags before bundling |
| `.agents/skills/llm-chat/` | First-party in-repo scripts (`llm_chat.py`, `agy_core.py`), checked into the repository | MIT (covered by root [LICENSE](../LICENSE)) |
| `agy`, model CLIs (`claude`, `codex`) | External executables/processes, not bundled | Governed by their respective vendor terms; this repository grants no redistribution rights for external CLIs |

## Research Datasets & Game Records

- The [Batch 1 International Chess position bank](../data/batch1/chess.jsonl) was sampled from the [Lichess Open Puzzles Database](https://database.lichess.org/#puzzles), which upstream releases under CC0. Sampling took place on 2026-09-25; filtering and sampling rules are documented in the [Batch 1 selection script](../data/batch1/select_positions.py). The checked-in JSONL represents the frozen benchmark for that batch. Lichess puzzles carried over into Batch 2 retain the same CC0 provenance; see the [Batch 2 selection script](../data/batch2/select_positions.py).
- Both Xiangqi position banks and the full-game chess positions added in Batch 2 were drawn from historical games played in this study and its preliminary runs, as documented in the corresponding JSONL files and selection scripts. `runs/` now includes all 69 official model match directories (175 `game.pgn` files and 174 engine analyses `analysis.jsonl`) and 9 judged position-quiz batches (50 `judged.jsonl` files and 9 `report.txt` summaries); only bulky raw `game.jsonl` event streams, raw engine-vs-engine calibration games, and `.mp4` videos are excluded. While Lichess puzzle positions remain CC0, first-party research artifacts in this repository are licensed under the root MIT License; see the [Research Index](research.en.md) for evidence boundaries.
- [Human rating scale data](../analysis/rating/human-scale.json) compiles third-party statistics with explicit citations; academic/research citation does not grant arbitrary relicensing rights over third-party datasets.

This document is not an exhaustive binary SBOM and does not cover future container base images or transitive system packages.
