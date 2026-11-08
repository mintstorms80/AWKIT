# CARD_LINT_RULES v1 - spec for `aw.py card-lint` (+ the card parser shared with `queue-check`)
Author: workflow-architect (brief E). Reader: engineer C. Rule ids are STABLE: never renumber, new rules append L47+.
The code block in section 3 is EXEC-ABLE and is the exact data the reference probe (`dev/card_lint_reference/lint_probe.py`) runs: copy it, do not retype it.

## 0. CLI contract
`aw.py card-lint <card.md|T-NNN|CHK-NNN|SPEC-NNN> [--strict]`  bare id => `.hermes/plans/cards/<ID>.md`; missing file => `CARD-LINT ERROR card not found: <path>` exit 2.
Output, sorted by line: `LINT ERROR|WARN <id> line <n>: <msg> -> <fix>` (msg <= 140 chars; NEVER echo secret text). LAST line `CARD-LINT OK|FAIL errors=<n> warn=<n>`.
Exit 0 iff errors==0 (and warn==0 with --strict); else 1. Read-only. Lint and queue-check call the SAME `parse_card()` and the SAME `matches()` (fnmatch) as the engine's OWNS check.
Optional context; if the file is missing the dependent rule is skipped SILENTLY: `.aw/ratchet.json` (floor), `tools/kit.env` (ALWAYS_OWNED; default = pristine list), `.aw/frozen.txt`, `.hermes/plans/{MODULES,QUESTIONS,DECISIONS,WORKLOG}.md`, sibling `cards/*.md`, pytest config.
Status PASS|ACCEPTED|OBSOLETE = history: skip L14-L20 (stale numbers are expected there). Tier M = implement by default; S = if the line budget allows. Drop order if tight: L43-L46, L39, L33, L31, L30, L29, L24, L22, L13, L09.

