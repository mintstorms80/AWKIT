#!/usr/bin/env python3
"""Reference implementation of docs/CARD_LINT_RULES.md (all 46 rules; the engine's card-lint is a subset). Stdlib only. Author-side QA, not installed.

  python3 lint_probe.py card FILE [--root DIR]   # lint one v2 card
  python3 lint_probe.py legacy FILE [--root DIR] # the earlier project-era card: map inline KEY: sections, then lint
  python3 lint_probe.py selftest                 # 3 positive fixtures + one mutant per rule + template guard

Rule DATA is not retyped here: every run execs the ```python block of CARD_LINT_RULES.md, so the bytes tested are the
bytes published. This is a PROBE, not the product: the engine's card-lint must reuse the same parse, not this file.
"""
import fnmatch
import os
import re
import shlex
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))   # kit root: dev/card_lint_reference/ -> ../..
OUT = []


def load_spec():
    md = open(os.path.join(ROOT, "docs", "CARD_LINT_RULES.md"), encoding="utf-8").read()
    m = re.search(r"```python\n(.*?)```", md, re.S)
    if not m:
        sys.exit("SPEC-DATA-MISSING in CARD_LINT_RULES.md")
    ns = {}
    exec(m.group(1), ns)  # noqa: S102 - the spec is the single source of truth
    return ns


SD = load_spec()
TITLE_RE, HEAD_RE, H2_RE, CHAIN_RE = SD["TITLE_RE"], SD["HEAD_RE"], SD["H2_RE"], SD["CHAIN_RE"]
LINE3_KEYS, REQ, HIST = SD["LINE3_KEYS"], SD["REQ"], SD["HIST"]
PH, CATA, NEVER, FZ, FAMILY, IDRE = SD["PLACEHOLDER_RE"], SD["CATASTROPHIC"], SD["NEVER_OWN"], SD["FROZEN_CLASS"], SD["FAMILY"], SD["ID"]

PROSE_SECS = ["GOAL", "PRE-FLIGHT", "BACKUP", "STEPS", "RED PROOF", "GATE", "INVARIANTS", "STOP", "ROLLBACK", "EVIDENCE", "AFTER"]
CMD_SECS = ["PRE-FLIGHT", "BACKUP", "STEPS", "GATE", "INVARIANTS", "ROLLBACK", "EVIDENCE"]
WRX = re.compile(r"(?<![<>&\d-])(?:>>?)\s*([^\s;&|<>`]+)|tee\s+(?:-a\s+)?([^\s;&|<>`]+)|"
                 r"aw\.py\s+patch\s+(\S+)\s+\S+\s+\S+|\b(?:cp|mv)\b[^;&|\n]*\s([^\s;&|<>`]+)\s*$")


def out(sev, rid, line, msg, fix=""):
    OUT.append((line, rid, f"LINT {sev} {rid} line {line}: {msg[:140]}" + (f" -> {fix}" if fix else "")))


def hide(ln):  # prose scope: backticked spans are payload, they get their own rules
    return re.sub(r"`[^`]*`", lambda m: " " * len(m.group(0)), ln)


def spans(s):
    return re.findall(r"`([^`\n]+)`", s)


def norm(p):
    p = re.sub(r"^(?:\./)+", "", p.strip().strip("`"))
    return os.path.normpath(p).replace("\\", "/") if p and p != "." else ""


def match(rel, pats):
    return any(p and fnmatch.fnmatch(norm(rel), norm(p)) for p in pats)


def overlap(a, b):
    """Could two globs/paths name one file? fnmatch either way, or a path lies inside the other's directory."""
    a, b = norm(a), norm(b)
    if fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a):
        return True
    ag, bg = ("*" in a or "?" in a), ("*" in b or "?" in b)
    if ag and not bg:
        return b.rsplit("/", 1)[0] == a.rstrip("/*").rsplit("/", 1)[0] or b.startswith(a.rstrip("/*") + "/")
    if bg and not ag:
        return a.rsplit("/", 1)[0] == b.rstrip("/*").rsplit("/", 1)[0] or a.startswith(b.rstrip("/*") + "/")
    return a.rsplit("/", 1)[0] == b.rsplit("/", 1)[0]


def cells(line):
    segs, cur, tick = [], "", False
    for ch in line:
        if ch == "`":
            tick = not tick
            cur += ch
        elif ch == "|" and not tick:
            segs.append(cur)
            cur = ""
        else:
            cur += ch
    segs.append(cur)
    if len(segs) > 2:
        segs = segs[1:]
        if not segs[-1].strip():
            segs = segs[:-1]
    return [s.strip() for s in segs]


