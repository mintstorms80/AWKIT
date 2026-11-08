# GUIDE - {{PROJECT_NAME}} (owner guide, English)

You are the AUTHOR: {{OWNER}}. This file is yours. It says what to type, what you should see, and what to do when you see
something else. The rules the models obey live in `.hermes/plans/PLAYBOOK.md`; this guide never contradicts them, it only
tells you how to drive them. One habit covers most of it: **one command, one line, act on that line.** A sentence from a
model is a claim; a command's output is a fact. Written {{DATE}}.

## 0. The picture in one minute

```
+-------------------------+   decisions -> files   +--------------------------+   cards, one at a time   +--------------------------+
| AUTHOR - you            | ---------------------> | ARCHITECT - strong model | -----------------------> | WORKER - cheap model     |
| domain, money, keys,    |                        | plans, writes cards,     |                          | executes ONE card, byte  |
| commits, deleting data  | <--------------------- | audits, moves the floor  | <----------------------- | for byte, decides nothing|
+-------------------------+  questions + options   +--------------------------+     ONE result line      +--------------------------+
```

| Piece | Who | What it may write |
|---|---|---|
| `.hermes/plans/PLAYBOOK.md` | read by everyone | the laws, roles, failure ladder |
| `.hermes/plans/PLAN_latest.md`, `MODULES.md`, `ROADMAP.md`, `cards/` | architect | the plan and the cards |
| `.hermes/plans/WORKLOG.md` | worker, append-only | one row per card |
| `.hermes/plans/AUDIT_LEDGER.md` | architect, append at the end only | every finding, every acceptance |
| `.hermes/plans/QUESTIONS.md` | worker asks, you or the architect answers | the one question channel |
| `.aw/ratchet.json`, `.aw/baseline.json`, `.aw/frozen.txt`, `.aw/checks.d/` | architect only | the floor, the hashes, the independent checks |

**Done means:** `GATE OK count=N` + `AUDIT PASS` + a WORKLOG row. Never the worker's word. **The kit never deletes your
data, never commits, never prints a secret's text, and never lowers a floor.**

## 1. One-time setup

Every step is: what to type -> what you should see -> what to do instead. Steps 1.1-1.2 run in the kit folder; from 1.3 the
project root is home, and `python3` means the `PY` you wrote in `tools/kit.env`. The architect does 1.4-1.6 in BLOCK 0 (its
steps 3-5); they are here so you know what you should see.

### 1.1 Prove the kit itself
```
python3 selftest.py
```
See two lines (the check count grows with the kit; only `failures=0` matters):
```
   lint findings on <folder>: 0
SELFTEST PASS  failures=0  checks=<n>  skipped=<n>  seconds=<s>
```
`<folder>` is the kit folder's name. If checks were skipped, a line `SKIPPED (UNMEASURED, not failures): ...` follows - skipped
means "not measured", not "fine".
Instead: `SELFTEST FAIL failures=<n>` -> do not install; send the `FAIL ...` lines to the architect. Only python 3.9+ is needed.

### 1.2 Install into the project
```
python3 init_project.py "C:/path/to/project" --name "{{PROJECT_NAME}}" --lang en --owner "{{OWNER}}"
```
See: `INSTALLED into <path>: <n> new file(s), 0 collision(s) staged in kit_stage/ (lang=en)` - `0 collision(s)` is the part that matters.
Instead: `COLLISION (merge by hand, backup first): <path>` -> nothing was overwritten; the new copy sits in `kit_stage/`.
`refusing to install into the kit's own tree` -> you passed the kit folder, pass the project folder.
Re-run it any time: it is safe, it stages and never overwrites. `python3 init_project.py --check "C:/path/to/project"`
prints `SAME|DIFF|MISSING|STATE` per file and ends with `KIT-CHECK engine_same=<n> engine_diff=0 missing=0`.

