@echo off
setlocal EnableExtensions
title Pricer – Run (venv + deps)

rem Переходим в корень репозитория (папка скрипта)
cd /d "%~dp0.."

echo [1/3] Проверка виртуального окружения...
if not exist .venv\Scripts\python.exe (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3.12 -m venv .venv || py -3 -m venv .venv
  ) else (
    where python3.12 >nul 2>&1 && python3.12 -m venv .venv || python -m venv .venv
  )
)

echo [2/3] Обновление pip и установка зависимостей...
call .venv\Scripts\python -m pip install --upgrade pip >nul
call .venv\Scripts\python -m pip install -r requirements.txt || goto :pip_fail

echo [3/3] Запуск приложения...
rem Для глобальных хоткеев могут потребоваться права администратора (keyboard)
call .venv\Scripts\python main.py

goto :eof

:pip_fail
echo Не удалось установить зависимости Python. Проверьте сообщения выше.
exit /b 1

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
