<!-- WRITER: AUTHOR/ARCHITECT kit file | ENGINE class: byte-identical to the kit | project-specific rules go to AGENTS.md and .aw/checks.d, never here -->
# SELF_IMPROVE - how the project gets better without relying on memory
A system improves only if every mistake becomes a lasting barrier. The loop is closed by registers and by one command, not by "remember to ...".

```
Worker --WORKLOG--> Architect (audit) --ARCHITECT_FEEDBACK--> Worker (reads OPEN entries before every queue)
                        |--AUDIT_LEDGER (findings)   |--PROPOSALS (improvements) --> Author decides   |--METRICS (trend)
```

## 1. Each audit (the order)
1. `python3 -I -B tools/aw.py improve` - read-only; every `IMPROVE ACTION ...` line is work for this audit.
2. WORKLOG entries since the last METRICS row. A claimed PASS without a `gate_output/` file is a finding.
3. Each earlier F-NNN: check in code / WORKLOG that it was applied; edit its status word to `APPLIED` or `IGNORED`.
4. Each P-NN: status and measured effect (lifecycle in PROPOSALS.md).
5. Re-measure, do not trust the log: `bash tools/gate.sh <label>`, `python3 -I -B tools/aw.py integrity`, plus every project check named in AGENTS.md; compare changed files with the card's OWNS.
6. Write: ledger rows, F-NNN corrections, P-NN proposals, ONE METRICS row. A phase change or a big finding gets its own `AUDIT_<date>_architect.md`.
7. Close with the critical questions and proposals for the Author (shape: ARCHITECT.md), and list every `Ruling:` you took with its cost if wrong: a ruling left in a log is a decision made in secret.

## 2. A repeated mistake
The same topic twice in ARCHITECT_FEEDBACK (or in WORKLOG) => a PROPOSALS row for an automatic barrier: a test, a guard, a `.aw/checks.d` metric or a line in AGENTS.md. `aw.py improve` prints it as `repeated-error`.

## 3. Limits of the auditor
Changes no code and none of: AGENTS.md, PLAN_latest.md, anything the Author froze. Takes no domain decision (content, thresholds, money, signatures). Starts no long or expensive job. Deletes nothing. Closes no finding without a gate result it ran itself. A proposal that changes plan, schema or protocol waits for the Author; one that only touches these registers the Architect applies alone.

## 4. Rhythm
After every 3 accepted cards, after any FAIL or write outside OWNS, before a release; a project may add a schedule (a weekday morning audit via the host scheduler) as an Author decision recorded in DECISIONS.md.

## 5. What `aw.py improve` measures (and what it does not)
Counts F-NNN by status, lists OPEN and IGNORED ones, repeated topics, P-NN by status (ACCEPTED/DONE not yet VERIFIED are actions), open questions. Last line `IMPROVE OK` or `IMPROVE ACTION <n>`. It does not judge quality, does not read code and writes nothing.

## 6. `tools/learn.py` - the project-specific miner (read-only)
`aw.py improve` counts registers; `python3 -I -B tools/learn.py` reads THIS project's own history (WORKLOG, AUDIT_LEDGER, ARCHITECT_FEEDBACK, gate_output, ratchet) and prints `LEARN SUGGEST <kind> | evidence file:line | barrier: ...` for: recurring pitfall families (>=3 hits), unstable cards (>=2 FAIL/STOP), high fail rate, `empty-pass` (PASS with no changed file), open CRIT/HIGH and backlog, ratchet lag (measured count >= floor+10; the Architect raises once), hot files, `blind-check`, `guardrail-off` (hook shipped, not enabled), `steering-sprawl` (AGENTS.md > 6500 chars), repeated feedback not AUTOMATED, `kit-behind` (this project's `.aw/KIT_VERSION` is older than the kit named by `KIT_HOME` in `tools/kit.env`; barrier: `UPGRADE_KIT.cmd`; silent without the key), `stale-proposal` (a P-NN still PROPOSED after >= 3 later METRICS rows). Last line `LEARN OK` or `LEARN SUGGEST <n>`. It writes nothing unless `--write` (only `.hermes/plans/LEARN_latest.md`).
Use: each audit, after `improve`. Verify ONE cited line per suggestion, then record a PROPOSALS row (P-NN) naming the barrier; an unverified suggestion is a candidate, never a finding. Honest limit: keyword families are heuristics; they find where to look, not what is true.

Barrier choice (mattpocock/skills retro, MIT): a MECHANICAL violation (fixed pattern, banned call, file location) gets a `.aw/checks.d` check, never a prose rule; only a JUDGEMENT call earns one AGENTS.md line. AGENTS.md carries pointers and non-obvious rules, not what a command prints.
