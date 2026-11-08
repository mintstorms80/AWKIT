@echo off
rem Double-click in the PROJECT folder: starts the Hermes architect profile on this project and gives it its first task.
rem Profile and model for one run: set AW_ARCH_PROFILE=...  AW_ARCH_MODEL=...  AW_ARCH_PROVIDER=...  (defaults: architect / claude-sonnet-5-5 / anthropic)
rem Effort: tools\effort.py stage picks the level (ultra for plan and cards, a FAIL, a SPEC card, else medium). Override: set AW_ARCH_EFFORT=ultra (or medium, high)
rem A project without tools\effort.py keeps the profile's own level.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist tools\aw.py (echo Run awkit\new_project.cmd first. & pause & exit /b 1)
if "%AW_ARCH_PROFILE%"=="" set "AW_ARCH_PROFILE=architect"
if "%AW_ARCH_MODEL%"=="" set "AW_ARCH_MODEL=claude-sonnet-5-5"
if "%AW_ARCH_PROVIDER%"=="" set "AW_ARCH_PROVIDER=anthropic"
where hermes >nul 2>&1 || (echo hermes CLI not found in PATH. & pause & exit /b 1)
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py -3"
if "%AW_ARCH_EFFORT%"=="" if defined PY if exist tools\effort.py for /f "delims=" %%L in ('%PY% -I -B tools\effort.py stage --level') do set "AW_ARCH_EFFORT=%%L"
set "EFFORT_ARG="
set "EFFORT_MSG="
if defined AW_ARCH_EFFORT set "EFFORT_ARG=--reasoning %AW_ARCH_EFFORT%"
if defined AW_ARCH_EFFORT set "EFFORT_MSG= Session effort: %AW_ARCH_EFFORT%."
call hermes -p %AW_ARCH_PROFILE% -m %AW_ARCH_MODEL% --provider %AW_ARCH_PROVIDER% chat %EFFORT_ARG% --in "%~dp0." -q "Read .hermes/START_PROMPT.md in this project and do what it says.%EFFORT_MSG%"
pause
