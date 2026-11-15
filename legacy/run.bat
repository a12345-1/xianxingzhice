@echo off
setlocal
cd /d "%~dp0"

if /i "%SKIP_INSTALL%"=="1" goto run
if exist ".venv\.deps_ok" goto run
if exist ".venv\Scripts\python.exe" goto deps

echo [1/3] Creating virtual environment ...
py -3.12 -m venv .venv 2>nul
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo [ERROR] Cannot create venv. Please install Python 3.11 or 3.12 first.
  echo Download: https://www.python.org/downloads/
  pause
  exit /b 1
)

:deps
echo [2/3] Installing dependencies, first run may take 1-3 minutes ...
rem Use the mirror and fail fast: the default index may be unreachable from campus network.
".venv\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check --timeout 15 --retries 1
if errorlevel 1 (
  echo.
  echo Default index failed, retrying with Tsinghua mirror ...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check --timeout 20 --retries 1 -i https://pypi.tuna.tsinghua.edu.cn/simple
)
if errorlevel 1 (
  echo.
  echo [ERROR] Install failed. Check network, or run the zero-dependency preview:
  echo   .venv\Scripts\python.exe scripts\devserver.py 8010
  pause
  exit /b 1
)
echo ok> ".venv\.deps_ok"

:run
echo [3/3] Starting server ...
echo.
echo   Web   : http://127.0.0.1:8000
echo   Docs  : http://127.0.0.1:8000/docs
echo   Phone : http://YOUR-IP:8000  same WiFi
echo   Stop  : Ctrl+C
echo.
".venv\Scripts\python.exe" -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
pause
