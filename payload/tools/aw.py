#!/usr/bin/env python3
"""aw.py - Architect<->Worker kit engine v2. One file, stdlib only (>=3.9), no network.

  gate [label]                        run TEST_CMD, enforce count >= floor, no failure pattern; tail -> gate_output/
  audit [T-NNN]                       gate + integrity + secrets + OWNS + state tripwire + WORKLOG freshness + ledger block
  integrity [--write-baseline --i-am-architect] [--allow g1,g2]
                                      frozen manifest (implicit core + .aw/frozen.txt) + .aw/checks.d metrics
  ratchet [--raise N --i-am-architect] test-count floor: only rises; a lowered file is reported as RATCHET-LOWERED
  doctor                              read-only environment/kit health: python, PY, TEST_CMD, PYTHONPATH, bash/WSL, LF, git
  start T-NNN                         begin a card: state fingerprint + file snapshot (OWNS + tripwire baseline)
  restore T-NNN [--dry-run] [--force] copy backups/T-NNN/** back over the originals; never deletes, lists NEW files
  backup T-NNN path [path..]          copy files to .hermes/plans/backups/T-NNN/ (refuses to overwrite)
  patch FILE OLD.txt NEW.txt          assert-once replace: OLD must occur exactly once; keeps each line's ending
  report                              .hermes/plans/REPORT_latest.md (<=60 lines): kit, next id, queue, doctor
  ask "text"                          append Q-NNN to QUESTIONS.md (worker channel; cannot forge ANSWER/## lines)
  answer Q-NNN "text"                 append the author/architect answer line
  next-id [T|CHK|SPEC|AUD|F|P|Q|D|M|W|PH]   next free id from the union of every register, card and gate output
  card-lint CARD|ID [--strict]        card check, a SUBSET of docs/CARD_LINT_RULES.md (docs/HONEST_LIMITS.md); last line CARD-LINT OK|FAIL
  queue-check QUEUE.md                Chain line grammar + card files + ran= arithmetic + OWNS overlap
  modules                             validate the MODULES.md registry: ids, deps, cycles, waves, one owner per file
  improve                             read-only self-improve check: open/ignored F-NNN, repeated topics, proposals not VERIFIED

Exit codes: 0 ok, 1 check failed, 2 usage/config error. Every error names its fix.
Secrets: findings print FILE:LINE and the rule name, NEVER the matched text.
"""
from __future__ import annotations
import difflib
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; PLANS = ROOT / ".hermes/plans"; AW = ROOT / ".aw"
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "backups", "kit_stage", ".pytest_cache", ".ruff_cache", ".mypy_cache", "dist", "build", "target", "site-packages"}
MAX_SCAN = 2_000_000
# E3: implicit frozen core - always in the manifest, a worker edit shows as FROZEN-CHANGED.
CORE = ("tools/*", ".aw/frozen.txt", ".aw/secrets_allow.txt", ".aw/checks.d/**", ".hermes/prompts/*",
        "AGENTS.md", ".hermes/plans/TASK_CARD.template.md")
# E4: state files whose fingerprint `start` records and `audit T-NNN` re-checks (LAW-9).
STATE = ("ratchet.json", "baseline.json", "frozen.txt", "secrets_allow.txt"); ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,39}$")
def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
def die(msg: str, code: int = 2) -> None:
    print(msg); sys.exit(code)
def to_int(v) -> int:
    try: return int(v)
    except (TypeError, ValueError): return 0
def read_env(keys: dict[str, str] | None = None) -> dict[str, str]:
    out = dict(keys or {}); p = ROOT / "tools/kit.env"
    if not p.is_file(): return out
    try: txt = rtext(p)
    except OSError: return out
    for ln in txt.replace("\r\n", "\n").split("\n"):
        if ln.strip() and not ln.lstrip().startswith("#") and "=" in ln: k, v = ln.split("=", 1); out[k.strip()] = v.strip()
    return out
def cfg() -> dict[str, str]:
    if not (ROOT / "tools/kit.env").is_file():
        die("tools/kit.env missing -> run `python3 init_project.py <this dir> --name <Project>` to install it", 2)
    c = read_env()
    for k in ("TIMEOUT_S", "WORKLOG_STALE_S"):
        if c.get(k) is not None:
            try: int(c[k])
            except ValueError: die(f"tools/kit.env: {k}={c[k]!r} is not an integer -> fix it (e.g. {k}=900)", 2)
    for k, dflt in (("COUNT_REGEX", r"(\d+) passed"), ("FAIL_REGEX", r"$^")):
        try: rx = re.compile(c.get(k) or dflt)
        except re.error as e: die(f"tools/kit.env: {k} is not a valid regex ({e}) -> fix it, e.g. COUNT_REGEX=(\\d+) passed", 2)
        if k == "COUNT_REGEX" and rx.groups < 1: die("tools/kit.env: COUNT_REGEX needs one capture group -> e.g. COUNT_REGEX=(\\d+) passed", 2)
    return c
def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")
def rtext(p: Path) -> str:
    """Read text without newline translation (Path.read_text(newline=) is 3.13+): an LF file must stay LF."""
    with open(p, encoding="utf-8-sig", errors="replace", newline="") as f:
        return f.read()


def _fresh(p: Path) -> None:
    """A file written a millisecond ago can still stat with its OLD size on Windows: force a re-stat."""
    try:
        os.utime(p, None)
    except OSError:
        pass


def jload(p: Path, default):
    _fresh(p)
    try: return json.loads(rtext(p))
    except (OSError, ValueError): return default
def write_utf8(p: Path, text: str) -> None:
    """Atomic, LF-only, mode-preserving: a crashed/parallel run must never leave a half-written register."""
    p.parent.mkdir(parents=True, exist_ok=True); tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(text.encode("utf-8"))  # bytes: no CRLF translation on Windows
    try:
        if p.exists(): os.chmod(tmp, p.stat().st_mode)  # keep the exec bit of a rewritten script
    except OSError:
        pass
    os.replace(tmp, p)
def jsave(p: Path, obj) -> None:
    write_utf8(p, json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
def append_log(text: str) -> None:
    p = AW / "baseline.log"; p.parent.mkdir(parents=True, exist_ok=True); head = ""
    if p.is_file():
        b = p.read_bytes()
        if b and not b.endswith(b"\n"): head = "\n"
    with p.open("ab") as f: f.write((head + text).encode("utf-8"))
def matches(rel: str, globs) -> bool:
    return any(fnmatch.fnmatch(rel, g.strip()) for g in globs if g and g.strip())
def walk(links: bool = False):
    stack = [str(ROOT)]; ln = len(str(ROOT)) + 1
    while stack:
        d = stack.pop()
        try: entries = list(os.scandir(d))
        except OSError: continue
        for e in entries:
            try: is_dir = e.is_dir(follow_symlinks=False)
            except OSError: continue
            if is_dir:
                if e.name not in SKIP_DIRS: stack.append(e.path)
                continue
            yield Path(e.path), e.path[ln:].replace(os.sep, "/")
def files():
    return walk(False)
def snap() -> dict:
    out: dict[str, list] = {}
    for p, rel in walk(True):
        try: st = p.lstat()
        except OSError: continue
        out[rel] = [st.st_size, st.st_mtime_ns]
    return out
def find_bash() -> str | None:
    cands: list[str] = []
    if os.environ.get("AW_BASH"): cands.append(os.environ["AW_BASH"])
    w = shutil.which("bash")
    if w: cands.append(w)
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", "C:/Program Files"), os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", "")):
            if base: cands += [base + "/Git/bin/bash.exe", base + "/Git/usr/bin/bash.exe", base + "/Programs/Git/bin/bash.exe"]
    else: cands += ["/bin/bash", "/usr/bin/bash"]
    for c in cands:
        try:
            p = Path(c)
            if not p.is_file(): continue
        except OSError: continue
        low = str(p).lower().replace("\\", "/")
        if "/windows/system32/" in low or "/windowsapps/" in low or "/microsoft/windowsapps/" in low: continue  # the WSL launcher, not a shell
        return str(p)
    return None
def chk_id(v: str) -> str:
    if not ID_RE.match(v or ""):
        die(f"invalid id {v!r} -> ids look like T-001, CHK-003, SPEC-002, W-12 (letters, digits, '.', '-', '_'; no path separators)", 2)
    return v
def argp(args: list[str], booleans: tuple[str, ...] = (), valued: tuple[str, ...] = ()):
    pos: list[str] = []; fl: set[str] = set(); kv: dict[str, str] = {}
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-h", "--help"): fl.add("--help")
        elif a in booleans: fl.add(a)
        elif a in valued:
            if i + 1 >= len(args): die(f"{a} needs a value -> e.g. {a} 5", 2)
            kv[a] = args[i + 1]; i += 1
        elif a.startswith("-") and a not in ("-", "--"): die(f"unknown flag {a} -> see `aw.py --help`", 2)
        else: pos.append(a)
        i += 1
    return pos, fl, kv
# ---------------------------------------------------------------- gate
def gate_file(label: str | None) -> Path:
    name = re.sub(r"[^A-Za-z0-9._-]", "_", (label or "gate")).lstrip(".") or "gate"; return PLANS / "gate_output" / f"{name}.txt"
def floor_now() -> tuple[int, int]:
    rat = to_int(jload(AW / "ratchet.json", {}).get("min_tests", 0)); base = to_int(jload(AW / "baseline.json", {}).get("floor", 0))
    return max(rat, base), base
def run_gate(label: str | None, c: dict[str, str]) -> tuple[bool, str, int, int]:
    cmd = c.get("TEST_CMD", "")
    if not cmd: die("tools/kit.env: TEST_CMD is empty -> set the ONE command that runs your suite (e.g. TEST_CMD=python3 -m pytest -q)", 2)
    cwd = ROOT / c.get("TEST_DIR", ".")
    if not cwd.is_dir(): die(f"TEST_DIR={c.get('TEST_DIR')!r} is not a directory under {ROOT} -> fix tools/kit.env", 2)
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=to_int(c.get("TIMEOUT_S", "900")), env=_clean_env())
        out, code = (r.stdout or "") + (r.stderr or ""), r.returncode
    except subprocess.TimeoutExpired: out, code = "TIMEOUT", 124
    except OSError as e: out, code = f"cannot run TEST_CMD: {e}", 127
    floor, _ = floor_now(); count = 0
    try:
        ms = re.findall(c.get("COUNT_REGEX") or r"(\d+) passed", out)
        if ms: m0 = ms[-1]; count = to_int(m0 if isinstance(m0, str) else m0[0])
    except (ValueError, IndexError, re.error): count = 0
    try: red = bool(re.search(c.get("FAIL_REGEX") or r"$^", out))
    except re.error: red = False
    reasons = []
    if code != 0: reasons.append(f"exit={code}")
    if red: reasons.append("failure-pattern")
    if count == 0: reasons.append("no-count-parsed")
    elif count < floor: reasons.append(f"count<{floor}")
    ok = not reasons; tail = "\n".join(out.strip().splitlines()[-20:]); f = gate_file(label); f.parent.mkdir(parents=True, exist_ok=True)
    write_utf8(f, f"$ {cmd}\n(cwd={c.get('TEST_DIR', '.')}) {now()}\n{tail}\n")
    line = f"GATE {'OK' if ok else 'FAIL'} count={count} min={floor}" + ("" if ok else " reason=" + ",".join(reasons))
    return ok, line, count, floor
def cmd_gate(pos, fl, kv) -> int:
    if len(pos) > 1: die("usage: aw.py gate [label] -> the label names gate_output/<label>.txt", 2)
    label = pos[0] if pos else None; ok, line, _, _ = run_gate(label, cfg()); print(line)
    if not ok:
        gf = gate_file(label)
        tail = rtext(gf).splitlines()[-20:] if gf.is_file() else ["(no gate file)"]
        print("\n".join(tail))
    return 0 if ok else 1
