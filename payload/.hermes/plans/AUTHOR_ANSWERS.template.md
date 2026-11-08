<!-- WRITER: ARCHITECT, verbatim from the Author | copy to AUTHOR_ANSWERS_<date>.md | record BEFORE any card moves; append-only once APPLIED -->
# AUTHOR_ANSWERS <date> - answers to QUESTIONNAIRE_<date>.md  (<who>, via file|chat; signature: author-written | owner-for-author)
Status: RECORDED - nothing applied yet.   Later: APPLIED <date>, ledger block `### <date> ANSWERS <this file>`.
Answer letters keep the questionnaire's alphabet (Latin A and Cyrillic A look alike but differ in bytes): record each letter as given.

| Q | Answer | Consequence |
|---|---|---|
| Q1 | B: <as printed> | <what changes / "nothing to implement" / BLOCKED/AUTHOR / OPEN: missing half> |

## What each kind of answer does
| Answer | Action |
|---|---|
| confirms the current state | nothing to implement; check that no card still encodes the opposite |
| reverses an earlier ruling | same session: `grep -n "<id>\|<old ruling>" cards/ PLAN_latest.md`, patch case lists, counts in prose, queue rows |
| keeps an ambiguous case as printed | the ambiguity stays a finding; add the case, do not close it |
| orders content the source never prints | REFUSE: BLOCKED/AUTHOR with the printed evidence; no placeholder; say what unblocks it |
| needs a field or table that does not exist | P-NN (owner: author, PROPOSED) + a design step, not a default value |
| partial ("will specify later") | stays OPEN; name the missing half |
| free text, not a letter | record as PROSE with its consequence; never map it to the nearest letter |
| signature | record WHICH it is: the Author's own written confirmation, or the owner speaking for her/him |

## Batch after recording (one pass, this order)
1) DECISIONS.md D-NN rows (Source = this file + Qk)  2) ledger block `ANSWERS` (new AUD ids for what the answers open; old rows stay)  3) ARCHITECT_FEEDBACK F-NNN if the worker must change  4) PROPOSALS P-NN  5) METRICS row  6) only then cards and queue.
Report: asked <n> / answered <n> / OPEN <n> / BLOCKED-AUTHOR <n> + this file's path (a "done" without the path is a claim).
