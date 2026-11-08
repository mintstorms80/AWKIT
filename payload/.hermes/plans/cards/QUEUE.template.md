<!-- WRITER: ARCHITECT | copy to cards/QUEUE_<date>.md | edit in place until pasted; after that EXTEND (second package), never renumber | the worker never edits it -->
# QUEUE <date> - {{PROJECT_NAME}} - cards <first id>..<last id>
Baseline (MEASURED by the Architect <date>, HEAD <sha>): <n> passed | INTEGRITY <line> | RATCHET min_tests=<n> | lint <n> | git <clean / n dirty> | DOCTOR <line>
Chain: base=<int> | <ID>:+<int> <ID>:+<int> | final=<int>
Arithmetic: base = live ratchet floor (or the measured count if higher). +k = tests the card adds (0 for lint and census). final = base + sum(k). A card's first `ran=` (the count BEFORE its own tests) = base + the k of all rows above it. The Architect runs `ratchet --raise <final> --i-am-architect` once, after ALL cards PASS. After a FAIL, later `ran=` = chain value - that card's k: log the real number; raise to the MEASURED count.
Order: only READY (dry-run proven) cards; +0 cards first, +k cards in chain order, CENSUS last. Lane SPEC never runs here (another executor).

| # | ID | Lane | Adds | Depends | On FAIL | Title |
|---|---|---|---|---|---|---|
| 1 | <ID> | ROTE | +0 | - | CONTINUE | <fill> |

On FAIL: CONTINUE = no later card shares a file with this one; STOP = a later card depends on it (a card with a Depends edge to it, or overlapping OWNS). Not queued: <ID: reason>.

## START BLOCK (paste once; a later package = the same block, only the rows range changes)
```
ROLE: [HERMES EXECUTION ENGINE]. Follow .hermes/prompts/WORKER.md and AGENTS.md. Answer in {{REPLY_LANG}}.
Run rows <1>..<n> of .hermes/plans/cards/QUEUE_<date>.md in order. Never ask the owner between cards.
First: cd <repo root>; unset PYTHONPATH; read the OPEN entries of ARCHITECT_FEEDBACK.md.
Per card: procedure and result line as in WORKER.md; card file .hermes/plans/cards/<ID>.md; raw output gate_output/<ID>.txt; WORKLOG entry with date -Iseconds.
On card FAIL or STOP: the WORKER.md procedure (restore, WORKLOG entry, worker_report.py --ask), then the row's On FAIL rule.
HALT at once, never CONTINUE: LEDGER-REWRITTEN, RATCHET-LOWERED, ARCHITECT-STATE-CHANGED, FROZEN-CHANGED in .aw/ tools/ .hermes/prompts/.
A question = --ask (Q-NNN), then the next card that shares no file with the blocked one.
Never: commit, delete, ratchet --raise, integrity --write-baseline, edit ledger / plan / prompts / .aw / tools. Do not touch: <Author's or frozen list>.
Last line: QUEUE DONE <n PASS> / <n FAIL> / <n STOP>
```
Second package: append rows numbered on from the last, extend the Chain line, change the rows range above. Never renumber.
Worked example (EXAMPLE numbers, not measured; it must not start with the word Chain, queue-check counts such lines):
    e.g. Chain: base=602 | T-036:+0 T-043:+5 T-044:+6 | final=613
First `ran=` seen: T-036 602, T-043 602, T-044 607 (= 602+0+5). After all PASS: ratchet --raise 613.
Return line, the worker's LAST line of the run: `QUEUE DONE <n PASS> / <n FAIL> / <n STOP>`
