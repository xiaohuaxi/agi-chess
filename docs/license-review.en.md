[English](license-review.en.md) | [简体中文](license-review.md)

# License Review for Public Release & Distribution

Initial draft: 2026-11-05; licensing plan finalized: 2026-11-08. For the factual dependency inventory, see [Dependencies & Provenance](dependencies.en.md). This document distinguishes between license text, FSF interpretations, and repository-specific engineering inferences; it does not substitute for copyright-holder authorization or formal legal advice under applicable law.

**The GPL does not prohibit publishing source code, but "we only publish source code, so slapping MIT/Apache on everything is enough" does not hold—nor is binary distribution a loophole to avoid providing source.** Authors may license their own original, independent code under permissive terms such as MIT or Apache-2.0, while third-party components retain their licenses and any combined work falling within GPL scope must also satisfy the GPL.

## Why Integration Architecture Matters

- **License text:** [GPLv3 §§4–6](https://www.gnu.org/licenses/gpl-3.0.html#section4) specify distinct obligations for conveying verbatim source, modified source, and non-source forms; §5 clarifies that a mere *aggregate* of separate works does not extend GPL terms to the other works in the aggregate. Consequently, source distribution itself can carry obligations, and whether a `.so` binary or executable is included in the repository is not the sole deciding factor.
- **FSF interpretation:** [Library linking and language bindings](https://www.gnu.org/licenses/gpl-faq.html#IfLibraryIsGPL) are generally treated by the FSF as forming a combined program, whereas [separate processes](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation) depend on the communication mechanism and semantics rather than process boundaries alone. This represents the license steward's interpretation rather than a universal judicial rule that every `import` in every jurisdiction automatically creates a derivative work.
- **Repository inference:** `chess` (`python-chess`) and `pyffish` are imported directly in-process by our rule modules—and `pyffish` is an in-process C++ extension—so running or distributing the combined match harness with them should be treated as a GPL-3.0-or-later combination. By contrast, `Stockfish`, `Fairy-Stockfish`, and `lc0` run as separate processes communicating over the standard, swappable text-based UCI protocol, which strongly supports treating them as separate works. Shipping engines alongside the harness in an archive or container image may qualify as an aggregate, though the engines' own GPL obligations still apply to the engine binaries. (Note: the legacy `cchess` package, which had conflicting LGPL PyPI metadata vs. GPL source files, has been completely removed and replaced by in-repo Chinese notation code.)

## Distribution Scenarios & Obligations

| Scenario | Impact on This Project |
|---|---|
| Private execution & internal research | Standard GPL permits private use and modification; however, "academic/non-commercial research" is not a blanket exemption when distributing externally. |
| Publishing only first-party source code while users install third-party libraries via `pip` | Permitted. Independent first-party components may carry MIT licensing, while we explicitly document that combining them with GPL-3.0-or-later libraries (`chess`, `pyffish`) at runtime or in redistributed bundles is governed by GPL-3.0-or-later. We do not misrepresent the combined runtime program as MIT-only. |
| Bundling libraries, engine binaries, wheels, or container images | You must fulfill license notices, copyright attributions, and Corresponding Source obligations for all included GPL components; for combined works, copyleft scope extends to the combination. Separate works in an aggregate each follow their own license. |
| Running on a server where users only receive game outputs | Under standard GPLv3 §0, network interaction without conveying copies is not "conveying" and normally does not trigger source-disclosure obligations for server code. (Sending frontend JS to a browser or handing container images to a third party *is* conveying.) |
| Providing a network service using an AGPL-modified component | [AGPLv3 §13](https://www.gnu.org/licenses/agpl-3.0.html#section13) requires offering Corresponding Source to remote network users. No core dependency in this repository uses AGPL. |

Under [GPLv3 §§1 and 6](https://www.gnu.org/licenses/gpl-3.0.html#section1), *Corresponding Source* means all source code and build/installation scripts needed to generate, install, run, and modify the work (subject to System Library exceptions)—not merely a link to an upstream homepage or a moving `main` branch.

Dynamic linking under standard GPL does not grant a general exception; only [LGPLv3 §4](https://www.gnu.org/licenses/lgpl-3.0.html#section4) provides specific conditions for applications to retain separate terms when linking to an LGPL library.

## Finalized Licensing Plan (2026-11-08)

The maintainer has finalized and implemented the following licensing structure:

- **First-party code and materials:** The root directory provides a standard MIT [LICENSE](../LICENSE) covering all first-party Python source code, the built-in `.agents/skills/llm-chat/` driver, documentation and research reports, position banks, checked-in `runs/` game records and quiz evaluations, and the `viewer/` web application.
- **Vendored frontend libraries and media:** Components under `viewer/vendor/` retain their respective permissive licenses (BSD-2-Clause, MIT, BSD-3-Clause, CC0 1.0).
- **Python rule libraries & combination boundaries:**
  - The legacy `cchess` runtime dependency (which had conflicting LGPL metadata vs. GPL source files) has been completely removed and replaced with in-repo move notation code;
  - The core rule libraries `chess` and `pyffish` (both GPL-3.0-or-later) are not distributed in this repository and are installed locally on demand via `requirements.txt`;
  - Running the combined program that imports `chess` and `pyffish` in-process, or redistributing a bundled package containing them, is subject to GPL-3.0-or-later terms;
  - Rating recomputation (`analysis/rating`) and the web PGN viewer (`viewer/`) are independent first-party components and are not subject to rule-library copyleft.
