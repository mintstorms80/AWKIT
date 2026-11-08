<!-- WRITER: WORKER only | APPEND-ONLY | real time from `date -Iseconds`, never back-dated (a late entry gets the real time now and `deviations: RECOVERED`). A card without its entry is not done. -->
# WORKLOG - {{PROJECT_NAME}}
One entry per card (ID = T-NNN or CHK-NNN). The heading line is machine-read; keep it exactly like this:

    ## T-NNN | <date -Iseconds> | PASS|FAIL | <title>
    files: <changed files>   backup: backups/T-NNN/
    commands->output: <command> => <result line>   (raw tail in gate_output/<file>)
    deviations: none | <what and why>
    for author/architect: none | Q-NNN

The `GATE OK count=<n> min=<m>` line of the card goes into commands->output verbatim: the Architect compares its count with the queue Chain.
