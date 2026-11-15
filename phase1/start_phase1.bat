@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PY=..\.venv\Scripts\python.exe
if not exist "%PY%" (
  echo [ERROR] venv not found: %PY%
  echo Run cxcy\run.bat once to create it.
  pause
  exit /b 1
)

echo Starting XianXing ZhiCe v1 (single player) ...
echo.
echo   Web  : http://127.0.0.1:8002
echo   Docs : http://127.0.0.1:8002/docs
echo   Stop : Ctrl+C  (or run cxcy\stop.bat 8002)
echo.

"%PY%" -m uvicorn server.main:app --host 0.0.0.0 --port 8002
pause