### 1.3 Health check
```
cd "C:/path/to/project"
python3 -I -B tools/aw.py doctor
```
See: `DOCTOR PASS warn=<n> fail=0`. WARNs on a fresh install are not failures: `baseline` and `ratchet` go away with 1.5-1.6;
`gitignore` when you create a `.gitignore` with `.env`, `backups/`, `kit_stage/` (the installer never touches yours); `wsl-bash`
(Windows with WSL only) means a `bash` outside git-bash is WSL: replace `bash tools/gate.sh X` with
`python3 -I -B tools/aw.py gate X` and `bash tools/re_audit.sh X` with `python3 -I -B tools/aw.py audit X` (the scripts only call these).
Instead: any `DOCTOR FAIL <topic>: ...` -> fix exactly that topic before anything else (python, `PY`, `TEST_CMD`, kit
files). `DOCTOR FAIL TEST_CMD: <prog> not found -> TEST_CMD will fail with exit=127` -> the project's test runner is not the one
in `kit.env`.

### 1.4 Configure the gate (architect edits, you approve)
In `tools/kit.env`: `PY` = the project's python (on Windows the venv python by full path), `TEST_DIR`, `TEST_CMD` = ONE
command that runs the whole suite, `COUNT_REGEX` = exactly one group holding the number of passing tests. Then:
```
bash tools/gate.sh baseline
```
See: `GATE OK count=<N> min=0`, and `.hermes/plans/gate_output/baseline.txt` holding the raw tail of that run.
Instead: `GATE FAIL count=0 min=0 reason=exit=1,no-count-parsed` -> the suite did not run, or `COUNT_REGEX` does not match
this runner's output. Open the gate file: its tail names the real error. That is a setup bug, not a worker bug. A red gate
is the truth; a PASS from a model is only a claim.

### 1.5 Raise the floor, once (architect only)
```
python3 -I -B tools/aw.py ratchet --raise <N> --i-am-architect
```
See: `RATCHET min_tests=<N>` with the same N the gate printed.
Instead: `REFUSED: floor only rises (2 -> 1)` -> a lower number was typed. The floor only goes up, on purpose.

### 1.6 Freeze what must not change, add one independent check, record the baseline
- `.aw/frozen.txt`: one glob per line - source of truth, schemas, tests other work must not silently rewrite.
- `.aw/checks.d/`: one executable per check. Copy `example_todo_count.py.disabled` to `.py` to start. It must NOT import
  the code it audits; it prints `METRIC <name> <int>` (lower is better) or `ZERO <name> <int>`.
```
python3 -I -B tools/aw.py integrity --write-baseline --i-am-architect
python3 -I -B tools/aw.py integrity
```
See: `BASELINE WRITTEN files=<n> metrics=<m> core=<n> floor=<N> (record it in AUDIT_LEDGER)`, then
`INTEGRITY OK frozen=<n> metrics=<m> core=<n>`.
Instead: `INTEGRITY FAIL 1: FROZEN-CHANGED <path>` -> a frozen file differs from the baseline. On purpose: the architect
re-baselines (`integrity --write-baseline --i-am-architect --allow <path>`) and writes a ledger row. Accident: restore it
from git. `RATCHET-LOWERED` -> someone edited `.aw/ratchet.json` by hand: treat it as an incident.

### 1.7 Put the prompts where the models live (once per project)
- Strong model = architect: paste `.hermes/prompts/ARCHITECT.md` as its system prompt or soul.
- Cheap model = worker: paste `.hermes/prompts/WORKER.md` into the worker profile's soul.
The kit's `profiles/` folder holds thin global souls, installed by hand, never into the project tree. If you change a rule,
change the prompt file; a rule that lives only in chat does not exist.

### 1.8 The dry run (the most valuable ten minutes)
Paste **BLOCK 1** from `.hermes/plans/START_BLOCKS.md` into the worker. Both cards are inside the block: `T-DRY1` writes a new
file `DRY_RUN.txt`; `T-DRY2` is deliberately impossible - its PRE-FLIGHT expects `GATE OK count=0 min=0`.
See: `PASS T-DRY1 gate=OK count=<N> evidence=gate_output/T-DRY1.txt`; for the impossible one a `FAIL ...` block of at most 20
lines, `ASKED Q-001`, and `STOPPED` - and nothing edited. `DRY_RUN.txt` stays (nobody deletes): the architect moves it to `_to_delete/`.
Instead: a worker that "works around" the impossible card, edits the card, or reports a number no command printed must
not receive a queue. That is the whole point of the drill: you are buying the STOP, not the PASS.

