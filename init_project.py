#!/usr/bin/env python3
"""init_project.py - install the awkit payload into a project, or measure an existing install's drift.

  python3 init_project.py TARGET_DIR [--name PROJECT_NAME] [--lang bg|en] [--owner NAME]
      installs payload/ into TARGET_DIR. NEVER overwrites and never deletes: a file that already exists is written to
      TARGET_DIR/kit_stage/<same path> instead and listed, so you merge by hand (backup first).
      --lang picks docs/GUIDE.<lang>.md for .hermes/plans/GUIDE.md and the {{REPLY_LANG}} placeholder.
  python3 init_project.py --check TARGET_DIR
      reports drift: `SAME|DIFF|MISSING|STATE <path>` per file, then
      `KIT-CHECK engine_same=<n> engine_diff=<n> missing=<n>`. ENGINE-class files (one named list below) must be
      byte-identical to the kit; STATE-class files are the project's own history and are expected to differ.
Exit codes: 0 ok / 1 --check found engine drift or a missing file / 2 usage error.
"""
import argparse
import os
import re
import stat
import sys
import time
from pathlib import Path

KIT = Path(__file__).resolve().parent
PAYLOAD = KIT / "payload"
JUNK = {"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}   # tool caches that must never be installed
TEXT = {".md", ".py", ".sh", ".env", ".txt", ".json", ".yaml", ".yml", ".disabled", ""}
LANGS = {"bg": "Bulgarian", "en": "English"}

# ONE classification for install and --check. ENGINE = the kit's own code/docs (must be byte-identical after install).
# Everything not listed here is STATE: the project's kit.env, ratchet, frozen list, checks and every plan register.
ENGINE_GLOBS = (
    "tools/aw.py", "tools/gate.sh", "tools/re_audit.sh", "tools/worker_report.py", "tools/learn.py", "tools/review_pack.py", "tools/findings_lint.py", "tools/effort.py", ".githooks/pre-commit",
    ".aw/KIT_VERSION", ".aw/checks.d/README.md", ".aw/checks.d/example_todo_count.py.disabled", ".aw/checks.d/example_debug_tags.py.disabled",
    ".hermes/prompts/*", ".hermes/plans/TASK_CARD.template.md", ".hermes/plans/PLAYBOOK.md",
    ".hermes/plans/START_BLOCKS.md", ".hermes/plans/SELF_IMPROVE.md", ".hermes/plans/CARD_PATTERNS.md", ".hermes/plans/GUIDE.md",
    ".hermes/plans/HANDOFF.template.md", ".hermes/plans/QUESTIONNAIRE.template.md",
    ".hermes/plans/AUTHOR_ANSWERS.template.md", ".hermes/plans/cards/QUEUE.template.md",
    ".hermes/plans/gate_output/.gitkeep", ".gitattributes",
)
import fnmatch


def is_engine(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, g) for g in ENGINE_GLOBS)


def render(data: bytes, subs: dict) -> bytes:
    """Text files: LF only, BOM stripped, {{PLACEHOLDERS}} substituted. Binaries are copied byte-for-byte."""
    try:
        t = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    for k, v in subs.items():
        t = t.replace("{{" + k + "}}", v)
    return t.encode("utf-8")


PLACEHOLDER_RX = re.compile(r"\{\{[A-Z_]+\}\}")


def same_ignoring_placeholders(kit_text: str, dst_text: str) -> bool:
    """An ENGINE file with {{...}} slots is project-specific after install: compare around the slots."""
    if dst_text == kit_text:
        return True
    parts = PLACEHOLDER_RX.split(kit_text)
    if len(parts) == 1:
        return False
    rx = "^" + ".+?".join(re.escape(p) for p in parts) + "$"
    return re.match(rx, dst_text, re.S) is not None


def check(target: Path) -> int:
    same = diff = missing = state = 0
    for src in sorted(PAYLOAD.rglob("*")):
        if src.is_dir():
            continue
        if set(src.relative_to(PAYLOAD).parts) & JUNK or src.suffix == ".pyc":
            continue
        rel = src.relative_to(PAYLOAD).as_posix()
        dst = target / rel
        if not is_engine(rel):
            state += 1
            print(("STATE" if dst.is_file() else "MISSING") + " " + rel)
            missing += 0 if dst.is_file() else 1
            continue
        if not dst.is_file():
            print("MISSING " + rel)
            missing += 1
            continue
        try:
            k = src.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
            d = dst.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
            ok = same_ignoring_placeholders(k, d)
        except UnicodeDecodeError:
            ok = src.read_bytes() == dst.read_bytes()
        if ok:
            same += 1
            print("SAME " + rel)
        else:
            diff += 1
            print("DIFF " + rel)
    g = target / ".hermes/plans/GUIDE.md"
    if g.is_file():
        txt = g.read_text(encoding="utf-8", errors="replace")
        pick = [lang for lang, name in LANGS.items() if _guide(lang).read_text(encoding="utf-8", errors="replace") == txt]
        print("STATE .hermes/plans/GUIDE.md" + (f" (matches docs/GUIDE.{pick[0]}.md)" if pick else " (edited after install)"))
    print(f"KIT-CHECK engine_same={same} engine_diff={diff} missing={missing}")
    if diff or missing:
        print("FIX: re-install the engine files (`python3 init_project.py <dir>`) - they land in kit_stage/ and you merge by hand;"
              " STATE files are the project's own history and are never touched")
        return 1
    return 0


