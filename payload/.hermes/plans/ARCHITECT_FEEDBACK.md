<!-- WRITER: ARCHITECT | NOT append-only: only the status word in an entry heading is edited in place, entries are never deleted | the WORKER reads the OPEN entries before every queue -->
# ARCHITECT_FEEDBACK - corrections to the worker (and to the architect itself)
Entry (next id: `python3 tools/aw.py next-id F`; open ones: `grep -n "| OPEN$" ARCHITECT_FEEDBACK.md`):

    ## <date> | F-NNN | <topic> | OPEN|APPLIED|IGNORED|AUTOMATED
    - Seen: <fact with file / command evidence>
    - Correction: <one imperative sentence>
    - Why: <consequence if repeated>
    - Repetition: first | second -> P-NN | third -> must be automated

Rule: the same error twice (here or in WORKLOG) = a PROPOSALS row for an automatic check (test, guard, checks.d metric). "Remember to ..." is not a barrier.