### 1.9 Commit before any real work (yours alone)
`.gitignore` first (see 1.3), then:
```
git add -A
git commit -m "kit installed"
git rev-parse --short HEAD
```
See: a short hash. VCS is the only witness that survives a rewritten engine; the kit's hashes live inside the tree they
protect.

## 2. Day to day

| # | You do | Where | What comes back |
|---|---|---|---|
| 1 | paste **BLOCK A** (architect audit session) | strong model | 3 bullets: MEASURED / UNMEASURED, paths written, ONE question |
| 2 | answer the question | terminal | `ANSWERED Q-NNN` |
| 3 | paste **BLOCK Q** (the queue) | worker | exactly ONE line, or `QUEUE DONE ...` |
| 4 | paste the worker's line into the architect | strong model | verified numbers, an `ARCH-ACCEPT` ledger row, the next block |
| 5 | the architect raises the floor, once per queue | strong model | `RATCHET min_tests=<final>` from the queue's `Chain:` line |

All blocks live in `.hermes/plans/START_BLOCKS.md` - you paste them, you do not write them: **BLOCK 0** - the architect's first
session in a new or existing project (survey, questions, 1.4-1.6, first queue); **BLOCK 1** - the worker's dry run (1.8);
**BLOCK Q** - the queue; **BLOCK R** - the worker resumes after a STOP or crash; **BLOCK A** - every architect session;
**BLOCK X** - when you tell the architect "fix it". For several specialists at once say "load the specialists" (+ a count): the
rules are in `.hermes/prompts/SWARM.md`.

**BLOCK A** opens with: `ROLE: ARCHITECT. Read REPORT_latest.md, WORKLOG (tail), AUDIT_LEDGER (§1-3 + tail), QUESTIONS
(open), PLAYBOOK.md.` Its step 1 re-measures (`gate`, `integrity`, `ratchet`, `git status`, `card-lint` per queued card)
so the architect's numbers are its own, not the worker's.

**BLOCK Q** runs the cards in file order with no pause between them. The worker returns, per card:
```
PASS T-003 gate=OK count=<N> evidence=gate_output/T-003.txt
```
and at the end of the run, as its last line:
```
QUEUE DONE <n PASS> / <n FAIL> / <n STOP>
```
A **FAIL** block is at most 20 lines: the failing command, its exit code, the last raw output lines, one question, then
`ASKED Q-NNN`. A **STOP** is one line: `STOP: <key> missing in <path>. Need: <value>.` Those two are the system working,
not failing.

**Who raises the ratchet:** only the architect, only once, only after the WHOLE queue PASSes, to the `final=` value of the
queue's `Chain:` line. The worker never runs `--raise`. Raising between two cards of one queue makes an unattended queue
stop on correct code, so it is a bug, not a habit.

Answering a worker question is the only command you type yourself:
```
python3 -I -B tools/aw.py answer Q-001 "the answer, one sentence"
```
See `ANSWERED Q-001`. If the question is about domain content, money, keys or deleting data, the answer is yours, not the
architect's; ask for options with their cost before you answer.

## 3. What to do when

Symptom cells quote the literal line the tool prints; the numbers inside them are examples.

| Situation | Symptom you see | What to do |
|---|---|---|
| Worker failed a card | `FAIL T-003 at=step#4 exit=1`, <= 20 lines, `ASKED Q-004` | Give the block to the architect. It classifies: card bug, environment, real defect, or your decision. Never say "try again". |
| Worker asked a question | `ASKED Q-005`, REPORT shows `open questions: 1` | Answer it (`answer Q-005 "..."`), or let the architect answer a technical one. Domain/money/legal = yours. |
| Gate fell below the floor | `GATE FAIL count=607 min=612 reason=count<612` | Tests disappeared. Do not lower the floor: the architect finds the diff and the test comes back. |
| A file outside OWNS changed | `OWNS 2 outside OWNS`, `OUT <path>` | The card was overstepped. Restore (`restore T-003`), then the architect re-cuts the card or widens OWNS with a reason in the ledger. |
| A frozen file changed | `FROZEN-CHANGED <path>` | If the card legitimately needed it: the architect re-baselines with `--allow <path>` and a ledger row. Otherwise restore it. |
| The ledger was rewritten | `LEDGER-REWRITTEN (prefix differs from last seen: append-only violated)` | Stop the queue. Restore the ledger from git, and from then on only append at the END. |
| WORKLOG is stale | `WARN WORKLOG older than newest gate_output (missing entry?)` | Something ran without a row: the architect asks the worker for a row with the real time now, marked `deviations: RECOVERED`. |
| A secret was detected | `SECRETS FAIL 1` and `file:line rule=openai-style-key` | Stop. Rotate the key, remove the line, add the file to `.gitignore`. The text is never printed - do not paste it in chat either. |
| The count cannot be read | `GATE FAIL count=0 min=0 reason=no-count-parsed` | `COUNT_REGEX` does not match this runner's output. The architect fixes `kit.env`, re-runs the gate, then re-baselines. |
| Doctor reports a failure | `DOCTOR FAIL <topic>: <detail>` | Fix that exact topic. `warn=` lines are not blockers (1.3). |


