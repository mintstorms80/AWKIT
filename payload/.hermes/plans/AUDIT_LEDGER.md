<!-- WRITER: ARCHITECT, plus the tool (aw.py audit appends RE-AUDIT blocks) | APPEND-ONLY at the END: the engine hashes the prefix, so an edit or insert above = LEDGER-REWRITTEN -->
# AUDIT_LEDGER - {{PROJECT_NAME}}
The ledger beats the plan. Every claim is MEASURED (command + output) or UNMEASURED. Floors only rise, ceilings only fall.
Sections 1-2 are written ONCE at setup, before the first `aw.py audit T-NNN`. After that add nothing above and no new `## `:
append `### ` blocks at the very end (inside section 8), <= 6 lines each, the newest block about an id wins. Read: sections 1-2, then `tail -n 80`.
Block headers (a registered row is never edited, a later block corrects it):
- `### <date> AUD-NN | <SEV> | <finding> | OPEN`  + lines `evidence: <cmd> => <output>` and `closing gate: <id>`
- `### <date> STATUS AUD-NN <OPEN|AUTHOR|FIXED|WONTFIX> | <gate or reason>`
- `### <date> ARCH-ACCEPT <ids> | ran=<n> min=<n> | floor <a> -> <b> | UNMEASURED: <list>`   (also ARCH-FIX, BASELINE, ANSWERS <file>, RECOVERED)
- `### <date> CORRECTION <block>: <one sentence>`

## 1. Severity and status
CRIT = wrong or unsafe output reaches a user, or data is lost | HIGH = guard missing or bypassable, claim unverifiable | MED = debt that will bite | LOW = hygiene.
Status: OPEN | AUTHOR (needs an Author decision) | FIXED (with gate) | WONTFIX (with reason).

## 2. Findings at setup (first audit, before any card runs)
| ID | Sev | Finding | Evidence (command + output) | Status | Closing gate |
|---|---|---|---|---|---|
| AUD-01 | | | | OPEN | |

## 8. RE-AUDIT LOG
