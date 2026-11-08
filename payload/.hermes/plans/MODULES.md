<!-- WRITER: ARCHITECT | APPEND-ONLY: no, living file; ids are never reused or renumbered | check: python3 tools/aw.py modules -->
# MODULES - {{PROJECT_NAME}}
Rules:
1. No two modules of ONE wave write the same file. Shared test infrastructure (conftest, fixtures, harness) has exactly ONE owner module.
2. A module's wave is later than the wave of everything it Depends on. A card's OWNS lies inside its module's OWNS.
3. A wave = modules with no dependency among them. The single worker runs them one after another; rule 1 makes their order irrelevant.
4. A wave is closed only when its gate passes; then the next wave starts. Delete the EXAMPLE rows when you register the first real module.

| ID | Module | Purpose | OWNS | Depends | Wave | Gate | Decides | Status |
|---|---|---|---|---|---|---|---|---|
| M-01 | core | EXAMPLE: shared library | src/core/**,tests/core/**,tests/conftest.py | - | W-1 | bash tools/gate.sh M-01 | architect | EXAMPLE |
| M-02 | api | EXAMPLE: HTTP layer on core | src/api/**,tests/api/** | M-01 | W-2 | bash tools/gate.sh M-02 | author | EXAMPLE |

Status: PLANNED | ACTIVE | DONE | BLOCKED(D-NN or Q-NNN). OWNS = comma-separated globs, no spaces. Decides = who settles the module's content.

| Wave | Modules | File-ownership partition (shared file -> its one owner) | Acceptance gate | Rollback |
|---|---|---|---|---|
| W-1 | M-01 | tests/conftest.py -> M-01 | GATE OK, count >= floor | `aw.py restore <ID>` per card, newest first |
| W-2 | M-02 | none shared | GATE OK + `aw.py modules` OK | same |

Critical path (longest Depends chain): M-01 -> M-02
Float (waves a module can slip without delaying a dependent): <module: n>
