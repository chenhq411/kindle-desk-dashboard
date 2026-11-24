@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Restore the project's .venv before removing its startup entry. See docs/INSTALL.md.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\manage_install.py" uninstall
pause