## 1. Parser contract (what `parse_card(text)` returns; queue-check reads the same fields)
- Normalise: BOM stripped, CRLF -> LF (L01 reports them first). Fence = line `^\s{0,3}(```+|~~~+)`; it closes on a line of the same char, >= same length, nothing else. Lines in fences are PAYLOAD.
- Sections = lines between `## ` headings (outside fences). Name = heading text before ` (`. `lane`,`status`,`depends[]`,`module`,`decisions[]` from line 2; optional line 3 `Key: value | Key: value` (keys Supersedes, Superseded by, Executor).
- `owns[]` = bullets `- <path>` of OWNS (a leading backtick span wins, else first token; strip trailing `.,;`); non-bullet lines are comments.
- Spans = `` `...` `` outside fences. Commands = spans in column 2 of table rows and in BACKUP/ROLLBACK lines + fenced lines that are not heredoc bodies and not `#` comments. Expected = column 3 of table rows.
- Table row = line starting `|`; split cells on `|` that is NOT inside a backtick span (so `` `x | tail -1` `` stays one cell); data rows need exactly 3 cells.
- Heredoc: a command containing `<<'TAG'` opens a body that ends at the line `TAG`; bodies are PAYLOAD (never scanned as commands). Opener without closing line, or inside a span => L23.
- cwd model: document order, `cd DIR` / `cd DIR &&` persists until the next `cd`; path = normpath(cwd/arg); skip any path containing `$ ( ) ` ~`.
- Write targets = `cat|tee [-a] > P`, `> P` / `>> P` (not `2>&1`, `/dev/null`), `aw.py patch P ..`, `cp|mv .. P` (last arg). Honest limit: writes done by code INSIDE a payload script are invisible to lint.
- `chain = (before, k, after, label)` from the one `CHAIN:` line of GATE: `before` = first `ran=` = base + sum of previous k (CONTRACT section 6) = the count `tools/gate.sh pre-<ID>` prints; `after` = before + k.

## 2. Rules (sev E=ERROR W=WARN; tier M/S; "->" = the failure it prevents; skill = S/ref/skill_aw-kit-orchestration.md)
| id | t | sev | detection | -> prevents |
|---|---|---|---|---|
| L01 | M | E | raw bytes: BOM, any `\r`, or invalid UTF-8 (line = first offender) | heredoc terminator `EOF\r` never matches; `python3\r` (selftest CRLF finding) |
| L02 | M | E | line 1 matches TITLE_RE; id == file stem when the stem is id-like; title >= 3 chars | worker runs a card with the wrong id; unfilled template (`T-NNN`, legend on line 1) |
| L03 | M | E | line 2 matches HEAD_RE; line 3, if it starts with a LINE3 key, parses as `Key: value` pairs (Supersedes/Superseded by = id or `-`); unknown key = W | malformed header = queue-check cannot read lane/depends |
| L04 | M | E | prefix<->lane: T=ROTE, CHK=CENSUS, SPEC=SPEC. HTML comments (`<!--`..`-->`) are inert: no rule reads them (a template legend must live there, never in `>` lines) | judgement card shipped to the cheap worker (skill: "plausible page built on invented data") |
| L05 | M | E | all 12 REQ H2 exactly once, in order (heading may carry `(...)`); optional H2 before STEPS = W | missing STOP/BACKUP = no recovery path |
| L06 | M | E | PLACEHOLDER_RE outside fences and outside DRY-RUN PROOF | `<N>`/`T-NNN` left in -> worker types it |
| L07 | M | E | OWNS has >= 1 bullet; each path project-relative, `/` only, no `..`, no drive letter, not in CATASTROPHIC; ROTE/CENSUS entry `**/*`-class = E | "closed list" violated; audit cannot prove scope |
| L08 | M | E | ROTE/CENSUS: OWNS entry overlaps NEVER_OWN => E. Overlaps FROZEN_CLASS or a line of `.aw/frozen.txt` => E unless AFTER contains `--allow <that path>` AND STOP contains `FROZEN-CHANGED`; SPEC: W | LAW-8; skill Step 6 "check what the MANIFEST freezes before queueing a tooling card" |
| L09 | S | W | ROTE: > 12 OWNS entries, or a glob matching > 10 files on disk | scope creep = top STOP reason |
| L10 | M | E | every write target (section 1) matches OWNS or ALWAYS_OWNED (use engine `matches`) | "file outside OWNS" FAIL on a card that wrote the wrong path |
| L11 | M | E | every write target not in ALWAYS_OWNED is in the `aw.py backup <ID> ..` args or in `NEW:`; `patch` targets must be in backup args; backup and NEW disjoint; backup arg outside OWNS = W | R-3; overwritten file with no backup (no `restore` possible) |
| L12 | S | E | each `aw.py patch` has exactly 3 args; OLD and NEW paths were written by an earlier heredoc/redirect in document order | `PATCH` usage error; OLD file never created |
| L13 | S | W | OLD heredoc body occurs != 1 time in the target (read with newline normalised); target missing = skip | `PATCH REFUSED: OLD occurs k times` on a correct card (skill Step 6 anchors). Caveat: an earlier card of the queue may create the anchor |
| L14 | M | E | exactly one CHAIN_RE line inside GATE; after == before + k; label MEASURED|UNMEASURED | chain arithmetic wrong -> worker STOP on correct code (skill Step 6 chain) |
| L15 | M | E | PRE-FLIGHT has a gate row (`tools/gate.sh`) expecting `GATE OK count=B min=F` with B == chain.before and F == live floor; and an integrity row expecting `INTEGRITY OK` | stale `min_tests=<then>`/`ran=<then>` stops the worker on the first line (skill Step 6; the earlier project W-26..W-35) |
| L16 | M | E | any `min_tests=N`, `min=N`, `floor N` outside fences/DRY-RUN PROOF where N != live floor; `--raise N` inside AFTER = W (floor is raised once to the queue `final=`) | templated-from-old-card numbers in COMMENT lines |
| L17 | M | E | ROTE/CENSUS tables in PRE-FLIGHT/STEPS/GATE: 3 cells, `#` = 1..n, action non-empty, Expected has a span or one of `UNMEASURED`,`record`,`none` | step with no checkable output = unverifiable (LAW compare byte for byte) |
| L18 | M | E/W | Expected token (spans, else the cell) passes iff the cell says UNMEASURED/record, or the token has NO ASCII letter and its numbers are 0 or in {before,after,k,floor}, or the token occurs verbatim in DRY-RUN PROOF (the found text, for any token that does carry letters, e.g. `INTEGRITY OK frozen=23 metrics=2`). E if Status in READY,RUNNING,REWORK; W if TODO. If DRY-RUN PROOF is absent or empty, every number is unproven (L19 already errors) | invented `4 insertions(+), 12 deletions(-)` (skill Step 4): an expected output is a measurement or a promise |
| L19 | M | E/W | Status READY|RUNNING needs DRY-RUN PROOF with >= 1 non-empty fenced block; chain label MEASURED needs `count=<after>` or `ran=<after>` in it (E); UNMEASURED with k > 0 = W | "READY = dry-run proven"; UI card "never run" came back as rework |
| L20 | M | E/W | FAMILY: approximation (`~5`, `about 5`, `+/-`) E in Expected cells, W in prose | PLAYBOOK "`~` is a smell"; the earlier project W-48 GOAL `~120` |
| L21 | M | E | FAMILY: discretion phrases in ROTE/CENSUS prose (spans removed) | "anything a worker must decide means the card is wrong" |
| L22 | S | W | FAMILY: hedge words (`maybe`, `if needed`, `etc.`) | same, softer |
| L23 | M | E | per command (not heredoc bodies, not `#` lines): `shlex.split` ValueError; unquoted heredoc `<<TAG`/`<<-TAG`; heredoc opener inside a span or with no closing line | apostrophe in single-quoted grep ends the bash string; unquoted heredoc expands `$`; skill Pitfalls (3 layers of quoting) |
| L24 | S | W | heredoc body contains a heredoc opener or `python3 - <<` | nested heredoc closes the outer one (skill Step 4) |
| L25 | M | E/W | FAMILY: irreversible commands E (`rm -r/-f`, `git push|commit|reset|clean|stash|restore|checkout --`, `rmtree`, `-delete`); plain delete W; `.py` payload deleting files W | nothing deletes user data; `git checkout` = rollback of accepted work (skill Step 8) |
| L26 | M | E | FAMILY: `--i-am-architect`, `--write-baseline`, `ratchet --raise` inside commands of PRE-FLIGHT..GATE, ROLLBACK (AFTER may carry them) | LAW-9: "no card may contain them" (skill Step 8) |
| L27 | M | E/W | FAMILY: `sed -i`/`perl -i`/`awk -i inplace` E; `echo|printf .. > file` W | LAW-4; MSYS `sed -i` corrupts regexes and exits 0 (skill Pitfalls) |
| L28 | M | E/W | FAMILY on every line outside DRY-RUN PROOF: `X:\` drive path E; `/tmp/` W | `unicodeescape` SyntaxError; MSYS rewrites paths; bash `/tmp` != Windows python `/tmp` |
| L29 | S | W | FAMILY: `.py` payload shelling out to `bash|sh`; payload printing non-ASCII (> 127 + `print(`) without `reconfigure(`/`PYTHONIOENCODING` | WSL bash.exe mojibake; cp1252 UnicodeEncodeError (skill Pitfalls) |
| L30 | S | W | command has `pytest` + `-q`/`-qq`, no `addopts=`, and project pytest config `addopts` already has `-q` | `-qq` hides the `N passed` line (skill Pitfall 1; the earlier project SELF_IMPROVE 3.5) |
| L31 | S | W | FAMILY: `grep -c '^def|^class'` | counts template strings; use `ast` (skill Pitfalls) |
| L32 | M | W | PRE-FLIGHT/GATE: `git status` row whose Expected says empty/clean/`nothing to commit` without `E0` (queue-check: E unless first card) | earlier cards leave dirty files; empty-tree assert stops a correct worker (skill Step 6/Card patterns) |
| L33 | S | E/W | FAMILY: install verbs E (`pip install`, `npm i`, `uv add`, `apt install`..); `curl|wget|git clone|http(s)://` W | INVARIANT "no new dependency"; the earlier project STOP "network/install/paid" |
| L34 | S | E/W | GOAL: empty = E; no backtick witness or > 3 lines = W | GOAL must be measurable (pristine template) |
| L35 | M | E | RED PROOF non-empty. ROTE: first line starts `n/a` + reason (>= 10 chars) OR mentions `step N` (N exists in STEPS) and `fail`. CENSUS: must start `n/a` | R-6; stated RED count was a lie when the test already passed (skill Step 6) |
| L36 | M | E | ROTE: STOP section contains `ROLLBACK` | every STOP branch names its recovery (CONTRACT) |
| L37 | M | E | ROTE: ROLLBACK section exists, has a command `aw.py restore <OWN-ID>`, expects `RESTORED`, mentions `NEW:`/`CREATED` | "aw.py has no restore" left half-applied patches (skill Step 7) |
| L38 | M | E | every id after `aw.py start|backup|restore|audit`, `gate.sh [pre-]`, `re_audit.sh [pre-]`, `gate_output/`, `backups/` equals OWN id; EVIDENCE names `gate_output/<OWN-ID>` | card templated from a neighbour keeps its id: backups/evidence land in the wrong card |
| L39 | S | W | other card ids in prose/spans not listed in Depends/Supersedes/Superseded by | same templated leftovers |
| L40 | M | E | GATE rows: gate row `tools/gate.sh <ID>` expecting `GATE OK count=<after>`; LAST row `re_audit.sh <ID>` (or `aw.py audit <ID>`) expecting `AUDIT PASS`; if its `OWNS='a,b'` is present the set == OWNS section (absent: E, or W if the engine reads OWNS from the card - see section 5 S1) | R-10; wrong OWNS env = false `OUT` FAIL |
| L41 | M | E/W | CENSUS: every OWNS entry matches `gate_output/<OWN-ID>*`; no `aw.py start|backup|patch` in a COMMAND (prose that mentions them is fine); GATE has a `git status --short` row with `E0` (E); verdict words `recommend|verdict|should be|propose` in STEPS/GATE prose = W | census = report only, no verdict (skill lane 3) |
| L42 | M | E | SPEC needs line 3 `Executor:` whose value is not worker/deepseek/cheap; ROTE/CENSUS with another Executor = E | cheap worker must never get a judgement card |
| L43 | S | E | Status READY|RUNNING and Author decisions != none: every `Q-N` lacks a line `ANSWER Q-N`, or a `D-N` is absent from DECISIONS.md => E (skip if registers missing) | blocked card dispatched before the author answered |
| L44 | S | E | Module != `-`: id is a row of MODULES.md; every OWNS entry matches an OWNS glob of that module | cross-module write; `modules` registry bypassed |
| L45 | S | E/W | Depends contains own id = E; unknown id (no card file, no WORKLOG `## <ID> |`) = W | dependency typo |
| L46 | S | E | Status OBSOLETE: prelude line `^OBSOLETE` (+ reason >= 10 chars when Superseded by is `-`) and `Superseded by:`; `Supersedes: X` => card X exists and is OBSOLETE; `Superseded by: Y` => Y exists | two runnable files for one job (skill Step 7) |
| L47 | M | E | ROTE/CENSUS: a fenced shell block (bash, sh, shell, console) outside DRY-RUN PROOF has a line with a standalone `&` (whitespace or the line edge on both sides; `&&`, `>&` and `&>` do not count); reported per line | the Hermes terminal refuses a foreground command with a standalone `&` and, under LAW-3 (`timeout` in front of `cat`), scans a heredoc body too: the worker improvises a write method (measured with the terminal guard itself). Engine only since 2.7.2: `dev/card_lint_reference` implements L01-L46 |

## 3. SPEC_DATA (exec-able Python; scopes: prose = non-fence lines of GOAL..ROLLBACK with spans blanked | cmd | exp | body = heredoc/fence payload (ext = target suffix) | all = every line except DRY-RUN PROOF; lanes R=ROTE C=CENSUS S=SPEC)
```python
import re
ID = r"(?:T|CHK|SPEC)-\d{3,5}"
IDS = rf"{ID}(?:\s*,\s*{ID})*"
QD = r"(?:D-\d{2,4}|Q-\d{3,4})"
TITLE_RE = re.compile(rf"^# ({ID}) [\u2014\u2013-] (\S.*)$")
HEAD_RE = re.compile(
    rf"^Status: (TODO|READY|RUNNING|PASS|FAIL|STOP|ACCEPTED|REWORK|OBSOLETE) \| Lane: (ROTE|CENSUS|SPEC) \| "
    rf"Depends: (-|{IDS}) \| Module: (-|M-\d{{2,3}}) \| Author decisions needed: (none|{QD}(?:\s*[,/]\s*{QD})*)\s*$")
LINE3_KEYS = ("Supersedes", "Superseded by", "Executor")
REQ = ["GOAL", "OWNS", "READ-ONLY", "PRE-FLIGHT", "BACKUP", "STEPS", "RED PROOF", "GATE", "INVARIANTS", "STOP", "EVIDENCE", "AFTER"]
H2_RE = re.compile(r"^## ([A-Z][A-Z -]*?)(?: \(.*\))?\s*$")
CHAIN_RE = re.compile(r"^CHAIN: ran=(\d+) \+(\d+) -> ran=(\d+) \((MEASURED|UNMEASURED)\)\s*$")
HIST = {"PASS", "ACCEPTED", "OBSOLETE"}
PLACEHOLDER_RE = re.compile(r"<[A-Z][A-Z0-9 +_/|-]*>|\b(?:T|CHK|SPEC)-NNN\b|\bTODO\b|\bTBD\b|\bFIXME\b|\?\?\?")
CATASTROPHIC = {"*", "**", "**/*", ".", "./", "./**", "/"}
NEVER_OWN = ["tools/aw.py", "tools/gate.sh", "tools/re_audit.sh", "tools/worker_report.py", "tools/kit.env", ".aw/*", ".hermes/prompts/*",
    "AGENTS.md", ".hermes/plans/TASK_CARD.template.md", ".hermes/plans/AUDIT_LEDGER.md", ".hermes/plans/PLAN_latest.md",
    ".hermes/plans/MODULES.md", ".hermes/plans/ROADMAP.md", ".hermes/plans/PLAYBOOK.md", ".hermes/plans/CARD_PATTERNS.md",
    ".hermes/plans/START_BLOCKS.md", ".hermes/plans/GUIDE.md", ".hermes/plans/ARCHITECT_FEEDBACK.md", ".hermes/plans/PROPOSALS.md",
    ".hermes/plans/METRICS.md", ".hermes/plans/DECISIONS.md", ".hermes/plans/cards/*", ".env", ".env.*", "*.pem", "*.key", "id_rsa*",
    "auth.json", "credentials.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "Cargo.lock", "uv.lock", "poetry.lock"]
FROZEN_CLASS = ["tools/*"]   # CONTRACT E3 implicit frozen core, plus every line of .aw/frozen.txt
DISC = (r"as you see fit|at your discretion|your (?:best )?judg(?:e)?ment|you (?:may|can|should|must) (?:decide|choose|pick)|"
        r"decide (?:whether|if|which|how)|choose (?:between|one|the)|pick (?:one|the)|whichever|feel free|"
        r"if you (?:think|feel|prefer|want|like|see)|use (?:common )?sense|adapt (?:as|it|to)|do whatever|"
        r"по твоя преценка|ако прецениш|както сметнеш|по твое усмотрение")
SOFT = r"\b(?:maybe|perhaps|probably|possibly|somehow|something like|or similar|and so on|etc\.?|if needed|if necessary|as needed|as appropriate|optionally|try to|might)\b"
APPROX = r"~\s*\d|\u2248|\b(?:about|approx\w*|roughly|around|circa)\b\s+~?\d|\d\s*(?:\+/-|\u00b1)|(?:около|приблизително)\s+\d"
DESTR = (r"\brm\s+(?:-[a-zA-Z]*[rRfF][a-zA-Z]*|--recursive|--force)\b|\bgit\s+(?:push|commit|reset|clean|stash|rebase|restore|filter-branch|checkout\s+--)\b|"
         r"\bshutil\.rmtree\b|Remove-Item\b.*-Recurse|\brmdir\s+/s|\bdel\s+/[sS]|\bfind\b.*\s-delete\b")
PLAINDEL = r"\brm\s+[^-\s]|\bdel\s+[^/\s]|\bos\.(?:remove|unlink)\(|\.unlink\("
PYDEL = r"shutil\.rmtree|os\.(?:remove|unlink|rmdir)\(|\.unlink\(|\.rmdir\("
ARCHF = r"--i-am-architect|--write-baseline|\bratchet\s+--raise|--raise\s+\d+"
SEDI = r"\bsed\s+(?:-[a-zA-Z]*i\b|--in-place)|\bperl\s+-[a-zA-Z]*i\b|\bawk\s+-i\s+inplace"
ECHOW = r"\b(?:echo|printf)\b[^|<>\n]*>{1,2}\s*(?!&|/dev/null|\S*gate_output)\S+"
WINP = r"(?<![A-Za-z0-9])[A-Za-z]:\\"
TMPP = r"(?<![\w.:/-])/tmp/"
BASHPY = r"subprocess\.\w+\(\s*[\[(]?\s*[\"'](?:bash|sh)[\"']|os\.system\(\s*[\"'](?:bash|sh)\b"
GREPC = r"\bgrep\s+-[A-Za-z]*c[A-Za-z]*\s+[\"']\^\s*(?:def|class)\b"
INSTALL = (r"\b(?:pip3?|uv\s+pip|npm|pnpm|yarn)\s+(?:install|add|i)\b|\buv\s+add\b|\bcargo\s+install\b|\bgo\s+get\b|"
           r"\b(?:apt(?:-get)?|winget|choco|brew)\s+install\b")
NET = r"\b(?:curl|wget)\b|\bgit\s+(?:clone|fetch|pull)\b|Invoke-WebRequest|https?://"
FAMILY = [  # (id, sev, scope, lanes, ext, regex, message)
 ("L20", "E", "exp",   "RCS", None,  APPROX,   "approximate number in an expected output -> measure it or write UNMEASURED"),
 ("L20", "W", "prose", "RCS", None,  APPROX,   "approximate number -> exact or UNMEASURED"),
 ("L21", "E", "prose", "RC",  None,  DISC,     "worker must not decide -> make it a pre-flight assert or a Q-NNN"),
 ("L22", "W", "prose", "RC",  None,  SOFT,     "hedge word -> exact instruction"),
 ("L25", "E", "cmd",   "RC",  None,  DESTR,    "irreversible command -> mv to _to_delete/ or architect act"),
 ("L25", "W", "cmd",   "RC",  None,  PLAINDEL, "deletes data -> mv to _to_delete/"),
 ("L25", "W", "body",  "RC",  ".py", PYDEL,    "payload deletes files -> move to _to_delete/"),
 ("L26", "E", "cmd",   "RC",  None,  ARCHF,    "architect-only flag in a worker command -> architect runs it (AFTER)"),
 ("L27", "E", "cmd",   "RC",  None,  SEDI,     "in-place edit (LAW-4) -> quoted heredoc or aw.py patch"),
 ("L27", "W", "cmd",   "RC",  None,  ECHOW,    "echo/printf write -> quoted heredoc"),
 ("L28", "E", "all",   "RCS", None,  WINP,     "Windows drive path -> use C:/ forward slashes or a relative path"),
 ("L28", "W", "all",   "RCS", None,  TMPP,     "/tmp differs between bash and Windows python -> use gate_output/"),
 ("L29", "W", "body",  "RC",  ".py", BASHPY,   "payload shells out to bash (WSL on Windows) -> run it from the card step"),
 ("L31", "W", "cmd",   "RC",  None,  GREPC,    "grep -c on def/class lies in template strings -> ast"),
 ("L33", "E", "cmd",   "RC",  None,  INSTALL,  "install = new dependency -> author decision (Q-NNN)"),
 ("L33", "W", "cmd",   "RC",  None,  NET,      "network command -> only if the card needs it; else remove"),
]
```

## 4. Queue-level rules (`queue-check`, same parser; Chain grammar is CONTRACT section 6)
| id | sev | detection |
|---|---|---|
| Q01 | E | exactly one `Chain: base=<int> \| <ID>:+<int> ... \| final=<int>` line; base >= live floor; final == base + sum(k); last line of the queue file says `QUEUE DONE <n PASS> / <n FAIL> / <n STOP>` (W if absent) |
| Q02 | E | every Chain id has `cards/<ID>.md`, lints with errors=0 (warns are listed), ids unique |
| Q03 | E | card i: chain.before == base + sum(k of cards < i) and chain.k == the Chain `+k` |
| Q04 | E | no card with Status OBSOLETE, PASS, ACCEPTED, FAIL or STOP in the queue; TODO/RUNNING = W "not dry-run proven" |
| Q05 | E | no SPEC card in the queue (the cheap worker never receives a judgement card) |
| Q06 | E | every `Depends` id is earlier in the Chain or already ACCEPTED/PASS in WORKLOG |
| Q07 | E | OWNS of card i overlaps OWNS of an earlier card j (fnmatch either way, or one path prefix contains the other) but i does not list j (or a card depending on j) in Depends: declare it, so the FAIL rule "dependent => stop, independent => continue" is mechanical |
| Q08 | E | L32 pattern (empty `git status` assert) in any card but the first |
| Q09 | W | MODULES.md present: card Module wave goes backwards along the Chain without a Depends edge |

## 5. Suggestions to the engine owner (not rules)
- S1: `audit T-NNN` reads OWNS from `cards/<ID>.md` when env `OWNS` is unset: removes the OWNS-env typo class and one line of every card. Then L40 turns the `OWNS=` absence into W.
- S2: put `.hermes/plans/cards/**` into the implicit frozen core (E3) so a worker that "fixes the card to match what it did" trips FROZEN-CHANGED. Decision belongs to security-architect.
- S3: `restore T-NNN` should print `NOT-RESTORED-NEW <path>` for files changed since `task-start` that have no backup, so the ROLLBACK step can list `CREATED <path>` mechanically.
- Template guard: the unfilled `TASK_CARD.template.md` MUST fail card-lint (L02 line 1 is its legend, L06 placeholders). selftest should assert it.

## 6. Validation (dev/card_lint_reference/lint_probe.py, run 2026-10-30)
Probe reproduces the rules from THIS file (it `exec`s section 3 on every run: the bytes tested are the bytes above).
```
$ python3 dev/card_lint_reference/lint_probe.py selftest
  fixture T-043: errors=0
  fixture T-044: errors=0
  fixture CHK-007: errors=0
  fixture SPEC-002: errors=0
  unfilled template fires 6 rules incl L02=True
SELFTEST PASS fixtures=4 mutants=39
$ python3 lint_probe.py legacy <the earlier project card> --root <the earlier project project root>     # content-only pass (v1 header is a known gap)
K-9a_dryrun              CONTENT-RULES-FIRED ['L35', 'L36', 'L37'] (structural: ['L02'])
W-13_guard_whisper       CONTENT-RULES-FIRED ['L35', 'L36', 'L37'] (structural: ['L02'])
W-43_http_routes_tests   CONTENT-RULES-FIRED ['L35', 'L36', 'L37'] (structural: ['L02', 'L03'])
W-46_open_ledger_rows    CONTENT-RULES-FIRED ['L35', 'L36', 'L37'] (structural: ['L02', 'L03'])
W-36_ruff_alignment      CONTENT-RULES-FIRED ['L35', 'L36', 'L37'] (structural: ['L02', 'L03'])
W-48_durations           CONTENT-RULES-FIRED ['L20', 'L35', 'L36', 'L37'] (structural: ['L02', 'L03'])
```
The four true findings on real cards: no `RED PROOF` section (L35), `STOP` never names the recovery command (L36), no `ROLLBACK` section because `aw.py` had no `restore` (L37), and `~120` in a GOAL (L20). Structural L02/L03 on every v1 card is the expected migration gap, not a defect to fix in the old files.
Parser lessons the probe paid for (implement them, they are not academic):
1. A closing fence may carry trailing whitespace, and a heading may sit on the line a fence closes on: collect headings over ALL lines, then subtract fence lines from section prose.
2. Buffer adjacent headings: two `## X` in a row must not swallow the first section.
3. A heredoc body outlives the fence that opens it; compute body ranges per fenced block, and never treat a body line as a command.
4. `matches()` must be the engine's own fnmatch so lint and `audit` agree; a private path matcher drifts.
5. Table cells: split on `|` outside backtick spans, else every command containing `| tail -1` breaks the row.

