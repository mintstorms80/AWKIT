@echo off
rem Double-click in the PROJECT folder: starts the Hermes architect profile in PLAN / ACCEPT mode (no cards).
rem Profile for one run: set AW_ARCH_PROFILE=... (default: architect, as START_ARCHITECT.cmd).
rem Model: tools\kit.env MODEL_PLAN (default when empty: AW_ARCH_MODEL or claude-sonnet-5-5; override: set AW_PLAN_MODEL=...).
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist tools\aw.py (
    echo Run awkit\new_project.cmd first.
    pause
    exit /b 1
)
if "%AW_PLAN_MODEL%"=="" if exist tools\kit.env for /f "tokens=1,* delims==" %%A in ('findstr /b "MODEL_PLAN=" tools\kit.env') do set "AW_PLAN_MODEL=%%B"
if "%AW_PLAN_MODEL%"=="" set "AW_PLAN_MODEL=%AW_ARCH_MODEL%"
if "%AW_PLAN_MODEL%"=="" set "AW_PLAN_MODEL=claude-sonnet-5-5"
if "%AW_ARCH_PROFILE%"=="" set "AW_ARCH_PROFILE=architect"
if "%AW_ARCH_PROVIDER%"=="" set "AW_ARCH_PROVIDER=anthropic"
where hermes >nul 2>&1 || (
    echo hermes CLI not found in PATH.
    pause
    exit /b 1
)
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py -3"
if "%AW_ARCH_EFFORT%"=="" if defined PY if exist tools\effort.py for /f "delims=" %%L in ('%PY% -I -B tools\effort.py stage --level') do set "AW_ARCH_EFFORT=%%L"
set "EFFORT_ARG="
set "EFFORT_MSG="
if defined AW_ARCH_EFFORT set "EFFORT_ARG=--reasoning %AW_ARCH_EFFORT%"
if defined AW_ARCH_EFFORT set "EFFORT_MSG= Session effort: %AW_ARCH_EFFORT%."
call hermes -p %AW_ARCH_PROFILE% -m %AW_PLAN_MODEL% --provider %AW_ARCH_PROVIDER% chat %EFFORT_ARG% --in "%~dp0." -q "Read .hermes/START_PLAN_PROMPT.md in this project and do what it says.%EFFORT_MSG%"
pause
