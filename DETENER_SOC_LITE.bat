@echo off
title Detener SOC-Lite
cd /d "%~dp0"

echo ============================================================
echo               DETENIENDO SOC-LITE
echo ============================================================
echo.

powershell -Command "Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*uvicorn*8000*' -or $_.CommandLine -like '*uvicorn*8001*' -or $_.CommandLine -like '*serve_frontend.py*' } | Stop-Process -Force"
docker stop soc-lite-postgres >nul 2>&1
docker stop soc-lite-redis >nul 2>&1

echo [*] Todos los procesos de SOC-Lite han sido detenidos.
pause
