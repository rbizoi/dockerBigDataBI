@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "SPARK_JOBS_UI_PORT_VALUE=4040"
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do if "%%A"=="SPARK_JOBS_UI_PORT" set "SPARK_JOBS_UI_PORT_VALUE=%%B"
)

set "SPARK_JUPYTER_CONTAINER="
for /f "usebackq delims=" %%I in (`docker compose ps --status running -q spark-jupyter 2^>nul`) do set "SPARK_JUPYTER_CONTAINER=%%I"
if not defined SPARK_JUPYTER_CONTAINER (
  echo [FAIL] Le service spark-jupyter n'est pas accessible.
  echo Lancez d'abord INSTALL_CORE.cmd ou INSTALL_RESET_FULL.cmd.
  pause
  exit /b 1
)

docker compose exec -T spark-jupyter python3 -c "import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(0 if s.connect_ex(('127.0.0.1',4040)) == 0 else 1)" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Aucune SparkSession Jupyter active sur le port 4040.
  echo Ouvrez JupyterLab, executez la cellule qui cree la SparkSession,
  echo puis relancez OPEN_SPARK_JOBS.cmd.
  pause
  exit /b 2
)

start "" "http://127.0.0.1:%SPARK_JOBS_UI_PORT_VALUE%"
echo [OK] Spark Jobs UI: http://127.0.0.1:%SPARK_JOBS_UI_PORT_VALUE%
endlocal
