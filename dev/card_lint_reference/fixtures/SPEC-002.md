# SPEC-002 — mail tab layout against the reference screenshot
Status: READY | Lane: SPEC | Depends: - | Module: M-04 | Author decisions needed: none
Executor: claude-sonnet (strong model, separate session)

## GOAL
Design the mail tab so it matches the reference (Q-012 answered: layout approved) and uses only routes that exist; every field the source does not print stays `UNMEASURED`.

## OWNS
- web/index.html

## READ-ONLY
- everything else, in particular web/sw.js

## PRE-FLIGHT
| # | Command | Expected |
|---|---|---|
| 1 | `bash tools/gate.sh pre-SPEC-002` | `GATE OK count=602 min=602` |
| 2 | `python3 -I -B tools/aw.py integrity` | `INTEGRITY OK frozen=23 metrics=2` |

## BACKUP
`python3 -I -B tools/aw.py start SPEC-002`
`python3 -I -B tools/aw.py backup SPEC-002 web/index.html`

## STEPS
Reference beside current state, the routes that exist (grep the decorators, never guess a route), then the node tests the executor writes FIRST; judgement on layout and wording is the executor's.

## RED PROOF
The executor's new node test fails before the page change.

## GATE
CHAIN: ran=602 +0 -> ran=602 (UNMEASURED)

## INVARIANTS
- English strings stay the dictionary keys; no new route

## STOP
Any suite turns red; a needed route is missing => `--ask`, do not invent data.

## EVIDENCE
gate_output/SPEC-002.txt

## AFTER
Architect reviews the diff and the rendered page; owner confirms layout.

## DRY-RUN PROOF
```text
# SYNTHETIC FIXTURE OUTPUT (lint test data, not measured)
$ bash tools/gate.sh pre-SPEC-002
GATE OK count=602 min=602
$ python3 -I -B tools/aw.py integrity
INTEGRITY OK frozen=23 metrics=2
$ ls tests/*.test.mjs
tests/page_render.test.mjs  (reference only; the executor writes the new test first)
```
