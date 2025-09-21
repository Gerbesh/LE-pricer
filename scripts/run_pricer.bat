@echo off
setlocal EnableExtensions
title Pricer � Run (venv + deps)

rem Change to repo root (the folder of this script)
cd /d "%~dp0.."

echo [1/4] Ensuring virtual environment...
if not exist .venv\Scripts\python.exe (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3.12 -m venv .venv || py -3 -m venv .venv
  ) else (
    where python3.12 >nul 2>&1 && python3.12 -m venv .venv || python -m venv .venv
  )
)

echo [2/4] Upgrading pip and installing dependencies...
call .venv\Scripts\python -m pip install --upgrade pip >nul
call .venv\Scripts\python -m pip install -r requirements.txt || goto :pip_fail

echo [3/4] Checking Tesseract OCR availability...
where tesseract >nul 2>&1
if errorlevel 1 (
  if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    echo    Found default install at C:\Program Files\Tesseract-OCR\tesseract.exe
    echo    �?������'�� �?�'�?�' ���?�'�? �? ���?�>�� "�?�?�'�? �� Tesseract" �? ���?��>�?���?���.
  ) else (
    echo    �'�?��?���?���: tesseract.exe �?�� �?�����?��? �? PATH.
    echo    �?�?�'���?�?�?��'��: choco install -y tesseract
    echo    �>��+�? �?������'�� ���?�'�? �?�?�?�ؐ?�?�? �? ���?��>�?���?���.
  )
)

echo [4/4] Starting application...
rem ���?��+�?�?�'�?�? ���?���?�� ���?�?��?��?�'�?���'�?�?�� �?�>�? �?�>�?�+���>�?�?�?�?�? �:�?��� ��>���?����'�?�?�< (keyboard)
call .venv\Scripts\python main.py

goto :eof

:pip_fail
echo Failed to install Python dependencies. See errors above.
exit /b 1
