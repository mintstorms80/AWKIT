@echo off
rem Double-click in the PROJECT folder: runs the newest open queue (cards without a WORKLOG entry) with the worker profile.
rem Effort: kit.env EFFORT_WORKER through tools\effort.py (ultra, or auto = by the card). Override for one run: set AW_WORKER_EFFORT=ultra (or medium, high)  AW_WORKER_PROFILE=...  (default: worker)
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist tools\effort.py (echo This project has no tools\effort.py - upgrade the kit first. & pause & exit /b 1)
if "%AW_WORKER_PROFILE%"=="" set "AW_WORKER_PROFILE=worker"
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py -3"
if not defined PY (echo Python is not installed. & pause & exit /b 1)
where hermes >nul 2>&1 || (echo hermes CLI not found in PATH. & pause & exit /b 1)
set "QF=%TEMP%\aw_worker_%RANDOM%%RANDOM%.txt"
call %PY% -I -B tools\effort.py block --out "%QF%" || (pause & exit /b 1)
if "%AW_WORKER_EFFORT%"=="" for /f "delims=" %%L in ('%PY% -I -B tools\effort.py queue --level') do set "AW_WORKER_EFFORT=%%L"
call %PY% -I -B tools\effort.py queue
set "EFFORT_ARG="
if defined AW_WORKER_EFFORT set "EFFORT_ARG=--reasoning %AW_WORKER_EFFORT%"
call hermes -p %AW_WORKER_PROFILE% chat %EFFORT_ARG% --in "%~dp0." --query-file "%QF%"
del "%QF%" >nul 2>&1
pause
