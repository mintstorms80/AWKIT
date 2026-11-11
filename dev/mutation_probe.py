#!/usr/bin/env python3
"""Mutation probe: does selftest.py notice a one-token change in a kit file?  (dev tool, stdlib only, never ships into a project)

  python3 -B dev/mutation_probe.py payload/tools/aw.py --n 40 --seed 1 --out rows.jsonl
  python3 -B dev/mutation_probe.py payload/tools/aw.py --replay rows.jsonl --out after.jsonl   # the same mutants on the edited kit

Each mutant = one token changed (== != < > <= >= and or True False swapped, `not` dropped, an integer +1) in a COPY of the kit
under a private temp dir; the copy's own selftest.py is the judge. KILLED = selftest exits non-zero, SURVIVED = it stays green,
so nothing in the suite depends on that token. A survivor is a place to read, not a defect: some are equivalent (a default that
is never used, a number inside a message). The kit tree itself is only read. One selftest per mutant: 8 mutants on 8 workers
took 46 s here. --replay finds each old mutant by the text of its line (GONE = that line no longer exists)."""
import argparse, io, json, os, random, shutil, subprocess, sys, tempfile, tokenize
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
KIT = Path(__file__).resolve().parent.parent
SWAP = {"==": "!=", "!=": "==", "<": ">=", ">": "<=", "<=": ">", ">=": "<", "and": "or", "or": "and", "True": "False", "False": "True"}


def sites(src: str) -> list:
    """Every mutable token as [line, col_from, col_to, old, new, line_text]."""
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    lines, out = src.split("\n"), []
    for i, t in enumerate(toks):
        new = None
        if t.type in (tokenize.OP, tokenize.NAME) and t.string in SWAP:
            new = SWAP[t.string]
        elif t.type == tokenize.NAME and t.string == "not" and toks[i + 1].string != "in" and toks[i - 1].string != "is":
            new = ""
        elif t.type == tokenize.NUMBER and t.string.isdigit():
            new = str(int(t.string) + 1)
        if new is not None and t.start[0] == t.end[0]:
            out.append([t.start[0], t.start[1], t.end[1], t.string, new, lines[t.start[0] - 1]])
    return out


def relocate(row: list, src: str):
    """A site recorded on another revision -> the same token on this one, found by its line text; None when the line is gone."""
    lines = src.split("\n")
    hits = [n for n, ln in enumerate(lines, 1) if ln == row[5]]
    if not hits:
        return None
    return [min(hits, key=lambda n: abs(n - row[0]))] + row[1:]


def run(job, rel: str, src: str, tmp: Path) -> dict:
    idx, s = job
    if s is None:
        return {"id": idx, "verdict": "GONE"}
    ln, a, b, old, new, text = s
    lines = src.split("\n")
    assert lines[ln - 1][a:b] == old, (ln, old)
    lines[ln - 1] = text[:a] + new + text[b:]
    mutant = "\n".join(lines)
    row = {"id": idx, "site": s, "mutant": lines[ln - 1].strip()[:200]}
    try:
        compile(mutant, rel, "exec")
    except SyntaxError:
        return dict(row, verdict="INVALID")
    d = Path(tempfile.mkdtemp(prefix=f"m{idx}_", dir=tmp))
    try:
        shutil.copytree(KIT, d / "kit", ignore=shutil.ignore_patterns(".git", "__pycache__", "desktop.ini"))
        (d / "kit" / rel).write_bytes(mutant.encode("utf-8"))
        (d / "tmp").mkdir()
        env = dict(os.environ, TEMP=str(d / "tmp"), TMP=str(d / "tmp"), TMPDIR=str(d / "tmp"))
        try:
            p = subprocess.run([sys.executable, "-I", "-B", "selftest.py"], cwd=d / "kit", env=env, capture_output=True, timeout=900)
            out = p.stdout.decode("utf-8", "replace").splitlines()
            row.update(verdict="KILLED" if p.returncode else "SURVIVED", fails=[x.strip()[:120] for x in out if x.startswith("FAIL")][:5])
        except subprocess.TimeoutExpired:
            row.update(verdict="KILLED", fails=["timeout"])
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return row


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file", help="kit-relative path of the Python file to mutate, e.g. payload/tools/aw.py")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    ap.add_argument("--replay", help="rows.jsonl of an earlier run: test exactly those mutants again")
    ap.add_argument("--exclude", help="rows.jsonl whose sites are left out of the sample (a held-out sample)")
    ap.add_argument("--out", required=True, help="rows are appended here, one JSON object per mutant")
    a = ap.parse_args()
    src = (KIT / a.file).read_bytes().decode("utf-8")
    load = lambda p: [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]
    if a.replay:
        jobs = [(r["id"], relocate(r["site"], src)) for r in load(a.replay) if r.get("site")]
    else:
        skip = {(r["site"][5], r["site"][1], r["site"][3]) for r in load(a.exclude) if r.get("site")} if a.exclude else set()
        pool = [s for s in sites(src) if (s[5], s[1], s[3]) not in skip]
        random.Random(a.seed).shuffle(pool)
        jobs = list(enumerate(pool[:a.n]))
    tmp = Path(tempfile.mkdtemp(prefix="awkit_mutation_"))
    count: dict = {}
    with ThreadPoolExecutor(a.workers) as ex, open(a.out, "a", encoding="utf-8", newline="\n") as fh:
        for r in ex.map(lambda j: run(j, a.file, src, tmp), jobs):
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            count[r["verdict"]] = count.get(r["verdict"], 0) + 1
            if r["verdict"] == "SURVIVED":
                print(f"SURVIVED {a.file}:{r['site'][0]} {r['site'][3]!r} -> {r['site'][4]!r} | {r['mutant']}", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    k, s = count.get("KILLED", 0), count.get("SURVIVED", 0)
    print(f"MUTATION {a.file} mutants={len(jobs)} killed={k} survived={s} invalid={count.get('INVALID', 0)} gone={count.get('GONE', 0)}"
          + (f" kill-rate={100 * k // (k + s)}%" if k + s else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
