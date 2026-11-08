# CARD_PATTERNS v2 — architect's craft catalogue (model-agnostic)
Each line: an instruction, then the failure it prevents. Each was paid for on a real repo.

## 1. Dry-run protocol (a failure here lands as a worker STOP, not a card bug)
1. **Run the card's own bytes, then lint**: `aw.py card-lint <ID>` must print `CARD-LINT OK`; placeholders, stale numbers and unprotected writes are caught before dispatch. **Replay the GATE rows too (`re_audit.sh` included)**: skipping them leaves the whole card UNPROVEN.
2. **Heredoc payload**: extract every `cat > P <<'TAG'` block, write it to a scratch dir, run it there.
3. **Patch anchors**: for each `aw.py patch F OLD NEW`, count OLD in F (line endings normalised). `0` = drift, `2` = not an anchor. -> `PATCH REFUSED: OLD occurs k times` on a correct card.
4. **Whole-queue round trip** (>=2 dependent cards): copy the tree, per card write its heredocs, expect that card's RED, run its apply, expect GREEN, once at the end run the neighbour suites.
5. **Self-execute on a committed tree**: when everything the cards touch is committed, the real tree IS the clean copy. Run each card, then `git checkout -- <patched files>` and `rm` the scratch files; prove restoration with `git status --short`. Never when a touched file is uncommitted: that is a rollback of accepted work.
6. **Full-gate calibration**: run the whole suite once with the new modules in place and read the real `ran=`; per-card counts are arithmetic, the total is a measurement. -> a chain built on hope stops at card two.
7. **Characterization cards**: author the test in scratch, run it there, embed the exact bytes, and require GREEN on the first run. A RED there means the module changed after you read it.
8. **Census/report cards**: replay the card's own script on the live tree, keep its last line as the expected line, then DELETE the artifact the replay produced. -> a dirty tree makes every later "tree unchanged" assert fail.
9. **Record the proof** in `## DRY-RUN PROOF` and set `Status: READY`; without it the card is TODO and its numbers are promises.

## 2. Card ids (never reuse, never guess)
- Take the next id from the **union** of WORKLOG, AUDIT_LEDGER, QUESTIONS, DECISIONS, PROPOSALS, ARCHITECT_FEEDBACK, `cards/*.md` names and `gate_output/*` names: `aw.py next-id T`. -> a WORKLOG-only scan re-issues an id that exists only as a gate file.
- An id committed with an earlier queue but never run is still taken: `ls cards/` + `git ls-files cards | wc -l`. -> writing that card again silently replaces tracked bytes.
- After any collision, record a `CORRECTION:` sentence in a NEW ledger block; never edit the row that named the collision.
- Prefix picks the lane: `T-` ROTE, `CHK-` CENSUS, `SPEC-` SPEC. queue-check rejects a SPEC card.

## 3. Lanes and executors
| Lane | Executor | May contain | Must not contain |
|---|---|---|---|
| ROTE | cheap worker | exact bytes, one command per row, assert-once patches, RED first | judgement words, choices, protected paths |
| CENSUS | cheap worker | one `gate_output/<ID>.md` report, verbatim greps/dumps, "different number => record it" | verdicts, patches, backup/start, design proposals |
| SPEC | strong model, separate session | judgement, layout, wording, reference beside current state | the same session as the rote queue |
A judgement card handed to a cheap worker returns a plausible page built on invented data. Name the executor on line 3.

## 4. Recurring card shapes
- **Characterization**: no patch; tests pin CURRENT behaviour; `n/a - must pass first run; failure => STOP, never edit the test`; a docstring mismatch is a ledger finding, not a code change.
- **Census**: `file:line name(args) N lines` + a 4-line window; deliverable is the report; total is a witness, not an assert.
- **Lint per FILE, never per rule**: the rule, the exact line list, "fix from the LAST line upward", gate on that file's linter alone. -> line numbers shift mid-card and the worker edits the wrong line.
- **Fix with residual**: quote the post-fix residual, not the repair count; a cascade (`54 fixed` for 50 findings) is normal. Exclude files other tests PIN (`sha256`/`REFERENCE_*`) by name and state their residual.
- **Relocate, never delete**: move to `_to_delete/`, print `KEEP` for non-qualifying files, assert no name collision, end `moved <n> kept <m>`. Nothing in the kit deletes user data.
- **Guard that removes a feature = two-direction test**: unset => zero calls, flag on => the calls return. -> a later `return` deletes the feature and the suite stays green.
- **Bounded cache**: first test asserts the defect as a number (`len(...) <= ring_capacity`), the fix reuses the parameter that already exists, second test proves a resend is still accepted.
- **Narrow, do not widen**: when a step cannot reach its expected output inside OWNS, relax the card to record the measured lines (option B). Touching a config outside OWNS is another card and an owner-visible change.

