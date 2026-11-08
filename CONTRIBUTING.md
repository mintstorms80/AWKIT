# Contributing

## Before any change

Requirements: Python 3.11+ (the suite is measured on 3.11 and 3.14; CI runs 3.11 and 3.13).

1. `python3 -I -B selftest.py` must print `SELFTEST PASS failures=0 checks=N`. Read `N` from the run, never from a doc:
   the count grows with every rule.
2. `python3 -I -B selftest.py --lint-only` — the doc-rot guard: every command and path a document names must exist.
3. `python3 dev/guide_claims.py` — executes the claims of the owner guides against a fresh install.

## Rules that bite

- **A new `aw.py` command is four edits**, plus a row in `docs/CARD_LINT_RULES.md` when it is a lint rule: the command
  function and its route, the `--help` docstring, the allow-list in `selftest.py`, and the command table in `README.md`.
  `payload/tools/aw.py` sits at its 1,250-line budget: compress, never raise it.
- **A new engine helper** (`payload/tools/<tool>.py`) also needs its name in `ENGINE_GLOBS` in `init_project.py`, or it
  silently never installs.
- **Prompts have hard character budgets** (`BUDGETS` in `selftest.py`): `ARCHITECT.md` 9,000, `WORKER.md` 6,500,
  `PLAYBOOK.md` 11,000, `CARD_PATTERNS.md` 13,500. A prompt is paid on every turn: adding a sentence means cutting one.
- **Keep line endings**: the payload is LF, the Windows batch wrappers are CRLF (`.gitattributes`).
- **A claim in a document is a measurement**: put the command and its output next to it, or write `UNMEASURED`.

## Pull requests

One change per pull request, the selftest green, and the commit message says which tool measured the change. No generated
files, no `__pycache__`, no real project data (cards, ledgers and logs from your own project) — those are yours.
