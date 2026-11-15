@echo off
rem Stop the local server. Usage: stop.bat   or   stop.bat 8010
setlocal
set PORT=%~1
if "%PORT%"=="" set PORT=8000

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_server.ps1" -Port %PORT%
echo.
pause
