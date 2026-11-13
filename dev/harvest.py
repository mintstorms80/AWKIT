#!/usr/bin/env python3
"""dev/harvest.py - read-only harvest of self-improvement candidates across kit projects (author-side, never installed). Stdlib only.
  python3 dev/harvest.py PROJECT_ROOT [PROJECT_ROOT ...]
Per project: runs ITS OWN tools/learn.py (cwd = the project, nothing written), reads the PROPOSED rows of PROPOSALS.md and the
topics of ARCHITECT_FEEDBACK.md, and prints one `CANDIDATE <project>:<file>:<line> <family> | <text>` per suggestion. A family
met in >= 2 projects is printed `CROSS <family> projects=<n>`. A project without tools/learn.py prints `SKIP <project> ...`.
Last line: `HARVEST projects=<n> suggestions=<n> families=<n> cross_project=<n>`. Candidates are not findings: the Architect
verifies one cited line, then records a K-NN row in dev/KIT_PROPOSALS.md."""
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def rows(p: Path) -> list:
    try:
        return p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def harvest(root: Path) -> list:
    """(cite, family, text) for one project; learn.py runs with the project as cwd and its own interpreter flags."""
    out, pl = [], root / ".hermes" / "plans"
    r = subprocess.run([sys.executable, "-I", "-B", str(root / "tools" / "learn.py"), str(root)], cwd=root,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    for ln in r.stdout.splitlines():
        m = re.match(r"LEARN SUGGEST (\S+) \| (.*)", ln)
        if m:
            c = re.search(r"([\w.-]+\.\w+):(\d+)", m.group(2))
            out.append((f"{c.group(1)}:{c.group(2)}" if c else "learn.py", m.group(1), m.group(2)))
    for i, ln in enumerate(rows(pl / "PROPOSALS.md"), 1):
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) >= 7 and re.fullmatch(r"P-\d+", c[0]) and c[-2].upper() == "PROPOSED":
            out.append((f"PROPOSALS.md:{i}", "proposed", f"{c[0]} {c[2][:160]}"))
    for i, ln in enumerate(rows(pl / "ARCHITECT_FEEDBACK.md"), 1):
        m = re.match(r"##\s+\S+\s*\|\s*F-\d+\s*\|\s*([^|]+)\|", ln)
        if m:
            out.append((f"ARCHITECT_FEEDBACK.md:{i}", "feedback:" + m.group(1).strip().lower(), ln.strip()[:160]))
    return out


def main(argv=None) -> int:
    roots = [Path(a) for a in (sys.argv[1:] if argv is None else argv)]
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    fam, n_sug, n_proj = defaultdict(set), 0, 0
    for root in roots:
        if not (root / "tools" / "learn.py").is_file():
            print(f"SKIP {root.name} no tools/learn.py")
            continue
        n_proj += 1
        for cite, f, text in harvest(root):
            n_sug += 1
            fam[f].add(root.name)
            print(f"CANDIDATE {root.name}:{cite} {f} | {text}")
    cross = sorted(f for f, ps in fam.items() if len(ps) >= 2)
    for f in cross:
        print(f"CROSS {f} projects={len(fam[f])}")
    print(f"HARVEST projects={n_proj} suggestions={n_sug} families={len(fam)} cross_project={len(cross)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
