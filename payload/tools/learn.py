#!/usr/bin/env python3
"""learn.py - read-only self-improvement miner. Reads THIS project's own registers and prints barrier suggestions.
Usage: python3 -I -B tools/learn.py [project_root] [--write]    (--write only fills .hermes/plans/LEARN_latest.md)
Last line: `LEARN OK` or `LEARN SUGGEST <n>`. Every suggestion cites file:line. It never edits code, ratchet, ledger or cards.
Suggestions are CANDIDATES: the Architect verifies one cited line, then records a PROPOSALS row (aw.py improve tracks it)."""
import json, re, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

args = [a for a in sys.argv[1:] if not a.startswith("--")]
ROOT = Path(args[0] if args else ".").resolve()
PL = ROOT / ".hermes" / "plans"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def lines(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

# generic kit pitfalls: family -> (regex, barrier to propose when it recurs)
FAMILIES = {
    "out-of-OWNS": (r"out of owns|outside owns|вън от owns|извън owns", "tighten the card OWNS or add the file to .aw/frozen.txt"),
    "gate-count-0": (r"count=0|no tests ran|collected 0", "a gate that counts 0 is a false green: keep the NO TESTS RAN guard, check PYTHONPATH"),
    "encoding": (r"cp1252|UnicodeEncodeError|UnicodeDecodeError|mojibake", "force UTF-8 in the card commands; add a .aw/checks.d ZERO check for U+FFFD"),
    "path-quoting": (r"\bmsys\b|\bwsl\b|path with a space|cannot change to|no such file or directory", "write native C:/ paths in the cards and put a pre-flight `test -f` assert first"),
    "timeout": (r"timed out|\btimeout\b", "split the step or give the command a bounded subset; never an open recursive scan"),
    "hand-edit": (r"hand-edit|edited by hand|ръчно редакт", "an integrity baseline entry or a generator-owned header; refuse hand edits in a check"),
    "unmeasured-claim": (r"should work|should pass|seems to|probably fixed|би трябвало|непроверен|вероятно е", "demand the gate_output path in the card; no number without a command"),
    "git-anchor": (r"no commit|uncommitted|not a git repository|няма commit", "first VCS commit before the worker starts (Author decision)"),
    "deferral": (r"deferred|отложен|отлага|next phase|later phase|out of scope|извън обхват", "defer only when BLOCKED (impossible here, infrastructure missing, or a stated invariant): name which + the proving command; a scope cut is the Author's call"),
    "placeholder": (r"\bTBD\b|placeholder|n/a\b", "a ZERO check under .aw/checks.d that scans the deliverables"),
}
PROSE_ONLY = {"deferral", "placeholder"}
out = []

def sug(kind, evidence, barrier):
    out.append(f"LEARN SUGGEST {kind} | {evidence} | barrier: {barrier}")

# 1. recurring pitfall families across every register + gate output
SRC = [p for n in ("WORKLOG.md", "AUDIT_LEDGER.md", "ARCHITECT_FEEDBACK.md", "QUESTIONS.md") if (p := PL / n).exists()]
SRC += sorted((PL / "gate_output").glob("*.txt")) if (PL / "gate_output").is_dir() else []
hits = defaultdict(list)
for p in SRC:
    for i, ln in enumerate(lines(p), 1):
        if ln.lstrip().startswith(("#", "|", "-", "*")) or p.suffix == ".txt":
            for fam, (rx, _) in FAMILIES.items():
                if fam in PROSE_ONLY and ln.lstrip().startswith("|"):
                    continue  # a register table row names a finding, it is not a decision to defer
                if re.search(rx, ln, re.I):
                    hits[fam].append(f"{p.name}:{i}")
for fam, h in sorted(hits.items(), key=lambda kv: -len(kv[1])):
    if len(h) >= 3:
        sug("recurring-" + fam, f"{len(h)} hits, e.g. {', '.join(h[:3])}", FAMILIES[fam][1])

# 1b. blind checks: a checks.d script that prints ZERO but can never fail when it scanned nothing passes in silence
for p in sorted((ROOT / ".aw" / "checks.d").glob("*.py")):
    t = "\n".join(lines(p))
    if "ZERO" in t and not re.search(r"sys\.exit|raise |assert |\bexit\(", t):
        sug("blind-check", f"{p.name} prints ZERO and has no liveness guard", "fail when it scanned 0 files (assert scanned > 0): a rule that stopped detecting passes in silence")

# 2. unstable cards: several WORKLOG entries for one id with a FAIL/STOP among them
wl = PL / "WORKLOG.md"
wl_text = "\n".join(lines(wl))
runs = defaultdict(list)
cur = None
NONE = {"", "няма", "none", "no files", "-", "n/a", "no", "nothing"}
for i, ln in enumerate(lines(wl), 1):
    mf = re.match(r"\s*-\s*(Файлове|Files)\s*:\s*(.*)", ln)
    if mf and cur and cur[1] == "PASS" and mf.group(2).strip(" .`*-—").lower() in NONE and not cur[0].startswith(("CHK", "AUD")):
        sug("empty-pass", f"{cur[0]} PASS lists no changed file, WORKLOG.md:{i}", "a PASS with an empty diff is a refusal: require a file in OWNS to change, or lane it CENSUS")
    if ln.startswith("## ") and "|" in ln:
        cells = [c.strip() for c in ln[3:].split("|")]
        st = next((c.split()[0].upper() for c in cells if re.match(r"(PASS|FAIL|STOP|RED)\b", c, re.I)), None)
        cid = next((c for c in cells if re.fullmatch(r"[A-Z]+-?[A-Z0-9.]*\d[\w.]*", c)), None)
        if st and cid:
            runs[cid].append((st, i))
            cur = (cid, st)
for cid, r in runs.items():
    bad = [x for x in r if x[0] in ("FAIL", "STOP")]
    # a card whose latest run PASSed, or that a later entry says it replaces/supersedes, is resolved, not unstable
    if r[-1][0] == "PASS" or re.search(rf"(replaces|supersedes|superseded by)\W+(\w+\W+)?{re.escape(cid)}\b", wl_text, re.I):
        continue
    if len(bad) >= 3:
        sug("third-fail", f"{cid}: {len(bad)} FAIL/STOP of {len(r)} runs, WORKLOG.md:{bad[0][1]}", "3+ failures = the design is wrong, not the card: STOP, a QUESTION with options, no further attempt")
    elif len(bad) >= 2:
        sug("unstable-card", f"{cid}: {len(bad)} FAIL/STOP of {len(r)} runs, WORKLOG.md:{bad[0][1]}", "split the card or add a pre-flight assert; do not re-send it unchanged")
tot = sum(len(r) for r in runs.values())
fails = sum(1 for r in runs.values() for x in r if x[0] in ("FAIL", "STOP"))
if tot >= 10 and fails * 5 > tot:
    sug("high-fail-rate", f"{fails}/{tot} worklog runs FAIL/STOP", "lane every judgement step as SPEC; check card-lint ERRORs were zero before shipping")

# 3. open findings: severity mix and age (two real ledger shapes: table rows and `### AUD-NN | SEV | date | STATUS`)
led = lines(PL / "AUDIT_LEDGER.md")
openr = []
for i, ln in enumerate(led, 1):
    m = re.search(r"\b(AUD-\d+)\b\s*\|\s*(CRIT|HIGH|MED|LOW)\b(.*)", ln)
    if m and re.search(r"\|\s*(OPEN|AUTHOR)\b", m.group(3)):
        openr.append((m.group(1), m.group(2), i))
hi = [x for x in openr if x[1] in ("CRIT", "HIGH")]
if hi:
    sug("open-severe", f"{len(hi)} CRIT/HIGH OPEN: {', '.join(x[0] for x in hi[:5])}, AUDIT_LEDGER.md:{hi[0][2]}", "a card or a QUESTION per finding before any new feature")
if len(openr) >= 8:
    sug("ledger-backlog", f"{len(openr)} OPEN findings", "one cleanup queue; findings older than the last release get WONTFIX or a card")

# 4. ratchet lag: newest measured passing count vs the floor
try:
    floor = json.loads((ROOT / ".aw" / "ratchet.json").read_text(encoding="utf-8")).get("min_tests", 0)
except Exception:
    floor = None
best = None
for p in sorted((PL / "gate_output").glob("*.txt"), key=lambda q: q.stat().st_mtime, reverse=True)[:6] if (PL / "gate_output").is_dir() else []:
    t = "\n".join(lines(p)[-12:])
    m = re.search(r"(\d+) passed|Ran (\d+) tests|count=(\d+)", t)
    if m and "FAIL" not in t.split("\n")[-1]:
        best = (int(next(g for g in m.groups() if g)), p.name)
        break
if floor is not None and best and best[0] - floor >= 10:
    sug("ratchet-lag", f"floor {floor} vs measured {best[0]} in {best[1]}", "Architect only: after a PASSing queue run `aw.py ratchet --raise N --i-am-architect`")

# 4b. stale gate: tracked source newer than the newest gate output = every PASS/number after it is UNPROVEN until the gate is re-run
_g = list((PL / "gate_output").glob("*.txt")) if (PL / "gate_output").is_dir() else []
if _g:
    _t = max(p.stat().st_mtime for p in _g)
    try:
        _tr = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=30).stdout.splitlines()
    except Exception:
        _tr = []
    _nw = [f for f in _tr if not f.startswith((".hermes/", ".aw/")) and (ROOT / f).is_file() and (ROOT / f).stat().st_mtime > _t + 2]
    if _nw:
        sug("stale-gate", f"{len(_nw)} tracked file(s) newer than the newest gate output, e.g. {', '.join(_nw[:3])}", "re-run `bash tools/gate.sh active` before trusting any PASS or WORKLOG number")

