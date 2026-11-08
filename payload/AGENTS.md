<!-- AGENTS.md - project rules, binding for EVERY agent (Architect, Worker, analysts). The AUTHOR alone edits this file: no agent writes, rewords or deletes it. Read it fully at session start and before any write; if it conflicts with a card, it wins, and you STOP and report the conflict. Existing project? init_project.py stages this file into kit_stage/ - paste the sections under your own text, do not replace it. Delete this comment after filling. -->
# Project rules - {{PROJECT_NAME}} (owner: {{OWNER}}, since {{DATE}})

## Rule #1 - NOTHING IS INVENTED
> "Do not invent anything. Everything follows the source, with no creativity. This is rule number one: apply it before every action, without exception." - the author

A value, text, question or item that the source does not print stays unfilled. It is not inferred, defaulted, converted or copied from a neighbouring task; the deliverable reports it as missing instead.

### Forbidden - measured cases, not hypotheses
| Forbidden | Why (measured) |
|---|---|
| a default number where the source gives none (timeout, count, limit) | the source prints an empty field; a default becomes a fact nobody can trace |
| a guessed unit, scale or normalisation (cents, 0-100, per-item) | the unit decides the result; guessing it silently changes every number |
| values edited by hand in a generated file | the next generator run reverts them and the report keeps claiming them |
| <project-specific ban> | <the date + file:line where it cost a FAIL, or delete this row> |

## How it is enforced mechanically (not by promises)
An extractor returns the missing result WITH the exact reason, never a value (example class, 3 lines):
```
class MissingValue(Exception):    # raised where the source prints no value
    pass
raise MissingValue("the source prints no execution time for this item")
```
Every such reason reaches the report, so the author sees exactly what the source lacks.
A kit project adds zero-tolerance checks under `.aw/checks.d/` (they run inside `python3 tools/aw.py integrity`):
```
# .aw/checks.d/no_placeholders.py - example, verified: ZERO -> failure, fixed -> OK
import pathlib, re
BAD = re.compile(r"\b(TBD|N/A|PLACEHOLDER)\b|,(NA|null)?$", re.M)
n = sum(len(BAD.findall(p.read_text(encoding="utf-8", errors="ignore"))) for p in pathlib.Path("out").rglob("*.csv"))
print("ZERO placeholders", n)
```
`METRIC name N` = debt ceiling (lower is better, stored in the baseline); `ZERO name N` = must stay 0.
An output that genuinely cannot be produced gets `MANUAL` + the reason, never an invented value.

## Author decisions (a decision is not an invention)
| Date | Decision (verbatim) | Applies to |
|---|---|---|
| {{DATE}} |  | all |

A dated row here stands ABOVE extraction: it is the author's decision, not a default, and the report should name it when it overrides the source.

## Boundaries
- AUTHOR decides: content, schema, thresholds, norms, signatures, money, secrets, commits, deletions.
- AGENT: transcribes verbatim, states exactly what is missing, decides nothing.

## Before any report
```
bash tools/gate.sh <T-NNN>   # or the project's TEST_CMD; the count must stay >= the ratchet floor
python3 tools/aw.py integrity
```
