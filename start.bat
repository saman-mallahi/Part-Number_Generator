@echo off
setlocal EnableDelayedExpansion
title Part No. Generator - Server
cd /d "%~dp0"

echo ============================================
echo   Part No. Generator
echo ============================================
echo.

REM ---------- First-run check ----------
if not exist "config.txt" (
  echo Configuration file is missing.
  echo.
  echo Run setup.bat first ^(right-click it, choose
  echo "Run as administrator"^), then double-click
  echo start.bat again.
  echo.
  pause
  exit /b 1
)

REM ---------- Read port from config.txt ----------
set "CFG_PORT=1030"
for /f "usebackq tokens=1,* delims==" %%A in ("config.txt") do (
  if /i "%%A"=="PORT" set "CFG_PORT=%%B"
)

REM ---------- If port is below 1024, elevate ----------
if %CFG_PORT% LSS 1024 (
  net session >nul 2>nul
  if !errorlevel! neq 0 (
    echo This configuration requires Administrator privileges.
    echo Requesting elevation...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs" >nul 2>nul
    exit /b
  )
)

REM ---------- Find Python ----------
where python >nul 2>nul
if %errorlevel%==0 (
  python server.py
  goto :end
)

where py >nul 2>nul
if %errorlevel%==0 (
  py server.py
  goto :end
)

echo Python was not found on this computer.
echo.
echo Please install Python 3 from:
echo    https://www.python.org/downloads/
echo.
echo During installation, tick "Add Python to PATH".
echo Then run setup.bat once, then start.bat.

:end
echo.
echo Server stopped. Press any key to close this window.
pause > nul