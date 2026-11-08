# awkit — universal Architect<->Worker kit (v2)

What it is: a file-based protocol + a small stdlib engine (`tools/aw.py`) so a strong model (Architect) and a cheap model
(Worker) cooperate without drift: exact task cards, a ratcheted gate, independent checks, an append-only ledger, one
question channel — and an engine that tells you when its own environment is lying to you.

Requirements: Python 3.11+ (measured on 3.11 and 3.14), git, and on Windows git-bash for `tools/gate.sh`.

New to this? Read `docs/START_HERE.md` (one page, English), then `docs/GUIDE.en.md` (a Bulgarian translation ships as `docs/GUIDE.bg.md`).

## One-click start (Windows, no commands)
1. Put the `awkit` folder INSIDE your project folder (the folder's name becomes the project name).
2. Double-click `awkit\new_project.cmd` (`setup_project.py`): installs the kit, unittest test runner + seed test, `.gitignore`, `git init` (no commit), gate/ratchet/integrity baselines, doctor. Owner = `git config user.name`, else the Windows user. Safe to re-run (nothing is overwritten). `--en` = English guide.
3. Write your idea in `IDEA.md`, double-click `START_ARCHITECT.cmd` (copied to the project root): starts `hermes -p architect` on the project with a generated first-task prompt (written by setup_project.py) (doctor/report, read IDEA.md; STAGE 1: elaborate the idea into ONE questionnaire and stop; after the Author's answers STAGE 2: plan in KIT MODE, cards with dry-run). Model defaults to claude-sonnet-5-5 / anthropic (override: `AW_ARCH_MODEL`, `AW_ARCH_PROVIDER`). The effort level comes from `tools/effort.py` (ultra for plan + cards, a failed card, a SPEC card; else medium; override: `AW_ARCH_EFFORT`).
4. Double-click `START_WORKER.cmd`: it runs the newest open queue with `hermes -p worker` at the effort `EFFORT_WORKER` in `tools/kit.env` gives (ultra; override: `AW_WORKER_EFFORT`, `AW_WORKER_PROFILE`). Or paste the queue START BLOCK into the worker profile (then the profile's own level applies).

## Quick start (manual)
```
python3 init_project.py /path/to/project --name MyProject --lang en --owner "<Owner>"   # never overwrites; collisions -> kit_stage/
python3 selftest.py            # proves the kit end to end (green + red paths), plus kit-lint on the payload
python3 selftest.py --lint-only
cd /path/to/project
python3 -I -B tools/aw.py doctor          # read-only health: python, PY, TEST_CMD, PYTHONPATH, git-bash/WSL, line endings, git identity
# 1 edit tools/kit.env (PY, TEST_CMD, COUNT_REGEX)
# 2 bash tools/gate.sh baseline
# 3 python3 -I -B tools/aw.py ratchet --raise <measured N> --i-am-architect
# 4 fill .aw/frozen.txt, add .aw/checks.d/<independent check>.py, then
#   python3 -I -B tools/aw.py integrity --write-baseline --i-am-architect
# 5 paste .hermes/prompts/ARCHITECT.md into the strong model, WORKER.md into the worker's soul/system prompt
# 6 architect writes PLAN_latest.md, MODULES.md, cards + a queue (TASK_CARD.template.md, cards/QUEUE.template.md)
#   and validates them: python3 -I -B tools/aw.py card-lint T-001 ; python3 -I -B tools/aw.py queue-check .hermes/plans/cards/QUEUE_<date>.md
```
Read `.hermes/plans/PLAYBOOK.md` first (roles, decision rights, file ownership, lifecycle, failure ladder, anti-patterns).

## Commands (`tools/aw.py`, exit codes 0 ok / 1 check failed / 2 usage)
| Command | What it does |
|---|---|
| `gate [label]` | run TEST_CMD, enforce count >= floor, no failure pattern; raw tail -> `gate_output/<label>.txt` |
| `audit [T-NNN]` | gate + integrity + secrets + OWNS + state tripwire + WORKLOG freshness + append-only ledger block |
| `integrity [--write-baseline --i-am-architect] [--allow g1,g2]` | frozen manifest + `.aw/checks.d` metrics |
| `ratchet [--raise N --i-am-architect]` | the test-count floor: only rises; a lower floor is reported as `RATCHET-LOWERED` |
| `doctor` | read-only environment and kit health (`DOCTOR OK|WARN|FAIL <topic>: <detail>`) |
| `start T-NNN` | begin a card: state fingerprint + file snapshot (OWNS/tripwire baseline) |
| `restore T-NNN [--dry-run] [--force]` | put `backups/T-NNN/**` back after a FAIL; never deletes, lists files the card CREATED |
| `backup T-NNN path [path..]` | copy files to `.hermes/plans/backups/T-NNN/` (refuses to overwrite) |
| `patch FILE OLD.txt NEW.txt` | assert-once replace; keeps the file's line endings, refuses mixed endings |
| `report` | `.hermes/plans/REPORT_latest.md` (<= 60 lines) |
| `ask "text"` | append `Q-NNN` to `QUESTIONS.md` (the worker channel; cannot forge `ANSWER` lines) |
| `answer Q-NNN "text"` | append the answer line (architect/author channel) |
| `next-id [T|CHK|SPEC|AUD|F|P|Q|D|M|W|PH]` | next free id: register rows, `# T-NNN` card titles and `backups/T-NNN` (prose and examples are ignored) |
| `card-lint CARD|ID [--strict]` | card check, a SUBSET of `docs/CARD_LINT_RULES.md` (23 of 39 reference mutants caught, see `docs/HONEST_LIMITS.md`) (`LINT ERROR|WARN <id> line <n>: ...`, last line `CARD-LINT OK|FAIL`) |
| `queue-check QUEUE.md` | Chain line grammar + card files + `ran=` arithmetic + OWNS overlap |
| `modules` | validate the `MODULES.md` registry table (ids, deps, cycles, wave order, one owner per file) |
| `improve` | read-only self-improve loop check (`.hermes/plans/SELF_IMPROVE.md`): OPEN/IGNORED F-NNN, repeated topics, proposals not VERIFIED; last line `IMPROVE OK` or `IMPROVE ACTION <n>` |

## Contents
- `payload/tools/`: `aw.py` (the engine), `gate.sh`, `re_audit.sh`, `worker_report.py`, `learn.py` (read-only self-improvement miner), `review_pack.py` (one diff file for the Reviewer), `findings_lint.py` (shape check of analyst FINDING lines), `effort.py` (read-only: which reasoning effort the stage or the queue needs; 2.8.0), `kit.env`; optional `.githooks/pre-commit` (integrity guard; the Author enables it with `git config core.hooksPath .githooks`).
- `payload/.aw/`: `KIT_VERSION`, `ratchet.json` (floor), `frozen.txt` (extra frozen globs), `secrets_allow.txt` (globs + exact `path:LINE`),
  `checks.d/` (independent checks), `baseline.json` and `baseline.log` (written by the architect).
- `payload/.hermes/prompts/`: ARCHITECT.md, WORKER.md, SWARM.md. `payload/.hermes/plans/`: the protocol, registers and templates.
- `payload/AGENTS.md`: rules binding on every agent (Rule #1 slot for the Author). `payload/.gitattributes`: LF everywhere.
- `docs/GUIDE.bg.md`, `docs/GUIDE.en.md`: the owner guide; `init_project.py --lang` installs one as `.hermes/plans/GUIDE.md`.
- `docs/START_HERE.md`: the one-page version of the guide for the owner (English).
- `new_project.cmd`, `setup_project.py`, `start_architect.cmd`, `start_worker.cmd`: the one-click install and the architect and worker launchers (see One-click start).
- `profiles/`: thin global Hermes souls, copied into a profile by hand.
- `dev/` (author-side QA, never installed): `guide_claims.py` runs every claim of the owner guides against a fresh install; `card_lint_reference/` is the reference implementation of card-lint rules L01-L46 (`lint_probe.py selftest`; L47, added in 2.7.2, exists only in the engine) and `diff_lint.py` compares it with the engine's `card-lint` (the source of the numbers in `docs/HONEST_LIMITS.md`); `worker_e2e.py` runs the `worker` profile on two cards in a scratch project and re-measures the result with the project's own tools (`run` needs a model, `selfcheck` needs none); `worker_traps.py` does the same with six cards (two controls and four traps: a RED that does not fail, a number that differs, orders hidden in data, a lockfile in OWNS) and, as `control`, runs the traps with the soul and `WORKER.md` stubbed (cards, tools, `PLAYBOOK.md`, `AGENTS.md` and skills untouched) to show what the soul adds.
- Hermes skills `/plan-project` and `/plan-synth` live in the Hermes profile, not here. They detect this kit (`.aw/KIT_VERSION`) and plan in KIT MODE: modules, roadmap, cards and queue through `tools/aw.py`; their scaffolders refuse a plan dir that holds `AUDIT_LEDGER.md`.

## Honest limits
The kit detects drift and accidents of cooperative-but-sloppy agents. It is NOT a sandbox: whatever a process with file
access can rewrite, it can rewrite; the kit makes it LOUD (hash, tripwire, ledger), not impossible. `--i-am-architect` is a
guard against accidents, not security. Python >= 3.9 + bash (on Windows: git-bash — a bare `bash` from Python is WSL, which is
exactly what `doctor` and the selftest check). OWNS detection compares a size+mtime snapshot taken by `start`; a worker that
restores both exactly is invisible (say so, keep `.aw/baseline.log` and the ledger reviewed). Secret scan is pattern-based and
prints only `file:line` + rule name.

Full list: `docs/HONEST_LIMITS.md`. Card-lint rule set: `docs/CARD_LINT_RULES.md`.
Changes: `CHANGELOG.md`. Version: `payload/.aw/KIT_VERSION`.