def heredoc(cmd):
    m = re.search(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)['\"]?", cmd)
    return (m.group(2) != "", m.group(3), m.start()) if m else None


class Card:
    def __init__(self, text, name=""):
        self.name, self.lines, self.raw = name, text.split("\n"), text
        self.fence, self.herr, self.body, self.bodies = {}, [], [], {}
        fence, here = None, None
        hd_target = None
        for i, ln in enumerate(self.lines, 1):
            if fence:
                self.fence[i] = 1
                m = re.match(r"^\s{0,3}(`{3,}|~{3,})\s*$", ln)
                if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]:
                    fence = None  # a heredoc body may outlive the fence that carries it: keep `here`
                    continue
                if here:
                    if ln.strip() == here[1]:
                        here = None
                    else:
                        self.body.append((i, ln, hd_target))
                continue  # everything inside a fence is payload: no heading, no heredoc bookkeeping
            m = re.match(r"^\s{0,3}(`{3,}|~{3,})", ln)
            if m:  # a generic ``` inside a payload is shorter than the opener, so it cannot close it
                fence = (m.group(1)[0], len(m.group(1)))
                self.fence[i] = 1
                blk, j = [], i + 1
                while j <= len(self.lines) and not re.match(r"^\s{0,3}(`{3,}|~{3,})\s*$", self.lines[j - 1]):
                    blk.append((j, self.lines[j - 1]))
                    j += 1
                o = 0
                while o < len(blk):  # a fenced block may carry exactly one heredoc; its body is a range
                    ln2, txt = blk[o]
                    h = heredoc(txt)
                    mm = re.search(r"cat\s*>?\s*>?\s*(\S+)\s*<<", txt) if h else None
                    if not (h and mm):
                        o += 1
                        continue
                    e = o + 1
                    while e < len(blk) and blk[e][1].strip() != h[1]:
                        e += 1
                    tgt = norm(mm.group(1))
                    body = "\n".join(t for _, t in blk[o + 1:e])
                    self.bodies.setdefault(tgt, []).append((ln2, body))
                    for bidx, btxt in blk[o + 1:e]:
                        self.body.append((bidx, btxt, tgt))
                    o = e + 1
        self.bodylines = {b[0] for b in self.body}
        self.sec = []
        heads = [(i, m.group(1).strip()) for i, ln in enumerate(self.lines, 1) if (m := H2_RE.match(ln))]
        for n, (i, name) in enumerate(heads):  # headings may be adjacent: no section content between them
            end = heads[n + 1][0] if n + 1 < len(heads) else len(self.lines) + 1
            self.sec.append({"name": name, "line": i, "index": n,
                             "lines": [(j, self.lines[j - 1]) for j in range(i + 1, end) if j not in self.fence],
                             "raw_idx": list(range(i + 1, end)),
                             "raw": [self.lines[j - 1] for j in range(i + 1, end)]})
        self.fields, self.line3 = {}, {}
        if len(self.lines) > 1:
            m = HEAD_RE.match(self.lines[1])
            if m:
                dep = m.group(3)
                self.fields = {"status": m.group(1), "lane": m.group(2), "module": m.group(4),
                               "decisions": [] if m.group(5) == "none" else re.findall(r"[DQ]-\d+", m.group(5)),
                               "depends": [] if dep == "-" else re.findall(IDRE, dep)}
        if len(self.lines) > 2 and self.lines[2].strip() and not self.lines[2].startswith("#"):
            for part in self.lines[2].split("|"):
                if ":" in part:
                    k, v = part.split(":", 1)
                    if k.strip():
                        self.line3[k.strip()] = v.strip()
        m = TITLE_RE.match(self.lines[0] if self.lines else "")
        self.id = m.group(1) if m else ""
        own = []
        for _, ln in self.S("OWNS"):
            if re.match(r"^\s*- ", ln):
                s = spans(ln)
                own.append(norm(s[0] if s else re.sub(r"^\s*- ", "", ln).split()[0]))
        self.owns = [o for o in own if o]
        self.chainline = next(((i, ln) for i, ln in self.S("GATE") if ln.startswith("CHAIN:")), None)
        self.chain = None
        if self.chainline:
            m = CHAIN_RE.match(self.chainline[1])
            if m:
                self.chain = {"before": int(m.group(1)), "k": int(m.group(2)), "after": int(m.group(3)), "label": m.group(4)}
        self.tab = {}
        for s in self.sec:
            hdr, rows = None, []
            for i, ln in s["lines"]:
                if not ln.strip().startswith("|"):
                    continue
                c = cells(ln)
                if hdr is None:
                    hdr = c
                elif not all(re.fullmatch(r":?-{2,}:?", x or "") for x in c):
                    rows.append((i, c))
            if rows:
                self.tab[s["index"]] = rows

    def S(self, *names):
        return [(i, ln) for s in self.sec if s["name"] in names for i, ln in s["lines"]]

    def T(self, *names):
        return [r for s in self.sec if s["name"] in names for r in self.tab.get(s["index"], [])]

    def P(self, *names):
        return [(i, ln) for i, ln in self.S(*names) if not ln.strip().startswith("|")]

    def names(self):
        return [s["name"] for s in self.sec]

    def txt(self, *names):
        return "\n".join(ln for _, ln in self.S(*names))

    def verbatim(self, *names):
        """Section text including fenced lines (a proof or payload search must see the fences)."""
        return "\n".join(ln for s in self.sec if s["name"] in names for ln in s["raw"])

    def sec_of(self, line):
        for n, s in enumerate(self.sec):
            end = self.sec[n + 1]["line"] if n + 1 < len(self.sec) else len(self.lines) + 1
            if s["line"] <= line < end:
                return s["name"]
        return ""

    def cmds(self, *names):
        res = []
        for s in self.sec:
            if s["name"] not in names:
                continue
            rows = dict(self.tab.get(s["index"], []))
            for i, ln in s["lines"]:
                if i in rows:
                    if len(rows[i]) >= 2 and rows[i][1]:
                        res.append((i, rows[i][1].strip("`").strip()))
                elif not ln.strip().startswith("#"):
                    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", ln.strip()):  # FOO=bar prefix is env, not a command
                        continue
                    part = ln.split(" => ")[0] if ln.strip().startswith("`") else ln
                    res += [(i, x.strip()) for x in spans(part)]
            for j in s.get("raw_idx", []):  # fenced command lines in this section are commands too
                if j not in self.fence or j in self.bodylines:
                    continue
                x = self.lines[j - 1].strip()
                if x and not x.startswith("#") and not x.startswith("```"):
                    res.append((j, x))
        return res


class Ctx:
    def __init__(self, root=None):
        self.root = root
        self.floor = 0
        self.ao = [".hermes/plans/WORKLOG.md", ".hermes/plans/gate_output/**", ".hermes/plans/backups/**",
                   ".hermes/plans/REPORT_latest.md", ".hermes/plans/QUESTIONS.md", ".aw/task-start"]
        if root:
            m = re.search(r'"min_tests"\s*:\s*(\d+)', self.read(".aw/ratchet.json") or "")
            self.floor = int(m.group(1)) if m else 0
            m = re.search(r"^ALWAYS_OWNED=(.*)$", self.read("tools/kit.env") or "", re.M)
            if m:
                self.ao = [x for x in m.group(1).split(",") if x]

    def read(self, rel):
        p = os.path.join(self.root or "", rel)
        return open(p, encoding="utf-8", errors="replace").read() if os.path.isfile(p) else None

    def grep(self, rel, tok):
        t = self.read(rel)
        return bool(t and re.search(rf"(?<![A-Za-z0-9]){re.escape(tok)}(?![0-9])", t))


def _neg(line, cmd):
    """Text immediately before a command span, so a prohibition ('never `--write-baseline`') is not read as an action."""
    k = line.find(cmd)
    return re.sub(r"[\s`'\"]+$", "", line[:k]) if k > 0 else ""


def resolves(p):
    return bool(p) and not re.search(r'[$`()~*?<>{}\[\]]', p) and not p.startswith("/") and not re.match(r"^[A-Za-z]:", p)


