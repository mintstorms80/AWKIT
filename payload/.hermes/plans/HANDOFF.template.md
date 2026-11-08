<!-- WRITER: ARCHITECT or WORKER, whoever ends the session | copy to HANDOFF_<date>.md, one file per session; the same file is the WEEKLY REVIEW | <= 12 lines, every number MEASURED with its command -->
# HANDOFF <date> - {{PROJECT_NAME}} | role: architect|worker | model: <name>
- Read first: `python3 -I -B tools/aw.py report`, the tail of WORKLOG.md, this file.
- State (MEASURED): `GATE OK count=<n> min=<m>` | `RATCHET min_tests=<n>` | `INTEGRITY ...` | git <n dirty files, HEAD <sha>> | open CRIT/HIGH <n>/<n> | open Q <n> | `DOCTOR ...`
- Queue: <cards/QUEUE_<date>.md> chain <base -> final> | WORKLOG rows <done>/<total> | last return line `QUEUE DONE ...`
- Done: <ids -> evidence file>
- Blocked: <id: reason, waiting for whom>
- Next 3 (exact): 1) <command or card id>  2) <...>  3) <...>
- UNMEASURED / risks: <list>
- Decisions needed: <D-NN / Q-NNN: options A / B, DEFAULT = ...>