def cmd_ratchet(pos, fl, kv) -> int:
    p = AW / "ratchet.json"; cur = to_int(jload(p, {}).get("min_tests", 0))
    if "--raise" in kv:
        if "--i-am-architect" not in fl:
            die("ratchet --raise is architect-only -> add --i-am-architect (LAW-9: the worker never moves the floor)", 2)
        try: n = int(kv["--raise"])
        except ValueError: die(f"--raise needs an integer, got {kv['--raise']!r} -> e.g. ratchet --raise 602 --i-am-architect", 2)
        if n < cur: die(f"REFUSED: floor only rises ({cur} -> {n}) -> to lower it, delete .aw/baseline.json first (architect act, logged)", 1)
        jsave(p, {"min_tests": n}); base = jload(AW / "baseline.json", {})
        if to_int(base.get("version", 1)) >= 2:  # E5: the shadow floor follows the architect, never falls below the raise
            base["floor"] = max(to_int(base.get("floor", 0)), n); jsave(AW / "baseline.json", base)
        append_log(f"{now()} ratchet {cur}->{n}\n"); cur = n
    print(f"RATCHET min_tests={cur}"); return 0
# ---------------------------------------------------------------- integrity
def metrics() -> tuple[dict[str, int], dict[str, int], list[str]]:
    m: dict[str, int] = {}; z: dict[str, int] = {}; errs: list[str] = []
    d = AW / "checks.d"; bash = None
    for s in sorted(d.glob("*")) if d.is_dir() else []:
        if s.name.startswith(("README", ".")) or not s.is_file() or s.suffix not in (".py", ".sh"):
            continue  # only *.py / *.sh run; "*.disabled" and docs are ignored
        if s.suffix == ".py": runner = [sys.executable, "-I", "-B", str(s)]
        else:
            bash = bash or find_bash()
            if not bash:
                errs.append(f"{s.name}: no bash (set AW_BASH or install git-bash)")
                continue
            runner = [bash, str(s)]
        try:
            r = subprocess.run(runner, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=600, env=_clean_env())
        except (OSError, subprocess.SubprocessError) as e:
            errs.append(f"{s.name}: {type(e).__name__}")
            continue
        if r.returncode != 0: errs.append(f"{s.name}: exit {r.returncode}")
        for ln in (r.stdout or "").splitlines():
            t = ln.split()
            if len(t) == 3 and t[0] in ("METRIC", "ZERO") and t[2].lstrip("-").isdigit():
                (m if t[0] == "METRIC" else z)[f"{s.stem}.{t[1]}"] = int(t[2])
    return m, z, errs
