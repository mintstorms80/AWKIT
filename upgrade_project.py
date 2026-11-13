#!/usr/bin/env python3
"""upgrade_project.py - upgrade an existing awkit install from its older kit version to this kit's payload (stdlib only).
  python3 upgrade_project.py TARGET_DIR [--apply]
Dry-run by default (writes nothing); --apply backs up every replaced file and tools/kit.env into
.hermes/plans/backups/KIT-<old>-<date>.zip first, preserves each file's line endings, never touches STATE files or LOCAL engine edits
(stages the new copy into kit_stage/<path> instead), adds missing keys to tools/kit.env without changing existing lines, and writes
.aw/KIT_VERSION LAST. Exit 0 ok, 2 REFUSED."""
from __future__ import annotations

import argparse
import io
import re
import stat
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

KIT = Path(__file__).resolve().parent
sys.path.insert(0, str(KIT))
import init_project as ip  # noqa: E402
PAYLOAD = KIT / "payload"
LAUNCHERS = (("START_ARCHITECT.cmd", "start_architect.cmd"), ("START_WORKER.cmd", "start_worker.cmd"),
             ("START_PLAN.cmd", "start_plan.cmd"), ("UPGRADE_KIT.cmd", "upgrade_kit.cmd"))
Q3 = '"' * 3


def refuse(msg: str) -> int:
    print(f"REFUSED: {msg}")
    return 2


def vtuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except ValueError:
        return ()


