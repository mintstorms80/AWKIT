# checks.d : project-specific independent checks (the kit's answer to "a gate that agrees with itself")
Put one executable per check here (*.py runs with the kit's python, *.sh with a resolved bash). Each prints lines:
  METRIC <name> <int>   debt counter, LOWER is better. Ceiling stored in .aw/baseline.json; above ceiling = FAIL; new metric = FAIL until baselined.
  ZERO   <name> <int>   must be 0 (zero tolerance).
Non-zero exit = FAIL. Write the check WITHOUT importing the code it audits (that is the whole point).
Every check runs with PYTHONPATH removed (v2): a check that needs the project on sys.path must add it itself.
checks.d/** is in the implicit frozen core: a worker edit shows as FROZEN-CHANGED.
Good first checks: derived-vs-source diff count, TODO/FIXME count, files over N lines, endpoints without tests,
untested public functions, schema vs. model drift, doc links that 404 (offline), forbidden imports.
Example: example_todo_count.py.disabled  (rename to .py to activate)
A check must be able to FAIL: one that prints `ZERO x 0` after scanning nothing (missing dir, wrong glob) is a gate that agrees with itself. End with `assert scanned > 0` (or sys.exit(3)); `tools/learn.py` prints `blind-check` for a check without any such guard. Ship a must-catch fixture with the check when you can.
Example: example_debug_tags.py.disabled (leftover [DEBUG-<hex>] tags = ZERO; shows the liveness guard).
