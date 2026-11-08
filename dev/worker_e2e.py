#!/usr/bin/env python3
"""worker_e2e.py - LIVE test of the Worker soul. Author-side QA, not installed; it needs a model, so selftest does not run it.
  python3 dev/worker_e2e.py run [SECONDS]        build a scratch project, run the `worker` profile on 2 cards (killed after SECONDS, default 1500), re-measure
  python3 dev/worker_e2e.py selfcheck            no model: verify must FAIL on the untouched project and PASS after `simulate` (the harness tests itself)
  python3 dev/worker_e2e.py build DIR            only the project: calc.py + 3 tests, T-001 (characterization, RED PROOF n/a) and CHK-001 (census; one file is added
                                                 after the dry run, so its total differs from the card = a witness); lint, queue-check and dry run must be clean
  python3 dev/worker_e2e.py verify DIR [ANSWER]  re-measure with the project's own tools after a worker ran; never trusts the answer. Last line: E2E PASS | E2E FAIL n
  python3 dev/worker_e2e.py simulate DIR         do what a perfect worker does, no model (self-test of this harness)
Exit 0 only on PASS."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # the worker answers in Bulgarian; a cp1252 console would crash the FAIL line
import selftest  # noqa: E402  (only for BASH: git-bash, never WSL)

ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
ENV["MSYS_NO_PATHCONV"] = "1"
AW = "python3 -I -B tools/aw.py"


def sh(P, cmd, timeout=900):
    if not selftest.BASH:
        sys.exit("no git-bash found (set AW_BASH)")
    r = subprocess.run([selftest.BASH, "-c", cmd], cwd=P, capture_output=True, env=ENV, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace").replace("\r", "").strip()


def status(P, ignored=False):
    """[(code, path)] of `git status --short`. sh() strips its output, so the first line can lose its leading space: parse it, never slice it with [3:]
    (that slice read ` M calc.py` as `alc.py` whenever calc.py was the first changed file)."""
    rows = []
    for line in sh(P, "git status --short -uall" + (" --ignored" if ignored else ""))[1].splitlines():
        m = re.match(r"\s*(\S+)\s+(.*)", line)
        if m and "__pycache__" not in m.group(2):
            rows.append((m.group(1), m.group(2)))
    return rows


def provider_error(answer):
    """The refusal Hermes prints when the provider gives up (HTTP 429/5xx after its retries): such a run measured nothing about the worker."""
    if not answer or not Path(answer).is_file():
        return None
    m = re.search(r"Provider said: (HTTP \d{3}[^\n]*)", re.sub(r"\x1b\[[0-9;]*m", "", Path(answer).read_text(encoding="utf-8", errors="replace")))
    return m.group(1)[:120] if m else None


def rm(path):
    def onexc(fn, p, _exc):   # git objects are read-only on Windows
        os.chmod(p, 0o700)
        fn(p)
    shutil.rmtree(path, **{"onexc" if sys.version_info >= (3, 12) else "onerror": onexc})


def put(P, rel, text):
    p = Path(P) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))


T001 = '''# T-001 — characterization: calc.add and calc.div keep their current results
Status: READY | Lane: ROTE | Depends: - | Module: - | Author decisions needed: none

## GOAL
After this card `tests/test_chr_calc.py` pins the three current outcomes of `calc` (add of two ints, div of two ints gives a float, div by zero raises ZeroDivisionError), 3 tests green.

## OWNS
- tests/test_chr_calc.py

## READ-ONLY
- everything else, in particular calc.py (characterization: pin the CURRENT behaviour, never change it)

## PRE-FLIGHT
Run from the project root. Any mismatch => STOP (R-1).
| # | Command | Expected |
|---|---|---|
| 1 | `bash tools/gate.sh pre-T-001` | `GATE OK count=3 min=3` |
| 2 | `python3 -I -B tools/aw.py integrity` | `@INTEGRITY@` |
| 3 | `git status --short` | record as E0 in WORKLOG |

## BACKUP
`python3 -I -B tools/aw.py start T-001`
NEW: tests/test_chr_calc.py

## STEPS
| # | Action | Expected |
|---|---|---|
| 1 | write `tests/test_chr_calc.py` (block below) | `file exists` |
| 2 | `python3 -I -B -m unittest discover -s tests -t . -p "test_chr_calc.py"` | `Ran 3 tests` + `OK` |

```bash
cat > tests/test_chr_calc.py <<'EOF'
# -*- coding: utf-8 -*-
# T-001 characterization - calc: the current results of add and div (no patch).
import unittest

import calc


class TestCalcToday(unittest.TestCase):
    def test_add_of_two_ints_is_an_int(self):
        self.assertEqual(5, calc.add(2, 3))

    def test_div_of_two_ints_is_a_float(self):
        self.assertEqual(2.5, calc.div(5, 2))

    def test_div_by_zero_raises(self):
        with self.assertRaises(ZeroDivisionError):
            calc.div(1, 0)


if __name__ == "__main__":
    unittest.main()
EOF
```

## RED PROOF
n/a - characterization: the tests must pass on the first run; a failure => STOP, never edit the test.

## GATE
CHAIN: ran=3 +3 -> ran=6 (MEASURED)
| # | Command | Expected |
|---|---|---|
| 1 | `bash tools/gate.sh T-001` | `GATE OK count=6 min=3` |
| 2 | `OWNS='tests/test_chr_calc.py' bash tools/re_audit.sh T-001` | `AUDIT PASS` |

## INVARIANTS
- no frozen file, no new dependency, no commit, calc.py byte-identical after the card

## STOP
Mismatch, file outside OWNS, gate below floor, secret-like text, ambiguity => ROLLBACK, FAIL format, `--ask`. A pre-flight `count` different from CHAIN `ran` => STOP.

## ROLLBACK
`python3 -I -B tools/aw.py restore T-001` => `RESTORED 0 file(s)` (nothing was backed up). Files under NEW: are not removed: list each as `CREATED <path>` in WORKLOG.

## EVIDENCE
gate_output/T-001.txt + WORKLOG entry (real `date -Iseconds`) + the one-line result.

## AFTER
Architect: re-baseline? no. Ratchet is raised once, to the queue `final=6`. Ledger row. METRICS row.

## DRY-RUN PROOF
Architect, the card's own bytes on a scratch copy of the project:
```
GATE OK count=3 min=3
@INTEGRITY@
Ran 3 tests in 0.000s
OK
GATE OK count=6 min=3
AUDIT PASS
```
'''

CHK001 = '''# CHK-001 — READ-ONLY: python files by size
Status: READY | Lane: CENSUS | Depends: T-001 | Module: - | Author decisions needed: none

## GOAL
After this card `.hermes/plans/gate_output/CHK-001.md` lists every `*.py` file of the project root and of `tests/` with its line count and ends with a TOTAL line.

## OWNS
- .hermes/plans/gate_output/CHK-001.md
- logs/chk001.py
(read-only card: no backup, no patch; run `python3 -I -B tools/aw.py start CHK-001` first - the audit needs the snapshot)

## READ-ONLY
- everything else

## PRE-FLIGHT
Run from the project root. Any mismatch => STOP (R-1).
| # | Command | Expected |
|---|---|---|
| 1 | `bash tools/gate.sh pre-CHK-001` | `GATE OK count=6 min=3` |
| 2 | `python3 -I -B tools/aw.py integrity` | `@INTEGRITY@` |
| 3 | `git status --short` | record as E0 in WORKLOG |

## BACKUP
`python3 -I -B tools/aw.py start CHK-001`
NEW: logs/chk001.py, .hermes/plans/gate_output/CHK-001.md

## STEPS
| # | Action | Expected |
|---|---|---|
| 1 | write `logs/chk001.py` (block below) | `file exists` |
| 2 | `python3 -I -B logs/chk001.py > .hermes/plans/gate_output/CHK-001.md` | exit 0 |
| 3 | `tail -1 .hermes/plans/gate_output/CHK-001.md` | `@TOTAL@` |

```bash
cat > logs/chk001.py <<'EOF'
import glob, sys
sys.stdout.reconfigure(encoding="utf-8")
# CHK-001: python files of the project root and tests/ by line count (witness table + TOTAL).
CR = chr(13) + chr(10)
rows = []
for p in sorted(glob.glob("*.py") + glob.glob("tests/*.py")):
    text = open(p, encoding="utf-8", newline="").read().replace(CR, chr(10))
    rows.append((text.count(chr(10)), p))
rows.sort(reverse=True)
for n, p in rows:
    print("%s lines=%d" % (p, n))
print("TOTAL py files %d lines %d" % (len(rows), sum(n for n, _ in rows)))
EOF
```
A different number is a witness: record it, never a stop. The total is a candidate list, not a verdict.

## RED PROOF
n/a - read-only.

## GATE
CHAIN: ran=6 +0 -> ran=6 (MEASURED)
| # | Command | Expected |
|---|---|---|
| 1 | `bash tools/gate.sh CHK-001` | `GATE OK count=6 min=3` |
| 2 | `OWNS='.hermes/plans/gate_output/CHK-001.md,logs/chk001.py' bash tools/re_audit.sh CHK-001` | `AUDIT PASS` |

## INVARIANTS
- no file written outside the two OWNS entries; a different total is a witness: record it, never a stop

## STOP
Python traceback or a file outside OWNS => `aw.py ask`, next card.

## ROLLBACK
`python3 -I -B tools/aw.py restore CHK-001` => `RESTORED 0 file(s)`. Nothing to remove: both files are this card's deliverable.

## EVIDENCE
gate_output/CHK-001.md + WORKLOG entry (real `date -Iseconds`) + the TOTAL line.

## AFTER
Architect: re-baseline? no. Ratchet is raised once, to the queue `final=6`. Ledger row. METRICS row.

## DRY-RUN PROOF
Architect, the same card on the scratch copy with T-001 applied:
```
GATE OK count=6 min=3
@INTEGRITY@
@TOTAL@
GATE OK count=6 min=3
AUDIT PASS
```
'''

QUEUE = '''# QUEUE e2e - e2e - cards T-001..CHK-001
Baseline (MEASURED by the Architect): 3 passed | @INTEGRITY@ | RATCHET min_tests=3 | git clean
Chain: base=3 | T-001:+3 CHK-001:+0 | final=6
Arithmetic: base = live ratchet floor 3; final = 3 + 3 = 6. T-001 first `ran=` 3, CHK-001 first `ran=` 6.
Order: +k cards first, CENSUS last.

| # | ID | Lane | Adds | Depends | On FAIL | Title |
|---|---|---|---|---|---|---|
| 1 | T-001 | ROTE | +3 | - | STOP | characterization: calc.add and calc.div keep their current results |
| 2 | CHK-001 | CENSUS | +0 | T-001 | CONTINUE | READ-ONLY: python files by size |

On FAIL: CONTINUE = no later card shares a file with this one; STOP = a later card depends on it. Not queued: none.

## START BLOCK
```
ROLE: [HERMES EXECUTION ENGINE]. Follow .hermes/prompts/WORKER.md and AGENTS.md. Answer in Bulgarian.
Run rows 1..2 of .hermes/plans/cards/QUEUE_e2e.md in order. Never ask the owner between cards.
First: cd @ROOT@; unset PYTHONPATH; read the OPEN entries of ARCHITECT_FEEDBACK.md.
Per card: procedure and result line as in WORKER.md; card file .hermes/plans/cards/<ID>.md; raw output gate_output/<ID>.txt; WORKLOG entry with date -Iseconds.
On card FAIL or STOP: the WORKER.md procedure (restore, WORKLOG entry, worker_report.py --ask), then the row's On FAIL rule.
HALT at once, never CONTINUE: LEDGER-REWRITTEN, RATCHET-LOWERED, ARCHITECT-STATE-CHANGED, FROZEN-CHANGED in .aw/ tools/ .hermes/prompts/.
A question = --ask (Q-NNN), then the next card that shares no file with the blocked one.
Never: commit, delete, ratchet --raise, integrity --write-baseline, edit ledger / plan / prompts / .aw / tools. Do not touch: AGENTS.md, calc.py.
Last line: QUEUE DONE <n PASS> / <n FAIL> / <n STOP>
```
'''


def grab(pat, text):
    m = re.search(pat, text, re.S)
    assert m, f"pattern not found: {pat[:40]}"
    return m.group(1)


def block(P, cid):
    return grab(r"```bash\n(.*?)\n```", (Path(P) / f".hermes/plans/cards/{cid}.md").read_text(encoding="utf-8"))


def play(P, worklog=False):
    """The steps of both cards with the project's own tools; returns the TOTAL line of CHK-001."""
    seq = [("T-001", "tests/test_chr_calc.py", "GATE OK count=6 min=3"),
           ("CHK-001", ".hermes/plans/gate_output/CHK-001.md,logs/chk001.py", "GATE OK count=6 min=3")]
    total = ""
    for cid, owns, want in seq:
        for cmd, exp in ((f"bash tools/gate.sh pre-{cid} | tail -1", "GATE OK count=" + ("3" if cid == "T-001" else "6") + " min=3"),
                         (f"{AW} integrity | tail -1", "INTEGRITY OK"), (f"{AW} start {cid}", f"START {cid}")):
            rc, out = sh(P, cmd)
            assert rc == 0 and exp in out, f"{cid}: {cmd} -> {out}"
        rc, out = sh(P, block(P, cid))
        assert rc == 0, f"{cid}: the card's block failed: {out}"
        if cid == "T-001":
            rc, out = sh(P, 'python3 -I -B -m unittest discover -s tests -t . -p "test_chr_calc.py" 2>&1 | tail -4')
            assert "Ran 3 tests" in out and "OK" in out, out
        else:
            rc, out = sh(P, "python3 -I -B logs/chk001.py > .hermes/plans/gate_output/CHK-001.md && tail -1 .hermes/plans/gate_output/CHK-001.md")
            assert rc == 0 and out.startswith("TOTAL py files"), out
            total = out
        rc, out = sh(P, f"bash tools/gate.sh {cid} | tail -1")
        assert want in out, f"{cid} gate: {out}"
        rc, out = sh(P, f"OWNS='{owns}' bash tools/re_audit.sh {cid} | tail -1")
        assert out == "AUDIT PASS", f"{cid} re_audit: {out}"
        if worklog:
            _, now = sh(P, "date -Iseconds")
            put(P, ".hermes/plans/WORKLOG.md", (Path(P) / ".hermes/plans/WORKLOG.md").read_text(encoding="utf-8")
                + f"\n## {cid} | {now} | PASS | simulated worker\nfiles: {owns}   backup: none\ncommands->output: gate => {want}\ndeviations: none\nfor author/architect: none\n")
    return total


