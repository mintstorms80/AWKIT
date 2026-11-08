#!/usr/bin/env python3
"""review_pack.py [<fixed-point> [out_file]] - ONE file for the Reviewer: commit list, stat and full diff <ref>...HEAD.
No arguments = the newest tag (`git describe --tags --abbrev=0`): the pre-release review. Exit 2 BEFORE any reviewer starts when the ref does not resolve or the diff is empty (a bad ref must fail here, not inside two analysts).
Committed work only: uncommitted changes are not in a <ref>...HEAD diff, so commit first. The diff may hold secrets: the Architect reads it before it is handed on."""
import subprocess
import sys
from pathlib import Path


def git(*a):
    r = subprocess.run(["git", *a], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout


if len(sys.argv) < 2:
    ref = git("describe", "--tags", "--abbrev=0")[1].strip()
    if not ref:
        sys.exit("usage: review_pack.py [<fixed-point> [out_file]]  (no argument and no tag to default to)")
else:
    ref = sys.argv[1]
if git("rev-parse", "--verify", "--quiet", ref + "^{commit}")[0]:
    print(f"REVIEW-PACK FAIL ref does not resolve: {ref}")
    sys.exit(2)
diff = git("diff", "-U8", f"{ref}...HEAD")[1]
if not diff.strip():
    print(f"REVIEW-PACK FAIL empty diff {ref}...HEAD")
    sys.exit(2)
log = git("log", "--oneline", f"{ref}..HEAD")[1]
stat = git("diff", "--stat", f"{ref}...HEAD")[1]
out = Path(sys.argv[2] if len(sys.argv) > 2 else ".hermes/plans/gate_output/review_pack.diff")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(f"# commits\n{log}\n# stat\n{stat}\n# diff\n{diff}", encoding="utf-8", newline="\n")
print(f"REVIEW-PACK OK {out} files={stat.count('|')} lines={len(diff.splitlines())}")
