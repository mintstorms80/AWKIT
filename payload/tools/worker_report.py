#!/usr/bin/env python3
"""python -I -B tools/worker_report.py            -> writes .hermes/plans/REPORT_latest.md (<=60 lines)
   python -I -B tools/worker_report.py --ask "text" -> appends Q-NNN to QUESTIONS.md (the ONLY way the worker asks)"""
import runpy, sys
from pathlib import Path
sys.argv = [str(Path(__file__).with_name("aw.py")), "ask" if "--ask" in sys.argv else "report"] + [a for a in sys.argv[1:] if a != "--ask"]
runpy.run_path(sys.argv[0], run_name="__main__")