def lint(c, ctx, quiet=False):
    OUT.clear()
    L, st, names = c.lines, c.fields.get("status", ""), c.names()
    lane = c.fields.get("lane", "")
    owns_line = c.sec[names.index("OWNS")]["line"] if "OWNS" in names else 2
    # ---- L01
    if c.raw.startswith("\ufeff"):
        out("E", "L01", 1, "BOM at start of file", "save as UTF-8 without BOM")
    for i, ln in enumerate(L, 1):
        if "\r" in ln or "\x00" in ln:
            out("E", "L01", i, "CR or NUL byte: the file must be LF, UTF-8", "rewrite with LF endings")
            break
    # ---- L02..L05
    if not c.id:
        out("E", "L02", 1, "line 1 is not '# <ID> - <title>'", "put the id and title on line 1; delete the template legend")
    else:
        stem = os.path.splitext(os.path.basename(c.name))[0]
        if re.fullmatch(IDRE, stem) and stem != c.id:
            out("E", "L02", 1, f"id {c.id} differs from file name {stem}", "rename or re-title")
        if len(TITLE_RE.match(L[0]).group(2).strip()) < 3:
            out("E", "L02", 1, "title shorter than 3 characters", "name the card")
    if not c.fields:
        out("E", "L03", 2, "line 2 does not match the header grammar", "Status | Lane | Depends | Module | Author decisions needed")
    for k in c.line3:
        if k not in LINE3_KEYS:
            out("W", "L03", 3, f"unknown line-3 key '{k}'", "Supersedes / Superseded by / Executor")
    want = {"T": "ROTE", "CHK": "CENSUS", "SPEC": "SPEC"}.get(c.id.split("-")[0] if c.id else "")
    if want and lane and want != lane:
        out("E", "L04", 2, f"{c.id} must be Lane: {want}, header says {lane}", "id prefix and lane disagree")
    if c.id:
        for n in REQ:
            k = names.count(n)
            if k == 0:
                out("E", "L05", 2, f"missing H2 '{n}'", "add the heading")
            elif k > 1:
                out("E", "L05", [s["line"] for s in c.sec if s["name"] == n][1], f"duplicate H2 '{n}'", "keep one")
        seq = [n for n in names if n in REQ]
        if seq != [n for n in REQ if n in seq]:
            first = next(n for n in REQ if n in seq and seq.index(n) < REQ.index(n))
            out("E", "L05", [s["line"] for s in c.sec if s["name"] == first][0], "H2 sections are out of order", "follow the contract order")
        if "STEPS" in names:
            for s in c.sec:
                if s["name"] not in REQ and s["line"] < [x["line"] for x in c.sec if x["name"] == "STEPS"][0]:
                    out("W", "L05", s["line"], f"optional H2 '{s['name']}' before STEPS", "optional sections go after STEPS")
    # ---- L06
    for i, ln in enumerate(L, 1):
        if i in c.fence or c.sec_of(i) == "DRY-RUN PROOF":
            continue
        m = PH.search(ln)
        if m:
            out("E", "L06", i, f"unfilled placeholder {m.group(0)}", "fill or delete")
    # ---- L07..L09
    if "OWNS" in names and not c.owns:
        out("E", "L07", owns_line, "OWNS has no bullet", "OWN every path the card writes; OWNS is a closed list")
    for o in c.owns:
        if o in CATA:
            out("E", "L07", owns_line, f"catastrophic OWNS entry '{o}'", "name the paths")
        elif o.startswith("/") or re.match(r"^[A-Za-z]:", o) or "\\" in o or ".." in o.split("/"):
            out("E", "L07", owns_line, f"OWNS entry '{o}' is not project-relative", "relative path, forward slashes")
    frozen = [x.strip() for x in (ctx.read(".aw/frozen.txt") or "").split("\n") if x.strip() and not x.startswith("#")] + FZ
    for o in c.owns:
        for pat in NEVER:
            if overlap(o, pat):
                out("E" if lane in ("ROTE", "CENSUS") else "W", "L08", owns_line,
                    f"OWNS '{o}' overlaps protected '{pat}'", "not ownable: whoever owns the ledger owns the verdict")
        fr = [p for p in frozen if overlap(o, p)]
        if fr and f"--allow {o}" not in c.txt("AFTER") and f"--allow {fr[0]}" not in c.txt("AFTER"):
            out("E", "L08", owns_line, f"OWNS '{o}' is frozen ({fr[0]}) without --allow in AFTER",
                "make it a SPEC card, or expect INTEGRITY FAIL: FROZEN-CHANGED and allow it in AFTER")
    if lane == "ROTE" and c.owns:
        if len(c.owns) > 12:
            out("W", "L09", owns_line, f"{len(c.owns)} OWNS entries", "split the card")
        if ctx.root:
            files, seen = [], 0
            for d, ds, fs in os.walk(ctx.root):
                ds[:] = [x for x in ds if x not in (".git", ".venv", "node_modules")]
                files += [os.path.relpath(os.path.join(d, f), ctx.root).replace("\\", "/") for f in fs]
                seen += len(fs)
                if seen > 5000:
                    break
            for o in c.owns:
                if "*" in o and len(fnmatch.filter(files, o)) > 10:
                    out("W", "L09", owns_line, f"glob '{o}' matches more than 10 files", "narrow it")
    # ---- L10..L13 (commands in document order, cwd model)
    backup, new = [], []
    for _, ln in c.S("BACKUP"):
        m = re.search(r"aw\.py\s+backup\s+\S+\s+(.+)$", ln.strip())
        if m:
            backup = [norm(x) for x in (spans(m.group(1)) or m.group(1).split())]
        if ln.strip().startswith("NEW:"):
            new = [norm(x) for x in re.split(r"[,\s]+", ln.strip()[4:]) if x and x.lower() not in ("none", "-")]
    cwd, written, patches = "", set(), []
    for i, cmd in c.cmds(*CMD_SECS):
        m = re.match(r"^cd\s+(\S+)\s*(?:&&|$)", cmd)
        if m:
            cwd = "" if norm(m.group(1)) in ("", ".") else norm(m.group(1))
            continue
        for mt in WRX.finditer(cmd):
            p = next((g for g in mt.groups() if g), "")
            if not resolves(p):
                continue
            q = norm(os.path.join(cwd, p))
            if q.startswith(".."):
                out("E", "L10", i, f"write target '{p}' escapes the project root", "project-relative path")
                continue
            written.add(q)
            if not (match(q, c.owns) or match(q, ctx.ao)):
                out("E", "L10", i, f"write target '{q}' is outside OWNS", "add it to OWNS or write elsewhere")
            elif not match(q, ctx.ao) and q not in backup and q not in new:
                out("E", "L11", i, f"'{q}' is written but neither backed up nor declared NEW:", "add it to the backup list or to NEW:")
        if "aw.py patch" in cmd:
            mt = re.match(r".*aw\.py\s+patch\s+(\S+)\s+(\S+)\s+(\S+)", cmd)
            if not mt:
                out("E", "L12", i, "aw.py patch does not have exactly 3 arguments", "patch FILE OLD NEW")
            else:
                patches.append((i, norm(mt.group(1)), norm(mt.group(2)), norm(mt.group(3))))
    for o in backup:
        if o in new:
            out("E", "L11", c.sec[names.index("BACKUP")]["line"], f"'{o}' is both backed up and NEW:", "it exists or it does not")
        elif c.owns and not (match(o, c.owns) or match(o, ctx.ao)):
            out("W", "L11", c.sec[names.index("BACKUP")]["line"], f"backup arg '{o}' is outside OWNS", "back up only what the card owns")
    bodies = c.bodies
    for q, blks in bodies.items():  # the heredoc opener IS a write: check it against OWNS like any redirect
        if not (match(q, c.owns) or match(q, ctx.ao)):
            out("E", "L10", blks[0][0], f"heredoc target '{q}' is outside OWNS", "add it to OWNS or write elsewhere")
        elif not match(q, ctx.ao) and q not in backup and q not in new:
            out("E", "L11", blks[0][0], f"'{q}' is written but neither backed up nor declared NEW:", "add it to the backup list or to NEW:")
    step_writes = {norm(x) for _, cmd in c.cmds("STEPS") for mt in WRX.finditer(cmd) for x in mt.groups() if x}
    for _, r in c.T("STEPS"):  # a `write <path> (block below)` row names its target in the action cell
        if len(r) >= 2 and re.search(r"\b(?:write|create)\b|block below", r[1], re.I) and not re.search(r"(?:^|\s)\d*>", r[1]):
            step_writes |= {norm(x) for x in spans(r[1]) if "/" in x or "." in x}
    for p, blks in bodies.items():
        named = p in step_writes or any(p == norm(x) or norm(x).endswith("/" + p.rsplit("/", 1)[-1]) and p.startswith(".hermes/")
                                        for _, r in c.T("STEPS") if len(r) >= 2 for x in spans(r[1]) if "/" in x)
        if not named:
            out("E", "L12", blks[0][0], f"heredoc writes '{p}' but no STEPS row names it", "add the row that writes it")
    for i, tgt, old, newp in patches:
        for p in (old, newp):
            if p not in bodies:
                out("E", "L12", i, f"patch text '{p}' is never written by this card", "write it with a heredoc first")
        if old in bodies and ctx.root:
            t = ctx.read(tgt)
            if t is not None:
                n = t.replace("\r\n", "\n").count(bodies[old][0][1].replace("\r\n", "\n"))
                if n != 1:
                    out("W", "L13", bodies[old][0][0], f"OLD block occurs {n} times in {tgt}", "the anchor must occur exactly once")
    # ---- L14..L16
    if st not in HIST and c.id:
        pf = c.S("PRE-FLIGHT")
        if not c.chain:
            out("E", "L14", c.chainline[0] if c.chainline else 2, "GATE has no 'CHAIN: ran=A +K -> ran=B (MEASURED|UNMEASURED)'", "one chain line")
        elif c.chain["after"] != c.chain["before"] + c.chain["k"]:
            out("E", "L14", c.chainline[0], f"chain arithmetic: {c.chain['before']}+{c.chain['k']} != {c.chain['after']}", "recompute")
        gate_rows = [(i, ln) for i, ln in pf if "gate.sh" in ln]
        if not gate_rows:
            out("E", "L15", c.sec[names.index("PRE-FLIGHT")]["line"], "PRE-FLIGHT has no gate.sh row", "row 1 = gate at the CHAIN before-count")
        if not any("integrity" in ln for _, ln in pf):
            out("E", "L15", c.sec[names.index("PRE-FLIGHT")]["line"], "PRE-FLIGHT has no integrity row", "row 2 = integrity")
        for i, ln in gate_rows:
            m = re.search(r"GATE OK count=(\d+) min=(\d+)", ln)
            if m and c.chain and int(m.group(1)) != c.chain["before"]:
                out("E", "L15", i, f"PRE-FLIGHT expects count={m.group(1)}, CHAIN ran={c.chain['before']}", "a pre-flight count is the chain before-count")
            if m and ctx.floor and int(m.group(2)) != ctx.floor:
                out("E", "L15", i, f"PRE-FLIGHT min={m.group(2)}, live floor={ctx.floor}", "re-measure before queueing")
        for i, ln in c.S("PRE-FLIGHT", "GATE", "STEPS"):
            if i in c.fence:
                continue
            for m in re.finditer(r"(?<![\w-])(?:min_tests|min|floor)\s*=\s*(\d+)", ln):
                if ctx.floor and int(m.group(1)) != ctx.floor:
                    out("E", "L16", i, f"stale {m.group(0)} (live floor {ctx.floor})", "re-measure before queueing")
            for m in re.finditer(r"--raise\s+(\d+)", ln):
                out("W", "L16", i, f"hard-coded --raise {m.group(1)}", "the floor rises once, to the queue final=")
    # ---- L17/L18
    allow = {0, 1} | ({c.chain["before"], c.chain["after"], c.chain["k"]} if c.chain else set()) | ({ctx.floor} if ctx.floor else set())
    proof = c.verbatim("DRY-RUN PROOF")
    for i, r in c.T("PRE-FLIGHT", "STEPS", "GATE"):
        if len(r) != 3:
            out("E", "L17", i, f"row has {len(r)} cells, need 3", "index | command | expected")
            continue
        if not r[0].isdigit() or not r[1]:
            out("E", "L17", i, "row needs a number and a command", "1 | `cmd` | `expect`")
        e = r[2]
        if not (spans(e) or re.search(r"\b(?:UNMEASURED|record|none)\b", e)):
            out("E", "L17", i, "expected output is empty or uncheckable", "an exact literal, UNMEASURED or record")
            continue
        if re.search(r"\b(?:UNMEASURED|record)\b", e):
            continue
        for t in spans(e) or [e]:
            if re.search(r"\b(?:exit|rc)=\d+", t):
                continue
            if not re.search(r"\d", t):  # no number = nothing to prove
                continue
            if not re.search(r"[A-Za-z]", t) and re.fullmatch(r"[\d\s,.+-]+", t):  # a bare count list
                if {int(x) for x in re.findall(r"\d+", t)} <= allow:
                    continue
            elif t in proof:  # a literal such as `GATE OK count=607 min=602`: it must be in the proof
                continue
            out("E" if st in ("READY", "RUNNING", "REWORK") else "W", "L18", i,
                f"'{t}' carries a number with no measurement", "paste it into DRY-RUN PROOF or write UNMEASURED")
    # ---- L19
    if st in ("READY", "RUNNING") and c.id:
        pv = c.verbatim("DRY-RUN PROOF")
        has_body = any(x.strip() and not x.strip().startswith("```") for x in pv.split("\n"))
        if not re.search(r"```", pv) or not has_body:
            out("E", "L19", c.sec[names.index("DRY-RUN PROOF")]["line"] if "DRY-RUN PROOF" in names else 2,
                f"Status {st} without a DRY-RUN PROOF block", "dry-run the card and paste the real output")
        if c.chain and c.chain["label"] == "MEASURED" and not re.search(rf"(?:count|ran)={c.chain['after']}\b", proof):
            out("E", "L19", c.chainline[0], f"CHAIN says MEASURED but no count={c.chain['after']} in DRY-RUN PROOF", "prove it or write UNMEASURED")
        if c.chain and c.chain["label"] == "UNMEASURED" and c.chain["k"] > 0:
            out("W", "L19", c.chainline[0], "chain UNMEASURED: only the worker's run prints the real ran=", "measure the batch before queueing")
    # ---- family (regex table shared with the spec)
    lc = {"ROTE": "R", "CENSUS": "C", "SPEC": "S"}.get(lane, "?")
    for rid, sev, sc, lanes, ext, rx, msg in FAMILY:
        if lc not in lanes:
            continue
        rgx = re.compile(rx, re.I) if rid in ("L21", "L22") else re.compile(rx)
        if sc == "prose":
            hits = [(i, rgx.search(hide(ln))) for i, ln in c.P(*PROSE_SECS)]
        elif sc == "cmd":
            hits = [(i, rgx.search(cmd)) for i, cmd in c.cmds(*CMD_SECS)
                    if not re.search(r"(?:not|never|no|без|НЕ)$", _neg(c.lines[i - 1], cmd), re.I)]
        elif sc == "exp":
            hits = [(i, rgx.search(r[2])) for i, r in c.T("PRE-FLIGHT", "STEPS", "GATE") if len(r) == 3]
        elif sc == "body":
            hits = [(i, rgx.search(ln)) for i, ln, tgt in c.body if (tgt or "").endswith(ext or "")]
        else:
            hits = [(i, rgx.search(ln)) for i, ln in enumerate(L, 1) if i not in c.fence and c.sec_of(i) != "DRY-RUN PROOF"]
        for i, m in hits:
            if m:
                out(sev, rid, i, msg)
                break
    # ---- L23/L24
    for i, cmd in c.cmds(*CMD_SECS):
        if cmd.strip().startswith("#"):
            continue
        h = heredoc(cmd)
        if h and not h[0]:
            out("E", "L23", i, "heredoc terminator is not quoted", "use <<'EOF' so $ and backticks stay literal")
        if h and not any(c.lines[k - 1].strip() == h[1] for k in range(i + 1, len(c.lines) + 1)):
            out("E", "L23", i, "heredoc is never closed", "add the terminator line")
        try:
            shlex.split(cmd, posix=True)
        except ValueError as e:
            out("E", "L23", i, f"unbalanced quoting ({e})", "an apostrophe inside a single-quoted grep ends the string")
    for i, ln, _t in c.body:
        if i in {b[0] for bl in c.bodies.values() for b in bl}:
            continue  # the opener line itself is not payload
        if heredoc(ln) or "python3 - <<" in ln:
            out("W", "L24", i, "nested heredoc inside a payload", "split it into its own step")
    # ---- L30/L32
    if re.search(r"\bpytest\b", c.raw) and re.search(r"\s-q{1,2}\b", c.raw) and "addopts=" not in c.raw:
        cfg = "".join(filter(None, [ctx.read(x) for x in ("pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini")]))
        if re.search(r"addopts\s*=.*-q", cfg):
            i = next(i for i, ln in enumerate(L, 1) if "pytest" in ln and re.search(r"\s-q{1,2}\b", ln))
            out("W", "L30", i, "pytest -q with -q already in addopts (-qq hides 'N passed')", "drop the flag or pass -o addopts=")
    for i, r in c.T("PRE-FLIGHT", "GATE"):
        if len(r) == 3 and "git status" in r[1] and re.search(r"\b(?:empty|clean|nothing to commit)\b", r[2], re.I) and "E0" not in r[2]:
            out("W", "L32", i, "asserts an empty git status", "record it as E0 in WORKLOG and compare against E0")
    # ---- L34..L37
    if "GOAL" in names:
        g = [ln for _, ln in c.S("GOAL") if ln.strip()]
        if not g:
            out("E", "L34", c.sec[names.index("GOAL")]["line"], "GOAL is empty", "one measurable sentence")
        else:
            if not spans("\n".join(g)):
                out("W", "L34", c.sec[names.index("GOAL")]["line"], "GOAL has no backticked witness", "name the command, file or gate line that proves it")
            if len(g) > 3:
                out("W", "L34", c.sec[names.index("GOAL")]["line"], "GOAL longer than 3 lines", "one sentence")
    if lane == "ROTE" and st not in HIST:
        rp = c.txt("RED PROOF")
        if not rp.strip():
            out("E", "L35", c.sec[names.index("RED PROOF")]["line"] if "RED PROOF" in names else 2, "RED PROOF is empty", "R-6")
        else:
            first = next((ln.strip() for _, ln in c.S("RED PROOF") if ln.strip()), "")
            m = re.search(r"\bstep\s+(\d+)", rp, re.I)
            ok_na = first.lower().startswith("n/a") and len(first) > 5
            ok_step = bool(m and int(m.group(1)) in {int(r[0]) for _, r in c.T("STEPS") if len(r) and r[0].isdigit()})
            if not (ok_na or ok_step):
                out("E", "L35", c.sec[names.index("RED PROOF")]["line"], "RED PROOF names neither a failing step nor n/a + reason",
                    "the RED must be seen failing for the stated reason")
        if "ROLLBACK" not in c.txt("STOP"):
            out("E", "L36", c.sec[names.index("STOP")]["line"] if "STOP" in names else 2, "STOP does not name ROLLBACK", "every STOP branch names its recovery")
        if "ROLLBACK" not in names:
            out("E", "L37", 2, "ROTE card has no ROLLBACK section", "aw.py restore <ID>")
        else:
            rb, rl = c.txt("ROLLBACK"), c.sec[names.index("ROLLBACK")]["line"]
            if not re.search(rf"aw\.py\s+restore\s+{re.escape(c.id)}", rb):
                out("E", "L37", rl, "ROLLBACK does not run aw.py restore <ID>", "restore is the recovery command")
            if "RESTORED" not in rb:
                out("E", "L37", rl, "ROLLBACK does not state the RESTORED line", "the expected output is the check")
            if not re.search(r"\b(?:NEW:|CREATED)\b", rb):
                out("E", "L37", rl, "ROLLBACK does not say what happens to files the card created", "restore never deletes: list them as CREATED")
    # ---- L38..L40
    if c.id:
        for i, cmd in c.cmds(*CMD_SECS):
            for m in re.finditer(rf"(?:aw\.py\s+(?:start|backup|restore|audit)|gate\.sh|re_audit\.sh)\s+(?:pre-)?({IDRE})", cmd):
                if m.group(1) != c.id:
                    out("E", "L38", i, f"command uses {m.group(1)}, this card is {c.id}", "a templated id lands backups and evidence in the wrong card")
            for m in re.finditer(rf"(?:gate_output|backups)[/\\]({IDRE})", cmd):
                if m.group(1) != c.id:
                    out("E", "L38", i, f"evidence path uses {m.group(1)}, this card is {c.id}", "the evidence file is named after the card")
        if f"gate_output/{c.id}" not in c.txt("EVIDENCE") and f"gate_output/{c.id}" not in c.raw:
            out("E", "L38", c.sec[names.index("EVIDENCE")]["line"] if "EVIDENCE" in names else 2,
                f"EVIDENCE does not name gate_output/{c.id}", "the evidence file is named after the card")
        decl = set(c.fields.get("depends", [])) | {c.line3.get("Supersedes", ""), c.line3.get("Superseded by", "")}
        for i, ln in enumerate(L, 1):
            if i in c.fence or c.sec_of(i) == "DRY-RUN PROOF" or i == 1:
                continue
            for m in re.finditer(IDRE, ln):
                if m.group(0) != c.id and m.group(0) not in decl:
                    out("W", "L39", i, f"reference to {m.group(0)} is not declared", "add it to Depends/Supersedes or fix the templated id")
        rows = [(i, r) for i, r in c.T("GATE") if len(r) == 3]
        if rows:
            gr = [(i, r) for i, r in rows if "gate.sh" in r[1]]
            if gr and c.chain:
                m = re.search(r"count=(\d+)", gr[-1][1][2])
                if not m or int(m.group(1)) != c.chain["after"]:
                    out("E", "L40", gr[-1][0], "GATE row does not expect the CHAIN after-count", "count = ran after")
            if not re.search(rf"(?:re_audit\.sh|aw\.py\s+audit)\s+(?:pre-)?{re.escape(c.id)}", rows[-1][1][1]):
                out("E", "L40", rows[-1][0], "last GATE row is not re_audit on this card's id", "R-10: re_audit is the LAST step")
            for i, r in rows:
                m = re.search(r"OWNS='([^']*)'", r[1])
                if m:
                    if {norm(x) for x in m.group(1).split(",") if x.strip()} != set(c.owns):
                        out("E", "L40", i, "OWNS= in the audit row differs from the OWNS section", "a mismatched env produces a false OUT FAIL")
                elif (i, r) is rows[-1] and lane in ("ROTE", "CENSUS"):
                    out("E", "L40", i, "audit row has no OWNS= env", "pass OWNS='<OWNS>' (or the engine reads the card: S1)")
    # ---- L41/L42
    if lane == "CENSUS" and c.id:
        for o in c.owns:
            if not re.fullmatch(rf"\.hermes/plans/gate_output/{re.escape(c.id)}(?:\.[A-Za-z0-9]+)?", o):
                out("E", "L41", owns_line, f"CENSUS OWNS '{o}' is not gate_output/{c.id}.*", "a census card owns exactly its report")
        cmd_text = [x for x in [ln.strip() for _, ln in c.S("BACKUP", "STEPS")] +
                    [r[1].strip() for _, r in c.T("STEPS", "PRE-FLIGHT", "GATE") if len(r) >= 2]]
        if any(re.match(r"^`?(?:python3|bash|PY)\b", x) and re.search(r"aw\.py\s+(?:start|backup|patch)\b", x) for x in cmd_text):
            out("E", "L41", 2, "CENSUS card runs start/backup/patch", "read-only lane")
        if not re.search(r"git status[^\n]*E0", c.txt("GATE")):
            out("E", "L41", c.sec[names.index("GATE")]["line"] if "GATE" in names else 2, "CENSUS GATE has no git status row compared to E0", "the report must leave the tree as it found it")
        for i, ln in c.P("STEPS", "GATE"):
            if re.search(r"\b(?:recommend|verdict|should be|propose|suggest)\b", hide(ln), re.I):
                out("W", "L41", i, "verdict word in a census card", "report facts only")
    if lane == "SPEC":
        ex = c.line3.get("Executor", "")
        if not ex:
            out("E", "L42", 3, "SPEC card has no 'Executor:' line", "name the strong executor on line 3")
        elif re.search(r"\b(?:worker|deepseek|cheap|fast)\b", ex, re.I):
            out("E", "L42", 3, f"Executor '{ex}' is the cheap worker", "a judgement card needs a strong model")
    elif re.search(r"\b(?:claude|sonnet|opus|gpt|o3|strong)\b", c.line3.get("Executor", ""), re.I):
        out("E", "L42", 3, "ROTE/CENSUS card names a strong executor", "the cheap worker runs rote cards")
    # ---- L43..L46
    if c.fields.get("decisions") and st in ("READY", "RUNNING") and ctx.root:
        for d in c.fields["decisions"]:
            ok = ctx.grep(".hermes/plans/QUESTIONS.md", f"ANSWER {d}") if d.startswith("Q-") else ctx.grep(".hermes/plans/DECISIONS.md", d)
            if not ok:
                out("E", "L43", 2, f"{d} is still OPEN but the card is {st}", "the card stays TODO until the author answers")
    if c.fields.get("module", "-") != "-" and ctx.root:
        tab = ctx.read(".hermes/plans/MODULES.md")
        if tab:
            rows = [cells(ln) for ln in tab.split("\n") if ln.strip().startswith("|")]
            rows = [r for r in rows if len(r) >= 9 and re.match(r"^M-\d+", r[0])]
            hit = [r for r in rows if r[0] == c.fields["module"]]
            if not hit:
                out("E", "L44", 2, f"Module {c.fields['module']} is not in MODULES.md", "register it or use -")
            else:
                globs = [g.strip() for g in hit[0][3].split(",") if g.strip()]
                for o in c.owns:
                    if not match(o, globs):
                        out("E", "L44", owns_line, f"OWNS '{o}' is outside module {c.fields['module']}", "cross-module write")
    if c.id in c.fields.get("depends", []):
        out("E", "L45", 2, "Depends lists the card itself", "remove it")
    for d in c.fields.get("depends", []):
        if ctx.root and not os.path.isfile(os.path.join(ctx.root, ".hermes/plans/cards", d + ".md")) and not ctx.grep(".hermes/plans/WORKLOG.md", f"## {d} |"):
            out("W", "L45", 2, f"Depends {d} has no card file and no WORKLOG row", "typo or archived card")
    if st == "OBSOLETE":
        if not any(ln.startswith("OBSOLETE") for ln in L[:8]):
            out("E", "L46", 2, "OBSOLETE card without the line 'OBSOLETE - do not run it'", "a worker that opens the file must see it")
        if "Superseded by" not in c.line3:
            out("E", "L46", 2, "OBSOLETE card without 'Superseded by:'", "name the replacement, or - and a reason")
    for k in ("Supersedes", "Superseded by"):
        v = c.line3.get(k, "")
        if re.fullmatch(IDRE, v) and ctx.root:
            sib = os.path.join(ctx.root, ".hermes/plans/cards", v + ".md")
            if not os.path.isfile(sib):
                out("E", "L46", 3, f"{k} {v} has no card file", "a supersede must point at a real card")
            elif k == "Supersedes" and "Status: OBSOLETE" not in open(sib, encoding="utf-8", errors="replace").read():
                out("E", "L46", 3, f"Supersedes {v} but that card is not OBSOLETE", "mark the old card OBSOLETE")
    return report(quiet)


