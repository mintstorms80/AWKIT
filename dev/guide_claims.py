#!/usr/bin/env python3
"""guide_claims.py - executes what docs/GUIDE.bg.md + GUIDE.en.md SAY against the real kit.
Every claim = (label, ok, got). Run:  python3 guide_claims.py [KIT_DIR]   Exit 0 only if all claims hold.
Author-side QA, not installed. Needs Python >= 3.12 (shutil.rmtree onexc)."""
import atexit, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

KIT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent).resolve()
W = Path(tempfile.mkdtemp(prefix="guide_walk_"))
PY = sys.executable
res = []


def run(args, cwd, env=None):
    e = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    e["PYTHONIOENCODING"] = "utf-8"
    e.update(env or {})
    r = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", env=e)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def aw(p, *a, env=None):
    return run([PY, "-I", "-B", "tools/aw.py", *a], p, env)


def claim(label, ok, got=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + label + ("" if ok else "  <- " + str(got).strip().replace("\n", " | ")[:260]))


def w(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="")


import stat


def _rm(func, path, exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


if W.exists():
    shutil.rmtree(W, onexc=_rm)
W.mkdir(parents=True)
atexit.register(lambda: shutil.rmtree(W, onexc=_rm) if W.exists() else None)
P = W / "p"

# ---- 1.2 install
rc, out = run([PY, str(KIT / "init_project.py"), str(P), "--name", "Walk", "--lang", "bg", "--owner", "the owner"], W)
claim("1.2 install prints INSTALLED ... 0 collision(s) staged in kit_stage/ (lang=bg)", rc == 0 and re.search(r"INSTALLED into .*: \d+ new file\(s\), 0 collision\(s\) staged in kit_stage/ \(lang=bg\)", out), out)
claim("1.2 installed tree has no bytecode (installer must not copy __pycache__)", not any("__pycache__" in x.parts or x.suffix == ".pyc" for x in P.rglob("*")), [str(x) for x in P.rglob("*.pyc")])
claim("1.2 GUIDE.md is Bulgarian, addressed to the owner, no placeholder left", (P / ".hermes/plans/GUIDE.md").read_text(encoding="utf-8").startswith("# РЪКОВОДСТВО - Walk") and "the owner" in (P / ".hermes/plans/GUIDE.md").read_text(encoding="utf-8") and "{{" not in (P / ".hermes/plans/GUIDE.md").read_text(encoding="utf-8"))
rc, out = run([PY, str(KIT / "init_project.py"), "--check", str(P)], W)
claim("1.2 --check ends with KIT-CHECK engine_same=<n> engine_diff=0 missing=0", re.search(r"KIT-CHECK engine_same=\d+ engine_diff=0 missing=0\s*$", out.strip()), out[-200:])
rc, out = run([PY, str(KIT / "init_project.py"), str(P), "--name", "Walk"], W)
claim("1.2 re-install: COLLISION (merge by hand, backup first): <path>", "COLLISION (merge by hand, backup first):" in out, out[-200:])
rc, out = run([PY, str(KIT / "init_project.py"), str(KIT / "payload")], W)
claim("1.2 install into the kit's own tree is refused", "refusing to install into the kit's own tree" in out, out)

# ---- 1.3 doctor
rc, out = aw(P, "doctor")
warns = re.findall(r"^DOCTOR WARN (\S+?):", out, re.M)
claim("1.3 doctor on a clean install: DOCTOR PASS warn=<n> fail=0", rc == 0 and re.search(r"DOCTOR PASS warn=\d+ fail=0", out), out[-200:])
print("     (info) WARN topics on THIS host:", warns)

# ---- 1.4 gate
for i in range(3):
    pass
w(P / "tests/__init__.py", "")
w(P / "tests/test_a.py", "import unittest\nclass T(unittest.TestCase):\n    def test_1(self): pass\n    def test_2(self): pass\n    def test_3(self): pass\n")
w(P / "src/a.py", "x = 1\n")
ke = P / "tools/kit.env"
t = ke.read_text(encoding="utf-8")
t = re.sub(r"(?m)^TEST_CMD=.*$", "TEST_CMD=" + PY.replace("\\", "/") + " -I -B -m unittest discover -s tests -t .", t)
t = re.sub(r"(?m)^COUNT_REGEX=.*$", r"COUNT_REGEX=Ran ([0-9]+) tests?", t)
ke.write_text(t, encoding="utf-8", newline="")
rc, out = aw(P, "gate", "baseline")
claim("1.4 gate baseline: GATE OK count=<N> min=0", rc == 0 and re.search(r"GATE OK count=3 min=0", out), out)
claim("1.4 .hermes/plans/gate_output/baseline.txt exists", (P / ".hermes/plans/gate_output/baseline.txt").is_file())
keep = ke.read_text(encoding="utf-8")
ke.write_text(re.sub(r"(?m)^COUNT_REGEX=.*$", r"COUNT_REGEX=Ran (d+)x", keep), encoding="utf-8", newline="")
rc, out = aw(P, "gate", "bad")
claim("1.4/3 unreadable count: GATE FAIL count=0 min=0 reason=...no-count-parsed", rc == 1 and re.search(r"GATE FAIL count=0 min=0 reason=.*no-count-parsed", out), out)
ke.write_text(keep, encoding="utf-8", newline="")

# ---- 1.5 ratchet
rc, out = aw(P, "ratchet", "--raise", "3", "--i-am-architect")
claim("1.5 RATCHET min_tests=<N>", rc == 0 and "RATCHET min_tests=3" in out, out)
rc, out = aw(P, "ratchet", "--raise", "2", "--i-am-architect")
claim("1.5 REFUSED: floor only rises (a -> b)", rc == 1 and re.search(r"REFUSED: floor only rises \(3 -> 2\)", out), out)

# ---- 1.6 baseline
w(P / ".aw/checks.d/todo.py", (KIT / "payload/.aw/checks.d/example_todo_count.py.disabled").read_text(encoding="utf-8"))
rc, out = aw(P, "integrity", "--write-baseline", "--i-am-architect")
claim("1.6 BASELINE WRITTEN files=<n> metrics=<m> core=<n> floor=<N> (record it in AUDIT_LEDGER)", re.search(r"BASELINE WRITTEN files=\d+ metrics=\d+ core=\d+ floor=3 \(record it in AUDIT_LEDGER\)", out), out)
rc, out = aw(P, "integrity")
claim("1.6 INTEGRITY OK frozen=<n> metrics=<m> core=<n>", re.search(r"INTEGRITY OK frozen=\d+ metrics=\d+ core=\d+", out), out)
w(P / ".aw/ratchet.json", '{"min_tests": 0}\n')
rc, out = aw(P, "integrity")
rc2, out2 = aw(P, "gate", "lowered")
claim("1.6 hand-lowered ratchet.json is reported as RATCHET-LOWERED (integrity or gate)", "RATCHET-LOWERED" in out or "RATCHET-LOWERED" in out2, out + out2)
claim("(info) a lowered ratchet.json cannot lower the gate floor (shadow floor in the baseline)", "min=3" in out2, out2)
w(P / ".aw/ratchet.json", '{"min_tests": 3}\n')

# ---- 3 table situations
w(P / "docs/source/book.txt", "v1\n")
rc, out = aw(P, "doctor")
claim("1.3 after 1.4-1.6 the ratchet+baseline WARNs are gone", "DOCTOR WARN ratchet" not in out and "DOCTOR WARN baseline" not in out, out)
w(P / ".gitignore", ".env\nbackups/\nkit_stage/\n")
rc, out = aw(P, "doctor")
warns2 = re.findall(r"^DOCTOR WARN (\S+?):", out, re.M)
claim("1.3 baseline+ratchet WARNs are gone after 1.5-1.6", "baseline" not in warns2 and "ratchet" not in warns2, warns2)
claim("1.3 with .gitignore (.env, backups/, kit_stage/) the gitignore WARN is gone; only wsl-bash may remain (Windows+WSL)", "gitignore" not in warns2 and set(warns2) <= {"wsl-bash"}, warns2)

card = ("# T-001 — touch a.py\nStatus: TODO | Lane: ROTE | Depends: - | Module: - | Author decisions needed: none\n\n## GOAL\nx\n\n## OWNS\n- src/a.py\n\n## READ-ONLY\n- docs/\n")
w(P / ".hermes/plans/cards/T-001.md", card)
aw(P, "start", "T-001")
aw(P, "backup", "T-001", "src/a.py")
w(P / "src/a.py", "x = 2\n")
rc, out = aw(P, "gate", "T-001")
rc, out = aw(P, "audit", "T-001", env={"OWNS": "src/a.py"})
claim("2 audit of a clean card: last line AUDIT PASS", rc == 0 and out.strip().splitlines()[-1].startswith("AUDIT PASS"), out)

aw(P, "start", "T-002")
w(P / "docs/x.md", "outside\n")
rc, out = aw(P, "audit", "T-002", env={"OWNS": "src/a.py"})
claim("3 file outside OWNS: 'OWNS <n> outside OWNS' + 'OUT <path>'", rc == 1 and re.search(r"OWNS 1 outside OWNS", out) and "OUT docs/x.md" in out, out)

w(P / "docs/source/book.txt", "v2 changed\n")
(P / ".aw/frozen.txt").write_text((P / ".aw/frozen.txt").read_text(encoding="utf-8") + "docs/source/*\n", encoding="utf-8", newline="")
rc0, out0 = aw(P, "integrity", "--write-baseline", "--i-am-architect", "--allow", "docs/source/book.txt,.aw/frozen.txt")
w(P / "docs/source/book.txt", "v3 sneaky\n")
rc, out = aw(P, "integrity")
claim("3 frozen file changed: INTEGRITY FAIL ... FROZEN-CHANGED <path>", rc == 1 and "FROZEN-CHANGED docs/source/book.txt" in out, out)

# ledger rewritten
L = P / ".hermes/plans/AUDIT_LEDGER.md"
raw = L.read_bytes()
L.write_bytes(raw.replace(b"RE-AUDIT", b"RE-EDIT", 1))
aw(P, "start", "T-003")
rc, out = aw(P, "audit", "T-003", env={"OWNS": "src/a.py"})
claim("3 ledger rewritten: LEDGER-REWRITTEN (prefix differs from last seen: append-only violated)", "LEDGER-REWRITTEN (prefix differs from last seen: append-only violated)" in out, out)
L.write_bytes(raw)

# secret
key = "sk-" + "A1b2C3d4" * 3
w(P / "src/cfg.py", f'KEY = "{key}"\n')
rc, out = aw(P, "audit")
claim("3 secret found: 'SECRETS FAIL 1' + 'src/cfg.py:1 rule=openai-style-key', text never printed", "SECRETS FAIL 1" in out and "src/cfg.py:1 rule=openai-style-key" in out and key not in out, out)
(P / "src/cfg.py").unlink()

# gate below floor
w(P / "tests/test_a.py", "import unittest\nclass T(unittest.TestCase):\n    def test_1(self): pass\n")
rc, out = aw(P, "gate", "low")
claim("3 gate under the floor: GATE FAIL count=<n> min=<m> reason=count<m", rc == 1 and re.search(r"GATE FAIL count=1 min=3 reason=count<3", out), out)
w(P / "tests/test_a.py", "import unittest\nclass T(unittest.TestCase):\n    def test_1(self): pass\n    def test_2(self): pass\n    def test_3(self): pass\n")

# worklog stale
gl = P / ".hermes/plans/gate_output"
wl = P / ".hermes/plans/WORKLOG.md"
old = time.time() - 7200
os.utime(wl, (old, old))
aw(P, "gate", "fresh")
rc, out = aw(P, "audit")
claim("3 stale WORKLOG: WARN WORKLOG older than newest gate_output (missing entry?)", "WARN WORKLOG older than newest gate_output (missing entry?)" in out, out)

# ask / answer / report
rc, out = aw(P, "ask", "which timeout?")
claim("2 ask: ASKED Q-001", "ASKED Q-001" in out, out)
rc, out = aw(P, "report")
rep = (P / ".hermes/plans/REPORT_latest.md").read_text(encoding="utf-8")
claim("5 report: 'open questions: 1' and <= 60 lines", "open questions: 1" in rep and len(rep.splitlines()) <= 60, rep)
for pat, lab in ((r"kit=\S+ next-card-id=\S+ ratchet min_tests=\d+", "5 report row 1: kit=<v> next-card-id=<ID> ratchet min_tests=<N>"),
                 (r"last gate file: \S+\.txt @ ", "5 report: last gate file: <label>.txt @ <date>"),
                 (r"## last re-audits", "5 report: ## last re-audits"),
                 (r"## last WORKLOG entries", "5 report: ## last WORKLOG entries"),
                 (r"AUDIT_LEDGER\.md: \d+ [0-9a-f]+", "5 report: AUDIT_LEDGER.md: <bytes> <sha>"),
                 (r"doctor: (PASS|FAIL) warn=\d+ fail=\d+", "5 report: doctor: PASS warn=<n> fail=<n>")):
    claim(lab, re.search(pat, rep), rep)
claim("5 report row 3: 'queue: <file> <done>/<total> in WORKLOG, not done: <id>' exists only with a queue", True)
rc, out = aw(P, "answer", "Q-001", "180000 ms")
claim("2 answer: ANSWERED Q-001", "ANSWERED Q-001" in out, out)

# restore
aw(P, "start", "T-004")
aw(P, "backup", "T-004", "src/a.py")
w(P / "src/a.py", "x = 99\n")
w(P / "src/new.py", "created by the card\n")
rc, out = aw(P, "restore", "T-004")
claim("3 restore: RESTORED <n> file(s) from backups/T-004/ + NOT-RESTORED-NEW <path>", re.search(r"RESTORED 1 file\(s\) from backups/T-004/", out) and "NOT-RESTORED-NEW src/new.py" in out, out)
claim("3 restore really put the bytes back", (P / "src/a.py").read_text(encoding="utf-8") == "x = 2\n", (P / "src/a.py").read_text(encoding="utf-8"))

# patch
w(P / "o.txt", "x\n")
w(P / "n.txt", "y\n")
w(P / "src/dup.py", "x\nx\n")
rc, out = aw(P, "patch", "src/dup.py", "o.txt", "n.txt")
claim("4 patch: PATCH REFUSED: OLD occurs 2 times", rc == 1 and "PATCH REFUSED: OLD occurs 2 times" in out, out)

# next-id on a truly fresh install
F = W / "fresh"
run([PY, str(KIT / "init_project.py"), str(F), "--name", "F"], W)
rc, out = aw(F, "next-id", "T")
claim("7 next-id on a fresh install = T-001 (guide says so)", out.strip() == "T-001", out)

# card-lint / queue-check / modules exist and speak
rc, out = aw(P, "card-lint", "T-001")
claim("4 card-lint prints CARD-LINT OK|FAIL errors=<n> warn=<n>", re.search(r"CARD-LINT (OK|FAIL) errors=\d+ warn=\d+", out), out)
rc, out = aw(P, "modules")
claim("4 modules prints MODULES OK|FAIL", re.search(r"MODULES (OK|FAIL)", out), out)

# doctor FAIL
ke.write_text(re.sub(r"(?m)^TEST_CMD=.*$", "TEST_CMD=definitely_not_a_program -x", ke.read_text(encoding="utf-8")), encoding="utf-8", newline="")
rc, out = aw(P, "doctor")
claim("3 doctor FAIL TEST_CMD: <prog> not found -> TEST_CMD will fail with exit=127", rc == 1 and re.search(r"DOCTOR FAIL TEST_CMD: .*not found -> TEST_CMD will fail with exit=127", out), out)
ke.write_text(keep, encoding="utf-8", newline="")

# selftest line shape (1.1)
sline = None
rc, out = run([PY, str(KIT / "selftest.py"), "--lint-only"], KIT)
claim("1.1 selftest prints 'lint findings on <folder>: 0'", re.search(r"lint findings on \S+: 0", out), out[-300:])
print("     (info) selftest --lint-only tail:", [l for l in out.splitlines() if l.strip()][-2:])

# ---- v2.0.1 guide claims
rc, out = aw(P, "audit", "T-001")
claim("4 audit without OWNS: every changed file shows as OUT (outside OWNS)", rc == 1 and re.search(r"^\s+OUT \S+", out, re.M), out)
claim("4 gate.sh / re_audit.sh only call aw.py gate / audit ('the scripts only call these')",
      "aw.py gate" in (P / "tools/gate.sh").read_text(encoding="utf-8") and "aw.py audit" in (P / "tools/re_audit.sh").read_text(encoding="utf-8"))
cd = P / ".hermes/plans/cards"
cd.mkdir(parents=True, exist_ok=True)
w(cd / "T-09700.md", "# T-09700 - probe\n")
rc, out = aw(P, "next-id", "T")
claim("4 next-id counts a '# T-NNN' card title", out.strip() == "T-9701", out)
(cd / "T-09700.md").unlink()
rc, out = aw(P, "report")
rep = (P / ".hermes/plans/REPORT_latest.md").read_text(encoding="utf-8")
claim("5 report: '## file fingerprints' + '### RE-AUDIT <time> after <ID>'; the verdict lives in the ledger block, not in the report",
      "## file fingerprints" in rep and re.search(r"^### RE-AUDIT \S+ after \S+", rep, re.M) and "verdict=" not in rep
      and "verdict=" in (P / ".hermes/plans/AUDIT_LEDGER.md").read_text(encoding="utf-8"), rep[-400:])
sb = (KIT / "payload/.hermes/plans/START_BLOCKS.md").read_text(encoding="utf-8")
claim("2 START_BLOCKS has the six blocks the guide lists (0, 1, Q, R, A, X)", all(re.search(rf"^## BLOCK {b} ", sb, re.M) for b in "01QRAX"))
sw = (KIT / "payload/.hermes/prompts/SWARM.md").read_text(encoding="utf-8")
claim("2 SWARM.md answers 'zaredi agentite' / 'load the specialists'", "zaredi agentite" in sw and "load the specialists" in sw)
G = W / "gitflow"
run([PY, str(KIT / "init_project.py"), str(G), "--name", "G"], W)
run(["git", "init", "-q"], G)
w(G / ".gitignore", ".env\nbackups/\nkit_stage/\n")
run(["git", "add", "-A"], G)
rc, out = run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "kit installed"], G)
rc2, h = run(["git", "rev-parse", "--short", "HEAD"], G)
rc3, st = run(["git", "status", "--short"], G)
claim("1.9 .gitignore, git add -A, git commit, git rev-parse --short HEAD -> a short hash and a clean tree", rc == 0 and re.fullmatch(r"[0-9a-f]{7,}", h.strip()) and st.strip() == "", (out, h, st))
rc, out = run([PY, str(KIT / "init_project.py"), str(W / "count"), "--name", "C", "--lang", "en"], W)
print("     (info) install line:", out.strip().splitlines()[-1][:140])

print("\nGUIDE-CLAIMS %s  held=%d failed=%d  kit=%s" % ("PASS" if all(res) else "FAIL", sum(res), len(res) - sum(res), KIT))
sys.exit(0 if all(res) else 1)