def frozen_globs() -> list[str]:
    fz = AW / "frozen.txt"
    if not fz.is_file(): return []
    return [ln.strip() for ln in rtext(fz).splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
def is_core(rel: str) -> bool:
    return matches(rel, CORE)
def manifest() -> dict[str, str]:
    globs = frozen_globs(); out: dict[str, str] = {}
    for p, rel in files():
        if not (is_core(rel) or matches(rel, globs)): continue
        try: out[rel] = sha(p.read_bytes())
        except OSError: continue
    return out
def cmd_integrity(pos, fl, kv) -> int:
    return _integrity(fl, kv)[0]
def _integrity(fl, kv) -> tuple[int, str]:
    man = manifest(); m, z, errs = metrics(); bp = AW / "baseline.json"
    allow: list[str] = []
    if "--allow" in kv: allow = [x.strip() for x in kv["--allow"].split(",") if x.strip()]
    user = sum(1 for k in man if not is_core(k)); core = len(man) - user
    if "--write-baseline" in fl:
        if "--i-am-architect" not in fl: die("--write-baseline is architect-only -> add --i-am-architect (LAW-9)", 2)
        old = jload(bp, {}); ceil = {k: min(v, old.get("ceilings", {}).get(k, v)) for k, v in m.items()}
        rat = to_int(jload(AW / "ratchet.json", {}).get("min_tests", 0)); oldfloor = to_int(old.get("floor", 0)) if to_int(old.get("version", 1)) >= 2 else 0
        floor = max(rat, oldfloor)
        if rat < oldfloor:
            print(f"WARN ratchet.json min_tests={rat} < recorded floor {oldfloor} -> the baseline keeps {oldfloor} (only the architect raises it)")
        jsave(bp, {"version": 2, "ceilings": ceil, "manifest": man, "floor": floor})
        append_log(f"{now()} baseline files={user} core={core} metrics={len(ceil)} floor={floor}\n")
        msg = f"BASELINE WRITTEN files={user} metrics={len(ceil)} core={core} floor={floor} (record it in AUDIT_LEDGER)"; print(msg)
        return 0, msg
    if not bp.is_file():
        msg = "INTEGRITY UNMEASURED no .aw/baseline.json (architect: integrity --write-baseline --i-am-architect)"; print(msg)
        return 0, msg
    base = jload(bp, {}); legacy = to_int(base.get("version", 1)) < 2; bad: list[str] = [f"ZERO {k}={v}" for k, v in z.items() if v]
    for k, v in m.items():
        ceil = base.get("ceilings", {}).get(k)
        if ceil is None: bad.append(f"NEW-METRIC {k}={v} (not in baseline)")
        elif v > ceil: bad.append(f"METRIC {k}={v} > ceiling {ceil}")
    bad += [f"MISSING-METRIC {k}" for k in base.get("ceilings", {}) if k not in m]; bman = base.get("manifest", {})
    if legacy:  # a v1 baseline never recorded the implicit core: show it, do not fail on it (upgrade path)
        changed = [k for k in sorted(set(man) & set(bman)) if man.get(k) != bman.get(k) and not matches(k, allow)]
        if any(is_core(k) for k in man if k not in bman):
            print("WARN core files not in a v1 baseline -> architect: integrity --write-baseline --i-am-architect (E3 protection starts there)")
    else:
        changed = [k for k in sorted(set(man) | set(bman)) if man.get(k) != bman.get(k) and not matches(k, allow)]
        rat = to_int(jload(AW / "ratchet.json", {}).get("min_tests", 0))
        if rat < to_int(base.get("floor", 0)):
            bad.append(f"RATCHET-LOWERED min_tests={rat} < baseline floor {base.get('floor')} (LAW-9: only the architect raises it)")
    bad += [f"FROZEN-CHANGED {k}" for k in changed]; bad += [f"CHECK-ERROR {e}" for e in errs]
    if bad:
        msg = f"INTEGRITY FAIL {len(bad)}: " + "; ".join(bad[:6]) + (" ..." if len(bad) > 6 else ""); print(msg)
        for b in bad[:12]: print("   ", b)
        return 1, msg
    msg = f"INTEGRITY OK frozen={user} metrics={len(m)} core={core}"; print(msg)
    return 0, msg
# ---------------------------------------------------------------- secrets / owns / tripwire / ledger
SECRET_RULES = [
    ("openai-style-key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("bearer-token", re.compile(r"[Bb]earer\s+[A-Za-z0-9._~+/-]{20,}")),
    ("aws-key-id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("stripe-key", re.compile(r"[sr]k_(live|test)_[A-Za-z0-9]{16,}")),
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("npm-token", re.compile(r"npm_[A-Za-z0-9]{36}")),
    ("pypi-token", re.compile(r"pypi-[A-Za-z0-9_-]{20,}")),
    ("telegram-bot-token", re.compile(r"[0-9]{8,10}:[A-Za-z0-9_-]{35}")),
    ("azure-account-key", re.compile(r"AccountKey=[A-Za-z0-9+/=]{40,}")),
]; SECRET_NAMES = ("auth.json", ".env", "*.pem", "*.key", "id_rsa", "credentials.json")
# E4: files the TOOLS write by themselves during a card. Everything else under .aw/ is a card change (E6).
GENERATED = (".aw/task-start", ".aw/ledger.json")
def secrets_scan() -> tuple[int, list[str]]:
    ap = AW / "secrets_allow.txt"; allow = [ln.strip() for ln in rtext(ap).splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")] if ap.is_file() else []
    by_line = {a for a in allow if re.search(r":\d+$", a)}; by_path = [a for a in allow if a not in by_line]
    gi = [ln.strip() for ln in rtext(ROOT / ".gitignore").splitlines()] if (ROOT / ".gitignore").is_file() else []; bad: list[str] = []
    for p, rel in files():
        if matches(rel, by_path) or rel.startswith(".aw/"): continue
        if p.name != ".env.example" and any(fnmatch.fnmatch(p.name, n) for n in SECRET_NAMES):
            ignored = any(fnmatch.fnmatch(p.name, g.strip("/")) or g.strip("/") == rel for g in gi if g and not g.startswith("#"))
            if ignored: print(f"   WARN FILE {rel} (secret-type name, git-ignored; contents never read)")
            else: bad.append(f"FILE {rel} (secret-type name, NOT in .gitignore)")
            continue
        try:
            if p.is_symlink() or p.lstat().st_size > MAX_SCAN: continue
            txt = rtext(p)
        except (OSError, UnicodeDecodeError): continue
        # split on \n only: str.splitlines() also splits on \f, which shifts the reported line number
        for i, ln in enumerate(txt.split("\n"), 1):
            if f"{rel}:{i}" in by_line: continue  # E2: an exact path:LINE exemption, that line only
            for name, rx in SECRET_RULES:
                if rx.search(ln): bad.append(f"{rel}:{i} rule={name}")
    return len(bad), bad
def start_rec() -> dict:
    p = AW / "task-start"
    if not p.is_file(): return {}
    try:
        rec = json.loads(rtext(p))
        if isinstance(rec, dict): return rec
    except (OSError, ValueError): pass
    try:
        txt = rtext(p).strip(); t0 = p.stat().st_mtime
    except OSError: return {}
    return {"version": 1, "task": txt.split()[0] if txt.split() else "?", "t0": t0}
def state_now() -> dict:
    out: dict = {}
    for n in STATE:
        p = AW / n
        try: out[n] = sha(p.read_bytes()) if p.is_file() else None
        except OSError: out[n] = None
    return out
def baseline_log_size() -> int:
    try: return (AW / "baseline.log").stat().st_size
    except OSError: return 0
def changed_since_start(rec: dict):
    old = rec.get("files")
    if rec.get("version") != 2 or not isinstance(old, dict): return None
    cur = snap(); changed = [k for k, v in cur.items() if old.get(k) != v]; deleted = [k for k in old if k not in cur]; return changed, deleted
def owns_check(owns: list[str], c: dict[str, str]) -> tuple[str, list[str]]:
    rec = start_rec()
    if not rec: return "UNMEASURED (no .aw/task-start: run `aw.py start T-NNN` first)", []
    allowed = owns + [x for x in c.get("ALWAYS_OWNED", "").split(",") if x]; got = changed_since_start(rec)
    if got is None:  # legacy v1 marker: mtime only, deletions invisible
        t0 = rec.get("t0") or 0; ch = [rel for p, rel in files() if rel != ".aw/task-start" and p.stat().st_mtime > t0 + 0.01]
        out = [f for f in ch if not matches(f, allowed) and not f.startswith(".aw/")]
        return (f"{len(out)} outside OWNS" if out else f"ok ({len(ch)} changed, all in OWNS)"), out
    changed, deleted = got
    # Only the state files the tool itself may move are exempt; a worker file under .aw/ (e.g. checks.d) stays visible.
    outside = [x for x in changed + deleted if not matches(x, GENERATED) and not matches(x, allowed)
               and not any(x == f".aw/{n}" for n in STATE + ("baseline.log", "ledger.json"))]
    out = [x if x not in deleted else f"{x} (deleted)" for x in sorted(outside)]
    return (f"{len(out)} outside OWNS" if out else f"ok ({len(changed)} changed, {len(deleted)} deleted, all in OWNS)"), out
def tripwire(rec: dict) -> list[str]:
    out: list[str] = []; cur = state_now()
    for k, v in (rec.get("state") or {}).items():
        if cur.get(k) != v: out.append(f"ARCHITECT-STATE-CHANGED {k}")
    if to_int(rec.get("baseline_log")) != baseline_log_size(): out.append("ARCHITECT-STATE-CHANGED .aw/baseline.log")
    return out
def ledger_tail_warn() -> str:
    lp = PLANS / "AUDIT_LEDGER.md"
    if not lp.is_file(): return ""
    heads = [ln.strip() for ln in rtext(lp).splitlines() if ln.startswith("## ")]
    if heads and not heads[-1].startswith("## 8."):
        return f"WARN ledger section 8 is not last (last is {heads[-1][:40]!r}) -> demote later '## ' headings to '### ' (backup first)"
    return ""
def ledger_append(block: str) -> str:
    lp = PLANS / "AUDIT_LEDGER.md"
    if not lp.is_file(): return "ledger missing"
    data = lp.read_bytes(); st = jload(AW / "ledger.json", {})
    if st and (len(data) < st["len"] or sha(data[: st["len"]]) != st["sha"]):
        return "LEDGER-REWRITTEN (prefix differs from last seen: append-only violated)"
    new = data + (b"" if data.endswith(b"\n") else b"\n") + block.encode("utf-8"); lp.write_bytes(new); jsave(AW / "ledger.json", {"len": len(new), "sha": sha(new)})
    return "ok"
def card_owns(cid: str) -> list[str]:
    """The card's OWNS bullets (closed list). Empty when there is no card or no section."""
    p = card_path(cid)
    if not p or not p.is_file(): return []
    m = re.search(r"^##\s*OWNS[^\n]*\n(.*?)(?=^##\s)", rtext(p), re.M | re.S)
    if not m: return []
    return [ln.strip()[2:].strip().strip("`") for ln in m.group(1).splitlines()
            if ln.strip().startswith(("- ", "* ")) and "<" not in ln]

def cmd_audit(pos, fl, kv) -> int:
    c = cfg()
    if len(pos) > 1: die("usage: aw.py audit [T-NNN] -> one id (the card being closed)", 2)
    task = pos[0] if pos else None
    if task: chk_id(task)
    owns_env = [x for x in os.environ.get("OWNS", "").split(",") if x]; bad = 0; ok, gline, _, _ = run_gate(f"audit-{task or 'adhoc'}", c)
    print(gline); bad += 0 if ok else 1; irc, iline = _integrity(set(), {}); bad += irc
    if "UNMEASURED" in iline:   # no baseline = nothing to compare against: a PASS here would be a silent skip
        print("INTEGRITY-FAIL no baseline -> a card audit needs one: python3 -I -B tools/aw.py integrity --write-baseline --i-am-architect")
        bad += 1
    sn, sl = secrets_scan(); print(f"SECRETS {'OK' if not sn else 'FAIL ' + str(sn)} (names/lines only, never contents)")
    for x in sl[:10]: print("   ", x)
    bad += 1 if sn else 0; rec = start_rec(); ostat, out = owns_check(owns_env, c)
    if task and (not rec or rec.get("task") != task):  # a card audit without its own marker is unmeasurable
        print(f"   NOTE .aw/task-start is {rec.get('task')!r}, not {task!r} -> run `aw.py start {task}` at the card start")
        out = out + ["OWNS UNMEASURED (task-start mismatch)"]
    if task:
        co = card_owns(task)
        if co:
            c_missing = [x for x in co if x not in owns_env]; c_extra = [x for x in owns_env if x not in co]
            if c_missing or c_extra:
                print(f"OWNS-DECLARED differs from the card: missing_from_env={c_missing} not_in_card={c_extra}")
                out = out + ["OWNS-DECLARED (the card is the closed list; the env may not widen it)"]
    print("OWNS", ostat)
    for x in out[:10]: print("    OUT", x)
    bad += 1 if out else 0; sline = ""
    if task:
        ch = tripwire(rec)
        if not (rec.get("state") or {}):
            sline = "state=UNMEASURED (legacy task-start: no fingerprint)"; print("STATE " + sline)
        else:
            print(f"STATE {'ok' if not ch else 'CHANGED (' + str(len(ch)) + ')'}")
            for x in ch: print("    ", x)
            bad += 1 if ch else 0; sline = f"state={'OK' if not ch else 'CHANGED ' + ','.join(ch)[:120]}"
    wl, go = PLANS / "WORKLOG.md", PLANS / "gate_output"; warn = ""
    if wl.is_file() and go.is_dir():
        newest = max((f.stat().st_mtime for f in go.glob("*.txt") if not f.name.startswith("audit-")), default=0)
        if newest and newest - wl.stat().st_mtime > to_int(c.get("WORKLOG_STALE_S", "1800")):
            warn = "WARN WORKLOG older than newest gate_output (missing entry?)"; print(warn)
    lw = ledger_tail_warn()
    if lw: print(lw)
    if task:
        blk = (f"\n### RE-AUDIT {now()} after {task}\n- {gline}\n- {iline}\n- secrets={'OK' if not sn else 'FAIL'} owns={ostat} {sline}".rstrip()
               + (f"\n- {warn}" if warn else "") + f"\n- verdict={'PASS' if not bad else 'FAIL'}\n")
        r = ledger_append(blk); print("LEDGER", r); bad += 0 if r == "ok" else 1
    print("AUDIT " + ("PASS" if not bad else f"FAIL ({bad})")); return 1 if bad else 0
# ---------------------------------------------------------------- worker + architect helpers
def card_paths(cid: str) -> list[Path]:
    return [PLANS / "cards" / f"{cid}.md", PLANS / f"{cid}.md"]  # v2 location first, v1 layout second
def card_path(cid: str) -> Path:
    for p in card_paths(cid):
        if p.is_file(): return p
    return card_paths(cid)[0]
def cmd_start(pos, fl, kv) -> int:
    if not pos: die("usage: aw.py start T-NNN -> run it as the FIRST step of a card", 2)
    tid = chk_id(pos[0]); S = snap()
    rec = {"version": 2, "task": tid, "t0": now(), "state": state_now(), "baseline_log": baseline_log_size(), "files": S}; cp = card_path(tid)
    if cp.is_file():  # a worker that widens its own card later shows up as a state change
        rec["card"] = sha(cp.read_bytes())
    jsave(AW / "task-start", rec); print(f"START {tid}"); print(f"  fingerprint: {len(S)} files, {len(rec['state'])} state file(s) -> `aw.py audit {tid}` re-checks them")
    return 0
def cmd_backup(pos, fl, kv) -> int:
    if len(pos) < 2: die("usage: aw.py backup T-NNN path [path..] -> list every file the card will change", 2)
    tid = chk_id(pos[0])
    for a in pos[1:]:
        src = (ROOT / a).resolve()
        if not src.is_file() or ROOT not in src.parents: die(f"backup: not a file inside the project: {a} -> pass a project-relative path", 1)
        dst = PLANS / "backups" / tid / src.relative_to(ROOT)
        if dst.exists():
            die(f"backup: refuses to overwrite backups/{tid}/{src.relative_to(ROOT).as_posix()} -> same card ran before: use `aw.py restore {tid}` or a new card id", 1)
        dst.parent.mkdir(parents=True, exist_ok=True); b = src.read_bytes(); dst.write_bytes(b)
        print(f"BACKUP {a} sha256={sha(b)[:12]}")
    return 0
def cmd_restore(pos, fl, kv) -> int:
    if not pos: die("usage: aw.py restore T-NNN [--dry-run] [--force] -> run it after a FAIL, before the next card", 2)
    tid = chk_id(pos[0]); src_dir = PLANS / "backups" / tid
    if not src_dir.is_dir():
        die(f"RESTORE REFUSED: no backups/{tid}/ (nothing was backed up, or the card never ran) -> use git: `git status --short`, `git checkout -- <path>`", 1)
    rec = start_rec()
    if rec.get("task") and rec.get("task") != tid and "--force" not in fl:
        die(f"RESTORE REFUSED: backups/{tid}/ was taken for {tid}, .aw/task-start now says {rec.get('task')} -> "
            "review with --dry-run, then add --force (restore never deletes)", 1)
    dry = "--dry-run" in fl
    if rec.get("task") == tid:
        got = changed_since_start(rec)
        if got:
            for rel in sorted(got[0]):
                if not (src_dir / rel).is_file() and not matches(rel, GENERATED):
                    print(f"NOT-RESTORED-NEW {rel} (a file this card created; move it to _to_delete/ by hand - restore never deletes)")
    n = 0
    for p in sorted(src_dir.rglob("*")):
        if not p.is_file(): continue
        rel = p.relative_to(src_dir); dst = ROOT / rel
        try: same = dst.is_file() and dst.read_bytes() == p.read_bytes()
        except OSError: same = False
        if dry: print(f"RESTORE would-{'skip' if same else 'write'} {rel.as_posix()}")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True); dst.write_bytes(p.read_bytes())
            if not same: print(f"RESTORE --write {rel.as_posix()}")
        n += 1
    print(f"RESTORE dry-run: {n} file(s) under backups/{tid}/ (nothing written)" if dry else f"RESTORED {n} file(s) from backups/{tid}/"); return 0
def _split_lines(raw: str):
    """[(content, ending)] - ending is '\\r\\n', '\\n' or '' for the last line."""
    out = []
    for chunk in re.findall(r"[^\n]*\n|[^\n]+$", raw):
        if chunk.endswith("\r\n"):
            out.append((chunk[:-2], "\r\n"))
        elif chunk.endswith("\n"):
            out.append((chunk[:-1], "\n"))
        else: out.append((chunk, ""))
    return out


def cmd_patch(pos, fl, kv) -> int:
    if len(pos) != 3:
        die("usage: aw.py patch FILE OLD.txt NEW.txt -> OLD must occur exactly once in FILE", 2)
    f = (Path.cwd() / pos[0]).resolve() if not Path(pos[0]).is_absolute() else Path(pos[0]).resolve()
    if f != ROOT and ROOT not in f.parents:
        print(f"PATCH REFUSED: {pos[0]} is outside the project root {ROOT} -> patch only files inside the project")
        return 1
    if not f.is_file():
        print(f"PATCH REFUSED: {pos[0]} is not a file -> create it with a quoted heredoc first (LAW-4)")
        return 1
    try:
        old = rtext(Path(pos[1])).replace("\r\n", "\n"); new = rtext(Path(pos[2])).replace("\r\n", "\n"); rawf = f.read_bytes()
        raw = rawf.decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"PATCH REFUSED: cannot read the file or OLD/NEW ({type(e).__name__}) -> write both texts with a quoted heredoc first")
        return 1
    if not old:
        print("PATCH REFUSED: OLD is empty (need exactly 1 occurrence); nothing written")
        return 1
    lines = _split_lines(raw); ol = old.split("\n")
    if ol and ol[-1] == "":
        ol = ol[:-1]          # OLD ends with a newline: compare content only, endings stay the file's own
    nl = new.split("\n")
    if nl and nl[-1] == "":
        nl = nl[:-1]
    if not ol:
        print("PATCH REFUSED: OLD is empty (need exactly 1 occurrence); nothing written")
        return 1
    hits = [i for i in range(len(lines) - len(ol) + 1) if [c for c, _e in lines[i:i + len(ol)]] == ol]
    if len(hits) != 1:
        print(f"PATCH REFUSED: OLD occurs {len(hits)} times (need exactly 1); nothing written")
        print("  -> re-read the file and copy the anchor byte-for-byte (it must be unique), then retry")
        return 1
    i0 = hits[0]; span = lines[i0:i0 + len(ol)]; endings = [e for _c, e in span] or [lines[i0][1]]
    nle = "\r\n" if b"\r\n" in rawf else "\n"; repl = [(c, endings[min(n, len(endings) - 1)]) for n, c in enumerate(nl)]
    repl = [(c, e or nle) for c, e in repl[:-1]] + repl[-1:]  # only the block's last line may lack an ending (EOF): an inner one would glue two lines
    lines = lines[:i0] + repl + lines[i0 + len(ol):]; f.write_bytes("".join(c + e for c, e in lines).encode("utf-8"))
    print("PATCH OK %s (line endings kept: %s)" % (f, "CRLF" if b"\r\n" in rawf else "LF"))
    return 0


def _oneline(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").replace("\r", " ")).strip(); return re.sub(r"(?m)(?<!^)(?=ANSWER\s+Q-\d|#{1,6}\s)", " ", t)
def next_id(kind: str = "T") -> str:
    used: set[int] = set(); rx = re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(kind) + r"-(\d{1,5})(?![0-9])")
    for p, rel in files():
        # craft/example docs quote ids from other projects: never count them as used
        if p.suffix != ".md" or "template" in rel.lower() or rel.rsplit("/", 1)[-1] in ("GUIDE.md", "PLAYBOOK.md", "CARD_PATTERNS.md", "START_BLOCKS.md"):
            continue
        if not (rel.startswith(".hermes/plans/") or rel == "AGENTS.md"): continue
        try: txt = rtext(p)
        except OSError: continue
        # only REGISTER shapes count: a heading row, a card title "# T-001 - ...", a table row. Prose quoting an id is not a used id.
        for line in txt.splitlines():
            m2 = re.match(r"\s*(?:(?:#+\s*|\|\s*)(?:\d{4}-\d{2}-\d{2}\s*\|?\s*)?)?(" + re.escape(kind) + r")-(\d{1,5})(?![0-9])", line)
            if m2: used.add(int(m2.group(2)))
    bdir = PLANS / "backups"
    if bdir.is_dir(): used.update(int(m.group(1)) for m in (rx.match(d.name) for d in bdir.iterdir()) if m)
    n = max(used) + 1 if used else 1; return f"{kind}-{n:02d}" if kind in ("AUD", "F", "P", "D", "M", "W", "PH") else f"{kind}-{n:03d}"
def cmd_next_id(pos, fl, kv) -> int:
    kinds = ("T", "CHK", "SPEC", "AUD", "F", "P", "Q", "D", "M", "W", "PH")
    if not pos: print("\n".join(next_id(k) for k in kinds)); return 0
    k = pos[0].upper()
    if k not in kinds: die(f"unknown id kind {pos[0]!r} -> one of {', '.join(kinds)}", 2)
    print(next_id(k)); return 0
def cmd_ask(pos, fl, kv) -> int:
    if not pos: die('usage: aw.py ask "question" (usually via worker_report.py --ask)', 2)
    qp = PLANS / "QUESTIONS.md"
    if not qp.is_file(): write_utf8(qp, "# QUESTIONS\n")
    n = max([int(x) for x in re.findall(r"^## Q-(\d+)", rtext(qp), re.M)] or [0]) + 1; body = _oneline(" ".join(pos))
    with qp.open("a", encoding="utf-8", newline="\n") as f: f.write(f"\n## Q-{n:03d} | {now()} | OPEN\n> {body}\n")
    print(f"ASKED Q-{n:03d}"); return 0
def cmd_answer(pos, fl, kv) -> int:
    if len(pos) < 2: die('usage: aw.py answer Q-NNN "text" -> the architect/author answers a worker question', 2)
    if not re.match(r"^Q-\d{3,4}$", pos[0]): die(f"answer: {pos[0]!r} is not a question id -> `aw.py next-id Q` or see QUESTIONS.md", 2)
    qp = PLANS / "QUESTIONS.md"; txt = rtext(qp) if qp.is_file() else ""
    if not re.search(rf"^## {re.escape(pos[0])} \|", txt, re.M):
        die(f"answer: {pos[0]} is not in .hermes/plans/QUESTIONS.md -> run `aw.py report` for the open questions", 1)
    body = _oneline(" ".join(pos[1:]))
    if re.match(r"(?i)^(ANSWER\s+Q-\d|#{1,6}\s)", body): body = "> " + body
    with qp.open("a", encoding="utf-8", newline="\n") as f:
        if txt and not txt.endswith("\n"): f.write("\n")
        f.write(f"ANSWER {pos[0]} {time.strftime('%Y-%m-%d')} {body}\n")
    print(f"ANSWERED {pos[0]}"); return 0
def open_questions() -> list[str]:
    qp = PLANS / "QUESTIONS.md"; txt = rtext(qp) if qp.is_file() else ""
    answered = set(re.findall(r"^ANSWER (Q-\d+)", txt, re.M)); return [m for m in re.findall(r"^## (Q-\d+) \|", txt, re.M) if m not in answered]
def queue_progress() -> str:
    qs = sorted(PLANS.glob("cards/QUEUE*.md"), key=lambda p: p.stat().st_mtime) if (PLANS / "cards").is_dir() else []
    qs = [q for q in qs if "template" not in q.name.lower()]
    if not qs: return "queue: none (no .hermes/plans/cards/QUEUE*.md)"
    q = qs[-1]; txt = rtext(q); m = re.search(r"^\s*Chain:\s*base=\d+\s*\|(.+?)\|", txt, re.M); ids = re.findall(r"\b((?:T|CHK|SPEC)-\d{3,5})\s*:", m.group(1)) if m else []
    if not ids: return f"queue: {q.name} (no Chain: line)"
    wl = PLANS / "WORKLOG.md"; wtxt = rtext(wl) if wl.is_file() else ""
    done = [i for i in ids if re.search(rf"^## {re.escape(i)} \|", wtxt, re.M)]
    return f"queue: {q.name} {len(done)}/{len(ids)} in WORKLOG, not done: {' '.join([i for i in ids if i not in done][:6]) or '-'}"
def cmd_report(pos, fl, kv) -> int:
    c = cfg(); ver = rtext(AW / "KIT_VERSION").strip() if (AW / "KIT_VERSION").is_file() else "?"
    out = [f"# REPORT_latest | {c.get('PROJECT_NAME', '?')} | {now()}",
           f"kit={ver} next-card-id={next_id('T')} ratchet min_tests={to_int(jload(AW / 'ratchet.json', {}).get('min_tests', 0))}"]
    g = PLANS / "gate_output"; last = sorted(g.glob("*.txt"), key=lambda p: p.stat().st_mtime)[-1:] if g.is_dir() else []
    out.append("last gate file: " + (f"{last[0].name} @ {time.strftime('%F %T', time.localtime(last[0].stat().st_mtime))}" if last else "none"))
    lg = PLANS / "AUDIT_LEDGER.md"
    heads = re.findall(r"^### RE-AUDIT .*$", rtext(lg), re.M)[-5:] if lg.is_file() else []
    out += ["", queue_progress(), "", "## last re-audits"] + (heads or ["(none)"]); wl = PLANS / "WORKLOG.md"
    wh = re.findall(r"^## .*$", rtext(wl), re.M)[-3:] if wl.is_file() else []
    out += ["", "## last WORKLOG entries"] + (wh or ["(none)"]); q = open_questions()
    out += ["", f"## open questions: {len(q)}"] + q[:10]; out += ["", "## file fingerprints (bytes sha256[:12])"]
    for nm in ("AUDIT_LEDGER.md", "PLAN_latest.md", "QUESTIONS.md", "WORKLOG.md"):
        p = PLANS / nm; out.append(f"{nm}: " + (f"{p.stat().st_size} {sha(p.read_bytes())[:12]}" if p.is_file() else "missing"))
    ds = doctor_checks(); bad = sum(1 for lv, _t, _m in ds if lv == "FAIL"); wrn = sum(1 for lv, _t, _m in ds if lv == "WARN")
    out += ["", f"doctor: {'PASS' if not bad else 'FAIL'} warn={wrn} fail={bad} (full: `aw.py doctor`)"]; out = out[:60]
    write_utf8(PLANS / "REPORT_latest.md", "\n".join(out) + "\n"); print(f"REPORT written ({len(out)} lines)"); return 0
def cmd_improve(pos, fl, kv) -> int:  # read-only self-improve loop check; writes nothing
    fb = PLANS / "ARCHITECT_FEEDBACK.md"; topic: dict = {}; stat: dict = {}; SW = re.compile(r"\b(OPEN|APPLIED|IGNORED|AUTOMATED|CLOSED)\b", re.I)
    for ln in (rtext(fb).splitlines() if fb.is_file() else []):
        cols = [c.strip() for c in ln[3:].split("|")]; ids = re.findall(r"\bF-\d+\b", ln); sw = SW.search(cols[-1]) if len(cols) >= 3 else None
        if not (ln.startswith("## ") and ids and sw): continue                 # templates and notes carry no status word
        s = "APPLIED" if sw.group(1).upper() == "CLOSED" else sw.group(1).upper()
        if len(cols) >= 4 and re.fullmatch(r"F-\d+", cols[1]): topic[cols[1]] = cols[2].lower(); stat[cols[1]] = s   # ## date | F-NNN | topic | STATUS
        else: stat.update({f: s for f in ids})                                  # later update: ## date | status F-014, F-015 | APPLIED
    out = [f"IMPROVE ACTION {k.lower()}-correction {f} ({topic.get(f, '?')})" for k in ("OPEN", "IGNORED") for f in stat if stat[f] == k]
    print("IMPROVE feedback " + " ".join(f"{k}={sum(1 for f in stat if stat[f] == k)}" for k in ("OPEN", "APPLIED", "IGNORED", "AUTOMATED")))
    seen: dict = {}
    for f, tp in topic.items(): seen.setdefault(tp, []).append(f)
    out += [f"IMPROVE ACTION repeated-error '{tp}' {','.join(ids)} -> a PROPOSALS row for an automatic check" for tp, ids in seen.items() if len(ids) >= 2 and tp]
    pp = PLANS / "PROPOSALS.md"; pst: dict = {}
    for ln in (rtext(pp).splitlines() if pp.is_file() else []):
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) >= 6 and re.fullmatch(r"P-\d+", c[0]): pst[c[0]] = c[5].split()[0].upper() if c[5] else "?"
        elif not ln.startswith("|"): pst.update({m[0]: m[1].upper() for m in re.findall(r"\b(P-\d+)\s*(?:->|=>|:|=)\s*(PROPOSED|ACCEPTED|REJECTED|DONE|VERIFIED|NO_EFFECT)\b", ln, re.I)})   # later status line: `P-19 -> DONE (...)`
    ps: dict = {}
    for pid, s in pst.items(): ps.setdefault(s, []).append(pid)
    print("IMPROVE proposals " + (" ".join(f"{k}={len(v)}" for k, v in sorted(ps.items())) or "none"))
    out += [f"IMPROVE ACTION proposal {pid} accepted/done but not VERIFIED" for pid in ps.get("ACCEPTED", []) + ps.get("DONE", [])]
    print("\n".join(out)); print(f"IMPROVE open-questions={len(open_questions())}"); print("IMPROVE OK" if not out else f"IMPROVE ACTION {len(out)}"); return 0
# ---------------------------------------------------------------- card grammar (card-lint + queue-check)
# Data copied verbatim from e-cards/CARD_LINT_RULES.md section 3 (SPEC_DATA); rule ids are stable.
ID = r"(?:T|CHK|SPEC)-\d{3,5}"; IDS = rf"{ID}(?:\s*,\s*{ID})*"
QD = r"(?:D-\d{2,4}|Q-\d{3,4})"; TITLE_RE = re.compile(rf"^# ({ID}) [\u2014\u2013-] (\S.*)$")
HEAD_RE = re.compile(
    rf"^Status: (TODO|READY|RUNNING|PASS|FAIL|STOP|ACCEPTED|REWORK|OBSOLETE) \| Lane: (ROTE|CENSUS|SPEC) \| "
    rf"Depends: (-|{IDS}) \| Module: (-|M-\d{{2,3}}) \| Author decisions needed: (none|{QD}(?:\s*[,/]\s*{QD})*)\s*$")
LINE3_KEYS = ("Supersedes", "Superseded by", "Executor")
REQ = ["GOAL", "OWNS", "READ-ONLY", "PRE-FLIGHT", "BACKUP", "STEPS", "RED PROOF", "GATE", "INVARIANTS", "STOP", "EVIDENCE", "AFTER"]
CHAIN_RE = re.compile(r"^CHAIN: ran=(\d+) \+(\d+) -> ran=(\d+) \((MEASURED|UNMEASURED)\)\s*$")
PLACEHOLDER_RE = re.compile(r"<[A-Z][A-Z0-9 +_/|-]*>|\b(?:T|CHK|SPEC)-NNN\b|\bTODO\b|\bTBD\b|\bFIXME\b|\?\?\?"); CATASTROPHIC = {"*", "**", "**/*", ".", "./", "./**", "/"}
NEVER_OWN = ["tools/aw.py", "tools/gate.sh", "tools/re_audit.sh", "tools/worker_report.py", "tools/kit.env", ".aw/*", ".hermes/prompts/*",
             "AGENTS.md", ".hermes/plans/TASK_CARD.template.md", ".hermes/plans/AUDIT_LEDGER.md", ".hermes/plans/PLAN_latest.md",
             ".hermes/plans/MODULES.md", ".hermes/plans/ROADMAP.md", ".hermes/plans/PLAYBOOK.md", ".hermes/plans/CARD_PATTERNS.md",
             ".hermes/plans/START_BLOCKS.md", ".hermes/plans/GUIDE.md", ".hermes/plans/ARCHITECT_FEEDBACK.md", ".hermes/plans/PROPOSALS.md",
             ".hermes/plans/METRICS.md", ".hermes/plans/DECISIONS.md", ".hermes/plans/cards/*", ".env", ".env.*", "*.pem", "*.key", "id_rsa*",
             "auth.json", "credentials.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "Cargo.lock", "uv.lock", "poetry.lock"]
FROZEN_CLASS = ["tools/*"]
DEFAULT_ALWAYS = ".hermes/plans/WORKLOG.md,.hermes/plans/gate_output/**,.hermes/plans/backups/**,.hermes/plans/REPORT_latest.md,.hermes/plans/QUESTIONS.md,.aw/task-start"
FAMILY = [
    ("L20", "E", "exp", "RCS", None, r"~\s*\d|\u2248|\b(?:about|approx\w*|roughly|around|circa)\b\s+~?\d|\d\s*(?:\+/-|\u00b1)", "approximate number in an expected output -> measure it or write UNMEASURED"),
    ("L20", "W", "prose", "RCS", None, r"~\s*\d|\u2248|\b(?:about|approx\w*|roughly|around|circa)\b\s+~?\d|\d\s*(?:\+/-|\u00b1)", "approximate number -> exact or UNMEASURED"),
    ("L21", "E", "prose", "RC", None, r"as you see fit|at your discretion|your (?:best )?judg(?:e)?ment|you (?:may|can|should|must) (?:decide|choose|pick)|decide (?:whether|if|which|how)|choose (?:between|one|the)|pick (?:one|the)|whichever|feel free|if you (?:think|feel|prefer|want|like|see)|use (?:common )?sense|adapt (?:as|it|to)|do whatever|\u043f\u043e \u0442\u0432\u043e\u044f \u043f\u0440\u0435\u0446\u0435\u043d\u043a\u0430|\u0430\u043a\u043e \u043f\u0440\u0435\u0446\u0435\u043d\u0438\u0448", "worker must not decide -> make it a pre-flight assert or a Q-NNN"),
    ("L22", "W", "prose", "RC", None, r"\b(?:maybe|perhaps|probably|possibly|somehow|something like|or similar|and so on|etc\.?|if needed|if necessary|as needed|as appropriate|optionally|try to|might)\b", "hedge word -> exact instruction"),
    ("L25", "E", "cmd", "RC", None, r"\brm\s+(?:-[a-zA-Z]*[rRfF][a-zA-Z]*|--recursive|--force)\b|\bgit\s+(?:push|commit|reset|clean|stash|rebase|restore|filter-branch|checkout\s+--)\b|\bshutil\.rmtree\b|Remove-Item\b.*-Recurse|\brmdir\s+/s|\bdel\s+/[sS]|\bfind\b.*\s-delete\b", "irreversible command -> mv to _to_delete/ or architect act"),
    ("L25", "W", "cmd", "RC", None, r"\brm\s+[^-\s]|\bdel\s+[^/\s]|\bos\.(?:remove|unlink)\(|\.unlink\(", "deletes data -> mv to _to_delete/"),
    ("L25", "W", "body", "RC", ".py", r"shutil\.rmtree|os\.(?:remove|unlink|rmdir)\(|\.unlink\(|\.rmdir\(", "payload deletes files -> move to _to_delete/"),
    ("L26", "E", "cmd", "RC", None, r"--i-am-architect|--write-baseline|\bratchet\s+--raise|--raise\s+\d+", "architect-only flag in a worker command -> architect runs it (AFTER)"),
    ("L27", "E", "cmd", "RC", None, r"\bsed\s+(?:-[a-zA-Z]*i\b|--in-place)|\bperl\s+-[a-zA-Z]*i\b|\bawk\s+-i\s+inplace", "in-place edit (LAW-4) -> quoted heredoc or aw.py patch"),
    ("L27", "W", "cmd", "RC", None, r"\b(?:echo|printf)\b[^|<>]*>{1,2}\s*(?!&|/dev/null|\S*gate_output)\S+", "echo/printf write -> quoted heredoc"),
    ("L28", "E", "all", "RCS", None, r"(?<![A-Za-z0-9])[A-Za-z]:\\", "Windows drive path -> use C:/ forward slashes or a relative path"),
    ("L28", "W", "all", "RCS", None, r"(?<![\w.:/-])/tmp/", "/tmp differs between bash and Windows python -> use gate_output/"),
    ("L33", "E", "cmd", "RC", None, r"\b(?:pip3?|uv\s+pip|npm|pnpm|yarn)\s+(?:install|add|i)\b|\buv\s+add\b|\bcargo\s+install\b|\bgo\s+get\b|\b(?:apt(?:-get)?|winget|choco|brew)\s+install\b", "install = new dependency -> author decision (Q-NNN)"),
    ("L33", "W", "cmd", "RC", None, r"\b(?:curl|wget)\b|\bgit\s+(?:clone|fetch|pull)\b|Invoke-WebRequest|https?://", "network command -> only if the card needs it; else remove"),
]; CMD_SECS = ("PRE-FLIGHT", "BACKUP", "STEPS", "RED PROOF", "GATE", "ROLLBACK", "EVIDENCE"); TBL_SECS = ("PRE-FLIGHT", "STEPS", "GATE")
def _cells(ln: str) -> list:
    """Split a markdown table row on | outside `code spans`; callers strip the empty edge cells."""
    segs, cur, tick = [], "", False
    for ch in ln:
        if ch == "`": tick = not tick; cur += ch
        elif ch == "|" and not tick: segs.append(cur); cur = ""
        else: cur += ch
    return segs + [cur]
def parse_card(text: str) -> dict:
    t = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff"); L = t.split("\n"); infence = [False] * (len(L) + 1); op = [False] * (len(L) + 1); fenced: list = []
    i = 0
    while i < len(L):
        f = re.match(r"^\s{0,3}(```+|~~~+)\s*(\w*)", L[i])
        if f:
            ch, n = f.group(1)[0], len(f.group(1)); j = i + 1
            while j < len(L):
                c = re.match(r"^\s{0,3}(```+|~~~+)\s*$", L[j])
                if c and c.group(1)[0] == ch and len(c.group(1)) >= n: break
                j += 1
            op[i + 1] = True
            for k in range(i, min(j + 1, len(L))): infence[k + 1] = True
            fenced.append((i + 1, min(j + 1, len(L)), f.group(2) or f.group(1)[0] * 3)); i = j + 1; continue
        i += 1
    secs: dict = {}; heads: list = []; cur, cur_i = None, 0
    for idx, ln in enumerate(L, 1):
        if infence[idx] or op[idx]: continue
        m = re.match(r"^## ([A-Z][A-Z -]*?)(?: \((.*)\))?\s*$", ln)
        if m:
            if cur: secs[cur] = (cur_i, idx)
            cur, cur_i = m.group(1).strip(), idx; heads.append((cur, idx))
    if cur: secs[cur] = (cur_i, len(L) + 1)
    d = {"lines": L, "infence": infence, "fenced": fenced, "secs": secs, "heads": heads, "title": None, "id": None,
         "status": None, "lane": None, "depends": [], "module": None, "decisions": [], "line3": {"line": 0}, "owns": [], "status_line": 0}
    if L and (m := TITLE_RE.match(L[0])): d["id"], d["title"] = m.group(1), m.group(2).strip()
    sl = secs["Status"][0] if "Status" in secs else next((k for k in (1, 2, 3) if k < len(L) and HEAD_RE.match(L[k])), None)
    if sl is not None:
        a = sl; d["status_line"] = a + 1; m = HEAD_RE.match(L[a]) if a < len(L) else None
        if m:
            d.update(status=m.group(1), lane=m.group(2), module=m.group(4)); d["depends"] = [] if m.group(3) == "-" else [x.strip() for x in m.group(3).split(",")]
            d["decisions"] = [] if m.group(5) == "none" else [x.strip() for x in re.split(r"[,/]", m.group(5))]
    if "OWNS" in secs:
        a, b = secs["OWNS"]
        for ln in L[a:b - 1]:
            if ln.strip().startswith("-"):
                body = ln.strip()[1:].strip(); sp = re.search(r"`([^`]+)`", body)
                tok = (sp.group(1) if sp else (body.split()[0] if body.split() else "")).strip().rstrip(".,;")
                if tok: d["owns"].append(tok)
    for key in LINE3_KEYS:
        for idx in range(2, 6):
            if idx < len(L) and re.match(rf"^{key}:\s*\S", L[idx]):
                d["line3"][key] = L[idx].split(":", 1)[1].strip(); d["line3"]["line"] = idx + 1
                break
    return d
def _sec_lines(d: dict, name: str):
    if name not in d["secs"]: return []
    a, b = d["secs"][name]
    return [(i, d["lines"][i - 1]) for i in range(a + 1, min(b, len(d["lines"]) + 1))]
def _cmds(d: dict):
    out = []
    for name in CMD_SECS:
        for i, ln in _sec_lines(d, name):
            if d["infence"][i] or ln.lstrip().startswith("#"): continue
            if ln.startswith("|"):
                cells = [c for c in _cells(ln) if c.strip()]
                if len(cells) > 1: out += [(i, c) for c in re.findall(r"`([^`]+)`", cells[1])]
            elif name in ("BACKUP", "ROLLBACK"): out += [(i, c) for c in re.findall(r"`([^`]+)`", ln)]
    for a, b, lang in d["fenced"]:   # commands written in a fenced shell block count too; a heredoc body is payload, not a command
        if lang not in ("bash", "sh", "shell", "console") or not any(s in d["secs"] and d["secs"][s][0] < a < d["secs"][s][1] for s in CMD_SECS): continue
        tag = None
        for i in range(a + 1, b):
            ln = d["lines"][i - 1]
            if tag:
                tag = None if ln.strip() == tag else tag; continue
            m = re.search(r"<<-?\s*['\"]?([A-Za-z_]\w*)['\"]?", ln)
            closed = bool(m) and any(x.strip() == m.group(1) for x in d["lines"][i:b - 1])   # the opener carries its terminator only if the block has one
            if ln.strip() and not ln.lstrip().startswith("#"): out.append((i, ln.strip() + ("\n" + m.group(1) if closed else "")))
            if m: tag = m.group(1)
    return out
def _write_targets(cmd: str) -> list:
    out = [m.group(1) for m in re.finditer(r"(?<![0-9&])>{1,2}\s*([^\s|;&)]+)", cmd)]; out += [m.group(1) for m in re.finditer(r"\baw\.py\s+patch\s+(\S+)", cmd)]
    out += [m.group(1) for m in re.finditer(r"\b(?:cp|mv)\s+[^|;]+?\s+([^\s|;&]+)\s*$", cmd)]
    return [x.strip("'\"`") for x in out if x and not x.startswith(("&", "/dev/null", "$("))]
# ---------------------------------------------------------------- card-lint
def _sh_blocks(fuse: list, raw_lines: list):
    blocks = [(a, b) for a, b, lang in fuse if lang in ("bash", "sh", "shell", "console")]
    if not blocks: return []
    bash = find_bash()
    if not bash: return [("WARN", "L23", blocks[0][0], "no bash found -> bash -n skipped (UNMEASURED; set AW_BASH or install git-bash)")]
    text_of = {a: "\n".join(raw_lines[a:b - 1]) for a, b in blocks}
    try: r = subprocess.run([bash, "-n"], input="\n".join(text_of.values()).encode("utf-8"), capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError): return [("WARN", "L23", blocks[0][0], "bash -n could not run (UNMEASURED)")]
    if r.returncode == 0: return []
    out: list = []
    for a, b in blocks:
        try: r2 = subprocess.run([bash, "-n"], input=text_of[a].encode("utf-8"), capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError): continue
        if r2.returncode != 0:
            err = r2.stderr.decode("utf-8", "replace").strip().splitlines()
            msg = next((x.split(":", 2)[-1].strip() for x in err if ":" in x and "syntax error" in x.lower()),
                       err[-1] if err else "syntax error")
            out.append(("ERROR", "L23", a, "bash -n: " + msg[:90] + " -> fix the block before queueing"))
    return out
def _overlap(a: str, b: str) -> bool:
    """'These two globs can match one file': fnmatch either way, or (both have wildcards) a shared literal prefix+tail."""
    if a == b or fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a): return True
    if not any(ch in a for ch in "*?[") or not any(ch in b for ch in "*?["):
        return False   # a literal path vs a glob: fnmatch above is the answer
    pa, pb = re.split(r"[*?\[]", a, maxsplit=1), re.split(r"[*?\[]", b, maxsplit=1); lita, litb = pa[0], pb[0]
    taila, tailb = (pa[1] if len(pa) > 1 else ""), (pb[1] if len(pb) > 1 else ""); pre = bool(lita) and bool(litb) and (lita.startswith(litb) or litb.startswith(lita))
    suf = not taila or not tailb or taila.endswith(tailb) or tailb.endswith(taila)
    return bool(pre and suf)


def lint_card(path: Path, floor: int, always: list, ctx: dict) -> list:
    out: list = []
    def add(sev, rule, ln, msg):
        out.append((sev, rule, ln, msg))
    raw = path.read_bytes()
    try: text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        add("ERROR", "L01", raw[: e.start].count(b"\n") + 1, "not valid UTF-8 -> re-save the card as UTF-8"); text = raw.decode("utf-8", "replace")
    if raw.startswith(b"\xef\xbb\xbf"): add("ERROR", "L01", 1, "BOM at byte 0 -> save without BOM (a heredoc terminator never matches)")
    if b"\r" in raw:
        add("ERROR", "L01", raw[: raw.index(b"\r")].count(b"\n") + 1, "CRLF/CR in the card -> save LF; `EOF\\r` never closes a heredoc")
    d = parse_card(text); L, SEC = d["lines"], d["secs"]; dr = SEC.get("DRY-RUN PROOF", (0, 0))
    def prose(i: int) -> str:
        return re.sub(r"`[^`]*`", " ", L[i - 1])
    if not d["id"]: add("ERROR", "L02", 1, "# <ID> - <title> expected -> e.g. `# T-014 - fix the X parser`")
    else:
        if re.match(r"^(T|CHK|SPEC)-\d", path.stem) and path.stem != d["id"]:
            add("ERROR", "L02", 1, f"title id {d['id']} != file name {path.stem} -> one id per file")
        if len(d["title"] or "") < 3: add("ERROR", "L02", 1, "title too short -> one line naming the change")
    if not d["status"]:
        add("ERROR", "L03", d["status_line"] or 2, "Status line malformed -> `Status: TODO | Lane: ROTE | Depends: - | Module: - | Author decisions needed: none`")
    else:
        want = {"T": "ROTE", "CHK": "CENSUS", "SPEC": "SPEC"}.get((d["id"] or "").split("-")[0])
        if want and d["lane"] != want:
            add("ERROR", "L04", d["status_line"], f"a {d['id'].split('-')[0]}- card must use Lane: {want} (got {d['lane']}) -> a judgement card never goes to the cheap worker")
    names = [h for h, _i in d["heads"]]
    for h, i in d["heads"]:
        if h in REQ and names.count(h) > 1: add("ERROR", "L05", i, f"`## {h}` appears {names.count(h)} times -> exactly once")
    miss = [h for h in REQ if h not in SEC]
    if miss: add("ERROR", "L05", 1, "missing H2: " + ", ".join(miss) + " -> required by the card grammar")
    order = [h for h in names if h in REQ]
    if order != [h for h in REQ if h in order]: add("ERROR", "L05", 1, "H2 out of order -> " + " ".join(REQ))
    hdr = max(3, d["status_line"])   # the header block carries legal words like `Status: TODO`
    for i, ln in enumerate(L, 1):
        if i <= hdr or d["infence"][i] or (dr[0] < i < dr[1]): continue
        m = PLACEHOLDER_RE.search(ln)
        if m: add("ERROR", "L06", i, f"placeholder {m.group(0)!r} left in -> fill it or delete the line")
    if not d["owns"]: add("ERROR", "L07", SEC.get("OWNS", (1, 1))[0], "OWNS has no bullet -> a closed list of project-relative paths is required")
    for o in d["owns"]:
        if "\\" in o or ".." in o.split("/") or re.match(r"^[A-Za-z]:", o) or o.startswith("/"):
            add("ERROR", "L07", 1, f"OWNS {o!r} must be project-relative with '/' only, no '..' -> fix it")
        if d["lane"] in ("ROTE", "CENSUS") and o in CATASTROPHIC:
            add("ERROR", "L07", 1, f"OWNS {o!r} is the whole tree -> list the files the card writes")
        for prot, why in ([(n, "never-owned path") for n in NEVER_OWN] + [(n, "implicit frozen core (E3)") for n in FROZEN_CLASS]
                          + [(n, "a frozen.txt glob") for n in ctx.get("frozen", [])]):
            if _overlap(o, prot):
                add("ERROR", "L08", 1, f"OWNS {o!r} overlaps {prot!r} ({why}) -> LAW-8; the architect re-baselines, the card does not")
                break
    always = always or [x for x in DEFAULT_ALWAYS.split(",") if x]
    def owned(p: str) -> bool:
        return matches(p, d["owns"]) or matches(p, always) or re.search(r"[$()~<>]", p) is not None
    cmds = _cmds(d)
    for i, c in cmds:
        for t in _write_targets(c):
            if not owned(t): add("ERROR", "L10", i, f"write target {t!r} is outside OWNS -> add it to OWNS or write elsewhere")
    backed: list = []
    for _i, ln in _sec_lines(d, "BACKUP"):
        for c in re.findall(r"`([^`]+)`", ln):
            m = re.search(r"\baw\.py\s+backup\s+(\S+)\s+([^$`]+)", c)
            if m: backed += [x.strip("'\"") for x in m.group(2).split() if x.strip("'\"")]
    newf: list = []
    for _i, ln in _sec_lines(d, "BACKUP"):
        m = re.match(r"\s*NEW:\s*(.+)$", ln)
        if m and m.group(1).strip().upper() not in ("NONE", "-"): newf += [x.strip("'\"` ") for x in m.group(1).split(",") if x.strip("'\"` ")]
    for i, c in cmds:
        for t in _write_targets(c):
            if matches(t, always) or re.search(r"[$()~<>]", t): continue
            done = matches(t, backed) or t in newf   # a patch target must ALSO be back upped (R-3: no backup, no restore)
            if not done: add("ERROR", "L11", i, f"{t!r} is written but neither backed up nor listed under `NEW:` -> R-3: no backup, no restore")
    for b in backed:
        if not matches(b, d["owns"]): add("WARN", "L11", 1, f"backup arg {b!r} is outside OWNS -> back up only what the card may change")
        if b in newf: add("ERROR", "L11", 1, f"{b!r} is both backed up and NEW -> a new file has no backup")
    for i, c in cmds:
        m = re.search(r"\baw\.py\s+patch\s+(.+)$", c)
        if m and len(m.group(1).split()) != 3: add("ERROR", "L12", i, "aw.py patch needs exactly 3 args (FILE OLD.txt NEW.txt) -> fix the row")
    ch = [(i, CHAIN_RE.match(L[i - 1])) for i, _ln in _sec_lines(d, "GATE")]; ch = [(i, m) for i, m in ch if m]; before = after = k = None
    if len(ch) != 1:
        add("ERROR", "L14", SEC.get("GATE", (1, 1))[0], f"GATE needs exactly one `CHAIN: ran=N +K -> ran=M (MEASURED|UNMEASURED)` line (found {len(ch)})")
    else:
        i, m = ch[0]; before, k, after = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if after != before + k: add("ERROR", "L14", i, f"CHAIN arithmetic: {before}+{k} != {after} -> fix ran= or k")
    pf = [(i, ln) for i, ln in _sec_lines(d, "PRE-FLIGHT") if ln.startswith("|")]; grow = [(i, ln) for i, ln in pf if "tools/gate.sh" in ln]
    if not grow: add("ERROR", "L15", SEC.get("PRE-FLIGHT", (1, 1))[0], "PRE-FLIGHT needs a `bash tools/gate.sh pre-<ID>` row -> R-1")
    for i, ln in grow:
        cells = [c for c in _cells(ln) if c.strip()]; cvec = re.search(r"count=(\d+)\s+min=(\d+)", cells[2] if len(cells) > 2 else "")
        if not cvec:
            add("ERROR", "L15", i, "gate row expects no `GATE OK count=N min=F` -> paste the measured line")
            continue
        if before is not None and int(cvec.group(1)) != before:
            add("ERROR", "L15", i, f"PRE-FLIGHT count={cvec.group(1)} != CHAIN ran={before} -> stale `ran=` from an older card")
        if int(cvec.group(2)) != floor: add("ERROR", "L15", i, f"PRE-FLIGHT min={cvec.group(2)} != live floor {floor} -> re-measure (ratchet)")
    if not any("integrity" in ln for _i, ln in pf):
        add("ERROR", "L15", SEC.get("PRE-FLIGHT", (1, 1))[0], "PRE-FLIGHT needs an `aw.py integrity` row expecting INTEGRITY OK")
    for i, ln in enumerate(L, 1):
        if d["infence"][i] or (dr[0] < i < dr[1]) or PLACEHOLDER_RE.search(ln): continue
        for m in re.finditer(r"(?:min_tests=|min=|floor )(\d+)", ln):
            if int(m.group(1)) != floor: add("ERROR", "L16", i, f"{m.group(0)} != live floor {floor} -> stale number from an older card")
    at = SEC.get("AFTER", (0, 0))
    for i in range(at[0], at[1]):
        m = re.search(r"--raise\s+(\d+)", L[i - 1]) if i < len(L) else None
        if m and int(m.group(1)) != floor: add("WARN", "L16", i, "AFTER raises the floor to one card's count -> raise ONCE to the queue `final=`")
    allowed = {0, floor} | {x for x in (before, after, k) if x is not None}
    for name in TBL_SECS:
        n = 0
        rows = _sec_lines(d, name)
        for k, (i, ln) in enumerate(rows):
            if not ln.startswith("|") or d["infence"][i]: continue
            nxt = rows[k + 1][1] if k + 1 < len(rows) else ""
            if re.match(r"^\|?[\s:|-]+\|?\s*$", nxt) or re.match(r"^\|[\s:|-]+\|", ln): continue  # header + separator
            cells = [c.strip() for c in _cells(ln)]
            if cells and cells[0] == "": cells = cells[1:]
            if cells and cells[-1] == "": cells = cells[:-1]
            if len(cells) != 3 or set("".join(cells)) <= set("-: "): continue
            n += 1
            if not cells[0].isdigit() or int(cells[0]) != n: add("ERROR", "L17", i, f"table row # {cells[0]!r} should be {n} -> number the rows 1..n")
            if not cells[1]: add("ERROR", "L17", i, "empty action cell -> one command or one patch per row")
            if not (re.search(r"`[^`]+`", cells[2]) or re.search(r"\d", cells[2]) or re.search(r"(?i)UNMEASURED|record|none", cells[2])):
                add("ERROR", "L17", i, "Expected has no checkable output -> a span, a number, UNMEASURED, record or none")
            for tok in re.findall(r"`([^`]+)`", cells[2]) or [cells[2]]:
                for num in re.findall(r"\d{3,}", tok):
                    if int(num) not in allowed and num not in ctx.get("proof", ""):
                        sev = "ERROR" if d["status"] in ("READY", "RUNNING") else "WARN"
                        add(sev, "L18", i, f"expected number {num} is not in {{chain,floor}} nor DRY-RUN PROOF -> measure it or write UNMEASURED")
    if d["status"] in ("READY", "RUNNING") and d["lane"] in ("ROTE", "CENSUS"):
        blocks = [(a, b) for a, b, _lg in d["fenced"] if dr[0] <= a < dr[1]]
        if not blocks: add("ERROR", "L19", d["status_line"], "Status READY needs DRY-RUN PROOF -> run the card in a copy and paste the real output")
        elif ch and ch[0][1].group(4) == "MEASURED" and after is not None:
            pr = " ".join(x for a, b in blocks for x in L[a:b - 1])
            if f"count={after}" not in pr and f"ran={after}" not in pr:
                add("ERROR", "L19", dr[0], f"CHAIN says MEASURED but DRY-RUN PROOF shows no count={after}/ran={after} -> paste it or mark UNMEASURED")
    for i, c in cmds:
        try: shlex.split(c.replace("|", " "))
        except ValueError: add("ERROR", "L23", i, "unbalanced quote -> an apostrophe inside a single-quoted grep ends the string")
        if re.search(r"<<-?\s*[A-Za-z_]", c): add("ERROR", "L23", i, "unquoted heredoc (<<EOF) -> use <<'EOF' or $ and backticks expand")
        m = re.search(r"<<-?\s*['\"]?([A-Za-z_]\w*)['\"]?", c)
        if m and not re.search(rf"(?m)^{re.escape(m.group(1))}\s*$", c):
            add("ERROR", "L23", i, f"heredoc {m.group(1)} has no closing line in the same command -> the rest of the card becomes its body")
    out += _sh_blocks([fb for fb in d["fenced"] if not (dr[0] <= fb[0] < dr[1])], L); out += [("ERROR", "L47", i, "' & ' in a shell block -> the Hermes terminal refuses it (a heredoc body too under `timeout`): use && or one command per line") for a, b, lg in d["fenced"] if lg in ("bash", "sh", "shell", "console") and d["lane"] in ("ROTE", "CENSUS") and not (dr[0] <= a < dr[1]) for i, x in enumerate(L[a:b - 1], a + 1) if re.search(r"(?:^|\s)&(?:\s|$)", x)]; rp = SEC.get("RED PROOF", (0, 0))
    first = next((L[i - 1].strip() for i in range(rp[0] + 1, rp[1]) if i < len(L) and L[i - 1].strip()), "")
    if not first: add("ERROR", "L35", rp[0] or 1, "RED PROOF is empty -> R-6: paste the failing line")
    elif d["lane"] == "ROTE" and not (re.match(r"(?i)n/a", first) and len(first) >= 13) and \
            not (re.search(r"(?i)step\s+(\d+)", first) and "fail" in first.lower()):
        add("ERROR", "L35", rp[0], "ROTE RED PROOF must name the failing step + 'fail' or start `n/a <reason>`")
    elif d["lane"] == "CENSUS" and not re.match(r"(?i)n/a", first): add("ERROR", "L35", rp[0], "CENSUS RED PROOF must start `n/a` (report-only lane)")
    if d["id"]:
        for i, c in cmds:
            for m in re.finditer(r"(?:aw\.py\s+(?:start|backup|restore|audit)|(?:gate|re_audit)\.sh)\s+(?:pre-)?((?:T|CHK|SPEC)-\d{3,5})", c):
                if m.group(1) != d["id"]: add("ERROR", "L38", i, f"command names {m.group(1)} but this is {d['id']} -> templated from a neighbour")
            for m in re.finditer(r"(?:gate_output|backups)/((?:T|CHK|SPEC)-\d{3,5})", c):
                if m.group(1) != d["id"]: add("ERROR", "L38", i, f"evidence path names {m.group(1)} but this is {d['id']}")
    gr = [(i, ln) for i, ln in _sec_lines(d, "GATE") if ln.startswith("|")]
    if gr and not any("tools/gate.sh" in ln for _i, ln in gr):
        add("ERROR", "L40", SEC.get("GATE", (1, 1))[0], "GATE needs a `bash tools/gate.sh <ID>` row expecting `GATE OK count=<after>`")
    if gr:
        last_i, last = gr[-1]
        if not re.search(r"(?:re_audit\.sh|aw\.py\s+audit)\s+" + re.escape(d["id"] or "?"), last) or "AUDIT PASS" not in last:
            add("ERROR", "L40", last_i, "the LAST GATE row must be `re_audit.sh <ID>` expecting `AUDIT PASS` -> R-10")
        m = re.search(r"OWNS='([^']*)'", "\n".join(ln for _i, ln in gr))
        if m:
            if {x.strip() for x in m.group(1).split(",") if x.strip()} != set(d["owns"]):
                add("ERROR", "L40", last_i, "GATE OWNS='...' != the OWNS section -> a false OUT FAIL on correct work")
        elif d["lane"] == "ROTE": add("WARN", "L40", last_i, "no OWNS='...' on the re_audit row -> `audit` sees no scope (UNMEASURED)")
    for rid, sev, scope, lanes, ext, rx_s, msg in FAMILY:   # spec rows are (id, E|W, scope, lanes, ext, regex, msg)
        if d["lane"] and d["lane"][0] not in lanes: continue
        sev = "ERROR" if sev == "E" else "WARN"
        rx = re.compile(rx_s, re.I if rid in ("L21", "L22") else 0)
        if scope == "cmd":
            for i, c in cmds:
                if rx.search(c): add(sev, rid, i, msg)
        elif scope == "body":
            for a, b, _lg in d["fenced"]:
                if rx.search("\n".join(L[a:b - 1])): add(sev, rid, a, msg)
        elif scope == "exp":
            for name in TBL_SECS:
                for i, ln in _sec_lines(d, name):
                    cells = [c for c in _cells(ln) if c.strip()]
                    if ln.startswith("|") and len(cells) > 2 and rx.search(cells[2]): add(sev, rid, i, msg)
        else:
            for i in range(1, len(L) + 1):
                if not d["infence"][i] and not (dr[0] < i < dr[1]) and rx.search(prose(i)): add(sev, rid, i, msg)
    return sorted(set(out), key=lambda x: (x[2], x[1]))
def cmd_card_lint(pos, fl, kv) -> int:
    if not pos: die("usage: aw.py card-lint <card.md|T-NNN> [--strict] -> bare id = .hermes/plans/cards/<ID>.md", 2)
    a = pos[0]; path = Path(a) if a.endswith(".md") else card_path(a.upper())
    if not path.is_file():
        print(f"CARD-LINT ERROR card not found: {path}"); return 2
    floor, _b = floor_now(); always = [x for x in read_env().get("ALWAYS_OWNED", DEFAULT_ALWAYS).split(",") if x]; txt = rtext(path)
    m = re.search(r"(?ms)^## DRY-RUN PROOF\s*$(.*?)(?=^## |\Z)", txt)
    f = lint_card(path, floor, always, {"frozen": frozen_globs(), "proof": m.group(1) if m else ""})
    for sev, rid, ln, msg in f: print(f"LINT {sev} {rid} line {ln}: {msg}")
    e = sum(1 for x in f if x[0] == "ERROR"); w = len(f) - e; verdict = "FAIL" if e or ("--strict" in fl and w) else "OK"; print(f"CARD-LINT {verdict} errors={e} warn={w}")
    return 0 if verdict == "OK" else 1
# ---------------------------------------------------------------- queue-check
def _first_ran(d: dict):
    for _i, ln in _sec_lines(d, "GATE"):
        m = re.search(r"\bran=(\d+)", ln)
        if m: return int(m.group(1))
    return None
def cmd_queue_check(pos, fl, kv) -> int:
    if not pos: die("usage: aw.py queue-check .hermes/plans/cards/QUEUE.md -> validates the Chain line and every card", 2)
    q = Path(pos[0])
    if not q.is_file(): die(f"queue-check: {pos[0]} not found -> pass the queue file path", 1)
    txt = rtext(q); errs: list = []; warn: list = []
    lines = [ln.strip() for ln in txt.split("\n") if ln.strip().startswith("Chain:")]
    m = re.match(r"^Chain:\s*base=(\d+)\s*\|(.+?)\|\s*final=(\d+)\s*$", lines[0]) if len(lines) == 1 else None
    if len(lines) != 1: errs.append(f"needs exactly one `Chain:` line (found {len(lines)}) -> one line per queue")
    elif not m: errs.append("Chain grammar: `Chain: base=<int> | T-001:+0 T-002:+5 | final=<int>`")
    floor, _b = floor_now(); base = final = 0; items: list = []
    if m:
        base, final = int(m.group(1)), int(m.group(3)); items = re.findall(r"\b((?:T|CHK|SPEC)-\d{3,5})\s*:\+(\d+)", m.group(2))
        if base < floor: errs.append(f"base={base} < live floor {floor} -> re-measure the count (ratchet)")
        if final != base + sum(int(k) for _i, k in items): errs.append(f"final={final} != base+sum(k)={base + sum(int(k) for _i, k in items)}")
        wl = PLANS / "WORKLOG.md"; wtxt = rtext(wl) if wl.is_file() else ""; ids = [i for i, _k in items]
        if len(set(ids)) != len(ids): errs.append("duplicate card id in the Chain -> ids are never reused")
        done = {i for i in ids if re.search(rf"^## {re.escape(i)} \|.*(PASS|ACCEPTED)", wtxt, re.M)}; prev = 0
        cards = []
        for cid, ks in items:
            cp = card_path(cid)
            if not cp.is_file():
                errs.append(f"{cid}: no card file ({cp}) -> write it or fix the id"); prev += int(ks); continue
            d = parse_card(rtext(cp)); cards.append((cid, d))
            if d["lane"] == "SPEC": errs.append(f"{cid}: SPEC lane in a worker queue -> judgement cards are never queued")
            if d["status"] in ("OBSOLETE", "PASS", "ACCEPTED", "FAIL", "STOP"): errs.append(f"{cid}: Status {d['status']} must not be queued")
            elif d["status"] in ("TODO", "RUNNING"): warn.append(f"{cid}: Status {d['status']} is not dry-run proven (READY)")
            for dep in d["depends"]:
                if dep not in {c for c, _d in cards} and dep not in done:
                    errs.append(f"{cid}: Depends {dep} is not earlier in the Chain and has no PASS in WORKLOG")
            ran = _first_ran(d)
            if ran is None: errs.append(f"{cid}: no `ran=` in its GATE section -> chain arithmetic is UNMEASURED")
            elif ran != base + prev: errs.append(f"{cid}: ran={ran} but the chain says base+previous={base + prev}")
            prev += int(ks)
        for n, (cid, d) in enumerate(cards):
            for cid2, d2 in cards[:n]:
                shared = [x for x in d["owns"] for y in d2["owns"] if _overlap(x, y)]
                if shared and cid2 not in d["depends"]:
                    errs.append(f"{cid}: OWNS {shared[0]!r} overlaps earlier {cid2} but Depends does not list it -> dependent/independent becomes guesswork")
    if not re.search(r"(?m)^QUEUE DONE\s+\d+ PASS\s*/\s*\d+ FAIL\s*/\s*\d+ STOP\s*$", txt):
        warn.append("no return line `QUEUE DONE <n PASS> / <n FAIL> / <n STOP>` -> the next session cannot grep the outcome")
    for wv in warn: print("QUEUE-WARN", wv)
    if errs:
        print(f"QUEUE-CHECK FAIL {len(errs)}: " + "; ".join(errs[:6]) + (" ..." if len(errs) > 6 else ""))
        for e in errs[:20]: print("   ", e)
        return 1
    print(f"QUEUE-CHECK OK chain={base} -> ... -> {final}; after all PASS: ratchet --raise {final} --i-am-architect" if m else "QUEUE-CHECK OK")
    return 0
# ---------------------------------------------------------------- modules
MOD_HEADER = ["ID", "Module", "Purpose", "OWNS", "Depends", "Wave", "Gate", "Decides", "Status"]
def _owns_cell(v: str) -> list:
    return [x.strip().strip("`") for x in v.split(",") if x.strip().strip("`")]
def cmd_modules(pos, fl, kv) -> int:
    p = PLANS / "MODULES.md"
    if not p.is_file():
        print(f"MODULES FAIL 1: {p} missing -> install it (init_project.py) or write the registry table"); return 1
    L = rtext(p).replace("\r\n", "\n").split("\n"); hi = next((n for n, ln in enumerate(L) if re.match(r"^\|\s*ID\s*\|", ln)), None)
    if hi is None:
        print("MODULES FAIL 1: no registry table -> header `| ID | Module | Purpose | OWNS | Depends | Wave | Gate | Decides | Status |`")
        return 1
    cells = [c.strip().strip("<>") for c in _cells(L[hi]) if c.strip()]; errs: list = []
    if cells != MOD_HEADER: errs.append("header must be exactly `| ID | Module | Purpose | OWNS | Depends | Wave | Gate | Decides | Status |`")
    mods: dict = {}
    for ln in L[hi + 2:]:
        if not ln.strip().startswith("|"): break
        c = [x.strip() for x in _cells(ln)]
        if c and c[0] == "": c = c[1:]
        if c and c[-1] == "": c = c[:-1]
        if len(c) < len(cells): continue
        r = dict(zip(cells, c)); mid, wave = r.get("ID", "").strip("`"), r.get("Wave", "").strip("`")
        if not re.match(r"^M-\d{2,3}$", mid):
            errs.append(f"bad module id {mid!r} -> M-NN")
            continue
        if mid in mods: errs.append(f"duplicate module id {mid}")
        wm = re.match(r"^W-(\d+)$", wave)
        if not wm: errs.append(f"{mid}: Wave {wave!r} -> W-<n>")
        mods[mid] = {"wave": int(wm.group(1)) if wm else 0, "owns": _owns_cell(r.get("OWNS", "")),
                     "deps": [] if r.get("Depends", "-").strip() in ("-", "") else [x.strip() for x in re.split(r"[,\s]+", r.get("Depends", "")) if x.strip()]}
    for mid, v in mods.items():
        for dep in v["deps"]:
            if dep not in mods: errs.append(f"{mid}: unknown dependency {dep}")
            elif mods[dep]["wave"] >= v["wave"]:
                errs.append(f"{mid}: depends on {dep} of the same/later wave (W-{mods[dep]['wave']} >= W-{v['wave']}) -> waves would run it in parallel")
    def cyc(mid: str, seen: set) -> bool:
        if mid in seen: return True
        seen = seen | {mid}; return any(cyc(d, seen) for d in mods[mid]["deps"] if d in mods)
    if any(cyc(mid, set()) for mid in mods): errs.append("dependency cycle in the registry -> break it before queueing the wave")
    exist = [rel for _p, rel in files()]
    for a in sorted(mods):
        for b in sorted(mods):
            if a >= b or mods[a]["wave"] != mods[b]["wave"]: continue
            for x in mods[a]["owns"]:
                for y in mods[b]["owns"]:
                    if x == y: errs.append(f"{a} and {b} (both W-{mods[a]['wave']}) share the glob {x!r} -> one file, two owners")
                    elif any(matches(f, [x]) and matches(f, [y]) for f in exist):
                        errs.append(f"{a} and {b} (both W-{mods[a]['wave']}) both own an existing file via {x!r} / {y!r}")
    if errs:
        print(f"MODULES FAIL {len(errs)}: " + "; ".join(errs[:4]) + (" ..." if len(errs) > 4 else ""))
        for e in errs[:15]: print("   ", e)
        return 1
    print(f"MODULES OK modules={len(mods)} waves={len({v['wave'] for v in mods.values()})}"); return 0
# ---------------------------------------------------------------- doctor
def _prog_of(cmdline: str) -> str:
    try: toks = shlex.split(cmdline, posix=False)
    except ValueError: return ""
    for t in toks:
        t = t.strip("\"'")
        if not t or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t): continue
        return t
    return ""
def _prog_ok(prog: str, c: dict) -> str:
    if not prog: return "FAIL"
    if prog in ("cd", "set", "export", "echo", "true", "make", "bash", "sh"):
        return "WARN"  # shell builtin / resolved by the shell: do not guess
    if re.search(r"[\\/]", prog):
        p = Path(prog); p = p if p.is_absolute() else ROOT / c.get("TEST_DIR", ".") / p
        return "OK" if p.exists() else "FAIL"
    return "OK" if shutil.which(prog) else "FAIL"
def doctor_checks() -> list:
    r: list = []
    def add(level, topic, detail):
        r.append((level, topic, detail))
    ver = "%d.%d.%d" % sys.version_info[:3]; add("OK" if sys.version_info >= (3, 9) else "FAIL", "python", f"{ver} (engine needs >= 3.9)"); c = read_env()
    if not (ROOT / "tools/kit.env").is_file():
        add("FAIL", "kit.env", "tools/kit.env missing -> run `python3 init_project.py <this dir> --name <Project>`")
    else: add("OK", "kit.env", "tools/kit.env parsed")
    py = c.get("PY", "python3"); pyv = ""
    try:
        pr = subprocess.run([py, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20, env=_clean_env())
        if pr.returncode == 0 and "Python" in ((pr.stdout or "") + (pr.stderr or "")): pyv = ((pr.stdout or "") + (pr.stderr or "")).strip()
    except (OSError, subprocess.SubprocessError): pyv = ""
    add("OK" if pyv else "FAIL", "PY", f"`{py}` runs ({pyv})" if pyv
        else f"`{py}` is not runnable -> set PY in tools/kit.env to a real python (Windows: the venv python by full path)")
    cmd = c.get("TEST_CMD", ""); prog = _prog_of(cmd); lvl = _prog_ok(prog, c) if cmd else "FAIL"
    add(lvl, "TEST_CMD", (f"`{prog}` found on PATH" if lvl == "OK" else f"`{prog}` not found -> TEST_CMD will fail with exit=127")
        if cmd else "TEST_CMD is empty -> set the ONE command that runs your suite")
    if os.environ.get("PYTHONPATH"):
        add("WARN", "PYTHONPATH", f"host PYTHONPATH is set -> stripped for the gate and checks.d (/gate and /audit are safe); shell commands in cards still inherit it")
    else: add("OK", "PYTHONPATH", "not set")
    bash = find_bash()
    if os.name == "nt":
        if not bash:
            add("WARN", "bash", "no git-bash found -> gate.sh/re_audit.sh cannot run (install Git for Windows or set AW_BASH); `aw.py gate` still works")
        else: add("OK", "bash", f"git-bash: {bash}")
        wsl = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/bash.exe"
        if wsl.is_file():
            add("WARN", "wsl-bash", f"{wsl} exists -> a bare `bash` from Python is WSL, not git-bash; cards must use the resolved path (set AW_BASH)")
    else: add("OK" if bash else "WARN", "bash", bash or "no bash -> .sh checks and gate.sh are skipped")
    need = ["tools/aw.py", "tools/kit.env", "tools/gate.sh", "tools/re_audit.sh", "tools/worker_report.py", ".aw/ratchet.json",
            ".aw/frozen.txt", ".hermes/plans/AUDIT_LEDGER.md", ".hermes/plans/WORKLOG.md", ".hermes/plans/QUESTIONS.md"]
    miss = [x for x in need if not (ROOT / x).is_file()]
    add("OK" if not miss else "FAIL", "kit-files", "all present" if not miss else "missing: " + ", ".join(miss[:6]) + " -> re-run init_project.py (it stages, never overwrites)")
    v2 = ["AGENTS.md", ".aw/KIT_VERSION", ".aw/secrets_allow.txt", ".gitattributes", ".hermes/prompts/ARCHITECT.md", ".hermes/prompts/WORKER.md",
          ".hermes/plans/TASK_CARD.template.md", ".hermes/plans/cards/QUEUE.template.md"]
    m2 = [x for x in v2 if not (ROOT / x).is_file()]
    add("OK" if not m2 else "WARN", "kit-v2", "all present" if not m2 else "missing: " + ", ".join(m2[:6]) + " -> run init_project.py (v1 install: new files land, nothing is overwritten)")
    kp = AW / "KIT_VERSION"; kv = rtext(kp).strip() if kp.is_file() else ""
    add("OK" if kv else "WARN", "KIT_VERSION", f"{kv}" if kv else "no .aw/KIT_VERSION -> kit v1 install: re-run init_project.py to record the version"); crlf: list = []
    for p, rel in files():
        if rel.startswith((".aw/", ".hermes/prompts/", "tools/")) or rel in ("AGENTS.md", ".gitattributes") or (rel.startswith(".hermes/plans/") and rel.endswith(".md")):
            try:
                if p.is_symlink() or b"\r" not in p.read_bytes(): continue
            except OSError: continue
            crlf.append(rel)
    if crlf:
        scripts = [x for x in crlf if x.endswith((".sh", ".py"))]
        det = f"{len(crlf)} file(s) with CRLF: " + ", ".join(crlf[:5]) + (f" +{len(crlf) - 5}" if len(crlf) > 5 else "")
        det += (" -> a CRLF .sh/.py breaks bash/python; re-install with init_project.py (it writes LF)" if scripts
                else " -> save LF (`.gitattributes` with `* text eol=lf` keeps it)")
        add("FAIL" if scripts else "WARN", "line-endings", det)
    else: add("OK", "line-endings", "LF on the kit files")
    gi = rtext(ROOT / ".gitignore") if (ROOT / ".gitignore").is_file() else ""
    if gi:
        lack = [x for x in (".env", "backups/", "kit_stage/") if x not in gi]
        add("OK" if not lack else "WARN", "gitignore", "covers .env, backups/, kit_stage/" if not lack else "missing: " + ", ".join(lack) + " -> add them (a real .env must never be committed)")
    else: add("WARN", "gitignore", "no .gitignore -> add .env, backups/, kit_stage/")
    if (ROOT / ".git").exists():
        try:
            nm = subprocess.run(["git", "config", "user.name"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20)
            em = subprocess.run(["git", "config", "user.email"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20)
            okg = nm.returncode == 0 and em.returncode == 0 and nm.stdout.strip() and em.stdout.strip()
        except (OSError, subprocess.SubprocessError): okg = False
        add("OK" if okg else "WARN", "git-identity", "user.name/user.email set" if okg else "git user.name/user.email unset -> `git commit` fails after the stage; set them")
    warn = ledger_tail_warn()
    add("OK" if not warn else "WARN", "ledger-s8", "`## 8. RE-AUDIT LOG` is the last `## ` heading" if not warn else warn.replace("WARN ", ""))
    if not (AW / "baseline.json").is_file():
        add("WARN", "baseline", "no .aw/baseline.json -> `integrity` is UNMEASURED (architect: integrity --write-baseline --i-am-architect)")
    else: add("OK", "baseline", "present")
    flo = to_int(jload(AW / "ratchet.json", {}).get("min_tests", 0))
    add("OK" if flo else "WARN", "ratchet", f"min_tests={flo}" + ("" if flo else " -> run the gate once, then `ratchet --raise <measured> --i-am-architect`"))
    return r
def cmd_doctor(pos, fl, kv) -> int:
    ds = doctor_checks()
    for lv, topic, detail in ds: print(f"DOCTOR {lv} {topic}: {detail}")
    f = sum(1 for lv, _t, _m in ds if lv == "FAIL"); w = sum(1 for lv, _t, _m in ds if lv == "WARN")
    print(f"DOCTOR {'PASS' if not f else 'FAIL'} warn={w} fail={f}"); return 0 if not f else 1
# ---------------------------------------------------------------- dispatch
VAL_FLAGS = ("--allow", "--raise")   # every flag that takes a value (kit-lint reads this too)
COMMANDS = {
    "gate": (cmd_gate, "gate [label]", ()),
    "audit": (cmd_audit, "audit [T-NNN]", ()),
    "integrity": (cmd_integrity, "integrity [--write-baseline --i-am-architect] [--allow g1,g2]", ("--write-baseline", "--i-am-architect")),
    "ratchet": (cmd_ratchet, "ratchet [--raise N --i-am-architect]", ("--i-am-architect",)),
    "doctor": (cmd_doctor, "doctor", ()),
    "start": (cmd_start, "start T-NNN", ()),
    "restore": (cmd_restore, "restore T-NNN [--dry-run] [--force]", ("--dry-run", "--force")),
    "backup": (cmd_backup, "backup T-NNN path [path..]", ()),
    "patch": (cmd_patch, "patch FILE OLD.txt NEW.txt", ()),
    "report": (cmd_report, "report", ()),
    "ask": (cmd_ask, 'ask "text"', ()),
    "answer": (cmd_answer, 'answer Q-NNN "text"', ()),
    "next-id": (cmd_next_id, "next-id [T|CHK|SPEC|AUD|F|P|Q|D|M|W|PH]", ()),
    "card-lint": (cmd_card_lint, "card-lint CARD|ID [--strict]", ("--strict",)),
    "queue-check": (cmd_queue_check, "queue-check QUEUE.md", ()),
    "modules": (cmd_modules, "modules", ()),
    "improve": (cmd_improve, "improve", ()),
}
def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8")  # cp1252 chokes on Cyrillic and arrows
        except (AttributeError, ValueError): pass
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"): print(__doc__); return 0 if len(sys.argv) > 1 else 2
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd not in COMMANDS:
        near = difflib.get_close_matches(cmd, list(COMMANDS), n=1)
        print(f"unknown command {cmd!r}" + (f" -> did you mean `{near[0]}`?" if near else "") + " -> `aw.py --help` lists every command")
        return 2
    fn, _usage, bools = COMMANDS[cmd]
    if cmd in ("ask", "answer"): return fn(args, set(), {})  # free text: never parsed as flags
    pos, fl, kv = argp(args, bools, VAL_FLAGS)
    if "--help" in fl:
        print("usage: aw.py " + _usage); return 0
    return fn(pos, fl, kv)
if __name__ == "__main__": sys.exit(main())