def _guide(lang: str) -> Path:
    return KIT / "docs" / f"GUIDE.{lang}.md"


def main() -> int:
    ap = argparse.ArgumentParser(description="install awkit into a project, or check its drift")
    ap.add_argument("target", nargs="?", type=Path)
    ap.add_argument("--check", dest="check_dir", type=Path, default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--lang", choices=sorted(LANGS), default="en")
    ap.add_argument("--owner", default="Owner")
    a = ap.parse_args()
    if a.check_dir:
        t = a.check_dir.resolve()
        if not t.is_dir():
            print(f"KIT-CHECK FAIL: {t} is not a directory -> pass the project root")
            return 2
        return check(t)
    if not a.target:
        ap.print_usage()
        print("FIX: `python3 init_project.py <dir> --name <Project>` or `python3 init_project.py --check <dir>`")
        return 2
    target = a.target.resolve()
    if target == KIT or KIT in target.parents:
        print(f"refusing to install into the kit's own tree ({target}) -> pass the project directory")
        return 2
    name = a.name or target.name
    for _label, _value in (("--name", name), ("--owner", a.owner)):   # a newline here would inject a line into kit.env
        if chr(10) in _value or chr(13) in _value or len(_value) > 80:
            print(f"REFUSED: {_label} must be one line of at most 80 chars (a newline would inject a line into tools/kit.env)")
            return 2
    subs = {"PROJECT_NAME": name, "DATE": time.strftime("%Y-%m-%d"), "OWNER": a.owner, "REPLY_LANG": LANGS[a.lang]}
    target.mkdir(parents=True, exist_ok=True)
    if not (KIT / "docs").is_dir():
        print("WARN docs/GUIDE.<lang>.md missing in the kit -> payload GUIDE.md is installed as-is (write your own)")
    written, staged, identical = [], [], []
    for src in sorted(PAYLOAD.rglob("*")):
        if src.is_dir():
            continue
        if set(src.relative_to(PAYLOAD).parts) & JUNK or src.suffix == ".pyc":
            continue
        rel = src.relative_to(PAYLOAD)
        data = render(src.read_bytes(), subs)
        dst = target / rel
        if dst.exists():
            try:
                if dst.read_bytes() == data:
                    identical.append(str(rel))
                    continue  # byte-identical: nothing to merge, keep the tree quiet
            except OSError:
                pass
            dst = target / "kit_stage" / rel
            staged.append(str(rel))
        else:
            written.append(str(rel))
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            continue  # a kit_stage copy from a previous run: never overwrite it
        dst.write_bytes(data)
        if (rel.suffix in (".sh", ".py") and "tools" in rel.parts) or rel.as_posix() in ("init_project.py", "tools/gate.sh", "tools/re_audit.sh"):
            dst.chmod(dst.stat().st_mode | stat.S_IXUSR)
    src_guide = _guide(a.lang)
    if src_guide.is_file():
        gdst = target / ".hermes/plans/GUIDE.md"
        if not gdst.exists():
            gdst.parent.mkdir(parents=True, exist_ok=True)
            gdst.write_bytes(render(src_guide.read_bytes(), subs))
            written.append(".hermes/plans/GUIDE.md")
        elif gdst.read_bytes() != render(src_guide.read_bytes(), subs):
            staged.append(".hermes/plans/GUIDE.md")
            kd = target / "kit_stage/.hermes/plans/GUIDE.md"
            if not kd.exists():
                kd.parent.mkdir(parents=True, exist_ok=True)
                kd.write_bytes(render(src_guide.read_bytes(), subs))
    print(f"INSTALLED into {target}: {len(written)} new file(s), {len(staged)} collision(s) staged in kit_stage/"
          + (f", {len(identical)} already identical" if identical else "") + f" (lang={a.lang})")
    for s in staged:
        print("  COLLISION (merge by hand, backup first):", s)
    print("NEXT: python3 tools/aw.py doctor  ->  edit tools/kit.env (PY, TEST_CMD, COUNT_REGEX)  ->  bash tools/gate.sh baseline"
          "  ->  python3 tools/aw.py ratchet --raise <measured> --i-am-architect  ->  fill .aw/frozen.txt + .aw/checks.d  ->"
          "  python3 tools/aw.py integrity --write-baseline --i-am-architect")
    return 0


if __name__ == "__main__":
    sys.exit(main())
