# START_BLOCKS v2 — paste blocks (architect writes them; one block per sitting)
One block = one paste. The model answers in {{REPLY_LANG}}; markers (`PASS`, `GATE`, `STOP`) stay Latin.
Never paste a block whose expected output you have not seen yourself or marked UNMEASURED.

## BLOCK 0 — ARCHITECT GENESIS (first session, new or existing project)
```
ROLE: ARCHITECT. Kit: tools/aw.py. Read PLAYBOOK.md once, then .hermes/prompts/ARCHITECT.md. Steps IN ORDER; print the line each demands; stop + `aw.py ask` on mismatch.
1 SURVEY (read-only): every route/worker/migration/config file; list every workflow with no spec. OUT: workflow | entry point(file:line) | spec? | severity.
2 QUESTIONS: <=3 with options + default, only what the AUTHOR decides (domain, money, secrets). OUT: `## Q-NNN` from `tools/aw.py ask`.
3 CONFIG: fill tools/kit.env (PY, TEST_DIR, TEST_CMD, COUNT_REGEX); `aw.py doctor`. OUT: `DOCTOR PASS warn=<n> fail=0` (baseline/ratchet WARN until steps 4-5).
4 BASELINE: `bash tools/gate.sh baseline`; `aw.py ratchet --raise <measured> --i-am-architect`. OUT: `GATE OK count=<N>` and `RATCHET min_tests=<N>`, same N.
5 FREEZE: fill .aw/frozen.txt, add >=1 check in .aw/checks.d/, `aw.py integrity --write-baseline --i-am-architect`. OUT: `INTEGRITY OK frozen=<n> metrics=<m>`.
6 FIRST AUDIT: AUD-NN rows in AUDIT_LEDGER.md §3 (never edit a row). OUT: `grep -c '^| AUD-' .hermes/plans/AUDIT_LEDGER.md` > 0.
7 PLAN+MODULES+ROADMAP: one module per ownership boundary (exact header), one phase per milestone. OUT: `aw.py modules` => `MODULES OK modules=<n> waves=<n>`.
8 FIRST QUEUE: each card `aw.py card-lint <ID>` => CARD-LINT OK; one `Chain:` line. OUT: `aw.py queue-check <q.md>` => `QUEUE-CHECK OK chain=<base> -> ... -> <final>`.
9 VCS: first commit before any worker runs. OUT: `git rev-parse --short HEAD` prints a hash.
```

## BLOCK 1 — WORKER DRY RUN (proves the STOP path before real work)
```
ROLE: [HERMES EXECUTION ENGINE]. Caveman. Follow .hermes/prompts/WORKER.md.
Two cards, both written here (no card file exists). Print every result line you get.
1) T-DRY1 (trivial, real). OWNS: DRY_RUN.txt (new file). In order, one command each: `bash tools/gate.sh pre-T-DRY1` -> `GATE OK count=<N> min=<N>`;
   `python3 -I -B tools/aw.py integrity` -> `INTEGRITY OK ...`; `python3 -I -B tools/aw.py start T-DRY1`; write DRY_RUN.txt = the one line `dry run`;
   `bash tools/gate.sh T-DRY1` -> same count; `OWNS='DRY_RUN.txt' bash tools/re_audit.sh T-DRY1` LAST -> `AUDIT PASS`; WORKLOG row (`date -Iseconds`);
   result `PASS T-DRY1 gate=OK count=<N> evidence=gate_output/T-DRY1.txt`.
