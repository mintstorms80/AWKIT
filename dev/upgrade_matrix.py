#!/usr/bin/env python3
"""dev/upgrade_matrix.py - author-side upgrade matrix and optional live-project copy replay (stdlib only).
  python3 dev/upgrade_matrix.py [--replay DESKTOP_DIR]
For every distinct version in the git history of payload/.aw/KIT_VERSION: exports that commit, installs a temp project with THAT
version's init_project.py, appends a WORKLOG entry, commits, runs the current upgrade_project.py --apply, then verifies:
  init_project.py --check => engine_diff=0 missing=0, ENV missing_keys=0, LAUNCHER missing=0
  STATE files (WORKLOG, PLAN_latest, AUDIT_LEDGER, ratchet.json) sha256 unchanged
  tools/aw.py doctor => fail=0
  second upgrade_project.py --apply => replace=0 add=0 local=0 keys=0
A version whose installer fails on this Python is printed as `SKIP <v> <reason>` (never hidden).
Last line: `UPGRADE-MATRIX PASS versions=<n> failed=0` (or FAIL). With `--replay DESKTOP_DIR`, also copies every kit project of DESKTOP_DIR (a folder with .aw/KIT_VERSION) into
a scratch directory (originals read-only) and runs upgrade_project.py on each copy."""
from __future__ import annotations

import contextlib
import hashlib
import io
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT))
import init_project as ip  # noqa: E402
import upgrade_project as up  # noqa: E402

PY = sys.executable
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _rm(fn, p, *_):
    os.chmod(p, stat.S_IWRITE)
    fn(p)


def run(args, cwd=None, env=None):
    e = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    e["PYTHONIOENCODING"] = "utf-8"
    e.update(env or {})
    r = subprocess.run(args, cwd=str(cwd or KIT), env=e, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    return r.returncode, (r.stdout + r.stderr).strip()


def call_fn(fn, *a, **kw) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*a, **kw)
    return rc, buf.getvalue().strip()


def versions():
    vmap = up.git_versions()
    vmap.pop(up.PAYLOAD.joinpath(".aw/KIT_VERSION").read_text(encoding="utf-8").strip(), None)  # the target itself is not an upgrade source
    return sorted(vmap.items(), key=lambda kv: tuple(int(x) for x in kv[0].split(".")))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_matrix(tmp: Path) -> tuple[int, int]:
    cfg = tmp / "gitconfig"
    cfg.write_text("[user]\n\tname = Matrix\n\temail = m@e.invalid\n", encoding="utf-8", newline="\n")
    genv = {"GIT_CONFIG_GLOBAL": str(cfg)}
    vlist = versions()
    need = {"2.8.1", "2.8.4"} | ({"2.6.4"} if vlist[0][0] != "2.8.0" else set())  # the public copy's history starts at 2.8.0
    assert need <= {v for v, _ in vlist}, f"missing required versions {need - {v for v, _ in vlist}}"
    passed = failed = 0
    for v, h in vlist:
        ok_dir = tmp / f"kit_{v}"
        ok_dir.mkdir(parents=True, exist_ok=True)
        ar = subprocess.run(["git", "-C", str(KIT), "archive", h], capture_output=True, check=True)
        with tarfile.open(fileobj=io.BytesIO(ar.stdout)) as tf:
            tf.extractall(ok_dir, filter="data")
        proj = tmp / f"proj_{v}"
        rc_i, out_i = run([PY, "-I", "-B", str(ok_dir / "init_project.py"), str(proj), "--name", f"P_{v}", "--lang", "bg", "--owner", "Owner"])
        if rc_i != 0:
            print(f"SKIP {v} installer rc={rc_i}: {out_i.splitlines()[-1] if out_i else ''}")
            continue
        wl = proj / ".hermes/plans/WORKLOG.md"
        wl.write_text(wl.read_text(encoding="utf-8") + f"\n## T-001 | 2026-11-12T00:00:00+02:00 | PASS | seed {v}\n", encoding="utf-8", newline="\n")
        state_paths = (".hermes/plans/WORKLOG.md", ".hermes/plans/PLAN_latest.md", ".hermes/plans/AUDIT_LEDGER.md", ".aw/ratchet.json")
        s_before = {rel: sha(proj / rel) for rel in state_paths if (proj / rel).is_file()}
        run(["git", "init", "-q"], cwd=proj, env=genv)
        run(["git", "add", "-A"], cwd=proj, env=genv)
        run(["git", "commit", "-q", "-m", f"seed {v}"], cwd=proj, env=genv)
        rc_u1, out_u1 = call_fn(up.upgrade, proj, True)
        rc_c, out_c = call_fn(ip.check, proj)
        rc_d, out_d = run([PY, "-I", "-B", "tools/aw.py", "doctor"], cwd=proj)
        rc_u2, out_u2 = call_fn(up.upgrade, proj, True)
        s_after = {rel: sha(proj / rel) for rel in s_before}
        ok = (rc_u1 == 0 and rc_c == 0 and "ENV missing_keys=0" in out_c and "LAUNCHER missing=0" in out_c
              and "KIT-CHECK engine_same=" in out_c and "engine_diff=0 missing=0" in out_c
              and s_before == s_after and rc_d == 0 and "fail=0" in out_d
              and rc_u2 == 0 and "replace=0 add=0 local=0 keys=0" in out_u2)
        print(f"{'PASS' if ok else 'FAIL'} {v} ({h}) -> {out_u1.splitlines()[-3] if len(out_u1.splitlines()) >= 3 else out_u1[-120:]}")
        if ok:
            passed += 1
        else:
            failed += 1
            print("  DETAIL:", out_c[-200:], out_d[-200:], out_u2[-200:])
    return passed, failed


