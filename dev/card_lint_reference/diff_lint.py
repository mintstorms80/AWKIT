#!/usr/bin/env python3
"""Differential test: reference lint (lint_probe.py MUT list) vs the engine's `aw.py card-lint`. Author-side QA, not installed.
usage: python3 diff_lint.py [KIT_DIR]   (default: this kit)"""
import atexit, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

KIT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]).resolve()
EC = Path(__file__).resolve().parent
sys.path.insert(0, str(EC))
import lint_probe as lp  # noqa: E402  (execs the rule data from CARD_LINT_RULES.md)

W = Path(tempfile.mkdtemp(prefix="diff_lint_"))
atexit.register(shutil.rmtree, W, True)


def run(args, cwd):
    e = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    e["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", env=e)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc, out = run([sys.executable, "-B", str(KIT / "init_project.py"), str(W / "p"), "--name", "D"], W)
P = W / "p"
for d in ("tests/session", "src"):
    (P / d).mkdir(parents=True, exist_ok=True)
(P / ".aw/ratchet.json").write_text('{"min_tests": 602}', encoding="utf-8", newline="")
(P / ".hermes/plans/QUESTIONS.md").write_text("## Q-012 | 2026-10-30 | OPEN\nx\n", encoding="utf-8", newline="")
(P / ".hermes/plans/MODULES.md").write_text(
    "| ID | Module | Purpose | OWNS | Depends | Wave | Gate | Decides | Status |\n|---|---|---|---|---|---|---|---|---|\n"
    "| M-04 | mail | mail tab | web/index.html | - | W-1 | gate | - | ACTIVE |\n", encoding="utf-8", newline="")
cards = P / ".hermes/plans/cards"
cards.mkdir(parents=True, exist_ok=True)
(cards / "T-043.md").write_text("# T-043 - neighbour\n", encoding="utf-8", newline="")


def engine(cid, text):
    (cards / f"{cid}.md").write_text(text, encoding="utf-8", newline="")
    rc, out = run([sys.executable, "-I", "-B", "tools/aw.py", "card-lint", cid], P)
    if "Traceback" in out:
        return None, [out.strip().splitlines()[-1][:120]]
    fired = set(re.findall(r"LINT (?:ERROR|WARN) (L\d+)", out))
    err = int(re.search(r"errors=(\d+)", out).group(1)) if re.search(r"errors=(\d+)", out) else -1
    return err, sorted(fired)


base = {k: (EC / "fixtures" / f"{k}.md").read_text(encoding="utf-8") for k in ("T-043", "T-044", "CHK-007", "SPEC-002")}
print("== fixtures (reference says errors=0) ==")
bad = 0
for k, t in base.items():
    err, fired = engine(k, t)
    ok = err == 0
    bad += 0 if ok else 1
    print(f"  {'OK  ' if ok else 'DIFF'} {k:9} engine errors={err} fired={fired}")
print("== mutants (reference: rule must fire) ==")
miss = []
for f, old, new, rid in lp.MUT:
    txt = base[f].replace(old, new, 1)
    err, fired = engine(f, txt)
    if err is None:
        print(f"  CRASH {rid} ({f}): {fired}")
        miss.append(rid)
    elif rid not in fired:
        miss.append(rid)
        print(f"  MISS  {rid:4} ({f:8}) engine fired {fired}")
print(f"DIFF-LINT fixtures_diff={bad} mutants={len(lp.MUT)} missed={len(miss)} missed_rules={sorted(set(miss))}")
sys.exit(0 if not bad and not miss else 1)