2) T-DRY2 (deliberately impossible). PRE-FLIGHT: `bash tools/gate.sh pre-T-DRY2` must print `GATE OK count=0 min=0`; the real count is <N>, so it cannot.
   Required: FAIL format <=20 lines, ONE question via `python3 -I -B tools/worker_report.py --ask "<exact mismatch>"`, STOP.
   No start, no backup, no edit, no retry. Never edit a card, the kit or .aw/* to make it pass.
Print: the T-DRY1 PASS line; for T-DRY2 the failing line, `ASKED Q-NNN`, `STOPPED`.
Never touch AUDIT_LEDGER.md, PLAN_latest.md, prompts, .aw/*, FEEDBACK, PROPOSALS, METRICS, DECISIONS.
```

## BLOCK Q — WORKER QUEUE (unattended, one paste, one return line)
```
ROLE: [HERMES EXECUTION ENGINE]. Caveman. Follow .hermes/prompts/WORKER.md.
QUEUE: .hermes/plans/cards/QUEUE_<date>.md — every card in order, no pauses between cards.
BEFORE card 1: `aw.py ratchet`; `git status --short` (record as E0 in WORKLOG); confirm the `Chain:` base.
PER CARD: pre-flight (byte-for-byte) -> `aw.py start <ID>` -> `aw.py backup <ID> <files>` -> RED -> steps -> `bash tools/gate.sh <ID>`
-> `OWNS='<card OWNS>' bash tools/re_audit.sh <ID>` LAST -> WORKLOG row (`date -Iseconds`) -> one result line.
`aw.py ask` is NOT a pause (it files QUESTIONS.md): continue with the next card that depends on nothing failed.
ON FAILURE: `aw.py restore <ID>`, file Q-NNN, CONTINUE if the next card shares no file, else STOP. Never fix forward, never edit the card,
never touch .aw/*, never --write-baseline.
LAST LINE exactly: `QUEUE DONE <n PASS> / <n FAIL> / <n STOP>`
```

## BLOCK R — RESUME after a STOP or crash
```
ROLE: [HERMES EXECUTION ENGINE]. Caveman. Start no card yet.
1) `tail -n 12 .hermes/plans/WORKLOG.md`; `grep -n 'Q-' .hermes/plans/QUESTIONS.md | tail -3`. 2) `git status --short`; `ls .hermes/plans/gate_output/<ID>*`.
3) `aw.py integrity`. Print all three, then run exactly one:
a) the card's `## ROLLBACK` if the tree is dirty and the card is not ACCEPTED;
b) the next card if the tree is clean and its PRE-FLIGHT passes; c) nothing + `STOP: needs architect.` if they disagree.
```

## BLOCK A — ARCHITECT AUDIT SESSION (every session start)
```
ROLE: ARCHITECT. Read REPORT_latest.md, WORKLOG (tail), AUDIT_LEDGER (§1-3 + tail), QUESTIONS (open), PLAYBOOK.md.
0) EFFORT: `python3 -I -B tools/effort.py stage`; print its line first (PLAYBOOK §12).
1) MEASURE: `bash tools/gate.sh <glob> <floor>`, `aw.py integrity`, `aw.py ratchet`, `git status --short | wc -l`, `aw.py card-lint` per queued card.
2) CLAIMED vs FOUND: one table claim | measured | verdict (gate_output tails + mtimes are the evidence).
3) CLOSE what is proven: `aw.py ratchet --raise <measured> --i-am-architect`; one `ARCH-ACCEPT` row with YOUR numbers + explicit `UNMEASURED:` list.
4) RE-BASELINE only if a card legitimately changed a frozen file (`--write-baseline --i-am-architect --allow <path>`, one per flag).
5) NEXT QUEUE (card-lint + queue-check green) + ONE block.
OUT: 3 bullets MEASURED/UNMEASURED (state, risk, next move), the paths written, the critical questions and the skipped list as ARCHITECT.md defines them.
```

## BLOCK X — FIX-ORDER close-out (the Author says "fix it")
```
ROLE: ARCHITECT. Apply it, then close the loop like a worker PASS.
1) `aw.py backup FIX <files>` first. 2) apply. 3) `bash tools/gate.sh <glob> <floor>` -> `GATE OK count=<N>`. 4) `aw.py integrity`.
5) `aw.py ratchet --raise <measured> --i-am-architect`. 6) ONE `ARCH-FIX` ledger row: what changed, the numbers, explicit `UNMEASURED:`.
7) WORKLOG stays the worker's file. 8) Leave it UNCOMMITTED; end with the commit question. OUT: those four lines verbatim + the row id.
```
