#!/usr/bin/env bash
# gate.sh [label]  -> GATE OK|FAIL count=N min=M ; exit 0 only on OK. Logic lives in aw.py.
set -u
cd "$(dirname "$0")/.." || exit 2
PY=$(sed -n 's/^PY=//p' tools/kit.env | head -n1 | tr -d '\r')      # a CRLF kit.env used to yield "python3\r"
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'                    # MSYS rewrote "/fast" into a Windows path
"${PY:-python3}" -I -B tools/aw.py gate "$@"