def report(quiet=False):
    errs = sum(1 for x in OUT if x[2].startswith("LINT E"))
    if not quiet:
        for _, _, msg in sorted(OUT):
            print(msg)
    print(f"CARD-LINT {'OK' if not errs else 'FAIL'} errors={errs} warn={len(OUT) - errs}")
    return errs


LEG = ("GOAL", "OWNS", "READ-ONLY", "PRE-FLIGHT", "BACKUP", "STEPS", "RED PROOF", "GATE", "INVARIANTS", "STOP", "EVIDENCE", "AFTER")


def legacy(text):
    """the earlier project-era cards carry one line per section (`GOAL: ... OWNS: ... STEPS:`). Map the keys onto v2 headings so the
    content rules can run. Fidelity caveat: one-line sections become one bullet each; tables do not exist."""
    pat = re.compile(r"(" + "|".join(re.escape(k) for k in LEG) + r"):")
    res = []
    for ln in text.split("\n"):
        if ln.startswith("# ") or not pat.search(ln):
            res.append(ln)
            continue
        marks = [(m.start(), m.group(1)) for m in pat.finditer(ln)]
        if marks[0][0] > 0 and res and not res[-1].startswith("## "):
            res.append(ln[:marks[0][0]])
        for j, (pos, key) in enumerate(marks):
            end = marks[j + 1][0] if j + 1 < len(marks) else len(ln)
            res += [f"## {key}", "- " + ln[pos + len(key) + 1:end].strip()]
    return "\n".join(res)


