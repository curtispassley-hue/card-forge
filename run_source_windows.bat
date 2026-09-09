@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run build_windows.bat once first to create the local environment.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
if not exist cardforge\assets\fonts\manifest.json python scripts\fetch_fonts.py
python main.py