## 5. Chain and ratchet arithmetic
- `CHAIN: ran=<B> +<k> -> ran=<B+k> (MEASURED|UNMEASURED)`; `<B>` = the count the card's PRE-FLIGHT gate prints. The queue's `Chain:` line carries `base`, each `+k`, and `final = base + sum(k)`.
- A dependent card's pre-flight asserts the count the predecessor WILL have produced, and says where it came from ("T-043 must show ran=607 in WORKLOG, else STOP").
- The worker never raises the floor; the architect raises it ONCE to `final` after the whole queue PASSes. Raising between cards makes an unattended queue stop on correct code.
- Every +k must be measured on a dry run, not added up; the batch total comes from one real full-gate run.
- Re-measure an old card before it enters a queue: `min_tests=<then>`, `min=<then>`, `ran=<then>` and `--raise <then>` all go stale. card-lint L15/L16 catches them; a queue-check catches the rest.

## 6. Author decisions
- Batch every open question into ONE questionnaire; 2-3 lettered options, the printed evidence under each, one signature question, and a `## What is NOT asked here` list. -> a chain of chat questions loses the answer trail.
- Record answers in `AUTHOR_ANSWERS_<date>.md` (Q | answer | consequence) BEFORE any card moves, then ledger + feedback + proposals + metrics in one batch.
- An answer that reverses an earlier ruling: grep the old ruling across cards and plan in the same session and patch every line that says the opposite. -> a card keeps encoding the withdrawn decision and the worker STOPs on it.
- An answer that orders invented content is refused: log `BLOCKED/AUTHOR` with the printed evidence and name what would unblock it. A placeholder is the failure the project exists to prevent.
- An answer that needs a field or table that does not exist is a `P-NN` proposal + design, never a default value.
- A partial answer stays OPEN and names the missing half. Chat confirmation is not a signature.

## 7. Supersede, never duplicate
- A replacement goes under the NEXT free id; the old card gets `Status: OBSOLETE`, the line `OBSOLETE - do not run it`, and `Superseded by: <new id>`; the new card carries `Supersedes: <old id>`; the ledger records the swap.
- A withdrawn card gets the same marker plus the reason, even when nothing replaces it. -> two runnable files for one job and the worker runs whichever the queue lists first.
- A FAILed card is closed by a decision + a NEW queue that names the old one and says what changed; the old card gets a dated `REVISION`, its steps are never silently rewritten.

## 8. Host pitfalls that burned cards (git-bash on Windows)
- **Apostrophe inside a single-quoted grep ends the bash string** while earlier lines still print and the exit code lies: use `.` in the pattern or double quotes, then re-run the anchor dry-run.
- **Three quoting layers mangle escapes**: build CRLF as `chr(13)+chr(10)`; keep a generator in ONE `write_file`'d `.py`, never a Python heredoc inside a bash heredoc.
- **`bash` from Python = WSL** (`C:\Windows\System32\bash.exe`): run gates from the shell tool, let Python only edit files.
- **`sed -i` on MSYS eats `\s`/`\b`** and writes a corrupted regex that still compiles: edit with Python `assert count == 1`, then print the line.
- **`/tmp` from bash != `/tmp` from native Python**: pass `C:/...` or a project-relative path; `$(cygpath -m "$TMPDIR")` for scratch dirs.
- **cp1252 stdout kills Cyrillic/arrows**: `sys.stdout.reconfigure(encoding="utf-8")` in every script that prints owner text or UI strings.
- **`pytest -q` when `addopts` already has `-q` → `-qq`** hides `N passed`: run bare, or `-o addopts=`.
- **Host `PYTHONPATH` shadows the venv** (`count=0 reason=exit=4`): the engine drops it for gate and checks; a card never works around it.
- **A heredoc, `|` or `>` inside a table cell** breaks the row: payloads live in a fenced block below the table.
- **A Windows path literal in a Python payload dies at import** (`unicodeescape`): forward slashes or `os.sep`, never repaired with `sed`.

