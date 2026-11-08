> TEMPLATE: delete these 5 lines, fill every <ALL-CAPS> slot, set Status READY only after DRY-RUN PROOF is pasted; `python3 -I -B tools/aw.py card-lint <ID>` must print CARD-LINT OK.
> ROTE (T-): cheap worker. Exact bytes, ONE command or ONE patch per step, RED first. No choices, no judgement words. Expected = tool output taken from DRY-RUN PROOF, or the word UNMEASURED.
> CENSUS (CHK-): cheap worker, read-only. Deliverable = ONE gate_output/<ID>.md. OWNS = that file only. No start/backup/patch, no verdict. A census total is a witness: different number => record it, do not stop.
> SPEC (SPEC-): strong executor, NEVER the cheap worker, never queued. Line 3 `Executor: <MODEL>`. Judgement allowed; its tests are written FIRST. Surgical: every changed line traces to the GOAL; an unrelated finding is a WORKLOG note, never fixed in passing; remove only the orphans YOUR change created.
> Optional line 3: `Supersedes: <ID> | Superseded by: <ID> | Executor: <MODEL>`. An OBSOLETE card gets the line `OBSOLETE - do not run it` and `Superseded by:` (or `-` + reason).
# T-NNN — <TITLE>
Status: TODO | Lane: ROTE | Depends: - | Module: - | Author decisions needed: none

## GOAL
After this card `<OBSERVABLE FACT>` holds, proven by `<GATE LINE>`.

## OWNS
- <PATH>
(closed list, project-relative, `/` only. Always allowed: WORKLOG.md, gate_output/**, backups/**, REPORT_latest.md, QUESTIONS.md)

## READ-ONLY
- everything else, in particular <PATH>

## PRE-FLIGHT
Run from the project root. Any mismatch => STOP (R-1).
| # | Command | Expected |
|---|---|---|
| 1 | `bash tools/gate.sh pre-T-NNN` | `GATE OK count=<N> min=<N>` |
| 2 | `python3 -I -B tools/aw.py integrity` | `INTEGRITY OK frozen=<N> metrics=<N>` |
| 3 | `git status --short` | record as E0 in WORKLOG |

## BACKUP
`python3 -I -B tools/aw.py start T-NNN`
`python3 -I -B tools/aw.py backup T-NNN <FILE>`
NEW: <FILE|NONE>

## STEPS
One command or one patch per row. Heredoc payloads are fenced blocks below the table. A patch needs its OLD and NEW texts written by their own two rows first (both under gate_output/, which needs no OWNS entry).
| # | Action | Expected |
|---|---|---|
| 1 | write `<FILE>` (block below) | `file exists` |
| 2 | RED: `<TEST CMD>` | `<N> failed` |
| 3 | write `.hermes/plans/gate_output/T-NNN.old.txt` and `.hermes/plans/gate_output/T-NNN.new.txt` (blocks below) | `file exists` |
| 4 | `python3 -I -B tools/aw.py patch <FILE> .hermes/plans/gate_output/T-NNN.old.txt .hermes/plans/gate_output/T-NNN.new.txt` | `PATCH OK` |
| 5 | `<TEST CMD>` | `<N> passed` |

```bash
cat > <FILE> <<'EOF'
<EXACT BYTES>
EOF
```

## RED PROOF
Step 2 must fail for the stated reason; paste the failing line into WORKLOG. (CENSUS: `n/a - read-only`. Characterization: `n/a - must pass on the first run; a failure => STOP, never edit the test`.)

## GATE
CHAIN: ran=<N> +<K> -> ran=<N+K> (MEASURED|UNMEASURED)
| # | Command | Expected |
|---|---|---|
| 1 | `bash tools/gate.sh T-NNN` | `GATE OK count=<N+K> min=<N>` |
| 2 | `OWNS='<GLOBS>' bash tools/re_audit.sh T-NNN` | `AUDIT PASS` |

## INVARIANTS
- no frozen file, no new dependency, no commit, no baseline or ratchet move

## STOP
Mismatch, file outside OWNS, gate below floor, secret-like text, ambiguity => ROLLBACK, FAIL format, `--ask`. A pre-flight `count` different from CHAIN `ran` => STOP.

## ROLLBACK
`python3 -I -B tools/aw.py restore T-NNN` => `RESTORED <N> file(s) from backups/T-NNN/`. Files under NEW: are not removed: list each as `CREATED <path>` in WORKLOG.

## EVIDENCE
gate_output/T-NNN.txt + WORKLOG entry (real `date -Iseconds`) + the one-line result.

## AFTER
Architect: re-baseline? yes|no (`integrity --write-baseline --i-am-architect --allow <PATHS>`). Ratchet is raised once, to the queue `final=`. Ledger row. METRICS row.

## DRY-RUN PROOF
<PASTE COMMANDS AND REAL OUTPUT> (required from Status READY)
