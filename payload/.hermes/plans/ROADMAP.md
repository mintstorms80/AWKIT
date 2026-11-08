<!-- WRITER: ARCHITECT | APPEND-ONLY: table rows may change Status; every new layer is a `## Addendum` block appended at the END, never a rewrite -->
# ROADMAP - {{PROJECT_NAME}}
Principle: each phase is MEASURED before the next starts. The running queue is never reordered for a future phase; a future need becomes an Addendum + a PROPOSALS row.
A gate is a command with an exact expected output, or a file with a checkable property. "Looks good" and "reviewed" are not gates.

| PH | Phase (usual order: quick wins, then structure, then automation) | Gate (check + artifact) | Owner | Preconditions | Status |
|---|---|---|---|---|---|
| PH-0 | Current work: <the running queue> | <existing gate> | Architect | - | ACTIVE |
| PH-1 | <next capability> | `<cmd>` => `<expected>` | <who> | AUD-NN, D-NN | PLANNED |

Status: PLANNED | ACTIVE | GATE-PASSED | BLOCKED(<id>) | DROPPED(<why>). Preconditions = finding / decision ids that must be FIXED / decided first.

## Aggressive vs realistic
| Path | Done by | Holds only if | Checkpoints (date: gate that must be green) |
|---|---|---|---|
| Aggressive | <date> | no REWORK, no open D/Q, no env incident | <date: gate> |
| Realistic | <date> | + Author answers a batch in <n> days, 1 REWORK per phase | <date: gate> |
Dates: the next phase exact; later phases as ranges labelled UNMEASURED (the back half of a plan is uncertain).

## Re-planning triggers (any one: append an Addendum with the new plan, then tell the Author)
- a phase gate fails twice, or one card is REWORKed 3 times
- a CRIT/HIGH finding lands on a precondition of a PLANNED phase
- an Author answer reverses a ruling a card or phase encodes (grep the old ruling first)
- the Author names a new destination (record it, keep working the current phase)
- a phase takes > 2x its realistic estimate (ASSUMED threshold, edit it)
- the only way to pass a gate is to lower a ratchet (Author decision)

## Addenda
Each later revelation is a new block appended at the END: `## Addendum <YYYY-MM-DD> (<who>)` = what is new, which PH rows it adds, what stays unchanged. Never rewrite the table to "integrate" it; the earlier reasoning is the record. Three or four addenda are normal.
A risk with a legal, regulatory or domain owner is UNMEASURED and goes to that named human, never to an agent.
