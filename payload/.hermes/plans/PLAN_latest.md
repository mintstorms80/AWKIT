<!-- WRITER: ARCHITECT | APPEND-ONLY: no, living file (copy to backups/PLAN_latest.<date>.md before a big rewrite) | the LEDGER wins on conflict -->
# PLAN_latest - {{PROJECT_NAME}}  (created {{DATE}}, Author: {{OWNER}})
Map: modules + critical path MODULES.md | phases + timeline ROADMAP.md | findings AUDIT_LEDGER.md | rulings DECISIONS.md | laws + roles PLAYBOOK.md

## 1. Passport
- Goal (Author's words, <= 3 lines): <fill>
- DoD - ONE command, exact threshold: `<cmd>` => `<exact expected output>`
- Success metrics (command that measures each, else UNMEASURED): <name op value by date>
- Non-goals: <fill>
- NOT-TO-DO (habit to stop | failure it caused, with evidence): 1) <fill>

## 2. Facts (tags: DETECTED = a command printed it | DECLARED = Author said | INFERRED | ASSUMED; only DETECTED is MEASURED)
| Fact | Value | Command / source | Date | Tag |
|---|---|---|---|---|
| Stack, entry points, risky areas | <fill> | | | |
| Tests (floor) | <n> | `python3 tools/aw.py ratchet` | | DETECTED |
| Host (python, bash = git-bash not WSL) | <fill> | `python3 tools/aw.py doctor` | | |
| Git state (dirty files, HEAD) | <fill> | `git status --short` | | |

## 3. Assumptions (not facts until the command passes; then move the row to section 2)
| # | Assumption | Confirm with | Status |
|---|---|---|---|
| 1 | <fill> | `<cmd>` | OPEN |

## 4. Risks and RE-PLAN TRIGGERS (rows are appended, never renumbered)
| # | Risk | Prevention | If it happens | Re-plan when (measurable) |
|---|---|---|---|---|
| 1 | Author decision missing | one QUESTIONNAIRE batch | card BLOCKED/AUTHOR | >= 3 cards blocked on open D/Q |
| 2 | <fill> | | | |

## 5. Resources (MUST = nothing runs without it | OPT = a substitute exists; money is the Author's call)
| Resource | MUST/OPT | Scarce? | Cost / limit | If missing |
|---|---|---|---|---|
| Author (domain, money, secrets, commit) | MUST | yes | <fill> | cards BLOCKED/AUTHOR |
| Architect model | MUST | | <fill> | no new cards; queue drains |
| Worker model | MUST | | <fill> | no execution |

## 6. Queue (next <= 10 cards; history = WORKLOG + each card's Status line, the card wins)
| ID | Lane | Module | Depends | Waits for (D-NN / Q-NNN) | Status |
|---|---|---|---|---|---|
| <ID> | ROTE | M-NN | - | - | TODO |

## 7. Cadence
| When | Who | Reports | Where |
|---|---|---|---|
| each card | Worker | result line + entry | WORKLOG |
| each queue | Worker, then Architect | `QUEUE DONE` line, then ARCH-ACCEPT + row | ledger, METRICS |
| weekly | Architect to Author | done / blocked / next 3 + ONE question | HANDOFF_<date>.md |
| phase end | Architect + Author | full audit, sign-off | ROADMAP |

## 8. Open author decisions
Decided = DECISIONS.md. Open = QUESTIONS.md or QUESTIONNAIRE_<date>.md. A blocked card names its D-NN / Q-NNN; nothing else waits.
