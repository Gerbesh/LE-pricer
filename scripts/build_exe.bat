@echo off
setlocal EnableExtensions
title Pricer – Build EXE (PyInstaller)

rem Переходим в корень репозитория (папка скрипта)
cd /d "%~dp0.."

echo [1/5] Проверка виртуального окружения...
if not exist .venv\Scripts\python.exe (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3.12 -m venv .venv || py -3 -m venv .venv
  ) else (
    where python3.12 >nul 2>&1 && python3.12 -m venv .venv || python -m venv .venv
  )
)

echo [2/5] Установка зависимостей для сборки...
call .venv\Scripts\python -m pip install --upgrade pip >nul
call .venv\Scripts\python -m pip install -r requirements.txt || goto :pip_fail
call .venv\Scripts\python -m pip install pyinstaller || goto :pip_fail

echo [3/5] Сборка исполняемого файла (onedir)...
rem onedir оставляет рядом данные и даёт возможность обновлять шаблоны/базу
call .venv\Scripts\pyinstaller --noconfirm --clean --onedir --name Pricer --windowed ^
  --add-data "prices.json;." ^
  main.py || goto :build_fail

echo [4/5] Сборка завершена.
echo     Результат: dist\Pricer\Pricer.exe

echo [5/5] Дополнительно:
echo  - Перед публикацией очистите папку logs и обновите шаблоны на целевой машине.
echo  - Файл prices.json лежит рядом с exe и может обновляться пользователем.

exit /b 0

:pip_fail
echo Не удалось установить зависимости Python. Проверьте сообщения выше.
exit /b 1

:build_fail
echo Сборка не удалась. Проверьте вывод PyInstaller выше.
exit /b 1
echo [3/5] Building executable (onedir)...
rem onedir is preferred so data can be written alongside the exe
call .venv\Scripts\pyinstaller --noconfirm --clean --onedir --name Pricer --windowed ^
  --add-data "prices.json;." ^
  main.py || goto :build_fail

echo [4/5] Build complete.
echo     Output: dist\Pricer\Pricer.exe

echo [5/5] Note about Tesseract and data storage:
echo  - ��?��+��??��'��??��?, ��?��'�? tesseract ��? PATH ��?>��?? ��?������'��?? ���?��'�? ��? UI.
echo  - �������> prices.json ��?:�?���?��'��?�? ��?��?�?�?�?�? ��? exe (onedir ��?��+��?�?���).

exit /b 0

:pip_fail
echo Failed to install Python dependencies. See errors above.
exit /b 1

:build_fail
echo Build failed. Check PyInstaller output above.
exit /b 1
