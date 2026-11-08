#!/usr/bin/env python3
"""effort.py - which reasoning effort does this work need? Read-only: it reads the project files and prints ONE line
(only `block --out FILE` writes, and only FILE). It cannot change a running chat: Hermes gives a chat no tool to set its own
level and does not tell the model its level. The launchers START_ARCHITECT.cmd / START_WORKER.cmd pass the answer to `hermes chat --reasoning`.
  python3 -I -B tools/effort.py stage [--level]             ARCHITECT, by the files: E1 newest WORKLOG entry FAIL | E2 AUTHOR_ANSWERS_*.md and no card yet (plan + cards) | E3 an open SPEC card | E4 the rest
  python3 -I -B tools/effort.py card ID|FILE [--level]      one card: W1 SPEC lane (HARD) | W5 kit.env EFFORT_WORKER=<level> (default ultra) | with EFFORT_WORKER=auto: W2 it (or the card it supersedes) FAILED | W3 steps>=10 or fenced>=4000 B or OWNS>=5 | W4 the rest
  python3 -I -B tools/effort.py queue [QUEUE.md] [--level]  WORKER: the hardest card of the newest queue that still has cards without a WORKLOG entry
  python3 -I -B tools/effort.py block [QUEUE.md] --out FILE write that queue's START BLOCK (UTF-8, LF) for START_WORKER.cmd
Levels (none minimal low medium high xhigh max ultra): tools/kit.env EFFORT_DEFAULT (medium), EFFORT_HARD (ultra), EFFORT_WORKER (ultra or auto); a bad value is ignored and said.
Line: `EFFORT <level> <who> <rule> <reason>`; --level prints the level only. Exit 0; 2 usage; 3 nothing to run.
EFFORT_WORKER defaults to ultra: in 12 pilots (6 per level, 2026-11-08) medium finished 5 queues of 6, ultra 6 of 6 (p=1.0: a hint, not proof; CHANGELOG 2.8.0). W3 sits above all 19 cards of three projects (steps 3-9, fenced 117-3254 B, OWNS 1-4).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; PL = ROOT / ".hermes/plans"
LEVELS = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"); ID = r"(?:T|CHK|SPEC)-\d{3,5}"
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
def rd(p):
    try: return p.read_text(encoding="utf-8-sig", errors="replace")
    except OSError: return ""
def levels():
    env = {}
    for ln in rd(ROOT / "tools/kit.env").splitlines():
        if "=" in ln and not ln.lstrip().startswith("#"): k, v = ln.split("=", 1); env[k.strip()] = v.strip()
    lo, hi, wk = env.get("EFFORT_DEFAULT") or "medium", env.get("EFFORT_HARD") or "ultra", env.get("EFFORT_WORKER") or "ultra"
    if lo in LEVELS and hi in LEVELS and LEVELS.index(lo) <= LEVELS.index(hi) and wk in LEVELS + ("auto",): return lo, hi, wk, ""
    return "medium", "ultra", "ultra", f" [kit.env EFFORT_DEFAULT={lo} EFFORT_HARD={hi} EFFORT_WORKER={wk} ignored: levels are {' '.join(LEVELS)} (+ auto for the worker), DEFAULT not above HARD]"
def worklog(): return re.findall(rf"(?m)^## ({ID}) \| [^|\n]*\| (PASS|FAIL) \|", rd(PL / "WORKLOG.md"))
def facts(t):   # (lane, status, STEPS rows, OWNS lines, fenced bytes outside DRY-RUN PROOF)
    h = re.search(r"(?m)^Status: (\w+) \| Lane: (ROTE|CENSUS|SPEC) \|", t); sec = fence = ""; steps = owns = fb = 0
    for ln in t.split("\n"):
        m = re.match(r"^\s{0,3}(`{3,}|~{3,})", ln)
        if m:
            if not fence: fence = m.group(1)
            elif ln.strip() == m.group(1) and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence): fence = ""
            continue
        if fence: fb += (sec != "DRY-RUN PROOF") * (len(ln) + 1)
        elif ln.startswith("## "): sec = ln[3:].split(" (")[0].strip()
        elif sec == "STEPS" and re.match(r"\|\s*\d+\s*\|", ln): steps += 1
        elif sec == "OWNS" and ln.lstrip().startswith("-"): owns += 1
    return (h.group(2), h.group(1), steps, owns, fb) if h else ("?", "?", steps, owns, fb)
def open_fail():   # the newest WORKLOG entry is a FAIL and the question it filed (if any) has no ANSWER line yet
    t = rd(PL / "WORKLOG.md"); hs = list(re.finditer(rf"(?m)^## ({ID}) \| [^|\n]*\| (PASS|FAIL) \|.*$", t))
    if not hs or hs[-1].group(2) != "FAIL": return None
    qs = re.findall(r"\bQ-\d{3,4}\b", t[hs[-1].end():]); answered = set(re.findall(r"(?m)^ANSWER (Q-\d{3,4})\b", rd(PL / "QUESTIONS.md")))
    return hs[-1].group(1) if not qs or any(q not in answered for q in qs) else None
def judge_stage(lo, hi):
    cards = [p for p in (PL / "cards").glob("*.md") if re.fullmatch(rf"{ID}\.md", p.name)]
    if open_fail(): return hi, "E1", f"the newest WORKLOG entry is a FAIL ({open_fail()}) and its question is still open: diagnose it"
    if list(PL.glob("AUTHOR_ANSWERS_*.md")) and not cards: return hi, "E2", "the Author's answers are recorded and no card exists yet: stage 2 = plan + cards"
    spec = [p.stem for p in cards if re.search(r"(?m)^Status: (?:TODO|READY|RUNNING|REWORK) \| Lane: SPEC \|", rd(p))]
    if spec: return hi, "E3", f"open SPEC card {spec[0]}: judgement work"
    return lo, "E4", "no hard trigger in the files: audit, replay, upgrade, registers or the questionnaire"
def judge_card(arg, lo, hi, wk):
    p = Path(arg) if Path(arg).is_file() else PL / "cards" / (arg + ".md"); t = rd(p)
    if not t: return lo, "W0", f"card {arg} not found or empty"
    lane, _st, steps, owns, fb = facts(t); cid = p.stem; last = dict(worklog())   # a later entry of an id wins
    failed = [i for i in [cid] + re.findall(ID, " ".join(re.findall(r"(?m)^Supersedes:\s*(.+)$", t))) if last.get(i) == "FAIL"]
    if lane == "SPEC": return hi, "W1", f"{cid} is a SPEC card (judgement work): a strong executor, not the cheap worker"
    if wk != "auto": return wk, "W5", f"{cid}: kit.env EFFORT_WORKER={wk}, one level for every worker card (auto = rules W2-W4)"
    if failed: return hi, "W2", f"{failed[0]} FAILED in its last run: its re-run or replacement goes hard"
    if steps >= 10 or fb >= 4000 or owns >= 5: return hi, "W3", f"{cid} is large (steps={steps} fenced={fb}B owns={owns}): split it, else run it hard"
    return lo, "W4", f"{cid} {lane} within size (steps={steps} fenced={fb}B owns={owns})"
def newest_queue():
    qs = [p for p in (PL / "cards").glob("QUEUE*.md") if "template" not in p.name.lower()]
    return max(qs, key=lambda p: p.stat().st_mtime) if qs else None
def queue_ids(t):
    m = re.search(r"(?m)^\s*Chain:\s*base=\d+\s*\|(.+?)\|", t)
    return re.findall(rf"\b({ID})\s*:", m.group(1)) if m else []
def main(av):
    pos = [a for a in av if not a.startswith("--")]; only = "--level" in av; out = None
    if "--out" in av and av.index("--out") + 1 < len(av): out = av[av.index("--out") + 1]; pos = [a for a in pos if a != out]
    lo, hi, wk, note = levels(); cmd, arg = (pos + ["", ""])[:2]
    def say(level, who, rule, why): print(level if only else f"EFFORT {level} {who} {rule} {why}{note}"); return 0
    if cmd == "stage": return say(*(lambda r: (r[0], "architect", r[1], r[2]))(judge_stage(lo, hi)))
    if cmd == "card" and arg: return say(*(lambda r: (r[0], "worker", r[1], r[2]))(judge_card(arg, lo, hi, wk)))
    if cmd in ("queue", "block"):
        q = Path(arg) if arg else newest_queue(); t = rd(q) if q else ""
        if q is None or not t: print("" if only else "EFFORT none - no queue file (.hermes/plans/cards/QUEUE_<date>.md)"); return 3
        ids = queue_ids(t); done = {i for i, _v in worklog()}; todo = [i for i in ids if i not in done]
        if not ids or (not arg and not todo): print("" if only else f"EFFORT none - {q.name}: " + ("no Chain: line" if not ids else f"all {len(ids)} cards already have a WORKLOG entry")); return 3
        if cmd == "block":
            m = re.search(r"(?ms)^## START BLOCK[^\n]*\n(`{3,})[^\n]*\n(.*?)\n\1[ \t]*$", t)
            if not m or not out: print("EFFORT none - " + (f"{q.name} has no START BLOCK" if not m else "block needs --out FILE")); return 3
            Path(out).write_bytes((m.group(2).replace("\r\n", "\n") + "\n").encode("utf-8")); print(f"BLOCK {q.name} -> {out} ({len(m.group(2))} chars)"); return 0
        res = [judge_card(i, lo, hi, wk) for i in (todo or ids)]; top = max(range(len(res)), key=lambda k: LEVELS.index(res[k][0]))
        return say(res[top][0], "worker", res[top][1], f"queue {q.name}, {len(todo or ids)} card(s), hardest {(todo or ids)[top]}: {res[top][2]}")
    print((__doc__ or "").split("\n", 1)[0] + "\nusage: effort.py stage|card ID|queue [QUEUE.md]|block [QUEUE.md] --out FILE [--level]"); return 2
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
