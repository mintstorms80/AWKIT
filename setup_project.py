#!/usr/bin/env python3
"""setup_project.py - ONE-STEP install. Put the awkit folder INSIDE the project, double-click new_project.cmd.
Name = project folder name, owner = git user.name (else Windows user). Never overwrites (init_project.py stages collisions).
Does: install payload, unittest test runner, seed test, .gitignore, git init (NO commit), gate baseline, ratchet, integrity baseline, doctor."""
import os, re, subprocess, sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
lang = "en" if "--en" in sys.argv else "bg"
target = Path(args[0]).resolve() if args else KIT.parent
name = args[1] if len(args) > 1 else target.name
env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
env["PYTHONUTF8"] = "1"


def run(cmd, **kw):
    r = subprocess.run(cmd, cwd=target, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    return r.returncode, (r.stdout + r.stderr).strip()


def owner():
    try:
        o = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
    except OSError:
        o = ""
    return o or os.environ.get("USERNAME") or os.environ.get("USER") or "Owner"


def aw(*a):
    return run([sys.executable, "-I", "-B", "tools/aw.py", *a])


if target == KIT:
    sys.exit("ERROR: target is the awkit folder itself. Put awkit INSIDE your project folder and run it from there.")
own = owner()
print(f"PROJECT={name}  OWNER={own}  TARGET={target}  LANG={lang}")
if (target / "tools" / "aw.py").exists():
    print("ALREADY INSTALLED - nothing overwritten. Health check:")
    print(aw("doctor")[1])
    sys.exit(0)

rc, out = run([sys.executable, str(KIT / "init_project.py"), str(target), "--name", name, "--lang", lang, "--owner", own])
print(out.splitlines()[0] if out else "")
if rc:
    sys.exit(out)

# test runner: unittest ships with Python (pytest may be missing); a seed test keeps the gate from failing on 0 tests
ke = target / "tools" / "kit.env"
t = ke.read_text(encoding="utf-8")
t = re.sub(r"(?m)^TEST_CMD=.*$", "TEST_CMD=python3 -B -m unittest discover -s tests -t . -v", t)
t = re.sub(r"(?m)^COUNT_REGEX=.*$", lambda m: r"COUNT_REGEX=Ran (\d+) tests?", t)
ke.write_text(t, encoding="utf-8", newline="\n")
(target / "tests").mkdir(exist_ok=True)
for f, body in (("__init__.py", ""), ("test_smoke.py", "import sys\nimport unittest\n\n\nclass Smoke(unittest.TestCase):\n    def test_python_version(self):\n        self.assertGreaterEqual(sys.version_info[:2], (3, 9))\n")):
    p = target / "tests" / f
    if not p.exists():
        p.write_text(body, encoding="utf-8", newline="\n")
# the auto-start: IDEA.md (owner's words) + the prompt the architect receives + the launcher in the project root
idea = target / "IDEA.md"
if not idea.exists():
    idea.write_text("# IDEA - write here, in your own words, what the project must do (3-10 lines). Then double-click START_ARCHITECT.cmd\n", encoding="utf-8", newline="\n")
(target / ".hermes" / "START_PROMPT.md").write_text("""# START_PROMPT (written by setup_project.py; the Architect reads it as its first task)
You are the ARCHITECT for this project. Reply, and write every file the owner will read (QUESTIONNAIRE_*.md, the plan), in the language of the owner's sentences in IDEA.md, not of its template header. Keep ids, paths, commands and the tags DECLARED / INFERRED / MISSING / MEASURED / UNMEASURED in Latin.
1. Session start: `python3 -I -B tools/aw.py doctor`, then `report`; read .hermes/prompts/ARCHITECT.md and .hermes/plans/PLAYBOOK.md once.
2. Read IDEA.md. If it holds only the template header (no idea), STOP and ask the owner ONE question: what should the project do?
3. STAGE by FILES, never by chat (QUESTIONNAIRE_*.md and AUTHOR_ANSWERS_*.md in .hermes/plans/):
   a) no QUESTIONNAIRE_*.md yet -> STAGE 1. Load skill plan-ambitious and run ONLY its steps 0-2 for the goal = the text of IDEA.md (never run the project). Write ONE QUESTIONNAIRE_<date>.md from QUESTIONNAIRE.template.md: section "Owner's words" = the sentences of IDEA.md VERBATIM with their line numbers (DECLARED); section "Elaboration" = the AMBITION BRIEF you printed, line by line (Field, Beyond-goal, Types, Raw material, Methods, Ladder, Judge, Gate, Stretch, Crew, Needs, ROUTE), each tagged DECLARED (IDEA.md quote + line only), INFERRED (+ reason; your own choices are INFERRED) or MISSING; a number, name or fact that is not in IDEA.md and was not printed by a command is INFERRED or MISSING, never stated as a fact; then one lettered question per INFERRED/MISSING item that changes scope, stack, DoD or money. Re-read the file once: every number or claim that IDEA.md does not contain and no command printed gets UNMEASURED, or is deleted. Write NO plan file, NO MODULES row, NO card; never edit IDEA.md. STOP: print the lettered questions in your reply; when the owner answers them in chat, FIRST record the letters as typed in AUTHOR_ANSWERS_<date>.md (template AUTHOR_ANSWERS.template.md), then do STAGE 2 (after the effort gate, item 4).
   b) a QUESTIONNAIRE_*.md and no newer AUTHOR_ANSWERS_*.md -> STOP and list the open questions; do NOT edit QUESTIONNAIRE_*.md.
   c) both, the answers newer -> STAGE 2: plan in KIT MODE (skill plan-project): fill PLAN_latest.md, MODULES.md (check: `aw.py modules`), ROADMAP.md. PLAN_latest.md Goal = the owner's words; an INFERRED item, or a promise the owner never answered, enters only if the answers confirmed it.
4. (stage 2 only) EFFORT GATE, before ANY plan file or card: run `python3 -I -B tools/effort.py stage`. Its level HIGHER than the `Session effort:` in your first message (ladder: none < minimal < low < medium < high < xhigh < max < ultra) = write NOTHING and end your turn with ONE line to the owner: double-click START_ARCHITECT.cmd again (it starts stage 2 at that level), or type `/reasoning <level>` and then send `Session effort: <level>`. A later owner message with a `Session effort:` line replaces the one in your first message. No such line at all = the level is unknown: say so in one line and go on.
5. (stage 2 only) Write the first cards (ids from `aw.py next-id T`), RUN each card's own bytes in a scratch copy, paste the output under DRY-RUN PROOF, then `card-lint <ID> --strict` and `queue-check` on the QUEUE.
6. Anything that is the owner's decision (domain content, money, secrets, commits) becomes ONE questionnaire, not a guess.
7. Never commit, push or delete. End with the output shape from ARCHITECT.md and the queue START BLOCK to paste into the worker.
""", encoding="utf-8", newline="\n")
START_PLAN_PROMPT_TEXT = """# START_PLAN_PROMPT (written by setup_project.py; the plan/accept Architect start reads it as its first task)
You are the ARCHITECT in PLAN and ACCEPT mode (fleet/roles.md, D-06/D-09). Never write a task card (`cards/<ID>.md`) or a queue (`cards/QUEUE_*.md`) in this session; card authoring and dry-runs belong to `START_ARCHITECT.cmd`.
1. Session start: `python3 -I -B tools/aw.py doctor`, then `report`; read `AGENTS.md` whole, `.hermes/prompts/ARCHITECT.md` and `.hermes/plans/PLAYBOOK.md` once.
2. Check `python3 -I -B tools/effort.py stage` against `Session effort:` (PLAYBOOK section 12).
3. If a worker queue finished (`QUEUE DONE` in WORKLOG): re-run `bash tools/gate.sh active` and `python3 -I -B tools/aw.py integrity` yourself, verify raw tails in `gate_output/`, raise the ratchet ONCE (`python3 -I -B tools/aw.py ratchet --raise <measured> --i-am-architect`), append ONE `ARCH-ACCEPT` block in `AUDIT_LEDGER.md` section 8 and one row in `METRICS.md`.
4. Otherwise plan or audit: write `QUESTIONNAIRE_<date>.md`, `AUTHOR_ANSWERS_<date>.md`, `PLAN_latest.md` sections 1-5, `MODULES.md` (`python3 -I -B tools/aw.py modules`), `ROADMAP.md` and audit registers (`AUDIT_LEDGER.md`, `ARCHITECT_FEEDBACK.md`, `PROPOSALS.md`, `DECISIONS.md`).
5. Stop in the output shape of `ARCHITECT.md` and tell the owner to double-click `START_ARCHITECT.cmd` to author and dry-run the wave's cards.
"""
(target / ".hermes" / "START_PLAN_PROMPT.md").write_text(START_PLAN_PROMPT_TEXT, encoding="utf-8", newline="\n")
for _src, _dst in (("start_architect.cmd", "START_ARCHITECT.cmd"), ("start_worker.cmd", "START_WORKER.cmd"),
                   ("start_plan.cmd", "START_PLAN.cmd"), ("upgrade_kit.cmd", "UPGRADE_KIT.cmd")):
    if (KIT / _src).exists():
        (target / _dst).write_bytes((KIT / _src).read_bytes())
gi = target / ".gitignore"
if not gi.exists():
    gi.write_text(".env\nbackups/\nkit_stage/\n__pycache__/\n", newline="\n")
if not (target / ".git").exists():
    print("git init:", run(["git", "init", "-q"])[0] == 0)

for label, a in (("gate", ("gate", "baseline")), ("ratchet", ("ratchet", "--raise", "1", "--i-am-architect")),
                 ("baseline", ("integrity", "--write-baseline", "--i-am-architect"))):
    rc, out = aw(*a)
    print(label.upper(), "->", (out.splitlines() or [""])[-1])
    if rc:
        sys.exit(f"STOP at {label}: {out}")
print(aw("doctor")[1].splitlines()[-1])
print(f"""
DONE. {name} is ready. Nothing committed (the commit is your decision).
NEXT: 1) write your idea in IDEA.md  2) double-click START_ARCHITECT.cmd (the architect plans by itself)  3) double-click START_WORKER.cmd (or paste the queue START BLOCK into the worker profile).""")