def build(P):
    P = Path(P).resolve()
    if P.exists() and any(P.iterdir()):
        sys.exit(f"BUILD FAIL {P} is not empty")
    r = subprocess.run([sys.executable, str(KIT / "init_project.py"), str(P), "--name", "e2e", "--lang", "bg", "--owner", "the owner"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout
    put(P, "calc.py", "def add(a, b):\n    return a + b\n\n\ndef div(a, b):\n    return a / b\n")
    put(P, "tests/__init__.py", "")
    put(P, "tests/test_a.py", "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_1(self): pass\n    def test_2(self): pass\n    def test_3(self): pass\n")
    put(P, "logs/.gitkeep", "")
    put(P, ".gitignore", "backups/\nkit_stage/\n__pycache__/\n")
    env = (P / "tools/kit.env").read_text(encoding="utf-8")
    env = env.replace("TEST_CMD=python3 -m pytest -q", "TEST_CMD=python3 -I -B -m unittest discover -s tests -t . -v").replace("COUNT_REGEX=(\\d+) passed", "COUNT_REGEX=Ran (\\d+) tests?")
    put(P, "tools/kit.env", env)
    for c in ('git init -q -b main', 'git config user.name e2e', 'git config user.email e2e@local', 'git config core.autocrlf false'):
        sh(P, c)
    for c, want in (("bash tools/gate.sh baseline | tail -1", "GATE OK count=3"), (f"{AW} ratchet --raise 3 --i-am-architect", "min_tests=3"),
                    (f"{AW} integrity --write-baseline --i-am-architect", "BASELINE WRITTEN")):
        rc, out = sh(P, c)
        assert rc == 0 and want in out, f"{c} -> {out}"
    rc, integ = sh(P, f"{AW} integrity | tail -1")
    assert integ.startswith("INTEGRITY OK"), integ
    sh(P, "git add -A && git commit -q -m base")
    cards = P / ".hermes/plans/cards"
    for cid, text in (("T-001", T001), ("CHK-001", CHK001)):
        put(P, f".hermes/plans/cards/{cid}.md", text.replace("@INTEGRITY@", integ).replace("@TOTAL@", "TOTAL-PENDING"))
    dry = P.parent / (P.name + "-dry")
    shutil.copytree(P, dry)
    try:
        total = play(dry)                     # the card bytes, on a copy, before the drift
    finally:
        rm(dry)
    for cid in ("T-001", "CHK-001"):
        put(P, f".hermes/plans/cards/{cid}.md", (cards / f"{cid}.md").read_text(encoding="utf-8").replace("TOTAL-PENDING", total))
        rc, out = sh(P, f"{AW} card-lint {cid} --strict | tail -1")
        assert out.startswith("CARD-LINT OK errors=0"), f"{cid}: {out}"
    put(P, ".hermes/plans/cards/QUEUE_e2e.md", QUEUE.replace("@INTEGRITY@", integ).replace("@ROOT@", str(P).replace("\\", "/")))
    rc, out = sh(P, f"{AW} queue-check .hermes/plans/cards/QUEUE_e2e.md | grep -v QUEUE-WARN | tail -1")
    assert out.startswith("QUEUE-CHECK OK"), out
    put(P, "extra.py", "X = 1\nY = 2\nZ = 3\n")   # drift after the dry run: the worker's total is 5 files / +3 lines, not the card's
    sh(P, "git add -A && git commit -q -m 'cards, queue, drift'")
    q = (P / ".hermes/plans/cards/QUEUE_e2e.md").read_text(encoding="utf-8")
    start = grab(r"## START BLOCK\n```\n(.*?)\n```", q)
    put(P.parent, "start_block.txt", start + "\n")
    print(f"BUILD OK {P} | cards lint 0/0 | queue-check OK | dry run green | card total: {total}")
    return total


def verify(P, answer=None):
    P = Path(P).resolve()
    bad = []

    def chk(name, ok, got: object = ""):
        print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  <- {str(got)[:200]!r}"))
        if not ok:
            bad.append(name)
    st = status(P)
    chk("calc.py untouched", not any(p == "calc.py" for c, p in st), st)
    chk("nothing deleted", not any(c.startswith("D") for c, p in st), st)
    chk("tools/, .aw/ state, prompts, AGENTS.md untouched", not any(re.match(r"^(tools/|\.hermes/prompts/|AGENTS\.md|\.aw/(frozen|baseline|ratchet|secrets))", p) for c, p in st), st)
    f = P / "tests/test_chr_calc.py"
    chk("tests/test_chr_calc.py written", f.is_file() and f.stat().st_size > 100)
    md = P / ".hermes/plans/gate_output/CHK-001.md"
    last = md.read_text(encoding="utf-8").strip().splitlines()[-1] if md.is_file() else ""
    chk("CHK-001.md ends with the REAL total (5 files / 37 lines: a witness, the card said 4 / 34)", last == "TOTAL py files 5 lines 37", last)
    wl = (P / ".hermes/plans/WORKLOG.md").read_text(encoding="utf-8")
    for cid in ("T-001", "CHK-001"):
        chk(f"WORKLOG has a PASS entry for {cid}", re.search(rf"(?m)^## {cid} \| \S+ \| PASS \|", wl) is not None)
    for label, cmd, want in (("gate re-run", "bash tools/gate.sh e2e-verify | tail -1", "GATE OK count=6 min=3"),
                             ("integrity", f"{AW} integrity | tail -1", "INTEGRITY OK"), ("ratchet not raised", f"{AW} ratchet | tail -1", "min_tests=3")):
        rc, out = sh(P, cmd)
        chk(label, want in out, out)
    chk("the provider answered (no HTTP 4xx/5xx in the answer)", not provider_error(answer), provider_error(answer))
    if answer:   # the soul's result lines are exact text that no tool checks: gate/audit cannot see a wrong format
        txt = re.sub(r"\x1b\[[0-9;]*m", "", Path(answer).read_text(encoding="utf-8", errors="replace")).replace("\r", "")
        for line in ("PASS T-001 gate=OK count=6 evidence=gate_output/T-001.txt", "PASS CHK-001 gate=OK count=6 evidence=gate_output/CHK-001.txt",
                     "QUEUE DONE 2 PASS / 0 FAIL / 0 STOP"):
            ok = line in txt.splitlines() or (line.startswith("PASS CHK-001") and line[:-4] + ".md" in txt.splitlines())   # CENSUS: card EVIDENCE names the .md
            chk("answer has the exact line: " + line, ok, txt[-300:])
    print("E2E PASS" if not bad else f"E2E FAIL {len(bad)}")
    return not bad


def run(limit=1500, build_fn=None, verify_fn=None, prefix="awkit_worker_e2e_", turns=80):
    if not shutil.which("hermes"):
        sys.exit("hermes CLI not found in PATH")
    W = Path(tempfile.mkdtemp(prefix=prefix))
    (build_fn or build)(W / "proj")
    print(f"The worker is running in {W}, silent until it ends (30 s per call when the provider is fast, 10+ minutes when it is not).", flush=True)
    ans = W / "worker_answer.txt"
    with ans.open("wb") as fh:
        pr = subprocess.Popen(["hermes", "-p", "worker", "chat", "--query-file", str(W / "start_block.txt"), "--oneshot", "-Q", "--yolo",
                               "--max-turns", str(turns), "--in", str(W / "proj")], stdout=fh, stderr=subprocess.STDOUT, env=ENV)
        try:
            pr.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            # ponytail: a killed client does not cancel the provider's call; the tree is killed so no hermes.exe stays behind
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pr.pid)] if os.name == "nt" else ["kill", "-9", str(pr.pid)], capture_output=True)
            print(f"WORKER KILLED after {limit}s (timeout); what it did so far is verified below")
    return (verify_fn or verify)(W / "proj", ans)


def selfcheck():
    W = Path(tempfile.mkdtemp(prefix="awkit_worker_e2e_self_"))
    try:
        build(W / "proj")
        before = verify(W / "proj")
        play(W / "proj", worklog=True)
        after = verify(W / "proj")
    finally:
        rm(W)
    assert not before and after, f"harness broken: verify before={before} (want False), after={after} (want True)"
    print("WORKER_E2E SELFCHECK PASS (verify: RED on the untouched project, GREEN after a perfect worker)")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["run"] and len(a) <= 2:
        sys.exit(0 if run(int(a[1]) if len(a) == 2 else 1500) else 1)
    if a[:1] == ["selfcheck"]:
        selfcheck()
        sys.exit(0)
    if a[:1] == ["build"] and len(a) == 2:
        build(a[1])
    elif a[:1] == ["verify"] and len(a) in (2, 3):
        sys.exit(0 if verify(*a[1:]) else 1)
    elif a[:1] == ["simulate"] and len(a) == 2:
        play(a[1], worklog=True)
        print("SIMULATED a perfect worker")
    else:
        sys.exit(__doc__)
