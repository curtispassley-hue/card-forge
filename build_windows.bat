@echo off
setlocal
cd /d "%~dp0"
title CardForge 4D 0.6 Windows Builder

echo ==============================================
echo CardForge 4D 0.6 - build standalone Windows folder app
echo ==============================================

echo Checking Python...
where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python launcher was not found.
  echo Install 64-bit Python 3.12 for your USER account and enable the Python launcher.
  echo Administrator rights are not required.
  pause
  exit /b 1
)

if not exist .venv (
  py -3.12 -m venv .venv
  if errorlevel 1 py -m venv .venv
)
call .venv\Scripts\activate.bat

python -m pip install --upgrade pip
if errorlevel 1 goto :fail
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail
python -m pip install pyinstaller
if errorlevel 1 goto :fail

echo.
echo Downloading the pinned sample font library...
python scripts\fetch_fonts.py
if errorlevel 1 goto :fail

echo.
echo Checking bundled offline OCR runtime...
python -c "from rapidocr import RapidOCR; import onnxruntime; RapidOCR(); print('RapidOCR / ONNX Runtime ready')"
if errorlevel 1 goto :fail

echo.
echo Running core smoke test...
python -m tests.smoke_test
if errorlevel 1 goto :fail
python -m unittest discover -v
if errorlevel 1 goto :fail
python main.py --self-test source-test.json
if errorlevel 1 goto :fail

echo.
echo Building folder application...
pyinstaller --noconfirm --clean CardForge4D.spec
if errorlevel 1 goto :fail
start /wait "" dist\CardForge4D\CardForge4D.exe --self-test exe-test.json
if errorlevel 1 goto :fail

if exist dist\CardForge4D\CardForge4D.exe (
  echo.
  echo ==============================================
  echo SUCCESS
  echo Standalone executable:
  echo %CD%\dist\CardForge4D\CardForge4D.exe
  echo ==============================================
  echo.
  echo Copy the ENTIRE dist\CardForge4D folder to another Windows PC.
  echo It does not request administrator privileges.
  pause
  exit /b 0
)

:fail
echo.
echo BUILD FAILED. Review the messages above.
pause
exit /b 1
