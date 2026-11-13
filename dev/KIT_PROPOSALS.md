<!-- WRITER: ARCHITECT of the kit | the Status column is edited in place, rows are never deleted | author-side, never installed -->
# KIT_PROPOSALS - kit-level improvements harvested from the projects
Lifecycle: PROPOSED -> VERIFIED (a selftest check or a card-lint rule that is RED on the previous kit and GREEN on this one) | REJECTED (reason) | NO_EFFECT (comes back with a new approach).
`dev/harvest.py PROJECT...` prints candidates; the Architect verifies one cited line and records a row here. Next id: the highest K-NN + 1.

| ID | Date | Evidence (project:file:line) | Barrier | Status | Check |
|---|---|---|---|---|---|
| K-01 | 2026-11-13 | project A:.hermes/plans/PROPOSALS.md:7 (P-01) | card-lint L33 also matches `git` with option prefixes (`git -c k=v clone`, `git -C dir fetch`) and tells a local source path from a URL | PROPOSED | - |
| K-02 | 2026-11-13 | project A:.hermes/plans/PROPOSALS.md:8 (P-02) | WORKER.md "any git write" names the repository it protects (the project repo), so a card may clone or branch a nested staging repo | PROPOSED | - |
