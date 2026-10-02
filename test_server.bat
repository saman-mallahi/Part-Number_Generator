@echo off
title Part No. Generator - Test Server
cd /d "%~dp0"

echo ============================================
echo   Part No. Generator - Test / Debug
echo ============================================
echo.

if not exist "server.py" (
  echo ERROR: server.py not found in this folder.
  echo Put this .bat file next to server.py and try again.
  echo.
  pause
  exit /b 1
)

echo Starting server...
echo Stop with Ctrl+C
echo.

python server.py

echo.
echo Server stopped. Press any key to close.
pause > nul