## 4. Command cheat-sheet

Run from the project root. `python3` = the `PY` in `tools/kit.env`. With the `wsl-bash` WARN (1.3) use `aw.py gate X` instead
of `bash tools/gate.sh X` and `aw.py audit X` instead of `bash tools/re_audit.sh X`.

| Command | Who runs it | What it proves |
|---|---|---|
| `bash tools/gate.sh baseline` | architect | the suite runs; prints `GATE OK count=N min=M` |
| `bash tools/gate.sh T-003` | worker, architect | the suite after a card; evidence in `gate_output/T-003.txt` |
| `OWNS='a/*,b.py' bash tools/re_audit.sh T-003` | worker, LAST step; architect | gate + integrity + secrets + OWNS + state + a ledger block; last line `AUDIT PASS` |
| `python3 -I -B tools/aw.py doctor` | anyone | the environment can run the kit at all |
| `python3 -I -B tools/aw.py report` | anyone | writes `REPORT_latest.md`; writes nothing else |
| `python3 -I -B tools/aw.py integrity` | anyone | frozen files unchanged, metrics at or under their ceiling |
| `python3 -I -B tools/aw.py ratchet` | anyone | the current floor |
| `python3 -I -B tools/aw.py ratchet --raise 613 --i-am-architect` | architect only | the floor becomes 613; it can never go down |
| `python3 -I -B tools/aw.py start T-003` | worker | records the pre-card fingerprint the audit compares against |
| `python3 -I -B tools/aw.py backup T-003 src/a.py` | worker | a copy in `backups/T-003/`; refuses to overwrite |
| `python3 -I -B tools/aw.py restore T-003` | worker, architect | puts the backups back; lists files the card created, never deletes |
| `python3 -I -B tools/aw.py patch src/a.py old.txt new.txt` | worker | one exact replacement, or nothing (`PATCH REFUSED: OLD occurs 2 times`) |
| `python3 -I -B tools/aw.py ask "one question"` | worker | appends `Q-NNN`, prints `ASKED Q-001` |
| `python3 -I -B tools/aw.py answer Q-001 "text"` | you, architect | prints `ANSWERED Q-001` |
| `python3 -I -B tools/aw.py next-id T` | worker, architect | the next free id: counts register rows, `# T-NNN` card titles and `backups/T-NNN`; prose is ignored |
| `python3 -I -B tools/aw.py card-lint T-003` | architect, before dispatch | `CARD-LINT OK errors=0 warn=0` or the exact broken line |
| `python3 -I -B tools/aw.py queue-check .hermes/plans/cards/QUEUE_2026-10-30.md` | architect | chain arithmetic, card files, OWNS overlap |
| `python3 -I -B tools/aw.py modules` | architect | the module registry has no cycle and one owner per file |
| `OWNS='a/*,b.py' python3 -I -B tools/aw.py audit T-003` | worker, architect | the same as `re_audit.sh` (it only calls this), minus bash; without `OWNS` every changed file shows as outside OWNS |
| `python3 -I -B tools/worker_report.py` | worker, architect | same as `report`, without `aw.py` in the command |

Exit codes everywhere: `0` ok, `1` a check failed, `2` usage or config error. Every error line names its fix.

## 5. How to read `REPORT_latest.md`

Written by `report` (60 lines maximum). Read it top to bottom; each line is one question:

