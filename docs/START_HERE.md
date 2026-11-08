# Working with the kit — the short version

> Easiest (Windows): put the `awkit` folder INSIDE your project folder, double-click `awkit\new_project.cmd`, write your idea in `IDEA.md`, double-click `START_ARCHITECT.cmd`. No commands. The first time, the Architect writes a questionnaire instead of a plan: your own sentences as you wrote them, plus its elaboration. You answer with letters in the chat; only then does it write the plan.

**The idea.** Two models work in shifts. The ARCHITECT (strong model) plans and writes cards: exact instructions, one command per line. The WORKER (cheap model) executes a card letter by letter. "Done" is not said by a model but by the tests: `GATE OK count=N` and `AUDIT PASS`. You decide only domain content, money, keys and commits.

## Once per project
1. **Install.** `python3 init_project.py <folder> --name <Name> --lang en --owner "<Owner>"`. It never overwrites your files (collisions go to `kit_stage/`).
2. **Check the environment.** In the project folder: `python3 -I -B tools/aw.py doctor`. You want `DOCTOR PASS`; warnings are allowed.
3. **Architect, first run.** Open the project in the strong model's profile, paste BLOCK 0 from `.hermes/plans/START_BLOCKS.md`. It measures the tests, freezes what must not be touched, writes the first audit, the plan, the modules and the first `QUEUE_<date>.md`. When it needs a decision from you it writes a question to `.hermes/plans/QUESTIONS.md`.
4. **Dry run of the worker.** In the worker profile, paste BLOCK 1. It must print `PASS T-DRY1` and stop with `STOPPED` on T-DRY2. That is how you know it stops when it must.
5. **First commit.** Yours only, before real work starts.

## Every round
| Where | What you paste | What you see at the end |
|---|---|---|
| Worker | the START BLOCK of `QUEUE_<date>.md` (BLOCK Q) | last line `QUEUE DONE <n PASS> / <n FAIL> / <n STOP>` |
| Architect | BLOCK A (audit) | 3 MEASURED/UNMEASURED bullets, the file paths, ONE question for you |
| Architect | new goal: `/plan-synth <goal>`; many modules: `/plan-project <project> :: module1, module2` | new cards `T-NNN` and a new queue, checked with `card-lint` and `queue-check` |

A model asks a question? You answer: `python3 -I -B tools/aw.py answer Q-001 "text"`.

## When something is wrong
- The worker stopped or broke: worker profile, BLOCK R. It shows three things and does exactly one of three.
- You suspect a forbidden edit: `python3 -I -B tools/aw.py integrity` (names the protected file that differs).
- Big picture: `python3 -I -B tools/aw.py report`, then read `.hermes/plans/REPORT_latest.md` (up to 60 lines).
- You tell the Architect "fix it": BLOCK X (applies, measures and closes the round).

## Effort: medium by default, ultra when it pays
Double-clicking `START_ARCHITECT.cmd` or `START_WORKER.cmd` picks the level itself (`tools/effort.py`): ultra for a plan and cards, for a broken card and for a SPEC card, medium otherwise. The worker is always ultra: in 12 pilot runs medium finished 5 queues of 6, ultra 6 of 6 (a small difference, not proof), the wall time is in the same order, and the cheap worker does not spend your subscription. In an already open chat the kit cannot change the level itself (Hermes has no such command): the Architect says in ONE line what to do and stops — either run `START_ARCHITECT.cmd` again, or type `/reasoning ultra` and then `Session effort: ultra`.

## What you do NOT do
You do not write code or cards. You do not touch `.aw/`, `tools/`, `.hermes/prompts/`. You do not accept "done" without `GATE OK`. You do not tell the worker "try again": it tries once and asks.

## Honest
The kit catches mistakes and drift; it is not a defence against a malicious model. `card-lint` checks part of the rules (23 of 39 reference errors), so the real check is the dry run of the card. Everything in detail: `docs/GUIDE.en.md`; the limits: `docs/HONEST_LIMITS.md`.
