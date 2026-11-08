# PLAYBOOK — Architect <-> Worker protocol for {{PROJECT_NAME}}
Read once per session. The AUTHOR decides domain, money, secrets, commits; the ARCHITECT plans and audits; the WORKER executes.

## 1. Why this exists
A strong model designs and audits; a cheap model executes exactly and invents silently. Judgement happens ONCE (card writing, auditing),
execution is mechanical and checkable. Four invariants hold the whole system:
1. One channel: files. No chat-only decisions, no hidden state.
2. Claims are checked by something other than the claimant (gate, re-audit, architect's own run).
3. Every change is small, backed up, and provably inside its declared scope.
4. Progress is monotone: the test floor only rises, the debt ceiling only falls, history is append-only.

## 2. Laws (defined here once; prompts carry the short form)
LAW-1 ATOMIC one task = one change = one gate. LAW-2 ONE ATTEMPT run each command once; on error STOP, ask, never retry-and-hope, never fix forward.
LAW-3 TIMEOUT every command under `timeout --signal=KILL <s>` except a LAW-4 heredoc write (no `timeout`, no `bash`). LAW-4 WRITE only via a quoted heredoc (`<<'EOF'`) or `aw.py patch` (assert-once).
LAW-5 SECRETS never in a file, log or message; name the file, never the content. LAW-6 NUMBERS only from a command you ran.
LAW-7 OWNS only declared paths. LAW-8 PROTECTED never edit: AUDIT_LEDGER, PLAN_latest, prompts, `.aw/*` (except through the named tool),
ARCHITECT_FEEDBACK, PROPOSALS, METRICS, DECISIONS, cards, frozen files, lockfiles. LAW-9 FLOOR only the architect moves the ratchet/baseline.
LAW-10 GENERATED files change only through their generator.

Rules: R-1 pre-flight · R-2 OWNS · R-3 backup before change · R-4 numbers from commands · R-5 no extras · R-6 RED PROOF ·
R-7 one gate · R-8 counts live in the ratchet/ledger · R-9 the gate never falls below the ratchet · R-10 `re_audit` is the LAST step ·
R-11 worker->architect only via WORKLOG + `--ask` · R-12 architect->worker only via cards + `ANSWER Q-NNN`.

## 3. Decision rights
| Decision | AUTHOR | ARCHITECT | WORKER |
|---|---|---|---|
| Domain/method/clinical/legal content | DECIDES | asks with options | never |
| Task order, card design, gates, thresholds | approves big changes | DECIDES | never |
| Executing a card | - | verifies | executes, decides nothing |
| Secrets, money, commits/pushes, deleting data | DECIDES | proposes | never |
| Moving ratchet/baseline, re-baselining | - | ONLY architect | never |
| "Is it done?" | - | gate + re-audit + own run | reports, never declares |
A decision with no owner above is the AUTHOR's: write a QUESTION with options, cost and a default.

## 4. File ownership (who may write what)
| File | Writer | Rule |
|---|---|---|
| cards/**, PLAN_latest, START_BLOCKS, CARD_PATTERNS, MODULES, ROADMAP | Architect | ledger beats plan on conflict |
| AUDIT_LEDGER.md | Architect (`re_audit` appends §8) | append-only; a registered row is never edited; `## 8.` stays the LAST heading |
| ARCHITECT_FEEDBACK, PROPOSALS, METRICS, DECISIONS, AUTHOR_ANSWERS | Architect | author may append a decision |
| WORKLOG.md | Worker | append-only, real `date -Iseconds` |
| QUESTIONS.md | worker asks (`--ask`), architect/author answers (`aw.py answer Q-NNN "text"`) | |
| gate_output/**, backups/**, REPORT_latest | tools | never hand-edited |
| `.aw/ratchet.json`, `baseline.json`, `frozen.txt`, `checks.d/**` | Architect | worker never runs `--write-baseline`/`--raise` |
| source, tests, data | Worker, inside OWNS only | |

## 5. Card lifecycle — state, mover, file, exact line
| State | Moved by | Recorded in | Exact line |
|---|---|---|---|
| TODO | architect writes | card line 2 | `Status: TODO` |
| READY | architect, after dry run | card line 2 + proof | `Status: READY` + `## DRY-RUN PROOF` with real output |
| RUNNING | worker | `.aw/task-start`, WORKLOG | `START T-NNN` |
| PASS | worker | WORKLOG | `## T-NNN \| <date -Iseconds> \| PASS \| <title>` + `PASS T-NNN gate=OK count=<N> evidence=gate_output/<file>.txt` |
| FAIL | worker | WORKLOG + QUESTIONS | `## T-NNN \| ... \| FAIL \| <title>`, `ASKED Q-NNN` |
| STOP | worker | QUESTIONS + WORKLOG | `STOP: <key> missing in <path>. Need: <value>.` |
| ACCEPTED | architect, after own measurement | AUDIT_LEDGER §8 | `### ARCH-ACCEPT <date> after <ID>` row with measured numbers |
| REWORK | architect | feedback + new card | `F-NNN` line + a corrected card under a new id |
| OBSOLETE | architect | card + ledger | `Status: OBSOLETE` + `OBSOLETE - do not run it` + `Superseded by:` |

## 6. Lifecycle tree (every branch, its recovery command, its handoff line)
```
PLAN  architect: measure -> card -> card-lint OK -> dry run -> READY -> queue (queue-check OK)
      | handoff: ONE START BLOCK naming the chain (`base -> ... -> final`) and the stop list
DISPATCH  worker: reads card, pre-flight
      |- mismatch -> STOP: ask + FAIL format; architect classifies (card bug / env / defect / author)
      |- ok -> aw.py start <ID> -> aw.py backup <ID> <files>
EXECUTE
      |- RED not failing for the stated reason -> STOP (the test does not exercise the bug)
      |- step output differs -> aw.py restore <ID> -> ask -> STOP
      |- write outside OWNS refused by self-check -> aw.py restore <ID> -> ask -> STOP
      |- PASS -> bash tools/gate.sh <ID> -> OWNS='..' bash tools/re_audit.sh <ID> (LAST) -> WORKLOG -> PASS line
            | handoff: `PASS <ID> gate=OK count=<N> evidence=gate_output/<ID>.txt`
VERIFY  architect re-runs gate + integrity + reads the raw tail
      |- numbers match -> ratchet --raise <measured> once per QUEUE -> ARCH-ACCEPT row -> next queue
      |- PASS but the card's own numbers were wrong (scope, RED, count) -> do NOT accept: REWORK card under a new id,
      |  `F-NNN` to the worker, ledger row; the floor does NOT move
      |- tree dirty outside the card's OWNS -> aw.py restore <ID>, AUD-NN, STOP the queue
FAIL MID-QUEUE
      |- next card DEPENDS on the failed one (its Depends lists it, or the OWNS intersect) -> STOP: restore, ask, wait
      |- next card INDEPENDENT (no Depends edge, disjoint OWNS) -> restore, ask, CONTINUE; fix the chain count by the lost tests
STOP / ASK
      |- worker: restore if the tree is dirty, `--ask` one precise question, one WORKLOG line, stop that card
      |- architect: answer in QUESTIONS.md (`aw.py answer Q-NNN "text"`), a card change, or a QUESTIONNAIRE for the AUTHOR
      |- answer arrives AFTER the STOP -> the stopped card is closed by a decision + a NEW queue; a `REVISION <date>` line on the old card
RE-BASELINE NEEDED (a frozen file changed on purpose)
      |- architect only: `integrity --write-baseline --i-am-architect --allow <path>` (one path per flag)
      |- until then INTEGRITY FAIL is EXPECTED; the card said so in STOP (`FROZEN-CHANGED`)
OBSOLETE / SUPERSEDE
      |- architect: old card OBSOLETE + `Superseded by:`, new card `Supersedes:` under the next free id, ledger row, queue updated
SESSION CRASH / RESUME
      |- worker: BLOCK R (WORKLOG tail, git status, integrity, then exactly one of rollback / next card / STOP)
      |- architect: read REPORT_latest + ledger tail; a gate file newer than WORKLOG means a missing entry, not progress
```

## 7. Handoff contracts (the only two directions)
```
WORKER -> ARCHITECT
  PASS   : PASS T-NNN gate=OK count=<N> evidence=gate_output/<ID>.txt          (one line, no prose)
  FAIL   : <=20 lines: failing command, exit code, last <=15 raw lines, ONE question; then `ASKED Q-NNN`
  STOP   : STOP: <key> missing in <path>. Need: <value>.
  FILE   : WORKLOG row `## T-NNN | <date -Iseconds> | PASS|FAIL | <title>` + `files:` `commands->output:` `deviations:` `for author/architect:`
  NEVER  : "done", "should work", a number not printed by a command
ARCHITECT -> WORKER
  CARD   : line 1 `# <ID> — <title>`, line 2 header, 12 H2 sections, CHAIN line, ROLLBACK, DRY-RUN PROOF (card-lint OK)
  QUEUE  : one `Chain:` line, card order, stop list, `QUEUE DONE <n PASS> / <n FAIL> / <n STOP>` as the last line
  ANSWER : `ANSWER Q-NNN <date> <text>` in QUESTIONS.md (the worker re-reads it; chat is not a channel)
```

## 8. Self-improvement cycle (a repeated mistake becomes a barrier, not a note)
`WORKLOG -> audit -> ARCHITECT_FEEDBACK (F-NNN with a repetition counter) -> AUDIT_LEDGER (findings) -> PROPOSALS (P-NN) -> AUTHOR decides -> DONE -> VERIFIED`
- The SAME correction twice -> a proposal for a permanent barrier: a check in `.aw/checks.d/`, a new card-lint rule, a template line.
- Third time -> it must already exist; if it does not, the missing barrier is itself a CRIT finding.
- "Remember to..." is not a barrier. A barrier is a command that fails.

## 9. Failure ladder
Worker: error -> restore -> STOP -> one WORKLOG line -> `--ask`.
Architect: read FAIL -> classify: (a) card bug -> fix the card, `F-NNN` to self; (b) environment -> a card that fixes the environment;
(c) real defect -> AUD-NN + a card; (d) author decision -> QUESTION.
Escalate to the AUTHOR when: domain content, an irreversible action, conflicting answers, or a gate that can only pass by lowering the floor.

## 10. Cadence
Per card: gate + re-audit. Per queue: ratchet raise once, one ledger row. Every 3 accepted cards or after any FAIL: an audit block.
Before a release: full audit + the author's sign-off on domain content. Weekly: METRICS row, proposals reviewed.

## 11. Anti-patterns (each one broke something)
Self-reported numbers as fact · a gate that shares code with what it grades · work with no WORKLOG row · hand-edited generated files ·
editing a registered ledger row · proximity used as proof of ownership · "fix forward" after a FAIL · a baseline quietly re-written to make red green ·
a queue with no chain line · two runnable cards for one job · a worker told to "ask" but not to restore · a floor raised between cards of one queue.

## 12. Effort: medium by default, ultra when it pays
`python3 -I -B tools/effort.py stage` (Architect) and `card|queue` (worker) print `EFFORT <level> <who> <rule> <why>`; levels in `tools/kit.env`.
ARCHITECT hard (EFFORT_HARD): E1 newest WORKLOG entry FAIL, question open; E2 AUTHOR_ANSWERS recorded, no card yet (plan + cards); E3 an open SPEC card. In chat also: a new plan, a FAIL with no obvious cause. Else E4 EFFORT_DEFAULT: audit, replay, upgrade, registers, questionnaire.
WORKER: W5 EFFORT_WORKER (ultra; `auto` = W2 failed before, W3 steps>=10 or fenced>=4000 B or OWNS>=5, else W4 medium). W1 a SPEC card is always hard, never the cheap worker's.
A running chat cannot change or read its own level (Hermes: no tool, not in the prompt). `START_ARCHITECT.cmd` and `START_WORKER.cmd` pass `--reasoning` and state `Session effort: <level>.`; before a hard step the Architect re-runs `effort.py stage`: higher than stated = ONE line to the Author (double-click START_ARCHITECT.cmd again, or `/reasoning <level>` then `Session effort: <level>`), then stop; a later `Session effort:` line replaces the first; none = say unknown, go on.
