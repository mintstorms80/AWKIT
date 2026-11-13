@echo off
rem UPGRADE_KIT.cmd in a PROJECT folder: double-click it. upgrade_kit.cmd in the KIT folder: drag a project folder onto it (2.9.1).
rem Runs upgrade_project.py dry-run first, then pauses before --apply. `call`: a python.cmd shim first on PATH would otherwise end the script after one line.
setlocal
chcp 65001 >nul
set "P=%~1"
if "%P%"=="" set "P=%~dp0."
if not exist "%P%\tools\kit.env" (
    echo No tools\kit.env in "%P%".
    echo Double-click UPGRADE_KIT.cmd inside a kit project, or drag the project folder onto upgrade_kit.cmd in the kit folder.
    pause
    exit /b 1
)
set "KH=%AW_KIT_HOME%"
if "%KH%"=="" if exist "%~dp0upgrade_project.py" set "KH=%~dp0."
if "%KH%"=="" for /f "tokens=1,* delims==" %%A in ('findstr /b "KIT_HOME=" "%P%\tools\kit.env"') do set "KH=%%B"
if "%KH%"=="" (
    echo No kit folder: set KIT_HOME=^<kit folder^> in tools\kit.env, or drag this project folder onto upgrade_kit.cmd in the kit folder.
    pause
    exit /b 1
)
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    echo Python is not installed.
    pause
    exit /b 1
)
call %PY% -I -B "%KH%/upgrade_project.py" "%P%" || exit /b 1
echo.
echo Press any key to apply the upgrade (Ctrl+C to cancel)...
pause >nul
call %PY% -I -B "%KH%/upgrade_project.py" "%P%" --apply
pause
