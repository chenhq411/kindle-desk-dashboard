@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0scripts\run_dashboard.py"
) else (
  echo Install dependencies in .venv first. See README.md.
  exit /b 1
)
if errorlevel 1 pause
