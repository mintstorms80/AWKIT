<!-- WRITER: WORKER asks via `python3 -I -B tools/worker_report.py --ask "..."`; ARCHITECT or AUTHOR answers via `python3 tools/aw.py answer Q-NNN "text"` | APPEND-ONLY | ids come from the tool (`aw.py next-id Q`), never typed by hand -->
# QUESTIONS - {{PROJECT_NAME}}
Entry (written by the tool):

    ## Q-NNN | <timestamp> | OPEN
    <one precise question: what you were doing, what value you need>

Answer (one line, written by the tool):

    ANSWER Q-NNN <YYYY-MM-DD> <text>

A question without an ANSWER line is OPEN (counted in REPORT_latest.md). Inside a queue the worker asks and goes on with the next card that shares no file with the blocked one. A question that is really an Author decision becomes a D-NN row in DECISIONS.md.
