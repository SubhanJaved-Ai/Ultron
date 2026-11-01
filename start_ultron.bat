@echo off
title Ultron AI - Standalone Launcher
echo =======================================================
echo           ULTRON AI - LAUNCHING STANDALONE
echo =======================================================
echo.
cd /d "%~dp0"

echo [1/3] Starting FastAPI Backend Server (Port 8000)...
start "Ultron Backend (FastAPI)" cmd /k "cd /d "%~dp0" && .\.venv\Scripts\python.exe -m openjarvis.server"

echo [2/3] Waiting for backend initialization...
timeout /t 3 /nobreak >nul

echo [3/3] Starting Vite Frontend UI (Port 5173)...
start "Ultron Frontend (Vite)" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Waiting for frontend dev server...
timeout /t 3 /nobreak >nul

echo Opening Ultron in your browser...
start http://localhost:5173

echo.
echo =======================================================
echo  Ultron is LIVE!
echo   - Frontend UI:  http://localhost:5173
echo   - 3D Hologram:  http://localhost:8000/hologram
echo   - API Swagger:  http://localhost:8000/docs
echo =======================================================
echo Press any key when you want to exit this launcher window...
pause >nul