## Deepen before you card (deeper, not bigger)
A SPEC card's Context answers four lines, else it is not ready: (1) what a top professional would add that the Author did not ask for; (2) the rawest source to start from (the file or log, not a summary of it); (3) the command or tool that measures it; (4) what OTHER than the worker and you shows it is right (a `.aw/checks.d` check, a gate count, a diff against the source). Without line 4 the gate grades its own author. Scope never grows: a deeper card stays one card. (Adapted from the be-ambitious skill, DannyMac180/skills, MIT.)

## Failure and refusal
- A card that FAILs once gets a corrected card, never an unchanged re-send; twice means the lane was wrong: re-lane (ROTE -> SPEC) or split it; a third FAIL means the design is wrong: STOP, a QUESTION with options, no fourth attempt (`learn.py`: `third-fail`). Repetition is evidence of misclassification.
- A PASS that lists no changed file on a ROTE card is a refusal, not a success (`learn.py`: `empty-pass`).
- A worker that cannot run (tool missing, denied, timeout) says so and STOPs; the Architect decides. Nobody quietly substitutes another route or cost. (Adapted from fable-advisor, MIT.)
- Defer only when BLOCKED: impossible here, needs infrastructure that does not exist, or breaks a stated invariant. Name which, with the command that proved it ("harder than expected" is no blocker); cutting scope is the Author's call, never a quiet worker cut.
- A search with no hit proves only that search: an absence claim names the command and its scope. (Both lines adapted from vercel-labs/agent-desktop AGENTS.md and technical-writer skill, Apache-2.0.)

## Bug cards (a loop before a theory)
- A bug card names ONE red-capable command the Architect already ran (output under DRY-RUN PROOF): it asserts the user's exact symptom, gives the same verdict every run, finishes in seconds, needs no human. No such command = no card: a QUESTION asks for the artifact or the environment. Reading code to build a theory first is the failure this prevents.
- Shrink the repro until every remaining element is load-bearing; it becomes the regression test. Write that test before the fix only at a seam where the real bug pattern occurs; no such seam is itself a finding (AUD row). Prove the test: revert the fix, it MUST fail, restore. (obra/superpowers, MIT)
- 3-5 ranked hypotheses, each with a falsifiable prediction, before any probe. Every debug print is tagged `[DEBUG-<hex>]`; `checks.d/example_debug_tags.py.disabled` makes leftovers a ZERO. The cause that turned out right goes in the WORKLOG entry. (Adapted from mattpocock/skills diagnosing-bugs, MIT.)

## Slice vertically
A card cuts one narrow path through every layer (schema, API, UI, test) and is verifiable alone; a one-layer card cannot land green. A wide refactor (one mechanical change fanning over thousands of call sites) is the exception: expand (new form beside the old), migrate callers in cards, contract (remove the old) last. Name each card's blockers; start with a card whose blockers are all done. (mattpocock/skills to-tickets, MIT.)

## Write for the worker
Each step ends on a checkable, exhaustive criterion ("every file in OWNS listed", not "a list"). State the target positively: a ban drags the banned thing into context ("write one-line comments", not "never long ones"); a hard NEVER keeps its positive twin. A sentence that does not change what the worker does is a no-op: delete it. Say a fact once; do not copy what a command prints. (mattpocock/skills writing-for-agents, MIT.)
Cold read before shipping: give a fresh analyst ONLY the card; ask which files it touches, which commands it runs, what it does when each GATE row fails. An answer that differs from your intent is a card defect; ship when a cold reader answers all three right. (anthropics/skills doc-coauthoring, Apache-2.0)
Pre-mortem before BLOCK Q: assume the queue FAILED tomorrow and name the 3 likeliest causes; each becomes a PRE-FLIGHT row or is dropped with a reason. (ckelsoe/prompt-architect, MIT)
