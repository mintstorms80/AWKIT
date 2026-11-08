#!/usr/bin/env python3
"""findings_lint.py <file>... - machine check of analyst FINDING lines (SWARM section 6).
Line format, one finding per line (split on ' | ', the evidence cell may hold more pipes):
  FINDING <id> | CONFIRMED|NEEDS-VALIDATION|REJECTED | <file>:<line> | <claim> | `<command>`   (CONFIRMED, REJECTED)
  FINDING <id> | NEEDS-VALIDATION | <file>:<line> | <claim> | fact: <the ONE unresolved fact>   (no severity assigned: 'severity', or a claim that starts with CRIT/HIGH/MED/LOW)
Last line `FINDINGS-LINT OK n=<k>` or `FINDINGS-LINT FAIL <m>`; exit 1 on FAIL or when a file holds no FINDING line.
It checks shape and evidence presence, not truth: the Architect still re-runs one cited command."""
import re
import sys
from pathlib import Path

SEV = re.compile(r"(?i)\bseverity\b|^\W*(CRIT|CRITICAL|HIGH|MED|MEDIUM|LOW)\b")  # a severity ASSIGNED, not a quoted source word
VERDICTS = ("CONFIRMED", "NEEDS-VALIDATION", "REJECTED")
if len(sys.argv) < 2:
    sys.exit("usage: findings_lint.py <file>... (a green result over zero files is refused)")
bad, n = [], 0
for f in sys.argv[1:]:
    seen = 0
    for i, ln in enumerate(Path(f).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not ln.startswith("FINDING "):
            continue
        seen += 1
        n += 1
        c = [x.strip() for x in ln.split(" | ", 4)]
        where = f"{f}:{i}"
        if len(c) != 5:
            bad.append(f"{where} needs 5 cells, has {len(c)}")
            continue
        head, verdict, loc, claim, ev = c
        if not re.fullmatch(r"FINDING \S+", head):
            bad.append(f"{where} first cell must be 'FINDING <id>', got '{head}'")
        if verdict not in VERDICTS:
            bad.append(f"{where} verdict '{verdict}' is not one of {'/'.join(VERDICTS)}")
        if not re.fullmatch(r".+:\d+", loc):
            bad.append(f"{where} location '{loc}' is not <file>:<line>")
        if not claim:
            bad.append(f"{where} empty claim")
        if verdict == "NEEDS-VALIDATION":
            if not re.match(r"fact:\s*\S", ev):
                bad.append(f"{where} NEEDS-VALIDATION must end with 'fact: <the one unresolved fact>'")
            if SEV.search(claim) or SEV.search(ev):
                bad.append(f"{where} NEEDS-VALIDATION carries a severity word")
        elif verdict in ("CONFIRMED", "REJECTED") and not re.search(r"`[^`]+`", ev):
            bad.append(f"{where} {verdict} needs a backticked command as evidence")
    if not seen:
        bad.append(f"{f} holds no FINDING line")
for b in bad:
    print("  " + b)
print(f"FINDINGS-LINT FAIL {len(bad)}" if bad else f"FINDINGS-LINT OK n={n}")
sys.exit(1 if bad else 0)
