@echo off
setlocal
cd /d "%~dp0"

if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python scripts\generate_samples.py
start "PIC-API" cmd /k "cd /d %~dp0 && .venv\Scripts\activate.bat && uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000"
timeout /t 2 /nobreak >nul
start "PIC-UI" cmd /k "cd /d %~dp0\frontend && npm install && npm run dev"
echo.
echo API: http://127.0.0.1:8000/health
echo UI:  http://localhost:5173
echo Then run: python scripts\run_batch.py
endlocal