MUT = [
 ("T-043", "\n## GATE", "\r\n## GATE", "L01"), ("T-043", "# T-043", "T-043", "L02"),
 ("T-043", "Lane: ROTE", "Lane: FAST", "L03"), ("T-043", "Lane: ROTE", "Lane: SPEC", "L04"),
 ("T-043", "## STOP", "## STOPPED", "L05"), ("T-043", "## GOAL", "## GOAL\n<N>", "L06"),
 ("T-043", "- tests/session/test_routes_http.py", "- **/*", "L07"),
 ("T-043", "- tests/session/test_routes_http.py", "- .hermes/plans/AUDIT_LEDGER.md", "L08"),
 ("T-043", "- tests/session/test_routes_http.py", "\n".join(f"- tests/x{i}/*.py" for i in range(13)), "L09"),
 ("T-043", "cat > tests/session/test_routes_http.py", "cat > tests/session/other.py", "L10"),
 ("T-043", "NEW: tests/session/test_routes_http.py", "NEW: none", "L11"),
 ("T-044", "| 5 | `python3 -I -B tools/aw.py patch src/cart.py", "| 5 | `python3 -I -B tools/aw.py patch src/cart.py --force", "L12"),
 ("T-043", "CHAIN: ran=602 +5 -> ran=607 (MEASURED)", "CHAIN: ran=602 +5 -> ran=608 (MEASURED)", "L14"),
 ("T-043", "GATE OK count=602 min=602", "GATE OK count=598 min=602", "L15"),
 ("T-043", "| `GATE OK count=602 min=602` |", "| `GATE OK count=602 min=777` |", "L16"),
 ("T-043", "| `5 passed` |", "| |", "L17"),
 ("T-043", "| `5 passed` |", "| `7 passed` |", "L18"),
 ("T-043", "## DRY-RUN PROOF", "## PROOF", "L19"),
 ("T-043", "| `5 passed` |", "| `about 5 passed` |", "L20"),
 ("T-043", "## INVARIANTS\n", "## INVARIANTS\nas you see fit\n", "L21"),
 ("T-043", "## INVARIANTS\n", "## INVARIANTS\nmaybe fine\n", "L22"),
 ("T-043", "<<'EOF'", "<<EOF", "L23"),
 ("T-043", "## INVARIANTS\n", "## INVARIANTS\ncd /tmp/x\n", "L28"),
 ("T-043", "## INVARIANTS\n", "## INVARIANTS\n`pip install requests`\n", "L33"),
 ("T-043", "| `uv run ruff check tests/session/test_routes_http.py` |", "| `grep -c '^def' tests/session/x.py` |", "L31"),
 ("T-043", "| record as E0 in WORKLOG |", "| `empty` |", "L32"),
 ("T-043", "After this card `tests/session/test_routes_http.py` holds 5 passing tests for routes that had no direct test, proven by `GATE OK count=607 min=602`.", "", "L34"),
 ("T-043", "n/a - characterization", "characterization run", "L35"),
 ("T-043", "=> ROLLBACK, FAIL format", "=> FAIL format", "L36"),
 ("T-043", "aw.py restore T-043", "aw.py start T-043", "L37"),
 ("T-043", "bash tools/gate.sh T-043", "bash tools/gate.sh T-099", "L38"),
 ("T-043", "## INVARIANTS\n", "## INVARIANTS\nsee T-099\n", "L39"),
 ("T-043", "| `GATE OK count=607 min=602` |", "| `GATE OK count=606 min=602` |", "L40"),
 ("CHK-007", "## BACKUP\nNEW: none", "## BACKUP\n`python3 -I -B tools/aw.py backup CHK-007 x`\nNEW: none", "L41"),
 ("SPEC-002", "Executor: claude-sonnet", "Executor: worker", "L42"),
 ("T-043", "Author decisions needed: none", "Author decisions needed: Q-777", "L43"),
 ("T-043", "Module: -", "Module: M-99", "L44"),
 ("T-043", "Depends: -", "Depends: T-043", "L45"),
 ("T-043", "Status: READY | Lane", "Status: OBSOLETE | Lane", "L46"),
]


