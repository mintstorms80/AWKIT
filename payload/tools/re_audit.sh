#!/usr/bin/env bash
# OWNS='glob,glob' bash tools/re_audit.sh T-001   -> LAST step of every task. Exit 0 only if every check passes.
set -u
cd "$(dirname "$0")/.." || exit 2
PY=$(sed -n 's/^PY=//p' tools/kit.env | head -n1 | tr -d '\r')
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
"${PY:-python3}" -I -B tools/aw.py audit "$@"