| Line | Question it answers | Red flag |
|---|---|---|
| `kit=<version> next-card-id=<ID> ratchet min_tests=<N>` | which kit, what the next id is, where the floor stands | a floor lower than yesterday |
| `last gate file: <label>.txt @ <date> <time>` | when the suite last ran | older than the last WORKLOG row (a row without proof) or newer than it (a card without a row) |
| `queue: <file> <done>/<total> in WORKLOG, not done: <ids>` | what is left in the running queue | a card "done" by chat but not in WORKLOG |
| `## last re-audits` / `### RE-AUDIT <time> after <ID>` | which cards were audited (last 5); the verdict `verdict=PASS` or `verdict=FAIL` is in the block in `AUDIT_LEDGER.md` | a card in WORKLOG with no `RE-AUDIT` heading |
| `## last WORKLOG entries` | the last three cards, claimed result | a PASS with no `gate_output/` file |
| `open questions: <n>` | unanswered worker questions | a number that only grows |
| `## file fingerprints` / `AUDIT_LEDGER.md: <bytes> <hash>` | size + first 12 chars of the sha256 for ledger, plan, questions, worklog | the ledger hash changed and the architect did not write it |
| `doctor: PASS warn=<n> fail=<n>` | the environment | any `fail=1` |

## 6. Is it set up correctly?

| # | Check | Pass looks like |
|---|---|---|
| 1 | `python3 selftest.py` in the kit folder | `SELFTEST PASS failures=0` and `lint findings on <folder>: 0` |
| 2 | `bash tools/gate.sh baseline` | `GATE OK count=<N> min=<N>` |
| 3 | `python3 -I -B tools/aw.py ratchet` | `RATCHET min_tests=<N>`, the same N |
| 4 | `python3 -I -B tools/aw.py integrity` | `INTEGRITY OK frozen=<n> metrics=<m>`, `frozen` > 0 |
| 5 | `.aw/checks.d/` | at least one `.py` or `.sh` file (`*.disabled` never runs) |
| 6 | `python3 -I -B tools/aw.py doctor` | `fail=0`, and no `wsl-bash` WARN left unnoticed |
| 7 | the two prompts | architect prompt in the strong model, worker prompt in the worker profile |
| 8 | the dry run (1.8) | the worker STOPped on the impossible card and asked, and changed nothing |
| 9 | `git status --short` before the first card | clean, or every dirty file named |
| 10 | `REPORT_latest.md` | `open questions: 0`, `fail=0` |

## 7. Unknowns and UNMEASURED

- The kit **detects drift, it is not a sandbox.** Whatever a process with file access can rewrite, it can rewrite; the kit
  makes it loud (hash, tripwire, ledger), never impossible. `--i-am-architect` guards against accidents, not intent.
- **OWNS is a snapshot comparison** (size + mtime, taken by `start`). A worker that restores both exactly is invisible.
  That is why the ledger and `git diff` stay part of the review, and why you commit before a queue.
- A PASS is a claim until the architect re-runs the gate. The secret scan is pattern-based and can miss a key that matches
  no pattern; it prints `file:line` and the rule name, never the text.
- `UNMEASURED` in any report is "not checked", not "fine". Same for a card whose DRY-RUN PROOF is missing.
- **`next-id` counts register rows only.** A fresh install prints `T-001`; ids quoted in prose or in
  `CARD_PATTERNS.md`/`PLAYBOOK.md` are not counted (measured). Take the printed id; never hand-number.
- **`card-lint` is a subset of the rules** (`docs/CARD_LINT_RULES.md` in the kit folder). Measured on 2.0.1: of 39 deliberately broken reference
  cards it catches 23. `CARD-LINT OK` means the checked structure holds, not that the card is right; the real checks are the DRY-RUN PROOF and `audit`.
- **`restore` never deletes.** Files the card created are listed as `NOT-RESTORED-NEW`; moving them to `_to_delete/` is a
  human decision, not an automatic one.
- **`doctor` cannot see your intent.** A green doctor proves the environment runs the kit, not that the plan is good.
- Timing, cost per card and how long a phase really takes are **UNMEASURED** until the first accepted queue; treat any
  date in `ROADMAP.md` before that as a range, and say so out loud.
