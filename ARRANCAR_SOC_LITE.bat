@echo off
setlocal
title Iniciar SOC-Lite
cd /d "%~dp0"

echo ============================================================
echo               INICIANDO SOC-LITE
echo ============================================================
echo.

REM 1. Verificar/Arrancar contenedor PostgreSQL en puerto 55432 y Redis
echo [*] Verificando base de datos PostgreSQL y Redis...
docker start soc-lite-postgres >nul 2>&1
if %errorlevel% neq 0 (
    docker run -d --name soc-lite-postgres -p 55432:5432 -e POSTGRES_USER=soclite -e POSTGRES_PASSWORD=soclite -e POSTGRES_DB=soclite postgres:17-alpine
)
docker start soc-lite-redis >nul 2>&1
if %errorlevel% neq 0 (
    docker run -d --name soc-lite-redis -p 6379:6379 redis:7-alpine
)

REM 2. Arrancar Backend
echo [*] Iniciando Backend FastAPI (puerto 8000)...
start "SOC-Lite Backend" /min backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

REM 3. Arrancar LangChain
echo [*] Iniciando Triaje LangChain (puerto 8001)...
start "SOC-Lite Triaje" /min langchain-service\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir langchain-service --host 127.0.0.1 --port 8001

REM 4. Arrancar Frontend
echo [*] Iniciando Servidor Frontend (puerto 5173)...
start "SOC-Lite Frontend" /min backend\.venv\Scripts\python.exe scripts\serve_frontend.py --port 5173 --api http://127.0.0.1:8000

echo.
echo ============================================================
echo   SERVICIOS INICIADOS:
echo   - Dashboard (SPA):  http://127.0.0.1:5173
echo   - API REST:         http://127.0.0.1:8000/api/v1
echo   - Swagger Docs:     http://127.0.0.1:8000/docs
echo   - Triaje LangChain: http://127.0.0.1:8001/health
echo ============================================================
timeout /t 3 >nul
start http://127.0.0.1:5173