# 4c. stale task-start: `aw.py audit` diffs against .aw/task-start, so commits made after it (a kit upgrade, a hand fix) show as "outside OWNS" and audit FAILs on a clean tree
_ts = ROOT / ".aw" / "task-start"
if _ts.is_file():
    try:
        _n = int(subprocess.run(["git", "rev-list", "--count", f"--since={int(_ts.stat().st_mtime)}", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=30).stdout.strip() or 0)
    except Exception:
        _n = 0
    if _n >= 3:  # ponytail: fixed threshold of 3 commits; measured 17 and 12 on two projects, tune if it fires on an active task
        sug("stale-task-start", f"{_n} commits since .aw/task-start", "`aw.py audit` will list files changed by those commits as outside OWNS: run `aw.py start <next card>` before the next audit, and read an `OWNS n outside OWNS` FAIL against this")

# 4d. CR CR LF: a text-mode rewrite on Windows turns every LF into CR CR LF, which changes every byte of an append-only register and trips the ledger tripwire on the next re_audit
_CCL = bytes([13, 13, 10])
_cc = [f.name for f in sorted(PL.glob("*.md")) if _CCL in f.read_bytes()]
if _cc:
    sug("crcrlf", f"{', '.join(_cc[:3])} hold CR CR LF line endings", "re-write as LF with the same bytes otherwise (replace CR CR LF and CR LF by LF), prove the old file is a prefix of the result, then re-record .aw/ledger.json; write registers in binary mode")

# 5. hot files: touched by many worklog entries and not frozen (the places the next regression will come from)
touch = Counter()
for ln in lines(wl):
    m = re.match(r"\s*-\s*(Файлове|Files)\s*:\s*(.*)", ln)
    if m:
        for t in re.findall(r"[\w./\\-]+\.\w{1,5}", m.group(2)):
            touch[t.replace("\\", "/")] += 1
for f, n in [x for x in touch.most_common(8) if not x[0].startswith((".hermes/", ".aw/"))][:3]:
    if n >= 6:
        sug("hot-file", f"{f} touched in {n} worklog entries", "an independent .aw/checks.d check that does not import it, or split the file")

# 6. repeated feedback topics already seen twice but never automated
fb = defaultdict(list)
for i, ln in enumerate(lines(PL / "ARCHITECT_FEEDBACK.md"), 1):
    m = re.match(r"##\s+\S+\s*\|\s*F-\d+\s*\|\s*([^|]+)\|", ln)
    if m:
        fb[m.group(1).strip().lower()].append(i)
for k, v in fb.items():
    if len(v) >= 2 and not re.search(r"AUTOMATED", "\n".join(lines(PL / "ARCHITECT_FEEDBACK.md")[v[0] - 1:v[0] + 1]), re.I):
        sug("repeated-feedback", f"'{k}' x{len(v)}, ARCHITECT_FEEDBACK.md:{v[0]}", "automate it (check/guard/AGENTS line) - see SELF_IMPROVE.md section 2")

# 7. guardrails and steering size (retro: a shipped guard that is switched off, an AGENTS.md that sprawls)
cfg = ROOT / ".git" / "config"
if (ROOT / ".githooks" / "pre-commit").exists() and cfg.exists() and "hooksPath" not in "\n".join(lines(cfg)):
    sug("guardrail-off", ".githooks/pre-commit shipped, core.hooksPath unset", "Author decision: `git config core.hooksPath .githooks` makes integrity a commit-time guard")
ag = ROOT / "AGENTS.md"
if ag.exists() and len(ag.read_text(encoding="utf-8", errors="replace")) > 6500:
    sug("steering-sprawl", f"AGENTS.md is {len(ag.read_text(encoding='utf-8', errors='replace'))} chars (> 6500)", "Author: move mechanical rules to .aw/checks.d, judgement rules behind a pointer, delete no-op sentences")

for o in out:
    print(o)
print("LEARN OK" if not out else f"LEARN SUGGEST {len(out)}")
if "--write" in sys.argv:
    (PL / "LEARN_latest.md").write_text("# LEARN_latest (generated by tools/learn.py, read-only miner; candidates, not findings)\n\n" + "\n".join("- " + o for o in out) + f"\n\n{out and 'LEARN SUGGEST ' + str(len(out)) or 'LEARN OK'}\n", encoding="utf-8")