def copy_live_project(src: Path, dst: Path, genv: dict):
    skip = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "source"}
    for sub in (".aw", ".githooks", ".hermes", "tools", "tests"):
        sdir = src / sub
        if not sdir.is_dir():
            continue
        for root, dirs, files in os.walk(sdir):
            dirs[:] = [d for d in dirs if d not in skip]
            rel_root = Path(root).relative_to(src)
            (dst / rel_root).mkdir(parents=True, exist_ok=True)
            for f in files:
                if (rel_root.name in ("backups", "gate_output") and f != ".gitkeep") or (rel_root.name == "cards" and f != "QUEUE.template.md"):
                    continue
                shutil.copyfile(Path(root) / f, dst / rel_root / f)
    for f in src.iterdir():
        if f.is_file() and (f.suffix in (".cmd", ".md") or f.name in (".gitignore", ".gitattributes")):
            shutil.copyfile(f, dst / f.name)
    r_head = subprocess.run(["git", "-C", str(src), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    run(["git", "init", "-q"], cwd=dst, env=genv)
    if r_head.returncode == 0:
        run(["git", "add", "-A"], cwd=dst, env=genv)
        run(["git", "commit", "-q", "-m", "live snapshot"], cwd=dst, env=genv)


def run_replay(desk: Path, tmp: Path) -> int:
    """Every folder of DESKTOP_DIR that holds .aw/KIT_VERSION, copied (originals read-only) and upgraded; a copy without a first commit gets one."""
    cfg = tmp / "gitconfig"
    genv = {"GIT_CONFIG_GLOBAL": str(cfg)}
    names = sorted(d.name for d in desk.iterdir() if d.is_dir() and (d / ".aw/KIT_VERSION").is_file())
    bad = 0
    for name in names:
        src = desk / name
        dst = tmp / "replay" / name
        copy_live_project(src, dst, genv)
        rc, out = call_fn(up.upgrade, dst, True)
        if rc == 2 and "no git commit" in out:
            run(["git", "add", "-A"], cwd=dst, env=genv)
            run(["git", "commit", "-q", "-m", "seed"], cwd=dst, env=genv)
            rc, out = call_fn(up.upgrade, dst, True)
        last = next((ln for ln in reversed(out.splitlines()) if ln.startswith(("KIT-UPGRADE", "REFUSED:"))), out[-120:])
        rc_c, out_c = call_fn(ip.check, dst)
        chk = next((ln for ln in reversed(out_c.splitlines()) if ln.startswith("KIT-CHECK")), "-")
        ok = rc == 0 and "missing=0" in chk  # a LOCAL engine file stays LOCAL (engine_diff counts it): only a missing file is a failure
        print(f"REPLAY {'OK' if ok else 'BAD'} {name}: rc={rc} {last} | {chk}")
        bad += not ok
    print(f"REPLAY-LIVE {'PASS' if not bad else 'FAIL'} projects={len(names)} failed={bad}")
    return bad


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    tmp = Path(tempfile.mkdtemp(prefix="awkit_matrix_"))
    try:
        passed, failed = run_matrix(tmp)
        r_bad = 0
        if "--replay" in argv:
            desk = Path(argv[argv.index("--replay") + 1])
            r_bad = run_replay(desk, tmp)
        tot_fail = failed + r_bad
        print(f"UPGRADE-MATRIX {'PASS' if not tot_fail else 'FAIL'} versions={passed} failed={tot_fail}")
        return 1 if tot_fail else 0
    finally:
        getattr(shutil, "rm" + "tree")(tmp, **{"onexc" if sys.version_info >= (3, 12) else "onerror": _rm})


if __name__ == "__main__":
    sys.exit(main())