def git_versions() -> dict:
    if not (KIT / ".git").exists():
        return {}
    try:
        log = subprocess.check_output(["git", "-C", str(KIT), "log", "-p", "--format=COMMIT %h", "--", "payload/.aw/KIT_VERSION"],
                                      text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return {}
    out: dict = {}
    cur = None
    for ln in log.splitlines():
        if ln.startswith("COMMIT "):
            cur = ln.split()[1]
        elif ln.startswith("+2.") and cur:
            out.setdefault(ln[1:].strip(), cur)
            cur = None
    cur_v = (PAYLOAD / ".aw/KIT_VERSION").read_text(encoding="utf-8", errors="replace").strip() if (PAYLOAD / ".aw/KIT_VERSION").is_file() else ""
    if cur_v and cur_v not in out:
        out[cur_v] = "WORKING"
    return out


def load_tree(sha: str) -> dict[str, bytes]:
    if sha == "WORKING":
        return {p.relative_to(KIT).as_posix(): p.read_bytes() for p in KIT.rglob("*") if p.is_file() and ".git" not in p.parts}
    r = subprocess.run(["git", "-C", str(KIT), "archive", sha], capture_output=True)
    if r.returncode != 0:
        return {}
    blobs: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
        for m in tf.getmembers():
            if m.isfile():
                f = tf.extractfile(m)
                if f is not None:
                    blobs[m.name] = f.read()
    return blobs


def candidates(blob: bytes | None, subs: dict) -> list[bytes]:
    if blob is None:
        return []
    lf = blob.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    rlf = ip.render(blob, subs)
    rcrlf = rlf.replace(b"\n", b"\r\n")
    return [blob, lf, crlf, rlf, rcrlf]


def extract_subs(target: Path) -> dict | None:
    arch = target / ".hermes/prompts/ARCHITECT.md"
    if not arch.is_file():
        return None
    t = arch.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    m1 = re.search(r"^# ARCHITECT v2\.0 \u2014 (.+)$", t, re.M)
    m2 = re.search(r"the AUTHOR \(([^)]+)\) decides .* Reply in ([A-Za-z]+);", t)
    if not (m1 and m2):
        return None
    date_val = time.strftime("%Y-%m-%d")
    g = target / ".hermes/plans/GUIDE.md"
    if g.is_file():
        mg = re.search(r"(?:\u0421\u044a\u0437\u0434\u0430\u0434\u0435\u043d\u043e|Written) (\d{4}-\d{2}-\d{2})\.",
                       g.read_text(encoding="utf-8", errors="replace"))
        if mg:
            date_val = mg.group(1)
    return {"PROJECT_NAME": m1.group(1).strip(), "OWNER": m2.group(1).strip(),
            "REPLY_LANG": m2.group(2).strip(), "DATE": date_val}


def start_plan_prompt() -> bytes:
    sp = (KIT / "setup_project.py").read_text(encoding="utf-8")
    m = re.search("START_PLAN_PROMPT_TEXT = " + Q3 + "(.*?)" + Q3, sp, re.S)
    return (m.group(1) if m else "# START_PLAN_PROMPT\nNo cards here; use START_ARCHITECT.cmd for cards.\n").encode("utf-8")


def start_arch_prompt(old_blobs: dict[str, bytes]) -> list[bytes]:
    out = []
    sources = [(KIT / "setup_project.py").read_bytes()]
    if "setup_project.py" in old_blobs:
        sources.append(old_blobs["setup_project.py"])
    if (KIT / ".git").exists():
        try:
            shas = subprocess.check_output(["git", "-C", str(KIT), "log", "--format=%h", "--", "setup_project.py"],
                                           text=True, stderr=subprocess.DEVNULL).split()
            if shas:
                blobs = subprocess.check_output(["git", "-C", str(KIT), "show", *[f"{h}:setup_project.py" for h in shas]],
                                                stderr=subprocess.DEVNULL)
                sources.append(blobs)
        except (OSError, subprocess.SubprocessError):
            pass
    for src in sources:
        txt = src.decode("utf-8", errors="replace")
        for m in re.finditer(r"write_text\(" + Q3 + "(# START_PROMPT.*?)" + Q3, txt, re.S):
            clean = re.sub(r"(?m)^[+-]", "", m.group(1)).replace("\r\n", "\n").encode("utf-8")
            out += [clean, clean.replace(b"\n", b"\r\n")]
            raw = m.group(1).replace("\r\n", "\n").encode("utf-8")
            out += [raw, raw.replace(b"\n", b"\r\n")]
    return out


def env_blocks(kit_env_text: str, subs: dict) -> list[tuple[str, str]]:
    rendered = ip.render(kit_env_text.encode("utf-8"), subs).decode("utf-8")
    out, comments = [], []
    for ln in rendered.split("\n"):
        if ln.startswith("#"):
            comments.append(ln)
        elif re.match(r"^[A-Z_][A-Z0-9_]*=", ln):
            k = ln.split("=", 1)[0]
            out.append((k, "\n".join(comments + [ln])))
            comments = []
        else:
            comments = []
    return out


def upgrade(target: Path, apply: bool = False) -> int:
    if not target.is_dir():
        return refuse(f"{target} is not a directory")
    r = subprocess.run(["git", "-C", str(target), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return refuse(f"no git commit in {target} (make the first commit before upgrading)")
    kv_file = target / ".aw/KIT_VERSION"
    if not kv_file.is_file():
        return refuse("missing .aw/KIT_VERSION in target")
    old_v = kv_file.read_text(encoding="utf-8", errors="replace").strip()
    new_v = (PAYLOAD / ".aw/KIT_VERSION").read_text(encoding="utf-8").strip()
    if not vtuple(old_v) or not vtuple(new_v):
        return refuse(f"invalid version string ({old_v!r} -> {new_v!r})")
    if vtuple(old_v) > vtuple(new_v):
        return refuse(f"target version {old_v} is newer than kit {new_v}")
    vmap = git_versions()
    if not vmap:
        return refuse("kit has no git history (use `python3 init_project.py <dir>` to stage into kit_stage/)")
    if old_v not in vmap:
        return refuse(f"target version {old_v} is not in the kit's git history (use init_project.py -> kit_stage/)")
    old_blobs = load_tree(vmap[old_v])
    subs = extract_subs(target)
    if not subs:
        return refuse("cannot extract PROJECT_NAME/OWNER/REPLY_LANG from .hermes/prompts/ARCHITECT.md")
    arch_dst = (target / ".hermes/prompts/ARCHITECT.md").read_bytes()
    if arch_dst not in candidates(old_blobs.get("payload/.hermes/prompts/ARCHITECT.md"), subs) + candidates((PAYLOAD / ".hermes/prompts/ARCHITECT.md").read_bytes(), subs):
        return refuse("installed .hermes/prompts/ARCHITECT.md cannot be reproduced from its kit version")

    lang_code = "bg" if subs["REPLY_LANG"] == "Bulgarian" else "en"
    actions = []
    for src in sorted(PAYLOAD.rglob("*")):
        if src.is_dir() or ip.JUNK.intersection(src.relative_to(PAYLOAD).parts) or src.suffix == ".pyc":
            continue
        rel = src.relative_to(PAYLOAD).as_posix()
        if not ip.is_engine(rel):
            continue
        raw_src = (KIT / f"docs/GUIDE.{lang_code}.md").read_bytes() if rel == ".hermes/plans/GUIDE.md" and (KIT / f"docs/GUIDE.{lang_code}.md").is_file() else src.read_bytes()
        rendered_lf = ip.render(raw_src, subs)
        if re.search(rb"\{\{[A-Z_][A-Z0-9_]*\}\}", rendered_lf):
            return refuse(f"unfilled placeholder '{{{{' in rendered {rel}")
        dst = target / rel
        if not dst.is_file():
            actions.append(("ADD", rel, rendered_lf))
            continue
        cur = dst.read_bytes()
        new_cands = [rendered_lf, rendered_lf.replace(b"\n", b"\r\n")]
        if cur in new_cands and rel != ".aw/KIT_VERSION":
            actions.append(("SAME", rel, rendered_lf))
            continue
        old_cands = candidates(old_blobs.get(f"payload/{rel}"), subs)
        if rel == ".hermes/plans/GUIDE.md":
            old_cands += candidates(old_blobs.get(f"docs/GUIDE.{lang_code}.md"), subs)
        if cur in old_cands or cur in new_cands:
            actions.append(("SAME" if cur in new_cands else "REPLACE", rel, rendered_lf))
        else:
            actions.append(("LOCAL", rel, rendered_lf))

    for rel, new_lf, old_cands in (
        (".hermes/START_PROMPT.md", start_arch_prompt(old_blobs)[0], start_arch_prompt(old_blobs)),
        (".hermes/START_PLAN_PROMPT.md", start_plan_prompt(), []),
    ):
        dst = target / rel
        if not dst.is_file():
            actions.append(("ADD", rel, new_lf))
        elif dst.read_bytes() in [new_lf, new_lf.replace(b"\n", b"\r\n")]:
            actions.append(("SAME", rel, new_lf))
        elif dst.read_bytes() in old_cands:
            actions.append(("REPLACE", rel, new_lf))
        else:
            actions.append(("LOCAL", rel, new_lf))

    for dst_name, kit_name in LAUNCHERS:
        ksrc = KIT / kit_name
        if not ksrc.is_file():
            continue
        new_lf = ksrc.read_bytes().replace(b"\r\n", b"\n")
        dst = target / dst_name
        old_cands = candidates(old_blobs.get(kit_name), {})
        if not dst.is_file():
            actions.append(("ADD", dst_name, new_lf))
        elif dst.read_bytes() in [new_lf, new_lf.replace(b"\n", b"\r\n")]:
            actions.append(("SAME", dst_name, new_lf))
        elif dst.read_bytes() in old_cands:
            actions.append(("REPLACE", dst_name, new_lf))
        else:
            actions.append(("LOCAL", dst_name, new_lf))

    ke_dst = target / "tools/kit.env"
    ke_raw = ke_dst.read_bytes() if ke_dst.is_file() else b""
    ke_txt = ke_raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    have_keys = {m.group(1) for m in re.finditer(r"^([A-Z_][A-Z0-9_]*)=", ke_txt, re.M)}
    missing_kv = [(k, blk) for k, blk in env_blocks((PAYLOAD / "tools/kit.env").read_text(encoding="utf-8"), subs) if k not in have_keys]

    actions.sort(key=lambda x: (x[1] == ".aw/KIT_VERSION", x[1]))
    for kind, rel, _ in actions:
        print(f"{kind} {rel}")
    for k, _ in missing_kv:
        print(f"KEY {k}")

    n_rep = sum(x[0] == "REPLACE" for x in actions)
    n_add = sum(x[0] == "ADD" for x in actions)
    n_loc = sum(x[0] == "LOCAL" for x in actions)
    n_key = len(missing_kv)

    if not apply:
        print(f"KIT-UPGRADE PLAN from={old_v} to={new_v} replace={n_rep} add={n_add} local={n_loc} keys={n_key}")
        return 0

    proj_crlf = b"\r\n" in ke_raw or b"\r\n" in arch_dst
    bdir = target / ".hermes/plans/backups"
    bdir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d")
    zpath = bdir / f"KIT-{old_v}-{stamp}.zip"
    idx = 2
    while zpath.exists():
        zpath = bdir / f"KIT-{old_v}-{stamp}.{idx}.zip"
        idx += 1

    if n_rep or n_add or n_loc or n_key:
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
            for kind, rel, _ in actions:
                if kind == "REPLACE" and (target / rel).is_file():
                    zf.writestr(rel, (target / rel).read_bytes())
            if n_key and ke_dst.is_file():
                zf.writestr("tools/kit.env", ke_raw)

    if n_key and ke_dst.is_file():
        eol = b"\r\n" if b"\r\n" in ke_raw else (b"\r\n" if proj_crlf else b"\n")
        prefix = ke_raw if ke_raw.endswith(b"\n") else ke_raw + eol
        added_bytes = ("\n".join(blk for _, blk in missing_kv) + "\n").encode("utf-8").replace(b"\n", eol)
        ke_dst.write_bytes(prefix + added_bytes)

    for kind, rel, new_lf in actions:
        if kind == "SAME":
            continue
        dst = target / rel
        if kind == "LOCAL":
            st_dst = target / "kit_stage" / rel
            st_dst.parent.mkdir(parents=True, exist_ok=True)
            eol = b"\r\n" if b"\r\n" in dst.read_bytes() else b"\n"
            st_dst.write_bytes(new_lf.replace(b"\n", eol))
            continue
        use_crlf = (b"\r\n" in dst.read_bytes()) if dst.is_file() else proj_crlf
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(new_lf.replace(b"\n", b"\r\n" if use_crlf else b"\n"))
        if (dst.suffix in (".sh", ".py") and "tools" in Path(rel).parts) or rel in ("tools/gate.sh", "tools/re_audit.sh"):
            dst.chmod(dst.stat().st_mode | stat.S_IXUSR)

    zrel = zpath.relative_to(target).as_posix() if zpath.exists() else "none"
    print(f"KIT-UPGRADE DONE from={old_v} to={new_v} replace={n_rep} add={n_add} local={n_loc} keys={n_key} backup={zrel}")
    print("NEXT: python3 -I -B tools/aw.py integrity --write-baseline --i-am-architect  ->  python3 -I -B tools/aw.py integrity  ->  python3 -I -B tools/aw.py doctor  ->  git config core.hooksPath .githooks")
    print(f"LEDGER: ### {stamp} ARCH-UPGRADE kit {old_v} -> {new_v} | replace={n_rep} add={n_add} local={n_loc} keys={n_key} backup={zrel} | UNMEASURED: none")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="upgrade an awkit project install from its older kit version")
    ap.add_argument("target", nargs="?", type=Path)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    if not a.target:
        ap.print_usage()
        return 2
    return upgrade(a.target.resolve(), a.apply)


if __name__ == "__main__":
    sys.exit(main())