def selftest():
    root = tempfile.mkdtemp(prefix="awkit-lint-")
    for d in (".aw", ".hermes/plans/cards", "tests/session", "src"):
        os.makedirs(os.path.join(root, d))
    open(os.path.join(root, ".aw/ratchet.json"), "w").write('{"min_tests": 602}')
    open(os.path.join(root, ".hermes/plans/QUESTIONS.md"), "w").write("## Q-012 | 2026-10-30 | OPEN\nx\n")
    open(os.path.join(root, ".hermes/plans/cards/T-043.md"), "w").write("# T-043 - neighbour\n")
    open(os.path.join(root, ".hermes/plans/MODULES.md"), "w").write(
        "| ID | Module | Purpose | OWNS | Depends | Wave | Gate | Decides | Status |\n|---|---|---|---|---|---|---|---|---|\n"
        "| M-04 | mail | mail tab | web/index.html | - | W-1 | gate | - | ACTIVE |\n")
    base = {k: open(os.path.join(HERE, "fixtures", k + ".md"), encoding="utf-8").read() for k in ("T-043", "T-044", "CHK-007", "SPEC-002")}
    ctx, ok = Ctx(root), True
    for k, txt in base.items():
        errs = lint(Card(txt, k + ".md"), ctx, quiet=True)
        print(f"  fixture {k}: errors={errs}")
        ok &= errs == 0
    runs = 0
    for f, old, new, rid in MUT:
        txt = base[f].replace(old, new, 1)
        if txt == base[f]:
            print(f"  MUTANT-NOT-APPLIED {rid} ({f})")
            ok = False
            continue
        OUT.clear()
        lint(Card(txt, f + ".md"), ctx, quiet=True)
        got = {m.split()[2] for _, _, m in OUT}
        runs += 1
        if rid not in got:
            print(f"  MISS {rid}: fired {sorted(got)}")
            ok = False
    tpl = open(os.path.join(ROOT, "payload", ".hermes", "plans", "TASK_CARD.template.md"), encoding="utf-8").read()
    OUT.clear()
    lint(Card(tpl, "TASK_CARD.template.md"), ctx, quiet=True)
    got = {m.split()[2] for _, _, m in OUT}
    print(f"  unfilled template fires {len(got)} rules incl L02={'L02' in got}")
    ok &= "L02" in got
    print(f"SELFTEST {'PASS' if ok else 'FAIL'} fixtures=4 mutants={runs}")
    if ok:   # a PASS leaves nothing in %TEMP%; a FAIL keeps the dir to read
        shutil.rmtree(root, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "selftest":
        sys.exit(selftest())
    mode = a.pop(0) if a and a[0] in ("card", "legacy") else "card"
    root = a[a.index("--root") + 1] if "--root" in a else None
    a = [x for x in a if x != "--root" and x != root and x != "--strict"]
    if not a:
        sys.exit(__doc__)
    txt = open(a[0], encoding="utf-8", errors="replace").read()
    card = Card(legacy(txt) if mode == "legacy" else txt, a[0])
    if mode == "legacy":
        # content-only pass: the v1 header/headings are a KNOWN structural gap (L02/L03/L05), reported once.
        # Give the mapped card a lane so the content rules run, and keep its real (v1) id out of id-scoped rules.
        if not card.fields:
            card.fields = {"status": "TODO", "lane": "ROTE", "module": "-", "decisions": [], "depends": []}
        card.id = ""
        errs = lint(card, Ctx(root))
        structural = {m.split()[2] for _, _, m in OUT if m.split()[2] in ("L02", "L03", "L05")}
        content = sorted({m.split()[2] for _, _, m in OUT} - structural)
        print(f"CONTENT-RULES-FIRED {content if content else 'none'} (structural: {sorted(structural)})")
        sys.exit(0)
    errs = lint(card, Ctx(root))
    sys.exit(1 if errs else 0)
