@echo off
rem Put the awkit folder INSIDE your project folder, then double-click this file.
rem Project name = the project folder's name, owner = git user.name (else the Windows user).
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
where python >nul 2>&1 && (set "PY=python") || (where py >nul 2>&1 && (set "PY=py -3") || (echo Python is not installed. & pause & exit /b 1))
%PY% "%~dp0setup_project.py" %*
echo.
pause
