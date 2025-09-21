@echo off
setlocal EnableExtensions
title Install Tesseract via Chocolatey

where choco >nul 2>&1 || (
  echo Chocolatey not found. Install from https://chocolatey.org/install and re-run.
  exit /b 1
)

choco install -y tesseract || (
  echo Failed to install tesseract via Chocolatey.
  exit /b 1
)

echo Installed. Verify with: tesseract --version
exit /b 0

